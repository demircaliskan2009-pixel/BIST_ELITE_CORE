"""Deterministic soak-test harness — Phase 8B.

Long-run simulation harness for the managed paper-live service.

Design rules:
  - Uses existing crypto_core components only.
  - CI-safe and network-free: all events are synthetic / replayed.
  - Configurable cycle/event counts and multi-symbol scenarios.
  - Explicit result summaries with no silent truncation.
  - Any exception during soak surfaces explicitly in the result.
  - Fail-closed: no "best effort" hiding of failures.
  - Deterministic: same event sequence → same result (modulo wall-clock timestamps).

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Sequence

from crypto_core.service.audit import AuditConfig, AuditTrail
from crypto_core.service.health import HealthConfig, HealthTracker
from crypto_core.service.models import ServiceStatus
from crypto_core.service.paper_live_service import PaperLiveService

# ---------------------------------------------------------------------------
# Soak configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SoakConfig:
    """Configuration for a soak test run.

    total_events:           total synthetic events to inject.
    report_every_n:         produce an intermediate snapshot every N events.
    max_failures:           abort soak after this many failed cycles.
    max_queue_overflows:    abort soak after this many queue overflows.
    drain_timeout_s:        seconds to wait for queue to drain after injection.
    consumer_settle_s:      seconds to wait for consumer to process after injection.
    """

    total_events: int = 1000
    report_every_n: int = 100
    max_failures: int = 50
    max_queue_overflows: int = 10
    drain_timeout_s: float = 5.0
    consumer_settle_s: float = 0.5


# ---------------------------------------------------------------------------
# Per-symbol soak counters
# ---------------------------------------------------------------------------


@dataclass
class SymbolSoakCounters:
    """Mutable counters for one symbol during a soak run."""

    symbol: str
    exchange: str
    events_injected: int = 0


# ---------------------------------------------------------------------------
# Soak result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SoakResult:
    """Frozen result of a soak test run.

    Fields:
      success:                  True if soak completed without abort.
      aborted:                  True if soak was aborted early.
      abort_reason:             reason for abort; None if not aborted.
      total_events_injected:    total events pushed into the service.
      total_events_processed:   total events consumed by the queue bridge.
      total_cycles:             session cycles processed.
      approved_cycles:          cycles that approved a trade.
      blocked_cycles:           cycles rejected.
      failed_cycles:            cycles that raised an exception.
      max_queue_depth_observed: maximum queue depth seen during the run.
      total_queue_overflows:    total queue overflow count from the bridge.
      total_queue_dropped:      total events dropped due to overflow.
      final_service_mode:       ServiceMode value at the end of the run.
      final_session_mode:       SessionMode value at the end of the run; None if no runtime status.
      final_queue_depth:        queue depth at end of run.
      final_queue_pressure:     queue pressure at end of run.
      consumer_alive:           consumer thread alive at end of run.
      stall_detected:           stall detected at end of run.
      per_symbol_injected:      per-symbol event injection counts.
      errors_captured:          tuple of error strings captured during soak.
      intermediate_snapshots:   tuple of (event_index, ServiceStatus) pairs.
      duration_seconds:         wall-clock duration of the soak run.
      final_status:             final ServiceStatus snapshot.
    """

    success: bool
    aborted: bool
    abort_reason: str | None
    total_events_injected: int
    total_events_processed: int
    total_cycles: int
    approved_cycles: int
    blocked_cycles: int
    failed_cycles: int
    max_queue_depth_observed: int
    total_queue_overflows: int
    total_queue_dropped: int
    final_service_mode: str
    final_session_mode: str | None
    final_queue_depth: int
    final_queue_pressure: str
    consumer_alive: bool
    stall_detected: bool
    per_symbol_injected: tuple[tuple[str, str, int], ...]  # (symbol, exchange, count)
    errors_captured: tuple[str, ...]
    intermediate_snapshots: tuple[tuple[int, ServiceStatus], ...]
    duration_seconds: float
    final_status: ServiceStatus


# ---------------------------------------------------------------------------
# Soak harness
# ---------------------------------------------------------------------------


class SoakHarness:
    """Deterministic soak-test harness for the paper-live service.

    Replays large event sequences through the managed service and produces
    an explicit result summary.

    Usage::

        service = PaperLiveService(...)
        harness = SoakHarness(
            service=service,
            config=SoakConfig(total_events=5000),
        )
        result = harness.run(event_factory=my_event_factory)

    The event_factory is called with (index, symbol_list) and must return
    a synthetic event object suitable for the service.

    Thread safety: NOT thread-safe — run() must be called from one thread.
    """

    def __init__(
        self,
        *,
        service: PaperLiveService,
        config: SoakConfig | None = None,
        audit_trail: AuditTrail | None = None,
        health_tracker: HealthTracker | None = None,
    ) -> None:
        self._service = service
        self._config = config or SoakConfig()
        self._audit = audit_trail or AuditTrail(AuditConfig())
        self._health = health_tracker or HealthTracker(HealthConfig())

    def run(
        self,
        *,
        event_factory: Callable[[int, list[str]], object],
        symbols: Sequence[str] | None = None,
    ) -> SoakResult:
        """Execute the soak test run.

        Args:
            event_factory: callable(index, symbol_list) → event object.
                Called once per event in the sequence. The harness does NOT
                validate the event — the service/runner does.
            symbols: list of symbol names for multi-symbol scenarios.
                If None, defaults to ["BTCUSDT"].

        Returns:
            Frozen SoakResult with full run summary.
        """
        symbol_list = list(symbols or ["BTCUSDT"])
        cfg = self._config

        # Per-symbol counters.
        counters: dict[str, SymbolSoakCounters] = {}
        for sym in symbol_list:
            counters[sym] = SymbolSoakCounters(symbol=sym, exchange="binance")

        # Run state.
        max_queue_depth = 0
        errors: list[str] = []
        snapshots: list[tuple[int, ServiceStatus]] = []
        aborted = False
        abort_reason: str | None = None
        start_time = time.monotonic()

        for i in range(cfg.total_events):
            # Check abort conditions.
            status = self._service.status()
            q_depth = status.queue.current_depth
            if q_depth > max_queue_depth:
                max_queue_depth = q_depth

            # Health sample every iteration.
            self._health.record_sample(status)

            # Pressure tracking.
            self._audit.check_pressure(
                status.queue.pressure.value,
                status.queue.current_depth,
                status.queue.max_size,
            )

            # Check failed cycle limit.
            rs = status.runtime_status
            if rs is not None:
                failed = rs.session_status.failed_cycles
                if failed >= cfg.max_failures:
                    aborted = True
                    abort_reason = f"max_failures={cfg.max_failures} reached at event {i}"
                    self._audit.record_service_error(abort_reason)
                    errors.append(abort_reason)
                    break

            # Check overflow limit.
            if status.queue.total_dropped >= cfg.max_queue_overflows:
                aborted = True
                abort_reason = f"max_queue_overflows={cfg.max_queue_overflows} reached at event {i}"
                self._audit.record_service_error(abort_reason)
                errors.append(abort_reason)
                break

            # Check service mode — abort if FAILED/STOPPED.
            if status.service_mode in ("failed", "stopped"):
                aborted = True
                abort_reason = f"service_mode={status.service_mode} at event {i}"
                self._audit.record_service_error(abort_reason)
                errors.append(abort_reason)
                break

            # Generate and inject event.
            try:
                event = event_factory(i, symbol_list)
            except Exception as exc:
                error_msg = f"event_factory raised at index {i}: {exc}"
                errors.append(error_msg)
                self._audit.record_service_error(error_msg)
                aborted = True
                abort_reason = error_msg
                break

            try:
                self._service.enqueue_event(event)
            except Exception as exc:
                error_msg = f"enqueue_event raised at index {i}: {exc}"
                errors.append(error_msg)
                self._audit.record_service_error(error_msg)
                aborted = True
                abort_reason = error_msg
                break

            # Track per-symbol injection.
            sym_idx = i % len(symbol_list)
            sym = symbol_list[sym_idx]
            if sym in counters:
                counters[sym].events_injected += 1

            # Intermediate snapshots.
            if cfg.report_every_n > 0 and (i + 1) % cfg.report_every_n == 0:
                snapshots.append((i + 1, self._service.status()))

        # Wait for queue to drain.
        drain_start = time.monotonic()
        while time.monotonic() - drain_start < cfg.drain_timeout_s:
            if self._service.queue_bridge.is_empty():
                break
            time.sleep(0.01)

        # Brief settle.
        time.sleep(cfg.consumer_settle_s)

        # Final snapshot.
        final_status = self._service.status()
        final_depth = final_status.queue.current_depth
        if final_depth > max_queue_depth:
            max_queue_depth = final_depth

        duration = time.monotonic() - start_time

        # Extract final session mode.
        final_session_mode: str | None = None
        total_cycles = 0
        approved_cycles = 0
        blocked_cycles = 0
        failed_cycles = 0
        if final_status.runtime_status is not None:
            sess = final_status.runtime_status.session_status
            final_session_mode = sess.mode
            total_cycles = sess.total_cycles
            approved_cycles = sess.approved_cycles
            blocked_cycles = sess.blocked_cycles
            failed_cycles = sess.failed_cycles

        per_symbol = tuple((c.symbol, c.exchange, c.events_injected) for c in counters.values())

        return SoakResult(
            success=not aborted and final_status.service_mode not in ("failed", "stopped"),
            aborted=aborted,
            abort_reason=abort_reason,
            total_events_injected=final_status.queue.total_enqueued + final_status.queue.total_dropped,
            total_events_processed=final_status.queue.total_processed,
            total_cycles=total_cycles,
            approved_cycles=approved_cycles,
            blocked_cycles=blocked_cycles,
            failed_cycles=failed_cycles,
            max_queue_depth_observed=max_queue_depth,
            total_queue_overflows=final_status.queue.total_dropped,
            total_queue_dropped=final_status.queue.total_dropped,
            final_service_mode=final_status.service_mode,
            final_session_mode=final_session_mode,
            final_queue_depth=final_status.queue.current_depth,
            final_queue_pressure=final_status.queue.pressure.value,
            consumer_alive=final_status.watchdog.consumer_alive,
            stall_detected=final_status.watchdog.stall_detected,
            per_symbol_injected=per_symbol,
            errors_captured=tuple(errors),
            intermediate_snapshots=tuple(snapshots),
            duration_seconds=round(duration, 3),
            final_status=final_status,
        )
