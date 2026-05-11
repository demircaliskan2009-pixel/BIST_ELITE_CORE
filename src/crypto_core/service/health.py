"""Health trending and readiness snapshot — Phase 8B.

Bounded-memory deterministic health trend tracking and operator-facing
readiness assessment for the managed paper-live service.

Design rules:
  - Health trending uses simple deterministic rules, not ML/probabilistic scoring.
  - Bounded sliding window (deque) for sample history — no memory leak.
  - Readiness is a point-in-time frozen snapshot.
  - All models are frozen dataclasses.
  - Deterministic: same inputs → same outputs.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Health trend direction
# ---------------------------------------------------------------------------


class HealthTrend(str, Enum):
    """Directional health trend."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Readiness level
# ---------------------------------------------------------------------------


class ReadinessLevel(str, Enum):
    """Operator-facing readiness assessment.

    READY:     service healthy, trading active, all systems nominal.
    DEGRADED:  service running but health signals show degradation.
    BLOCKED:   service not processing — paused, recovering, or blocked.
    FAILING:   repeated failures, queue overflow, or service in FAILED state.
    UNKNOWN:   insufficient data to determine readiness.
    """

    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILING = "failing"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Health sample (internal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _HealthSample:
    """One point-in-time health observation."""

    timestamp_ns: int
    queue_pressure: str  # QueuePressure.value
    blocked_cycles: int  # cumulative
    failed_cycles: int  # cumulative
    stall_detected: bool
    consumer_alive: bool
    service_mode: str  # ServiceMode.value
    queue_depth: int
    queue_dropped: int  # cumulative


# ---------------------------------------------------------------------------
# Health trend snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthTrendSnapshot:
    """Frozen snapshot of health trending state.

    Fields:
      trend:                  current HealthTrend direction.
      trend_reason:           human-readable reason for the current trend.
      sample_count:           number of samples in the window.
      window_size:            configured window size.
      recent_blocked_delta:   blocked cycle increase in the window.
      recent_failed_delta:    failed cycle increase in the window.
      recent_stall_count:     number of stall detections in the window.
      recent_pressure_warnings: number of WARNING+ pressure samples.
      recent_drops_delta:     queue drop increase in the window.
      degradation_score:      simple 0-100 degradation score (higher = worse).
    """

    trend: HealthTrend
    trend_reason: str
    sample_count: int
    window_size: int
    recent_blocked_delta: int
    recent_failed_delta: int
    recent_stall_count: int
    recent_pressure_warnings: int
    recent_drops_delta: int
    degradation_score: int


# ---------------------------------------------------------------------------
# Readiness snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadinessSnapshot:
    """Operator-facing readiness assessment at a point in time.

    Answers: is this service healthy enough to keep running?

    Fields:
      level:                 ReadinessLevel assessment.
      reason:                human-readable reason for the assessment.
      service_mode:          current ServiceMode value string.
      trading_enabled:       True if trading cycles are being processed.
      queue_pressure:        current QueuePressure value string.
      queue_healthy:         True if pressure is NORMAL or WARNING.
      symbols_healthy:       True if all registered symbols have feed_ready=True.
      symbols_ready_count:   number of symbols with feed_ready=True.
      symbols_total_count:   total registered symbols.
      consumer_alive:        True if consumer thread is running.
      stall_detected:        True if watchdog detected a stall.
      health_trend:          current HealthTrend direction.
      degradation_score:     0-100 degradation score from health trending.
      recent_failures:       number of failed cycles in the recent window.
      recent_blocks:         number of blocked cycles in the recent window.
      last_error:            most recent error; None if clean.
    """

    level: ReadinessLevel
    reason: str
    service_mode: str
    trading_enabled: bool
    queue_pressure: str
    queue_healthy: bool
    symbols_healthy: bool
    symbols_ready_count: int
    symbols_total_count: int
    consumer_alive: bool
    stall_detected: bool
    health_trend: HealthTrend
    degradation_score: int
    recent_failures: int
    recent_blocks: int
    last_error: str | None


# ---------------------------------------------------------------------------
# Health trend configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthConfig:
    """Configuration for health trending.

    window_size:           number of samples to retain.
    degrading_threshold:   degradation score above which trend = DEGRADING.
    improving_threshold:   degradation score below which trend = IMPROVING.
    failing_mode_score:    score contribution for FAILED service mode.
    stall_score:           score contribution per stall detection.
    failure_score:         score contribution per failed cycle delta.
    block_score:           score contribution per blocked cycle delta.
    pressure_score:        score contribution per WARNING+ pressure sample.
    drop_score:            score contribution per queue drop delta.
    """

    window_size: int = 30
    degrading_threshold: int = 40
    improving_threshold: int = 10
    failing_mode_score: int = 50
    stall_score: int = 15
    failure_score: int = 10
    block_score: int = 3
    pressure_score: int = 5
    drop_score: int = 8


# ---------------------------------------------------------------------------
# Health tracker
# ---------------------------------------------------------------------------


class HealthTracker:
    """Bounded-memory deterministic health trend tracker.

    Thread-safe: all mutation and snapshot methods hold the internal lock.

    Usage::

        tracker = HealthTracker(HealthConfig(window_size=30))
        # Called periodically (e.g. every consumer loop iteration):
        tracker.record_sample(service_status)
        # Query trend at any time:
        snapshot = tracker.trend_snapshot()
        readiness = tracker.readiness(service_status)
    """

    def __init__(self, config: HealthConfig | None = None) -> None:
        self._config = config or HealthConfig()
        self._lock = threading.Lock()
        self._samples: deque[_HealthSample] = deque(maxlen=self._config.window_size)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_sample(self, service_status: object) -> None:
        """Record one health sample from a ServiceStatus snapshot.

        Call periodically (e.g. once per consumer loop iteration or on a timer).
        """
        from crypto_core.service.models import ServiceStatus

        ss: ServiceStatus = service_status  # type: ignore[assignment]
        rs = ss.runtime_status

        blocked = 0
        failed = 0
        if rs is not None:
            blocked = rs.session_status.blocked_cycles
            failed = rs.session_status.failed_cycles

        sample = _HealthSample(
            timestamp_ns=time.time_ns(),
            queue_pressure=ss.queue.pressure.value,
            blocked_cycles=blocked,
            failed_cycles=failed,
            stall_detected=ss.watchdog.stall_detected,
            consumer_alive=ss.watchdog.consumer_alive,
            service_mode=ss.service_mode,
            queue_depth=ss.queue.current_depth,
            queue_dropped=ss.queue.total_dropped,
        )

        with self._lock:
            self._samples.append(sample)

    def record_raw_sample(
        self,
        *,
        queue_pressure: str,
        blocked_cycles: int,
        failed_cycles: int,
        stall_detected: bool,
        consumer_alive: bool,
        service_mode: str,
        queue_depth: int,
        queue_dropped: int,
    ) -> None:
        """Record a health sample from raw values (useful for testing)."""
        sample = _HealthSample(
            timestamp_ns=time.time_ns(),
            queue_pressure=queue_pressure,
            blocked_cycles=blocked_cycles,
            failed_cycles=failed_cycles,
            stall_detected=stall_detected,
            consumer_alive=consumer_alive,
            service_mode=service_mode,
            queue_depth=queue_depth,
            queue_dropped=queue_dropped,
        )
        with self._lock:
            self._samples.append(sample)

    # ------------------------------------------------------------------
    # Trend snapshot
    # ------------------------------------------------------------------

    def trend_snapshot(self) -> HealthTrendSnapshot:
        """Produce a frozen health trend snapshot.

        Thread-safe.
        """
        with self._lock:
            samples = list(self._samples)

        if not samples:
            return HealthTrendSnapshot(
                trend=HealthTrend.UNKNOWN,
                trend_reason="no samples collected",
                sample_count=0,
                window_size=self._config.window_size,
                recent_blocked_delta=0,
                recent_failed_delta=0,
                recent_stall_count=0,
                recent_pressure_warnings=0,
                recent_drops_delta=0,
                degradation_score=0,
            )

        first = samples[0]
        last = samples[-1]

        blocked_delta = max(0, last.blocked_cycles - first.blocked_cycles)
        failed_delta = max(0, last.failed_cycles - first.failed_cycles)
        drops_delta = max(0, last.queue_dropped - first.queue_dropped)
        stall_count = sum(1 for s in samples if s.stall_detected)
        pressure_warnings = sum(1 for s in samples if s.queue_pressure in ("warning", "critical", "overflow"))

        # Compute degradation score (0-100, capped).
        score = 0
        if last.service_mode == "failed":
            score += self._config.failing_mode_score
        score += stall_count * self._config.stall_score
        score += failed_delta * self._config.failure_score
        score += blocked_delta * self._config.block_score
        score += pressure_warnings * self._config.pressure_score
        if drops_delta > 0:
            score += self._config.drop_score
        score = min(100, max(0, score))

        # Determine trend direction.
        if score >= self._config.degrading_threshold:
            trend = HealthTrend.DEGRADING
            reason = f"degradation_score={score} >= threshold={self._config.degrading_threshold}"
        elif score <= self._config.improving_threshold:
            trend = HealthTrend.IMPROVING
            reason = f"degradation_score={score} <= threshold={self._config.improving_threshold}"
        else:
            trend = HealthTrend.STABLE
            reason = f"degradation_score={score} in stable range"

        return HealthTrendSnapshot(
            trend=trend,
            trend_reason=reason,
            sample_count=len(samples),
            window_size=self._config.window_size,
            recent_blocked_delta=blocked_delta,
            recent_failed_delta=failed_delta,
            recent_stall_count=stall_count,
            recent_pressure_warnings=pressure_warnings,
            recent_drops_delta=drops_delta,
            degradation_score=score,
        )

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    def readiness(self, service_status: object) -> ReadinessSnapshot:
        """Produce a readiness snapshot from current service status + health trend.

        Args:
            service_status: ServiceStatus from PaperLiveService.status().

        Returns:
            Frozen ReadinessSnapshot.
        """
        from crypto_core.service.models import ServiceStatus

        ss: ServiceStatus = service_status  # type: ignore[assignment]
        trend = self.trend_snapshot()

        queue_healthy = ss.queue.pressure.value in ("normal", "warning")
        symbols_ready = sum(1 for sh in ss.symbol_health if sh.feed_ready)
        symbols_total = ss.symbol_count
        symbols_healthy = symbols_ready == symbols_total and symbols_total > 0

        # Determine readiness level (most severe condition wins).
        level: ReadinessLevel
        reason: str

        if ss.service_mode == "failed":
            level = ReadinessLevel.FAILING
            reason = f"service_mode=failed: {ss.last_error or 'unknown'}"
        elif trend.trend == HealthTrend.DEGRADING and trend.degradation_score >= 70:
            level = ReadinessLevel.FAILING
            reason = f"severe degradation: score={trend.degradation_score}"
        elif ss.service_mode in ("stopped", "stopping"):
            level = ReadinessLevel.BLOCKED
            reason = f"service_mode={ss.service_mode}"
        elif ss.service_mode == "paused":
            level = ReadinessLevel.BLOCKED
            reason = "service_paused"
        elif not ss.watchdog.consumer_alive and ss.service_mode == "running":
            level = ReadinessLevel.FAILING
            reason = "consumer_dead_while_running"
        elif ss.watchdog.stall_detected:
            level = ReadinessLevel.DEGRADED
            reason = "consumer_stall_detected"
        elif not queue_healthy:
            level = ReadinessLevel.DEGRADED
            reason = f"queue_pressure={ss.queue.pressure.value}"
        elif not symbols_healthy and symbols_total > 0:
            level = ReadinessLevel.DEGRADED
            reason = f"symbols_not_ready: {symbols_ready}/{symbols_total}"
        elif trend.trend == HealthTrend.DEGRADING:
            level = ReadinessLevel.DEGRADED
            reason = f"health_degrading: score={trend.degradation_score}"
        elif ss.trading_enabled and queue_healthy:
            level = ReadinessLevel.READY
            reason = "all_systems_nominal"
        elif ss.service_mode in ("created", "starting"):
            level = ReadinessLevel.UNKNOWN
            reason = f"service_mode={ss.service_mode}"
        else:
            level = ReadinessLevel.UNKNOWN
            reason = f"indeterminate: mode={ss.service_mode}"

        return ReadinessSnapshot(
            level=level,
            reason=reason,
            service_mode=ss.service_mode,
            trading_enabled=ss.trading_enabled,
            queue_pressure=ss.queue.pressure.value,
            queue_healthy=queue_healthy,
            symbols_healthy=symbols_healthy,
            symbols_ready_count=symbols_ready,
            symbols_total_count=symbols_total,
            consumer_alive=ss.watchdog.consumer_alive,
            stall_detected=ss.watchdog.stall_detected,
            health_trend=trend.trend,
            degradation_score=trend.degradation_score,
            recent_failures=trend.recent_failed_delta,
            recent_blocks=trend.recent_blocked_delta,
            last_error=ss.last_error,
        )
