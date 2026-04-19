"""Managed paper-live service — Phase 8A.

Top-level service owning the full paper-live runtime:

    DataIngestor → EventQueueBridge → consumer thread → PaperLiveRunner

Provides:
  - Async-safe event bridge (bounded queue between feed threads and consumer).
  - Single-threaded consumer loop that drains the queue into the runner.
  - Multi-symbol supervision with symbol-local failure isolation.
  - Watchdog / heartbeat / stall detection.
  - Backpressure / load-shedding based on queue pressure zones.
  - Rich operator status snapshot.
  - Lifecycle: start / stop / pause / resume / restart.
  - Paper-only enforcement (delegated to PaperLiveSession).

Design rules:
  - The consumer loop is the ONLY thread that touches runner.on_event().
  - Feed callback threads only call queue_bridge.enqueue() — never the runner.
  - Stall detection is computed lazily in status() — no watchdog thread.
  - All mutable state protected by _lock or confined to the consumer thread.
  - Service-level errors transition to FAILED; recoverable via restart().

PRD reference: §2 System Orchestration, §4 Data Layer, §7 Execution.
"""

from __future__ import annotations

import logging
import threading
import time

from crypto_core.data.ingestion.data_ingestor import DataIngestor
from crypto_core.data.models.feed_state import (
    ConnectionState,
    RecoveryState,
)
from crypto_core.runtime.runner import PaperLiveRunner
from crypto_core.service.execution_intelligence import (
    BootstrapResult,
    ExecutionIntelligenceBootstrap,
)
from crypto_core.service.models import (
    ExecutionIntelligenceConfig,
    ExecutionIntelligenceStatus,
    QueuePressure,
    ServiceConfig,
    ServiceMode,
    ServiceStatus,
    SymbolHealth,
    WatchdogStatus,
)
from crypto_core.service.queue_bridge import EventQueueBridge

logger = logging.getLogger(__name__)


class PaperLiveService:
    """Managed paper-live service with async-safe event bridge.

    Owns: DataIngestor, EventQueueBridge, PaperLiveRunner.
    Provides: lifecycle, watchdog, backpressure, operator status.

    Usage::

        service = PaperLiveService(
            runner=runner,
            ingestor=ingestor,
            config=ServiceConfig(),
        )
        # Register + start feeds (ingestor), then:
        service.start()
        # ... service is now running asynchronously ...
        status = service.status()
        service.stop()

    Thread safety:
        - start/stop/pause/resume/restart: NOT thread-safe (call from one thread).
        - status(): thread-safe (read-only snapshot).
        - enqueue_event(): thread-safe (used as DataIngestor on_event callback).
    """

    def __init__(
        self,
        *,
        runner: PaperLiveRunner,
        ingestor: DataIngestor,
        config: ServiceConfig | None = None,
        execution_intelligence_config: ExecutionIntelligenceConfig | None = None,
    ) -> None:
        self._runner = runner
        self._ingestor = ingestor
        self._config = config or ServiceConfig()
        self._ei_config = execution_intelligence_config
        self._queue_bridge = EventQueueBridge(self._config)

        # Execution intelligence state (set during start via bootstrap).
        self._ei_status: ExecutionIntelligenceStatus | None = None
        self._ei_bootstrap_result: BootstrapResult | None = None

        # Lifecycle state (protected by _lock for reads from status()).
        self._lock = threading.Lock()
        self._mode: ServiceMode = ServiceMode.CREATED
        self._last_error: str | None = None
        self._total_restarts: int = 0

        # Consumer thread.
        self._consumer_thread: threading.Thread | None = None
        self._consumer_stop: threading.Event = threading.Event()
        self._consumer_alive: bool = False

        # Watchdog timestamps.
        self._last_event_time_ns: int = 0  # last enqueue
        self._last_cycle_time_ns: int = 0  # last consumer loop iteration
        self._service_start_time_ns: int = 0

        # Symbol registry: feed_key → (symbol, exchange_str).
        self._symbol_registry: dict[str, tuple[str, str]] = {}

    # ------------------------------------------------------------------
    # Public: lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the managed service: runner + consumer thread.

        Transitions: CREATED/FAILED → STARTING → RUNNING.
        Idempotent if already RUNNING.
        """
        with self._lock:
            if self._mode == ServiceMode.RUNNING:
                logger.warning("PaperLiveService.start() — already running")
                return
            if self._mode not in (ServiceMode.CREATED, ServiceMode.FAILED, ServiceMode.STOPPED):
                logger.warning(
                    "PaperLiveService.start() — invalid state transition from %s",
                    self._mode.value,
                )
                return
            self._mode = ServiceMode.STARTING
            self._service_start_time_ns = time.time_ns()

        # Phase 9E: bootstrap execution intelligence before runner.start().
        self._bootstrap_execution_intelligence()

        # Fail-closed: if STRICT mode bootstrap failed, do not start.
        if self._ei_bootstrap_result is not None and self._ei_bootstrap_result.error is not None:
            with self._lock:
                self._mode = ServiceMode.FAILED
                self._last_error = self._ei_bootstrap_result.error
            logger.error(
                "PaperLiveService: execution intelligence bootstrap failed: %s", self._ei_bootstrap_result.error
            )
            return

        # Start the runner (which starts the session).
        try:
            self._runner.start()
        except Exception as exc:
            with self._lock:
                self._mode = ServiceMode.FAILED
                self._last_error = f"Runner start failed: {exc}"
            logger.error("PaperLiveService runner start failed: %s", exc)
            return

        # Phase 9E: update dedup status after session bootstrap.
        self._update_ei_dedup_status()

        # Start consumer thread.
        self._consumer_stop.clear()
        self._consumer_thread = threading.Thread(
            target=self._consumer_loop,
            daemon=True,
            name="paper-live-consumer",
        )
        self._consumer_thread.start()

        with self._lock:
            self._mode = ServiceMode.RUNNING
        logger.info("PaperLiveService started")

    def stop(self) -> None:
        """Gracefully stop the service: consumer + runner + ingestor.

        Transitions: any → STOPPING → STOPPED.
        """
        with self._lock:
            if self._mode == ServiceMode.STOPPED:
                return
            self._mode = ServiceMode.STOPPING

        # Signal consumer thread to stop.
        self._consumer_stop.set()
        if self._consumer_thread is not None and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5.0)

        # Shutdown feeds.
        try:
            self._ingestor.shutdown_all()
        except Exception as exc:
            logger.error("Ingestor shutdown error: %s", exc)

        # Stop runner (which stops the session).
        try:
            self._runner.stop()
        except Exception as exc:
            logger.error("Runner stop error: %s", exc)

        with self._lock:
            self._mode = ServiceMode.STOPPED
            self._consumer_alive = False
        logger.info("PaperLiveService stopped")

    def pause(self) -> None:
        """Pause the session — events still enqueued but cycles blocked.

        Transitions: RUNNING → PAUSED.
        """
        with self._lock:
            if self._mode != ServiceMode.RUNNING:
                logger.warning("PaperLiveService.pause() — not RUNNING (mode=%s)", self._mode.value)
                return
            self._mode = ServiceMode.PAUSED

        self._runner.session.pause()
        logger.info("PaperLiveService paused")

    def resume(self) -> None:
        """Resume the session from PAUSED.

        Transitions: PAUSED → RUNNING.
        """
        with self._lock:
            if self._mode != ServiceMode.PAUSED:
                logger.warning("PaperLiveService.resume() — not PAUSED (mode=%s)", self._mode.value)
                return
            self._mode = ServiceMode.RUNNING

        self._runner.session.resume()
        logger.info("PaperLiveService resumed")

    def restart(self) -> None:
        """Full restart: stop everything, clear queue, re-start.

        Transitions: any → STOPPED → STARTING → RUNNING.
        """
        self.stop()
        self._queue_bridge.clear()

        with self._lock:
            self._total_restarts += 1
            self._last_error = None
            self._mode = ServiceMode.CREATED

        self.start()
        logger.info("PaperLiveService restarted (total_restarts=%d)", self._total_restarts)

    # ------------------------------------------------------------------
    # Public: event entry point (thread-safe — used as DataIngestor callback)
    # ------------------------------------------------------------------

    def enqueue_event(self, event: object) -> None:
        """Enqueue an event from a feed callback thread.

        Thread-safe: this is the callback wired into DataIngestor(on_event=...).

        Events are dropped (not enqueued) if the service is STOPPED/STOPPING.
        """
        with self._lock:
            if self._mode in (ServiceMode.STOPPED, ServiceMode.STOPPING):
                return
            self._last_event_time_ns = time.time_ns()

        accepted = self._queue_bridge.enqueue(event)
        if not accepted:
            # Overflow — transition to FAILED.
            with self._lock:
                if self._mode != ServiceMode.FAILED:
                    self._mode = ServiceMode.FAILED
                    self._last_error = "Event queue overflow — events being dropped"
                    logger.error("PaperLiveService: queue overflow → FAILED")

    # ------------------------------------------------------------------
    # Public: symbol registration
    # ------------------------------------------------------------------

    def register_symbol(self, feed_key: str, symbol: str, exchange: str) -> None:
        """Register a symbol for health tracking.

        Called after DataIngestor.register_feed() so the service knows
        which symbols to report on.
        """
        self._symbol_registry[feed_key] = (symbol, exchange)

    # ------------------------------------------------------------------
    # Public: status (thread-safe read-only snapshot)
    # ------------------------------------------------------------------

    def status(self) -> ServiceStatus:
        """Produce an operator-facing service status snapshot.

        Thread-safe: creates a frozen snapshot with no shared mutation.
        """
        queue_snap = self._queue_bridge.queue_snapshot()

        # Watchdog computation.
        now_ns = time.time_ns()
        with self._lock:
            mode = self._mode
            last_error = self._last_error
            total_restarts = self._total_restarts
            consumer_alive = self._consumer_alive
            last_event_ns = self._last_event_time_ns
            last_cycle_ns = self._last_cycle_time_ns

        sec_since_event = (now_ns - last_event_ns) / 1e9 if last_event_ns > 0 else 0.0
        sec_since_cycle = (now_ns - last_cycle_ns) / 1e9 if last_cycle_ns > 0 else 0.0
        stall = consumer_alive and last_cycle_ns > 0 and sec_since_cycle > self._config.stall_threshold_s

        watchdog = WatchdogStatus(
            consumer_alive=consumer_alive,
            last_event_time_ns=last_event_ns,
            last_cycle_time_ns=last_cycle_ns,
            seconds_since_event=sec_since_event,
            seconds_since_cycle=sec_since_cycle,
            stall_detected=stall,
            stall_threshold_s=self._config.stall_threshold_s,
        )

        # Per-symbol health.
        symbol_health_list: list[SymbolHealth] = []
        for feed_key, (sym, exch) in self._symbol_registry.items():
            fs = self._ingestor.get_feed_state(feed_key)
            connected = False
            ready = False
            last_evt_ns = 0
            if fs is not None:
                connected = fs.connection_state == ConnectionState.CONNECTED
                ready = fs.recovery_state == RecoveryState.READY
                last_evt_ns = fs.last_event_ts_ns

            blocked = not ready
            block_reason = None
            if not connected:
                block_reason = "feed_disconnected"
            elif not ready:
                block_reason = f"recovery_state={fs.recovery_state.value if fs else 'unknown'}"

            symbol_health_list.append(
                SymbolHealth(
                    symbol=sym,
                    exchange=exch,
                    feed_connected=connected,
                    feed_ready=ready,
                    feed_key=feed_key,
                    last_event_time_ns=last_evt_ns,
                    blocked=blocked,
                    block_reason=block_reason,
                )
            )

        # Trading enabled = RUNNING + queue not in critical/overflow.
        trading_enabled = mode == ServiceMode.RUNNING and queue_snap.pressure in (
            QueuePressure.NORMAL,
            QueuePressure.WARNING,
        )

        blocked_reason: str | None = None
        if mode != ServiceMode.RUNNING:
            blocked_reason = f"service_mode={mode.value}"
        elif queue_snap.pressure in (QueuePressure.CRITICAL, QueuePressure.OVERFLOW):
            blocked_reason = f"queue_pressure={queue_snap.pressure.value}"

        # Runtime status (may be None if runner not started).
        try:
            runtime_status = self._runner.status()
        except Exception:
            runtime_status = None

        return ServiceStatus(
            service_mode=mode.value,
            runtime_status=runtime_status,
            queue=queue_snap,
            watchdog=watchdog,
            symbol_health=tuple(symbol_health_list),
            symbol_count=len(self._symbol_registry),
            trading_enabled=trading_enabled,
            blocked_reason=blocked_reason,
            last_error=last_error,
            total_service_restarts=total_restarts,
            execution_intelligence=self._ei_status,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> ServiceMode:
        """Current service mode."""
        with self._lock:
            return self._mode

    @property
    def queue_bridge(self) -> EventQueueBridge:
        """Underlying event queue bridge."""
        return self._queue_bridge

    @property
    def runner(self) -> PaperLiveRunner:
        """Underlying PaperLiveRunner."""
        return self._runner

    @property
    def ingestor(self) -> DataIngestor:
        """Underlying DataIngestor."""
        return self._ingestor

    @property
    def execution_intelligence_status(self) -> ExecutionIntelligenceStatus | None:
        """Current execution intelligence status snapshot."""
        return self._ei_status

    # ------------------------------------------------------------------
    # Execution intelligence bootstrap (Phase 9E)
    # ------------------------------------------------------------------

    def _bootstrap_execution_intelligence(self) -> None:
        """Build and wire execution intelligence components.

        Called during start() BEFORE runner.start().  Components are injected
        into the session's orchestrator so they participate in every pipeline cycle.

        DISABLED: no-op.
        OPTIONAL: builds what it can, reports degraded reasons.
        STRICT: builds all; sets error on BootstrapResult if any dependency missing.
        """
        if self._ei_config is None:
            # No config → execution intelligence not requested.
            self._ei_status = None
            self._ei_bootstrap_result = None
            return

        bootstrap = ExecutionIntelligenceBootstrap()
        result = bootstrap.build(self._ei_config)
        self._ei_bootstrap_result = result

        if result.error is not None:
            # STRICT mode failure — caller will transition to FAILED.
            self._ei_status = result.status
            return

        # Wire components into the orchestrator.
        orchestrator = self._runner.session._orchestrator

        if result.router is not None:
            orchestrator._metadata_gated_router = result.router
            logger.info("Execution intelligence: router injected")

        if result.tca_loop is not None:
            orchestrator._tca_loop = result.tca_loop
            logger.info("Execution intelligence: TCA loop injected")

        # Wire TCA store into session for dedup bootstrap.
        if result.tca_store is not None:
            self._runner.session._tca_store = result.tca_store
            logger.info("Execution intelligence: TCA store injected")

        # Update status with final state.
        self._ei_status = ExecutionIntelligenceStatus(
            mode=result.status.mode,
            route_binding_enabled=result.status.route_binding_enabled,
            tca_loop_enabled=result.status.tca_loop_enabled,
            tca_store_available=result.status.tca_store_available,
            replay_dedup_bootstrapped=False,
            degraded=result.status.degraded,
            degraded_reasons=result.status.degraded_reasons,
        )

    def _update_ei_dedup_status(self) -> None:
        """Update execution intelligence status after session start bootstraps dedup.

        Called after runner.start() completes (session._bootstrap_tca_dedup runs
        inside session.start()).
        """
        if self._ei_status is None:
            return
        # Check if dedup was bootstrapped by examining the TCA loop state.
        tca_loop = self._runner.session._orchestrator.tca_loop
        bootstrapped = False
        if tca_loop is not None:
            persisted_ids = tca_loop.get_persisted_tca_ids()
            bootstrapped = len(persisted_ids) > 0 or self._runner.session._tca_store is not None

        self._ei_status = ExecutionIntelligenceStatus(
            mode=self._ei_status.mode,
            route_binding_enabled=self._ei_status.route_binding_enabled,
            tca_loop_enabled=self._ei_status.tca_loop_enabled,
            tca_store_available=self._ei_status.tca_store_available,
            replay_dedup_bootstrapped=bootstrapped,
            degraded=self._ei_status.degraded,
            degraded_reasons=self._ei_status.degraded_reasons,
        )

    # ------------------------------------------------------------------
    # Consumer loop (runs in daemon thread)
    # ------------------------------------------------------------------

    def _consumer_loop(self) -> None:
        """Drain events from the queue and feed them to the runner.

        This is the ONLY code path that calls runner.on_event().
        Single-threaded by design — no concurrent access to runner internals.

        Exits when _consumer_stop is set.
        """
        with self._lock:
            self._consumer_alive = True

        logger.info("Consumer loop started")
        try:
            while not self._consumer_stop.is_set():
                event = self._queue_bridge.get(timeout=self._config.consumer_poll_timeout_s)
                if event is None:
                    # Timeout — no events, loop continues.
                    continue

                # Check backpressure: in CRITICAL zone, skip processing
                # to let the queue drain (events are consumed but not routed).
                pressure = self._queue_bridge.queue_snapshot().pressure
                if pressure == QueuePressure.OVERFLOW:
                    with self._lock:
                        if self._mode != ServiceMode.FAILED:
                            self._mode = ServiceMode.FAILED
                            self._last_error = "Consumer detected queue overflow"
                    logger.error("Consumer: queue overflow detected — stopping")
                    break

                # In CRITICAL zone: consume event but skip session cycle.
                # This drains the queue faster without firing expensive pipeline cycles.
                if pressure == QueuePressure.CRITICAL:
                    logger.debug("Consumer: CRITICAL pressure — event consumed but not routed")
                    with self._lock:
                        self._last_cycle_time_ns = time.time_ns()
                    continue

                # Normal + WARNING: route event to the runner.
                try:
                    self._runner.on_event(event)
                except Exception as exc:
                    logger.error("Consumer: runner.on_event() error: %s", exc)
                    with self._lock:
                        self._last_error = f"Consumer event processing error: {exc}"
                        if self._mode == ServiceMode.RUNNING:
                            self._mode = ServiceMode.FAILED
                    break

                with self._lock:
                    self._last_cycle_time_ns = time.time_ns()

        except Exception as exc:
            logger.error("Consumer loop unexpected error: %s", exc)
            with self._lock:
                self._mode = ServiceMode.FAILED
                self._last_error = f"Consumer loop crash: {exc}"
        finally:
            with self._lock:
                self._consumer_alive = False
            logger.info("Consumer loop exited")
