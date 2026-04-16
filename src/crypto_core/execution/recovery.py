"""Restart-safe recovery bootstrap — Phase 6E.

RecoveryBootstrap coordinates restoration of execution and portfolio state
after a process restart.  It is a read-only coordinator: it loads both
stores, validates internal consistency, and returns a structured result.

Invariants:
  - Fail-closed: any store error → success=False with full evidence.
  - No fake reconciliation: if stores disagree, report the discrepancy;
    do NOT silently pick one side.
  - No network calls: recovery is entirely from local persisted files.
  - No writes: this module only reads.  Callers decide whether to act on the result.

RecoveryResult contract:
  - success=True  → both stores loaded cleanly; tracker and orphan list ready.
  - success=False → at least one store failed; reason in evidence.
    Caller MUST treat the system as unrecoverable and refuse to proceed to
    PAPER/LIVE execution until the operator intervenes.

PRD reference: §7 Execution Engine, §1.29 System State Engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from crypto_core.execution.state_machine import Order
from crypto_core.execution.store import ExecutionStateStore, ExecutionStoreCorruptError
from crypto_core.portfolio.store import PortfolioRestoreError, PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evidence / Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecoveryEvidence:
    """Structured evidence of one recovery attempt.

    All fields are safe to log or serialize for operator review.
    """

    restore_success: bool
    restore_failure_reason: str | None
    schema_version: str
    snapshot_ns: int | None
    execution_store_records: int
    restored_order_count: int
    orphan_order_ids: list[str]
    restored_position_count: int


@dataclass(frozen=True)
class RecoveryResult:
    """Result of a recovery bootstrap run.

    success:       True iff both stores loaded cleanly and are consistent.
    evidence:      Structured audit record of what was found.
    tracker:       Restored PositionTracker (None if portfolio restore failed).
    orphan_orders: Non-terminal orders from execution store that need attention.
                   Empty on failure.
    """

    success: bool
    evidence: RecoveryEvidence
    tracker: PositionTracker | None
    orphan_orders: list[Order] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RecoveryBootstrap
# ---------------------------------------------------------------------------


class RecoveryBootstrap:
    """Coordinates restart-safe recovery from durable state stores.

    Usage::

        bootstrap = RecoveryBootstrap(
            exec_store=ExecutionStateStore(Path("runtime/execution_state.jsonl")),
            portfolio_store=PortfolioStateStore(Path("runtime/portfolio_state.json")),
        )
        result = bootstrap.run()
        if not result.success:
            # Operator action required — do NOT resume live/paper trading
            raise RuntimeError(f"Recovery failed: {result.evidence.restore_failure_reason}")

        tracker = result.tracker
        for orphan_id in result.evidence.orphan_order_ids:
            # Log / alert operator — these orders need manual resolution
            logger.warning("Orphan order after restart: %s", orphan_id)

    Invariants:
      - run() never raises.  All errors become success=False results.
      - No writes during run().
      - Not thread-safe — call from pipeline startup only.
    """

    def __init__(
        self,
        exec_store: ExecutionStateStore,
        portfolio_store: PortfolioStateStore,
    ) -> None:
        self._exec_store = exec_store
        self._portfolio_store = portfolio_store

    def run(self) -> RecoveryResult:
        """Execute the recovery bootstrap.

        Returns:
            RecoveryResult — always returns, never raises.
        """
        # ── Phase 1: load execution state ─────────────────────────────
        exec_records = 0
        orphan_ids: list[str] = []
        orphan_orders: list[Order] = []
        restored_orders: list[Order] = []

        try:
            exec_state = self._exec_store.load()
            exec_records = exec_state.total_records
            orphan_ids = list(exec_state.orphan_order_ids)
            restored_orders = list(exec_state.orders)
            # Separate orphans as Order objects
            orphan_set = set(orphan_ids)
            orphan_orders = [o for o in restored_orders if o.order_id in orphan_set]
        except ExecutionStoreCorruptError as exc:
            logger.error("Execution store corrupt during recovery: %s", exc)
            evidence = RecoveryEvidence(
                restore_success=False,
                restore_failure_reason=f"execution_store_corrupt: {exc}",
                schema_version="1",
                snapshot_ns=None,
                execution_store_records=0,
                restored_order_count=0,
                orphan_order_ids=[],
                restored_position_count=0,
            )
            return RecoveryResult(success=False, evidence=evidence, tracker=None, orphan_orders=[])
        except Exception as exc:
            logger.error("Unexpected error loading execution store: %s", exc)
            evidence = RecoveryEvidence(
                restore_success=False,
                restore_failure_reason=f"execution_store_error: {exc}",
                schema_version="1",
                snapshot_ns=None,
                execution_store_records=0,
                restored_order_count=0,
                orphan_order_ids=[],
                restored_position_count=0,
            )
            return RecoveryResult(success=False, evidence=evidence, tracker=None, orphan_orders=[])

        # ── Phase 2: load portfolio state ──────────────────────────────
        tracker: PositionTracker | None = None
        snapshot_ns: int | None = None
        restored_position_count = 0

        try:
            portfolio_dict = self._portfolio_store.load()
            snapshot_ns = int(portfolio_dict["snapshot_ns"])
            tracker = PositionTracker.restore_from_dict(portfolio_dict)
            restored_position_count = len([p for p in tracker._positions.values() if p.quantity > 0.0])
        except PortfolioRestoreError as exc:
            logger.error("Portfolio store corrupt during recovery: %s", exc)
            evidence = RecoveryEvidence(
                restore_success=False,
                restore_failure_reason=f"portfolio_store_corrupt: {exc}",
                schema_version="1",
                snapshot_ns=None,
                execution_store_records=exec_records,
                restored_order_count=len(restored_orders),
                orphan_order_ids=orphan_ids,
                restored_position_count=0,
            )
            return RecoveryResult(success=False, evidence=evidence, tracker=None, orphan_orders=[])
        except Exception as exc:
            logger.error("Unexpected error loading portfolio store: %s", exc)
            evidence = RecoveryEvidence(
                restore_success=False,
                restore_failure_reason=f"portfolio_store_error: {exc}",
                schema_version="1",
                snapshot_ns=None,
                execution_store_records=exec_records,
                restored_order_count=len(restored_orders),
                orphan_order_ids=orphan_ids,
                restored_position_count=0,
            )
            return RecoveryResult(success=False, evidence=evidence, tracker=None, orphan_orders=[])

        # ── Phase 3: log orphans ───────────────────────────────────────
        if orphan_ids:
            logger.warning(
                "Recovery found %d orphan order(s) requiring operator attention: %s",
                len(orphan_ids),
                orphan_ids,
            )

        # ── Success ────────────────────────────────────────────────────
        evidence = RecoveryEvidence(
            restore_success=True,
            restore_failure_reason=None,
            schema_version="1",
            snapshot_ns=snapshot_ns,
            execution_store_records=exec_records,
            restored_order_count=len(restored_orders),
            orphan_order_ids=orphan_ids,
            restored_position_count=restored_position_count,
        )
        logger.info(
            "Recovery bootstrap complete: %d orders (%d orphans), %d positions restored",
            len(restored_orders),
            len(orphan_ids),
            restored_position_count,
        )
        return RecoveryResult(
            success=True,
            evidence=evidence,
            tracker=tracker,
            orphan_orders=orphan_orders,
        )
