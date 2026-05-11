"""Operator audit trail — Phase 8B.

Bounded in-memory audit history for paper-live operations:
  - Cycle audit records (why blocked, why failed).
  - Service event records (state transitions, errors).
  - Queue pressure transition records.
  - Recovery suppression records.

Design rules:
  - All records are frozen dataclasses.
  - History buffers are bounded FIFO (collections.deque) — no memory leak.
  - Overflow is explicit: oldest records evicted, eviction counted.
  - Deterministic: same event sequence → same audit trail.
  - Thread-safe: lock protects append + snapshot.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Audit record types
# ---------------------------------------------------------------------------


class AuditCategory(str, Enum):
    """Top-level classification for audit records."""

    CYCLE_BLOCKED = "cycle_blocked"
    CYCLE_FAILED = "cycle_failed"
    CYCLE_APPROVED = "cycle_approved"
    SERVICE_TRANSITION = "service_transition"
    SERVICE_ERROR = "service_error"
    QUEUE_PRESSURE = "queue_pressure"
    RECOVERY_SUPPRESSION = "recovery_suppression"


@dataclass(frozen=True)
class AuditRecord:
    """Immutable audit record for one operational event.

    Fields:
      timestamp_ns:  wall-clock ns when the event occurred.
      category:      AuditCategory classification.
      detail:        human-readable detail string.
      cycle_number:  associated cycle number; 0 if not cycle-related.
      symbol:        associated symbol; None if not symbol-specific.
      source:        subsystem that produced this record.
    """

    timestamp_ns: int
    category: AuditCategory
    detail: str
    cycle_number: int = 0
    symbol: str | None = None
    source: str = "service"


@dataclass(frozen=True)
class PressureTransition:
    """Record of a queue pressure zone transition.

    Fields:
      timestamp_ns:    wall-clock ns when transition detected.
      from_pressure:   previous QueuePressure value string.
      to_pressure:     new QueuePressure value string.
      queue_depth:     queue depth at transition time.
      queue_max_size:  configured queue capacity.
    """

    timestamp_ns: int
    from_pressure: str
    to_pressure: str
    queue_depth: int
    queue_max_size: int


# ---------------------------------------------------------------------------
# Audit trail configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditConfig:
    """Configuration for bounded audit trail history.

    max_records:               maximum general audit records to retain.
    max_pressure_transitions:  maximum pressure transition records.
    """

    max_records: int = 1000
    max_pressure_transitions: int = 200


# ---------------------------------------------------------------------------
# Audit trail snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditSnapshot:
    """Frozen snapshot of the audit trail state.

    records:               recent audit records (oldest first).
    pressure_transitions:  recent pressure transitions (oldest first).
    total_records_logged:  total records logged since creation (may exceed retained).
    total_evicted:         total records evicted due to capacity limits.
    blocked_cycle_count:   count of CYCLE_BLOCKED records logged.
    failed_cycle_count:    count of CYCLE_FAILED records logged.
    service_error_count:   count of SERVICE_ERROR records logged.
    pressure_transition_count: total pressure transitions logged.
    """

    records: tuple[AuditRecord, ...]
    pressure_transitions: tuple[PressureTransition, ...]
    total_records_logged: int
    total_evicted: int
    blocked_cycle_count: int
    failed_cycle_count: int
    service_error_count: int
    pressure_transition_count: int


# ---------------------------------------------------------------------------
# Audit trail engine
# ---------------------------------------------------------------------------


class AuditTrail:
    """Bounded in-memory audit trail for paper-live operations.

    Thread-safe: all mutation and snapshot methods hold the internal lock.

    Usage::

        trail = AuditTrail(AuditConfig(max_records=500))
        trail.record_cycle_blocked(cycle=5, reason="session_paused", symbol="BTCUSDT")
        trail.record_service_error("consumer crash: ValueError")
        snapshot = trail.snapshot()
    """

    def __init__(self, config: AuditConfig | None = None) -> None:
        self._config = config or AuditConfig()
        self._lock = threading.Lock()
        self._records: deque[AuditRecord] = deque(maxlen=self._config.max_records)
        self._pressure_transitions: deque[PressureTransition] = deque(
            maxlen=self._config.max_pressure_transitions,
        )
        self._total_logged: int = 0
        self._total_evicted: int = 0
        self._blocked_count: int = 0
        self._failed_count: int = 0
        self._error_count: int = 0
        self._pressure_count: int = 0
        self._last_pressure: str | None = None

    # ------------------------------------------------------------------
    # Recording methods
    # ------------------------------------------------------------------

    def record_cycle_blocked(
        self,
        cycle: int,
        reason: str,
        symbol: str | None = None,
    ) -> None:
        """Record that a cycle was blocked with explicit reason."""
        record = AuditRecord(
            timestamp_ns=time.time_ns(),
            category=AuditCategory.CYCLE_BLOCKED,
            detail=reason,
            cycle_number=cycle,
            symbol=symbol,
            source="session",
        )
        with self._lock:
            self._append_record(record)
            self._blocked_count += 1

    def record_cycle_failed(
        self,
        cycle: int,
        error: str,
        symbol: str | None = None,
    ) -> None:
        """Record that a cycle failed with explicit error."""
        record = AuditRecord(
            timestamp_ns=time.time_ns(),
            category=AuditCategory.CYCLE_FAILED,
            detail=error,
            cycle_number=cycle,
            symbol=symbol,
            source="session",
        )
        with self._lock:
            self._append_record(record)
            self._failed_count += 1

    def record_cycle_approved(
        self,
        cycle: int,
        symbol: str | None = None,
    ) -> None:
        """Record that a cycle was approved."""
        record = AuditRecord(
            timestamp_ns=time.time_ns(),
            category=AuditCategory.CYCLE_APPROVED,
            detail="approved",
            cycle_number=cycle,
            symbol=symbol,
            source="session",
        )
        with self._lock:
            self._append_record(record)

    def record_service_transition(
        self,
        from_mode: str,
        to_mode: str,
    ) -> None:
        """Record a service lifecycle state transition."""
        record = AuditRecord(
            timestamp_ns=time.time_ns(),
            category=AuditCategory.SERVICE_TRANSITION,
            detail=f"{from_mode} → {to_mode}",
            source="service",
        )
        with self._lock:
            self._append_record(record)

    def record_service_error(self, error: str) -> None:
        """Record a service-level error."""
        record = AuditRecord(
            timestamp_ns=time.time_ns(),
            category=AuditCategory.SERVICE_ERROR,
            detail=error,
            source="service",
        )
        with self._lock:
            self._append_record(record)
            self._error_count += 1

    def record_pressure_transition(
        self,
        from_pressure: str,
        to_pressure: str,
        queue_depth: int,
        queue_max_size: int,
    ) -> None:
        """Record a queue pressure zone transition."""
        if from_pressure == to_pressure:
            return  # No actual transition.

        transition = PressureTransition(
            timestamp_ns=time.time_ns(),
            from_pressure=from_pressure,
            to_pressure=to_pressure,
            queue_depth=queue_depth,
            queue_max_size=queue_max_size,
        )
        record = AuditRecord(
            timestamp_ns=transition.timestamp_ns,
            category=AuditCategory.QUEUE_PRESSURE,
            detail=f"{from_pressure} → {to_pressure} (depth={queue_depth}/{queue_max_size})",
            source="queue",
        )
        with self._lock:
            self._append_record(record)
            was_full = len(self._pressure_transitions) == self._pressure_transitions.maxlen
            self._pressure_transitions.append(transition)
            if was_full:
                self._total_evicted += 1
            self._pressure_count += 1
            self._last_pressure = to_pressure

    def record_recovery_suppression(
        self,
        symbol: str,
        reason: str,
    ) -> None:
        """Record that a cycle was suppressed due to recovery state."""
        record = AuditRecord(
            timestamp_ns=time.time_ns(),
            category=AuditCategory.RECOVERY_SUPPRESSION,
            detail=reason,
            symbol=symbol,
            source="bridge",
        )
        with self._lock:
            self._append_record(record)

    # ------------------------------------------------------------------
    # Pressure tracking
    # ------------------------------------------------------------------

    def check_pressure(self, current_pressure: str, queue_depth: int, queue_max_size: int) -> None:
        """Check if pressure zone changed and record transition if so.

        Call this periodically (e.g. every consumer loop iteration) with
        the current queue pressure zone value.
        """
        with self._lock:
            prev = self._last_pressure

        if prev is not None and prev != current_pressure:
            self.record_pressure_transition(prev, current_pressure, queue_depth, queue_max_size)
        elif prev is None:
            with self._lock:
                self._last_pressure = current_pressure

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> AuditSnapshot:
        """Produce a frozen snapshot of the audit trail state.

        Thread-safe.
        """
        with self._lock:
            return AuditSnapshot(
                records=tuple(self._records),
                pressure_transitions=tuple(self._pressure_transitions),
                total_records_logged=self._total_logged,
                total_evicted=self._total_evicted,
                blocked_cycle_count=self._blocked_count,
                failed_cycle_count=self._failed_count,
                service_error_count=self._error_count,
                pressure_transition_count=self._pressure_count,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append_record(self, record: AuditRecord) -> None:
        """Append a record to the bounded FIFO. Must hold _lock."""
        was_full = len(self._records) == self._records.maxlen
        self._records.append(record)
        self._total_logged += 1
        if was_full:
            self._total_evicted += 1
