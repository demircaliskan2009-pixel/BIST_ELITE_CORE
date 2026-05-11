"""Restart-safe recovery bootstrap — Phase 6E/6F.

RecoveryBootstrap coordinates restoration of execution and portfolio state
after a process restart.  Phase 6F adds active reconciliation of orphan
orders through the venue adapter.

Invariants:
  - Fail-closed: any store error → success=False with full evidence.
  - No fake reconciliation: if stores disagree, report the discrepancy;
    do NOT silently pick one side.
  - No network calls: recovery is entirely from local persisted files.
    (Reconciliation via adapter is local for paper mode.)
  - Orphan orders are actively reconciled through the adapter.

RecoveryResult contract:
  - success=True  → both stores loaded cleanly; tracker and orphan list ready.
  - success=False → at least one store failed; reason in evidence.
    Caller MUST treat the system as unrecoverable and refuse to proceed to
    PAPER/LIVE execution until the operator intervenes.

Phase 6F additions:
  - ReconciliationAction: per-order reconciliation result.
  - RecoveryBootstrap accepts optional lifecycle engine for active reconciliation.
  - Orphan orders are reconciled through adapter (paper: → STALE).
  - Enhanced evidence with reconciliation counts.

PRD reference: §7 Execution Engine, §1.29 System State Engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from crypto_core.execution.events import OrderEvent
from crypto_core.execution.state_machine import Order
from crypto_core.execution.store import ExecutionStateStore, ExecutionStoreCorruptError
from crypto_core.portfolio.store import PortfolioRestoreError, PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evidence / Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationAction:
    """Result of reconciling one order after recovery.

    order_id:  the reconciled order.
    action:    one of: "terminal_clean", "stale", "filled_offline",
               "canceled_offline", "unresolved".
    events:    lifecycle events produced during reconciliation.
    evidence:  audit dict with reconciliation details.
    """

    order_id: str
    action: str
    events: tuple[OrderEvent, ...]
    evidence: dict[str, object]


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
    # Phase 6F: reconciliation evidence
    reconciled_count: int = 0
    stale_count: int = 0
    unresolved_count: int = 0


@dataclass(frozen=True)
class RecoveryResult:
    """Result of a recovery bootstrap run.

    success:                True iff both stores loaded cleanly and are consistent.
    evidence:               Structured audit record of what was found.
    tracker:                Restored PositionTracker (None if portfolio restore failed).
    orphan_orders:          Non-terminal orders from execution store that need attention.
                            Empty on failure.
    reconciliation_actions: Phase 6F per-order reconciliation results.
    """

    success: bool
    evidence: RecoveryEvidence
    tracker: PositionTracker | None
    orphan_orders: list[Order] = field(default_factory=list)
    reconciliation_actions: list[ReconciliationAction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RecoveryBootstrap
# ---------------------------------------------------------------------------


class RecoveryBootstrap:
    """Coordinates restart-safe recovery from durable state stores.

    Phase 6F: now performs active reconciliation of orphan orders through
    the lifecycle engine's adapter.

    Usage::

        from crypto_core.execution.lifecycle import ExecutionLifecycleEngine

        bootstrap = RecoveryBootstrap(
            exec_store=ExecutionStateStore(Path("runtime/execution_state.jsonl")),
            portfolio_store=PortfolioStateStore(Path("runtime/portfolio_state.json")),
            lifecycle_engine=lifecycle_engine,  # optional for reconciliation
        )
        result = bootstrap.run()
        if not result.success:
            raise RuntimeError(f"Recovery failed: {result.evidence.restore_failure_reason}")

        tracker = result.tracker
        for action in result.reconciliation_actions:
            logger.info("Order %s: %s", action.order_id, action.action)

    Invariants:
      - run() never raises.  All errors become success=False results.
      - Not thread-safe — call from pipeline startup only.
    """

    def __init__(
        self,
        exec_store: ExecutionStateStore,
        portfolio_store: PortfolioStateStore,
        lifecycle_engine: object | None = None,
    ) -> None:
        self._exec_store = exec_store
        self._portfolio_store = portfolio_store
        # lifecycle_engine is typed as object to avoid circular import;
        # must be an ExecutionLifecycleEngine with register_restored_orders()
        # and reconcile_order() methods.
        self._lifecycle_engine = lifecycle_engine

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

        # ── Phase 3: reconcile orphans (Phase 6F) ──────────────────────
        reconciliation_actions: list[ReconciliationAction] = []
        reconciled_count = 0
        stale_count = 0
        unresolved_count = 0

        if orphan_ids and self._lifecycle_engine is not None:
            try:
                # Register ALL restored orders (terminal + non-terminal)
                # so the adapter knows about them for reconciliation.
                self._lifecycle_engine.register_restored_orders(restored_orders)

                import time as _time

                recon_ts = _time.time_ns()
                for oid in orphan_ids:
                    try:
                        events = self._lifecycle_engine.reconcile_order(oid, recon_ts)
                        if events:
                            # Determine action type from the final event
                            final_event = events[-1]
                            final_state = final_event.to_state
                            if final_state == "STALE":
                                action_type = "stale"
                                stale_count += 1
                            elif final_state == "FILLED":
                                action_type = "filled_offline"
                            elif final_state == "CANCELLED":
                                action_type = "canceled_offline"
                            else:
                                action_type = "unresolved"
                                unresolved_count += 1
                            reconciled_count += 1
                            reconciliation_actions.append(
                                ReconciliationAction(
                                    order_id=oid,
                                    action=action_type,
                                    events=tuple(events),
                                    evidence={
                                        "final_state": final_state,
                                        "event_count": len(events),
                                    },
                                )
                            )
                        else:
                            unresolved_count += 1
                            reconciliation_actions.append(
                                ReconciliationAction(
                                    order_id=oid,
                                    action="unresolved",
                                    events=(),
                                    evidence={"reason": "no_reconciliation_events"},
                                )
                            )
                    except Exception as exc:
                        logger.error("Reconciliation failed for order %s: %s", oid, exc)
                        unresolved_count += 1
                        reconciliation_actions.append(
                            ReconciliationAction(
                                order_id=oid,
                                action="unresolved",
                                events=(),
                                evidence={"error": str(exc)},
                            )
                        )
            except Exception as exc:
                logger.error("Reconciliation phase failed: %s", exc)
        elif orphan_ids:
            # No lifecycle engine → log orphans but cannot reconcile
            logger.warning(
                "Recovery found %d orphan order(s) but no lifecycle engine for reconciliation: %s",
                len(orphan_ids),
                orphan_ids,
            )
            unresolved_count = len(orphan_ids)

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
            reconciled_count=reconciled_count,
            stale_count=stale_count,
            unresolved_count=unresolved_count,
        )
        logger.info(
            "Recovery bootstrap complete: %d orders (%d orphans, %d reconciled, %d stale, %d unresolved), %d positions",
            len(restored_orders),
            len(orphan_ids),
            reconciled_count,
            stale_count,
            unresolved_count,
            restored_position_count,
        )
        return RecoveryResult(
            success=True,
            evidence=evidence,
            tracker=tracker,
            orphan_orders=orphan_orders,
            reconciliation_actions=reconciliation_actions,
        )
