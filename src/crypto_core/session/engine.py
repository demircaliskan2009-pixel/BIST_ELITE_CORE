"""Paper-live trading session engine — Phase 7E.

Continuous loop service that wires:
  data events → pipeline orchestrator → execution → portfolio → telemetry

per cycle, with session-level lifecycle management, recovery on restart,
operator-facing status model, and fail-closed error handling.

Design rules:
  - Pull-based: caller invokes process_event() per market data tick.
    This preserves determinism — same events → same outcomes.
  - No hidden async or threading inside the session.
  - Fail-closed on any exception: session transitions to FAILED.
  - Recovery via RecoveryBootstrap on start() if persisted state exists.
  - Portfolio persisted after every fill (configurable).
  - Strictly paper-only: LIVE execution mode is rejected.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import logging
import time

from crypto_core.execution.models import ExecutionMode
from crypto_core.execution.recovery import RecoveryBootstrap, RecoveryResult
from crypto_core.execution.store import ExecutionStateStore
from crypto_core.orchestrator.models import MarketDataInput, PipelineResult
from crypto_core.orchestrator.pipeline import PipelineOrchestrator
from crypto_core.portfolio.store import PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.session.models import (
    CycleResult,
    PaperSessionConfig,
    PaperSessionStatus,
    SessionMode,
)
from crypto_core.state.models import SignalInputs

logger = logging.getLogger(__name__)


class PaperLiveSession:
    """Continuous paper-live trading session engine.

    Wraps a PipelineOrchestrator to provide:
      1. Session lifecycle management (start/stop/status).
      2. Recovery on restart from persisted execution + portfolio state.
      3. Per-cycle portfolio persistence after fills.
      4. Operator-facing session status snapshots.
      5. Fail-closed error handling.

    The session is pull-based: the caller drives the loop by invoking
    process_event() once per market data tick.  The data layer (DataIngestor)
    is external and not managed by this class.

    Strictly paper-only: raises ValueError if the orchestrator's execution
    engine is in LIVE mode.

    Usage::

        session = PaperLiveSession(
            config=PaperSessionConfig(session_id="run-001"),
            orchestrator=orchestrator,
            position_tracker=tracker,
            portfolio_store=PortfolioStateStore(Path("runtime/portfolio.json")),
            exec_store=ExecutionStateStore(Path("runtime/execution.jsonl")),
            lifecycle_engine=lifecycle_engine,
        )
        session.start()
        for event in market_events:
            result = session.process_event(event)
        session.stop()

    Invariants:
      - process_event() never raises; errors become CycleResult.error.
      - start() transitions to RUNNING or BLOCKED (never raises).
      - stop() transitions to STOPPED and persists final state.
      - Same event stream → same cycle results (deterministic).
      - Not thread-safe — single-threaded use only.
    """

    def __init__(
        self,
        *,
        config: PaperSessionConfig,
        orchestrator: PipelineOrchestrator,
        position_tracker: PositionTracker,
        portfolio_store: PortfolioStateStore | None = None,
        exec_store: ExecutionStateStore | None = None,
        lifecycle_engine: object | None = None,
    ) -> None:
        # Enforce paper-only mode.
        exec_mode = orchestrator._execution_engine._cfg.mode
        if exec_mode == ExecutionMode.LIVE:
            msg = "PaperLiveSession refuses LIVE execution mode — paper-only"
            raise ValueError(msg)

        self._config = config
        self._orchestrator = orchestrator
        self._position_tracker = position_tracker
        self._portfolio_store = portfolio_store
        self._exec_store = exec_store
        self._lifecycle_engine = lifecycle_engine

        # Session state
        self._mode: SessionMode = SessionMode.INITIALIZING
        self._start_time_ns: int = 0
        self._current_cycle_ns: int = 0
        self._cycle_count: int = 0
        self._total_fills: int = 0
        self._last_result: PipelineResult | None = None
        self._block_reasons: list[str] = []
        self._recovery_status: str = "none"
        self._recovery_evidence: object | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> PaperSessionStatus:
        """Start the session, recovering persisted state if available.

        Recovery logic:
          - If both stores exist and have data → run RecoveryBootstrap.
          - Recovery success with clean state → RUNNING.
          - Recovery success with unresolved orders → BLOCKED.
          - Recovery failure → BLOCKED with reason.
          - No stores → clean start → RUNNING.

        Returns:
            PaperSessionStatus snapshot after start.
        """
        self._start_time_ns = time.time_ns()

        if self._should_recover():
            self._mode = SessionMode.RECOVERING
            result = self._run_recovery()
            if not result.success:
                reason = result.evidence.restore_failure_reason or "unknown"
                self._recovery_status = f"failed:{reason}"
                self._mode = SessionMode.BLOCKED
                self._block_reasons.append(f"recovery_failed:{reason}")
                return self.status()

            # Recovery succeeded — apply restored state.
            if result.tracker is not None:
                self._position_tracker = result.tracker
                self._orchestrator.position_tracker = result.tracker

            if result.evidence.unresolved_count > 0:
                self._recovery_status = "incomplete"
                self._mode = SessionMode.BLOCKED
                self._block_reasons.append(f"unresolved_orders:{result.evidence.unresolved_count}")
                return self.status()

            self._recovery_status = "recovered"
            self._recovery_evidence = result.evidence
            self._mode = SessionMode.RUNNING
        else:
            self._recovery_status = "clean_start"
            self._mode = SessionMode.RUNNING

        return self.status()

    def process_event(
        self,
        data: MarketDataInput,
        signal_inputs: SignalInputs | None = None,
    ) -> CycleResult:
        """Process one market data event through the full pipeline.

        Fail-closed: any exception → session transitions to FAILED,
        and the CycleResult carries the error string.

        Args:
            data: validated market data snapshot for this cycle.
            signal_inputs: optional SHS signal overrides; None = zero signals.

        Returns:
            CycleResult with full audit trail for this cycle.
        """
        # Guard: reject if not running.
        if self._mode != SessionMode.RUNNING:
            return CycleResult(
                cycle_number=self._cycle_count,
                timestamp_ns=data.timestamp_ns,
                pipeline_result=None,
                fills_applied=0,
                portfolio_persisted=False,
                error=f"session_not_running:{self._mode.value}",
            )

        # Guard: max cycles.
        if self._config.max_cycles > 0 and self._cycle_count >= self._config.max_cycles:
            self._mode = SessionMode.STOPPED
            self._block_reasons.append("max_cycles_reached")
            return CycleResult(
                cycle_number=self._cycle_count,
                timestamp_ns=data.timestamp_ns,
                pipeline_result=None,
                fills_applied=0,
                portfolio_persisted=False,
                error="max_cycles_reached",
            )

        self._cycle_count += 1
        self._current_cycle_ns = data.timestamp_ns

        try:
            return self._do_cycle(data, signal_inputs)
        except Exception as exc:
            logger.exception("PaperLiveSession.process_event raised — fail-closed")
            self._mode = SessionMode.FAILED
            self._block_reasons.append(f"exception:{exc}")
            return CycleResult(
                cycle_number=self._cycle_count,
                timestamp_ns=data.timestamp_ns,
                pipeline_result=None,
                fills_applied=0,
                portfolio_persisted=False,
                error=str(exc),
            )

    def status(self) -> PaperSessionStatus:
        """Produce an operator-facing session status snapshot."""
        nav_usd: float | None = None
        gross_exposure_pct: float | None = None
        net_exposure_pct: float | None = None
        open_positions = 0
        unresolved_orders = 0

        if self._position_tracker is not None:
            snap = self._position_tracker.portfolio_snapshot(
                snapshot_ns=self._current_cycle_ns or time.time_ns(),
            )
            nav_usd = snap.nav_usd
            gross_exposure_pct = snap.gross_exposure_pct
            net_exposure_pct = snap.net_exposure_pct
            open_positions = snap.active_position_count

        # Unresolved orders from lifecycle engine.
        if self._lifecycle_engine is not None and hasattr(self._lifecycle_engine, "open_order_ids"):
            unresolved_orders = len(self._lifecycle_engine.open_order_ids)

        last_approved: bool | None = None
        if self._last_result is not None:
            last_approved = self._last_result.approved

        return PaperSessionStatus(
            session_id=self._config.session_id,
            mode=self._mode.value,
            start_time_ns=self._start_time_ns,
            current_cycle_time_ns=self._current_cycle_ns,
            total_cycles=self._cycle_count,
            total_fills=self._total_fills,
            recovery_status=self._recovery_status,
            unresolved_order_count=unresolved_orders,
            open_positions_count=open_positions,
            nav_usd=nav_usd,
            gross_exposure_pct=gross_exposure_pct,
            net_exposure_pct=net_exposure_pct,
            last_cycle_approved=last_approved,
            trading_blocked=self._mode != SessionMode.RUNNING,
            block_reasons=tuple(self._block_reasons),
        )

    def stop(self) -> PaperSessionStatus:
        """Gracefully stop the session and persist final state.

        Returns:
            Final PaperSessionStatus snapshot.
        """
        if self._mode == SessionMode.RUNNING and self._config.persist_on_stop:
            self._persist_portfolio()

        self._mode = SessionMode.STOPPED
        return self.status()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> SessionMode:
        """Current session mode."""
        return self._mode

    @property
    def cycle_count(self) -> int:
        """Total cycles processed."""
        return self._cycle_count

    @property
    def position_tracker(self) -> PositionTracker:
        """Position tracker instance (same reference as orchestrator)."""
        return self._position_tracker

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_cycle(
        self,
        data: MarketDataInput,
        signal_inputs: SignalInputs | None,
    ) -> CycleResult:
        """Execute one pipeline cycle — called inside try/except."""
        result = self._orchestrator.process(data, signal_inputs)
        self._last_result = result

        # Count fills from lifecycle results.
        fills_count = sum(len(lr.fill_events) for lr in result.execution_lifecycle_results)
        self._total_fills += fills_count

        # Persist portfolio after fills.
        persisted = False
        if fills_count > 0 and self._config.persist_every_fill:
            persisted = self._persist_portfolio()

        return CycleResult(
            cycle_number=self._cycle_count,
            timestamp_ns=data.timestamp_ns,
            pipeline_result=result,
            fills_applied=fills_count,
            portfolio_persisted=persisted,
            error=None,
        )

    def _should_recover(self) -> bool:
        """True when persisted state stores exist and contain data."""
        if self._portfolio_store is None or self._exec_store is None:
            return False
        return self._portfolio_store.exists()

    def _run_recovery(self) -> RecoveryResult:
        """Execute RecoveryBootstrap against the configured stores."""
        bootstrap = RecoveryBootstrap(
            exec_store=self._exec_store,
            portfolio_store=self._portfolio_store,
            lifecycle_engine=self._lifecycle_engine,
        )
        return bootstrap.run()

    def _persist_portfolio(self) -> bool:
        """Persist portfolio state to store. Returns True on success."""
        if self._portfolio_store is None:
            return False
        try:
            snapshot_dict = self._position_tracker.to_persistence_dict(
                snapshot_ns=self._current_cycle_ns or time.time_ns(),
            )
            self._portfolio_store.save(snapshot_dict)
            return True
        except Exception:
            logger.exception("Failed to persist portfolio state")
            return False
