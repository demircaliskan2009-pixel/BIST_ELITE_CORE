"""PaperLiveRunner — lifecycle service for continuous paper-live operation.

Wraps FeedSessionBridge + PaperLiveSession to provide:
  - start / stop lifecycle
  - feed event subscription via on_event()
  - per-symbol runtime readiness
  - operator-facing RuntimeStatus snapshot
  - recovery-aware blocking (session stays visible when feed recovers)

The runner does NOT manage DataIngestor lifecycle — the caller is
responsible for starting and stopping feeds.  This separation keeps the
runner fully testable without real network connections.

Paper-only: enforced by PaperLiveSession at construction time.
Determinism: same event sequence → same outputs.
Not thread-safe: on_event() must be called from the same thread.

PRD reference: §2 System Orchestration, §4.1-§4.5 Data Layer.
"""

from __future__ import annotations

import logging
import time

from crypto_core.runtime.bridge import FeedSessionBridge
from crypto_core.runtime.models import RuntimeStatus
from crypto_core.session.engine import PaperLiveSession

logger = logging.getLogger(__name__)


class PaperLiveRunner:
    """Continuous paper-live operation lifecycle service.

    Wires DataIngestor events → FeedSessionBridge → PaperLiveSession.

    Usage::

        runner = PaperLiveRunner(session=session, bridge=bridge)
        runner.start()

        # Inject the runner as the DataIngestor event callback:
        ingestor = DataIngestor(on_event=runner.on_event, ...)
        ingestor.register_feed(...)
        ingestor.start_feed_managed(feed_key)

        ...

        runner.stop()

    Invariants:
      - start() calls session.start() once; idempotent.
      - stop() calls session.stop(); idempotent.
      - on_event() is a no-op when the runner is not started.
      - status() is always callable, even before start().
    """

    def __init__(
        self,
        session: PaperLiveSession,
        bridge: FeedSessionBridge,
    ) -> None:
        self._session = session
        self._bridge = bridge
        self._running: bool = False
        self._start_time_ns: int = 0
        self._last_event_ns: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the session and activate the event bridge.

        Idempotent: calling start() when already running is a no-op (logged).
        """
        if self._running:
            logger.warning("PaperLiveRunner.start() called while already running — ignored")
            return

        self._start_time_ns = time.time_ns()
        self._session.start()
        self._running = True
        logger.info(
            "PaperLiveRunner started — session_id=%s mode=%s",
            self._session._config.session_id,
            self._session.mode.value,
        )

    def stop(self) -> None:
        """Gracefully stop the session.

        Idempotent: calling stop() when not running is a no-op.
        """
        if not self._running:
            return

        self._running = False
        self._session.stop()
        logger.info(
            "PaperLiveRunner stopped — session_id=%s cycles=%d fills=%d",
            self._session._config.session_id,
            self._session.cycle_count,
            self._session._total_fills,
        )

    # ------------------------------------------------------------------
    # Event entry point
    # ------------------------------------------------------------------

    def on_event(self, event: object) -> None:
        """Entry point for typed events from DataIngestor.

        Routes the event through the bridge. Any cycle fired by the bridge
        is available via the session's cycle state and the bridge's trigger_log.

        No-op when the runner has not been started.
        """
        if not self._running:
            return

        self._last_event_ns = time.time_ns()
        self._bridge.on_event(event)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> RuntimeStatus:
        """Produce an operator-facing RuntimeStatus snapshot.

        Always callable — returns a safe snapshot even before start().
        """
        session_status = self._session.status()

        # Per-symbol readiness and last trigger timestamps.
        per_symbol_ready: dict[str, bool] = {}
        per_symbol_last_trigger_ns: dict[str, int] = {}

        for sym, exch in self._bridge._assembler.registered_symbols():
            state = self._bridge._assembler.get_state(sym, exch)
            if state is not None:
                is_ready = state.feed_connection_state == "connected" and state.feed_recovery_state == "ready"
                per_symbol_ready[sym] = is_ready
                last_ts = max(state.last_trigger_ts_ns.values(), default=0)
                per_symbol_last_trigger_ns[sym] = last_ts

        # Recovery in progress if runner is started and any symbol is not ready.
        recovery_in_progress = self._running and any(not v for v in per_symbol_ready.values())

        blocked_reason: str | None = None
        if session_status.trading_blocked:
            reasons = session_status.block_reasons
            blocked_reason = ", ".join(reasons) if reasons else session_status.mode

        return RuntimeStatus(
            session_status=session_status,
            total_event_count=self._bridge.event_count,
            total_trigger_count=self._bridge.trigger_count,
            total_suppressed_count=self._bridge.suppressed_count,
            per_symbol_ready=per_symbol_ready,
            per_symbol_last_trigger_ns=per_symbol_last_trigger_ns,
            recovery_in_progress=recovery_in_progress,
            blocked_reason=blocked_reason,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True when the runner has been started and not yet stopped."""
        return self._running

    @property
    def session(self) -> PaperLiveSession:
        """Underlying PaperLiveSession."""
        return self._session

    @property
    def bridge(self) -> FeedSessionBridge:
        """Underlying FeedSessionBridge."""
        return self._bridge
