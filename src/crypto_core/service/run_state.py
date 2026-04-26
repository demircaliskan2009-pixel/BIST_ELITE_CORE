"""Resumable run state, persistence health, and inspection — Phase 8C.

Provides:
  1. RunMetadata — persistent run identity and counters.
  2. PersistenceHealth — tracks persistence success/failure for operator visibility.
  3. RunStateManager — coordinates persist/restore of run metadata + evidence.
  4. InspectionSnapshot — point-in-time operator inspection of the full system.

Design rules:
  - Run metadata persisted as atomic JSON snapshot via EvidenceStore.
  - Restore is deterministic and fail-closed on invalid data.
  - Persistence health uses explicit thresholds and reason codes.
  - Inspection is read-only — never mutates runtime state.
  - All snapshot models are frozen dataclasses.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig, WriteResult

logger = logging.getLogger(__name__)

_RUN_STATE_SNAPSHOT_NAME = "run_state"


# ---------------------------------------------------------------------------
# Persistence health
# ---------------------------------------------------------------------------


class PersistenceStatus(str, Enum):
    """Operator-facing persistence health level."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PersistenceHealthSnapshot:
    """Frozen snapshot of persistence health state.

    Fields:
      status:                    current PersistenceStatus.
      reason:                    human-readable reason for current status.
      total_writes:              total write attempts.
      total_successes:           total successful writes.
      total_failures:            total failed writes.
      consecutive_failures:      current consecutive failure count.
      last_success_time_ns:      wall-clock ns of last successful write.
      last_failure_time_ns:      wall-clock ns of last failed write.
      last_failure_reason:       reason string for last failure; None if clean.
      degraded_threshold:        configured threshold for DEGRADED status.
      failed_threshold:          configured threshold for FAILED status.
    """

    status: PersistenceStatus
    reason: str
    total_writes: int
    total_successes: int
    total_failures: int
    consecutive_failures: int
    last_success_time_ns: int
    last_failure_time_ns: int
    last_failure_reason: str | None
    degraded_threshold: int
    failed_threshold: int


@dataclass(frozen=True)
class PersistenceHealthConfig:
    """Configuration for persistence health tracking.

    degraded_after:  consecutive failures before DEGRADED status.
    failed_after:    consecutive failures before FAILED status.
    """

    degraded_after: int = 3
    failed_after: int = 10


class PersistenceHealth:
    """Track persistence write success/failure for operator visibility.

    Thread-safe: all mutation and snapshot methods hold the internal lock.
    """

    def __init__(self, config: PersistenceHealthConfig | None = None) -> None:
        self._config = config or PersistenceHealthConfig()
        self._lock = threading.Lock()
        self._total_writes: int = 0
        self._total_successes: int = 0
        self._total_failures: int = 0
        self._consecutive_failures: int = 0
        self._last_success_ns: int = 0
        self._last_failure_ns: int = 0
        self._last_failure_reason: str | None = None

    def record_success(self) -> None:
        """Record a successful persistence write."""
        with self._lock:
            self._total_writes += 1
            self._total_successes += 1
            self._consecutive_failures = 0
            self._last_success_ns = time.time_ns()

    def record_failure(self, reason: str) -> None:
        """Record a failed persistence write."""
        with self._lock:
            self._total_writes += 1
            self._total_failures += 1
            self._consecutive_failures += 1
            self._last_failure_ns = time.time_ns()
            self._last_failure_reason = reason

    def snapshot(self) -> PersistenceHealthSnapshot:
        """Produce a frozen persistence health snapshot."""
        with self._lock:
            consecutive = self._consecutive_failures
            cfg = self._config

            if self._total_writes == 0:
                status = PersistenceStatus.UNKNOWN
                reason = "no_writes_yet"
            elif consecutive >= cfg.failed_after:
                status = PersistenceStatus.FAILED
                reason = f"consecutive_failures={consecutive} >= threshold={cfg.failed_after}"
            elif consecutive >= cfg.degraded_after:
                status = PersistenceStatus.DEGRADED
                reason = f"consecutive_failures={consecutive} >= threshold={cfg.degraded_after}"
            else:
                status = PersistenceStatus.HEALTHY
                reason = "all_recent_writes_ok"

            return PersistenceHealthSnapshot(
                status=status,
                reason=reason,
                total_writes=self._total_writes,
                total_successes=self._total_successes,
                total_failures=self._total_failures,
                consecutive_failures=self._consecutive_failures,
                last_success_time_ns=self._last_success_ns,
                last_failure_time_ns=self._last_failure_ns,
                last_failure_reason=self._last_failure_reason,
                degraded_threshold=cfg.degraded_after,
                failed_threshold=cfg.failed_after,
            )


# ---------------------------------------------------------------------------
# Run metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunMetadata:
    """Persistent run identity and counters.

    Fields:
      run_id:              unique run identifier (UUID4 string).
      started_at_ns:       wall-clock ns when the run was created.
      updated_at_ns:       wall-clock ns of last metadata update.
      service_mode:        service mode at last update.
      session_mode:        session mode at last update.
      session_id:          session identifier.
      total_cycles:        total pipeline cycles at last update.
      approved_cycles:     approved cycles at last update.
      blocked_cycles:      blocked cycles at last update.
      failed_cycles:       failed cycles at last update.
      total_fills:         total fills at last update.
      total_events_enqueued: total events enqueued at last update.
      total_events_dropped:  total events dropped at last update.
      nav_usd:             NAV at last update; None if unavailable.
      symbol_count:        registered symbol count at last update.
      persistence_status:  persistence health status at last update.
    """

    run_id: str
    started_at_ns: int
    updated_at_ns: int
    service_mode: str
    session_mode: str
    session_id: str
    total_cycles: int
    approved_cycles: int
    blocked_cycles: int
    failed_cycles: int
    total_fills: int
    total_events_enqueued: int
    total_events_dropped: int
    nav_usd: float | None
    symbol_count: int
    persistence_status: str


class RunMetadataCorruptError(RuntimeError):
    """Raised when persisted run metadata is invalid."""


_RUN_METADATA_REQUIRED = frozenset(
    {
        "run_id",
        "started_at_ns",
        "updated_at_ns",
        "service_mode",
        "session_mode",
        "session_id",
        "total_cycles",
        "approved_cycles",
        "blocked_cycles",
        "failed_cycles",
        "total_fills",
        "total_events_enqueued",
        "total_events_dropped",
        "symbol_count",
        "persistence_status",
    }
)


def _validate_run_metadata(d: dict) -> None:
    """Fail-closed validation for run metadata dict."""
    missing = _RUN_METADATA_REQUIRED - set(d)
    if missing:
        raise RunMetadataCorruptError(f"Run metadata missing required fields: {sorted(missing)!r}")
    if not isinstance(d["run_id"], str) or not d["run_id"]:
        raise RunMetadataCorruptError("Run metadata run_id must be a non-empty string")
    if not isinstance(d["started_at_ns"], int):
        raise RunMetadataCorruptError("Run metadata started_at_ns must be int")


def _run_metadata_from_dict(d: dict) -> RunMetadata:
    """Create RunMetadata from a validated dict."""
    return RunMetadata(
        run_id=d["run_id"],
        started_at_ns=d["started_at_ns"],
        updated_at_ns=d["updated_at_ns"],
        service_mode=d["service_mode"],
        session_mode=d["session_mode"],
        session_id=d["session_id"],
        total_cycles=d["total_cycles"],
        approved_cycles=d["approved_cycles"],
        blocked_cycles=d["blocked_cycles"],
        failed_cycles=d["failed_cycles"],
        total_fills=d["total_fills"],
        total_events_enqueued=d["total_events_enqueued"],
        total_events_dropped=d["total_events_dropped"],
        nav_usd=d.get("nav_usd"),
        symbol_count=d["symbol_count"],
        persistence_status=d["persistence_status"],
    )


def _run_metadata_to_dict(meta: RunMetadata) -> dict:
    """Serialize RunMetadata to a dict."""
    return {
        "run_id": meta.run_id,
        "started_at_ns": meta.started_at_ns,
        "updated_at_ns": meta.updated_at_ns,
        "service_mode": meta.service_mode,
        "session_mode": meta.session_mode,
        "session_id": meta.session_id,
        "total_cycles": meta.total_cycles,
        "approved_cycles": meta.approved_cycles,
        "blocked_cycles": meta.blocked_cycles,
        "failed_cycles": meta.failed_cycles,
        "total_fills": meta.total_fills,
        "total_events_enqueued": meta.total_events_enqueued,
        "total_events_dropped": meta.total_events_dropped,
        "nav_usd": meta.nav_usd,
        "symbol_count": meta.symbol_count,
        "persistence_status": meta.persistence_status,
    }


# ---------------------------------------------------------------------------
# Inspection snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InspectionSnapshot:
    """Point-in-time operator inspection of the full system state.

    Answers: what is the system doing right now?

    Fields:
      timestamp_ns:         wall-clock ns when snapshot was taken.
      run_id:               current run identifier.
      service_mode:         current service mode.
      session_mode:         current session mode.
      session_id:           current session identifier.
      queue_depth:          current queue depth.
      queue_pressure:       current queue pressure zone.
      queue_total_enqueued: total events enqueued.
      queue_total_dropped:  total events dropped.
      consumer_alive:       True if consumer thread is running.
      stall_detected:       True if watchdog detected a stall.
      trading_enabled:      True if trading cycles active.
      total_cycles:         total cycles processed.
      approved_cycles:      approved cycles.
      blocked_cycles:       blocked cycles.
      failed_cycles:        failed cycles.
      total_fills:          total fills.
      nav_usd:              current NAV; None if unavailable.
      symbol_count:         total registered symbols.
      symbols_ready:        symbols with feed_ready=True.
      symbols_blocked:      symbols currently blocked.
      readiness_level:      ReadinessLevel string.
      health_trend:         HealthTrend string.
      degradation_score:    0-100 degradation score.
      persistence_status:   PersistenceStatus string.
      persistence_consecutive_failures: current consecutive failure count.
      last_error:           most recent error; None if clean.
    """

    timestamp_ns: int
    run_id: str
    service_mode: str
    session_mode: str
    session_id: str
    queue_depth: int
    queue_pressure: str
    queue_total_enqueued: int
    queue_total_dropped: int
    consumer_alive: bool
    stall_detected: bool
    trading_enabled: bool
    total_cycles: int
    approved_cycles: int
    blocked_cycles: int
    failed_cycles: int
    total_fills: int
    nav_usd: float | None
    symbol_count: int
    symbols_ready: int
    symbols_blocked: int
    readiness_level: str
    health_trend: str
    degradation_score: int
    persistence_status: str
    persistence_consecutive_failures: int
    last_error: str | None


# ---------------------------------------------------------------------------
# Run state manager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunStateConfig:
    """Configuration for the run state manager.

    evidence_dir:       root directory for evidence files.
    evidence_config:    EvidenceStoreConfig for the evidence store.
    persistence_config: PersistenceHealthConfig for persistence tracking.
    """

    evidence_dir: Path = field(default_factory=lambda: Path("runtime/evidence"))
    evidence_config: EvidenceStoreConfig = field(default_factory=EvidenceStoreConfig)
    persistence_config: PersistenceHealthConfig = field(default_factory=PersistenceHealthConfig)


class RunStateManager:
    """Coordinates run metadata persistence, evidence, and inspection.

    Owns:
      - EvidenceStore (JSONL + atomic snapshots).
      - PersistenceHealth (tracks write success/failure).
      - RunMetadata (current run identity and counters).

    Usage::

        manager = RunStateManager(
            config=RunStateConfig(evidence_dir=Path("runtime/evidence")),
        )
        manager.start_run(service_status)
        manager.persist_run_state(service_status)
        snapshot = manager.inspect(service_status, health_tracker, readiness)
        manager.persist_evidence("readiness_snapshot", {"level": "ready"})
        restored = manager.restore_run_metadata()
    """

    def __init__(self, config: RunStateConfig | None = None) -> None:
        cfg = config or RunStateConfig()
        self._evidence_store = EvidenceStore(
            evidence_dir=cfg.evidence_dir,
            config=cfg.evidence_config,
        )
        self._persistence_health = PersistenceHealth(cfg.persistence_config)
        self._run_metadata: RunMetadata | None = None
        self._run_id: str = ""
        self._started_at_ns: int = 0

    @property
    def evidence_store(self) -> EvidenceStore:
        """Underlying evidence store."""
        return self._evidence_store

    @property
    def persistence_health(self) -> PersistenceHealth:
        """Persistence health tracker."""
        return self._persistence_health

    @property
    def run_metadata(self) -> RunMetadata | None:
        """Current run metadata; None if no run started."""
        return self._run_metadata

    @property
    def run_id(self) -> str:
        """Current run identifier."""
        return self._run_id

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def start_run(self, service_status: object) -> RunMetadata:
        """Initialize a new run with a fresh run_id.

        Args:
            service_status: ServiceStatus from PaperLiveService.status().

        Returns:
            The initial RunMetadata for this run.
        """
        self._run_id = str(uuid.uuid4())
        self._started_at_ns = time.time_ns()
        meta = self._build_metadata(service_status)
        self._run_metadata = meta
        return meta

    def update_run_state(self, service_status: object) -> RunMetadata:
        """Update run metadata from current service status (in-memory only).

        Args:
            service_status: ServiceStatus from PaperLiveService.status().

        Returns:
            Updated RunMetadata.
        """
        meta = self._build_metadata(service_status)
        self._run_metadata = meta
        return meta

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist_run_state(self, service_status: object) -> WriteResult:
        """Persist current run state to disk.

        Updates the in-memory metadata, then writes an atomic snapshot.
        Tracks persistence health.

        Args:
            service_status: ServiceStatus from PaperLiveService.status().

        Returns:
            WriteResult indicating success or failure.
        """
        meta = self._build_metadata(service_status)
        self._run_metadata = meta
        result = self._evidence_store.save_snapshot(
            _RUN_STATE_SNAPSHOT_NAME,
            _run_metadata_to_dict(meta),
        )
        if result.success:
            self._persistence_health.record_success()
        else:
            self._persistence_health.record_failure(result.error or "unknown")
        return result

    def persist_evidence(
        self,
        evidence_type: str,
        data: dict,
    ) -> WriteResult:
        """Persist one evidence record to the JSONL log.

        Tracks persistence health.

        Args:
            evidence_type: one of EVIDENCE_TYPES.
            data: arbitrary dict payload.

        Returns:
            WriteResult indicating success or failure.
        """
        result = self._evidence_store.append_evidence(evidence_type, data)
        if result.success:
            self._persistence_health.record_success()
        else:
            self._persistence_health.record_failure(result.error or "unknown")
        return result

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_run_metadata(self) -> RunMetadata:
        """Restore run metadata from disk.

        Returns:
            Restored RunMetadata.

        Raises:
            EvidenceStoreCorruptError: if snapshot missing or malformed.
            RunMetadataCorruptError: if metadata fields are invalid.
        """
        envelope = self._evidence_store.load_snapshot(_RUN_STATE_SNAPSHOT_NAME)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise RunMetadataCorruptError(f"Run state snapshot 'data' must be a dict, got {type(data).__name__!r}")
        _validate_run_metadata(data)
        meta = _run_metadata_from_dict(data)
        self._run_id = meta.run_id
        self._started_at_ns = meta.started_at_ns
        self._run_metadata = meta
        return meta

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def inspect(
        self,
        service_status: object,
        readiness_snapshot: object | None = None,
        health_trend_snapshot: object | None = None,
    ) -> InspectionSnapshot:
        """Produce a point-in-time inspection snapshot.

        Read-only: does NOT mutate runtime state.

        Args:
            service_status: ServiceStatus from PaperLiveService.status().
            readiness_snapshot: optional ReadinessSnapshot.
            health_trend_snapshot: optional HealthTrendSnapshot.

        Returns:
            Frozen InspectionSnapshot.
        """
        from crypto_core.service.health import HealthTrend, HealthTrendSnapshot, ReadinessLevel, ReadinessSnapshot
        from crypto_core.service.models import ServiceStatus

        ss: ServiceStatus = service_status  # type: ignore[assignment]
        rs_snap: ReadinessSnapshot | None = readiness_snapshot  # type: ignore[assignment]
        ht_snap: HealthTrendSnapshot | None = health_trend_snapshot  # type: ignore[assignment]

        # Session data from runtime status.
        session_id = "unknown"
        session_mode = "unknown"
        total_cycles = 0
        approved_cycles = 0
        blocked_cycles = 0
        failed_cycles = 0
        total_fills = 0
        nav_usd: float | None = None
        if ss.runtime_status is not None:
            sess = ss.runtime_status.session_status
            session_id = sess.session_id
            session_mode = sess.mode
            total_cycles = sess.total_cycles
            approved_cycles = sess.approved_cycles
            blocked_cycles = sess.blocked_cycles
            failed_cycles = sess.failed_cycles
            total_fills = sess.total_fills
            nav_usd = sess.nav_usd

        symbols_ready = sum(1 for sh in ss.symbol_health if sh.feed_ready)
        symbols_blocked = sum(1 for sh in ss.symbol_health if sh.blocked)

        # Readiness / health.
        readiness_level = rs_snap.level.value if rs_snap else ReadinessLevel.UNKNOWN.value
        health_trend = ht_snap.trend.value if ht_snap else HealthTrend.UNKNOWN.value
        degradation_score = ht_snap.degradation_score if ht_snap else 0

        # Persistence health.
        ph = self._persistence_health.snapshot()

        return InspectionSnapshot(
            timestamp_ns=time.time_ns(),
            run_id=self._run_id or "not_started",
            service_mode=ss.service_mode,
            session_mode=session_mode,
            session_id=session_id,
            queue_depth=ss.queue.current_depth,
            queue_pressure=ss.queue.pressure.value,
            queue_total_enqueued=ss.queue.total_enqueued,
            queue_total_dropped=ss.queue.total_dropped,
            consumer_alive=ss.watchdog.consumer_alive,
            stall_detected=ss.watchdog.stall_detected,
            trading_enabled=ss.trading_enabled,
            total_cycles=total_cycles,
            approved_cycles=approved_cycles,
            blocked_cycles=blocked_cycles,
            failed_cycles=failed_cycles,
            total_fills=total_fills,
            nav_usd=nav_usd,
            symbol_count=ss.symbol_count,
            symbols_ready=symbols_ready,
            symbols_blocked=symbols_blocked,
            readiness_level=readiness_level,
            health_trend=health_trend,
            degradation_score=degradation_score,
            persistence_status=ph.status.value,
            persistence_consecutive_failures=ph.consecutive_failures,
            last_error=ss.last_error,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_metadata(self, service_status: object) -> RunMetadata:
        """Build RunMetadata from service status + internal state."""
        from crypto_core.service.models import ServiceStatus

        ss: ServiceStatus = service_status  # type: ignore[assignment]

        session_id = "unknown"
        session_mode = "unknown"
        total_cycles = 0
        approved_cycles = 0
        blocked_cycles = 0
        failed_cycles = 0
        total_fills = 0
        nav_usd: float | None = None
        if ss.runtime_status is not None:
            sess = ss.runtime_status.session_status
            session_id = sess.session_id
            session_mode = sess.mode
            total_cycles = sess.total_cycles
            approved_cycles = sess.approved_cycles
            blocked_cycles = sess.blocked_cycles
            failed_cycles = sess.failed_cycles
            total_fills = sess.total_fills
            nav_usd = sess.nav_usd

        ph = self._persistence_health.snapshot()

        return RunMetadata(
            run_id=self._run_id or "uninitialized",
            started_at_ns=self._started_at_ns,
            updated_at_ns=time.time_ns(),
            service_mode=ss.service_mode,
            session_mode=session_mode,
            session_id=session_id,
            total_cycles=total_cycles,
            approved_cycles=approved_cycles,
            blocked_cycles=blocked_cycles,
            failed_cycles=failed_cycles,
            total_fills=total_fills,
            total_events_enqueued=ss.queue.total_enqueued,
            total_events_dropped=ss.queue.total_dropped,
            nav_usd=nav_usd,
            symbol_count=ss.symbol_count,
            persistence_status=ph.status.value,
        )
