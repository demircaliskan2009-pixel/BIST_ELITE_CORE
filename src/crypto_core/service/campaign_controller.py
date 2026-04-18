"""Paper-live campaign controller — Phase 8D.

Orchestrates paper-live campaigns on top of PaperLiveService.

Provides:
  1. CampaignController — lifecycle, inspection, finalization.
  2. Campaign persistence (metadata + verdict artifacts).
  3. Symbol participation tracking.
  4. Campaign stability rollup.

Design rules:
  - Controller does NOT own core trading logic.
  - Controller orchestrates existing service/session/runtime stack.
  - All state transitions are deterministic and explicit.
  - Fail-closed: malformed persisted state → raise, never skip.
  - Bounded in-memory campaign history.
  - PAPER-ONLY.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import logging
import time

from crypto_core.service.campaign import (
    _TERMINAL_STATUSES,
    AcceptancePolicy,
    AcceptanceVerdict,
    CampaignConfig,
    CampaignMetadata,
    CampaignMetadataCorruptError,
    CampaignReport,
    CampaignSnapshot,
    CampaignStatus,
    SymbolParticipation,
    campaign_metadata_from_dict,
    new_campaign_id,
)
from crypto_core.service.evidence_store import (
    EvidenceStore,
    WriteResult,
)
from crypto_core.service.health import (
    HealthConfig,
    HealthTracker,
)
from crypto_core.service.models import ServiceStatus
from crypto_core.service.run_state import (
    PersistenceHealth,
    PersistenceHealthConfig,
)

logger = logging.getLogger(__name__)

_CAMPAIGN_SNAPSHOT_NAME = "campaign_metadata"
_CAMPAIGN_REPORT_SNAPSHOT_NAME = "campaign_report"


# ---------------------------------------------------------------------------
# Campaign controller
# ---------------------------------------------------------------------------


class CampaignController:
    """Orchestrates paper-live campaigns.

    Sits above PaperLiveService and RunStateManager.

    Usage::

        controller = CampaignController(config=CampaignConfig(...))
        controller.start(service_status, run_id="...")
        # ... events flow through service ...
        controller.update(service_status)
        snapshot = controller.snapshot(service_status)
        report = controller.finalize(service_status)

    Thread safety: NOT thread-safe — call from the operator thread only.
    """

    def __init__(
        self,
        config: CampaignConfig | None = None,
        *,
        evidence_store: EvidenceStore | None = None,
    ) -> None:
        cfg = config or CampaignConfig()
        cid = cfg.campaign_id or new_campaign_id()
        self._meta = CampaignMetadata(
            campaign_id=cid,
            config=cfg,
        )
        self._evidence_store = evidence_store
        self._policy = AcceptancePolicy(cfg.thresholds)
        self._health_tracker = HealthTracker(HealthConfig(window_size=50))
        self._persistence_health = PersistenceHealth(PersistenceHealthConfig())
        self._symbol_events: dict[str, bool] = {}
        self._symbol_cycles: dict[str, bool] = {}
        self._finalized = False

    @property
    def campaign_id(self) -> str:
        return self._meta.campaign_id

    @property
    def status(self) -> CampaignStatus:
        return self._meta.status

    @property
    def verdict(self) -> AcceptanceVerdict | None:
        return self._meta.verdict

    @property
    def metadata(self) -> CampaignMetadata:
        return self._meta

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, service_status: ServiceStatus, *, run_id: str = "") -> None:
        """Start the campaign.

        Args:
            service_status: current ServiceStatus snapshot.
            run_id: optional run_id linkage.

        Raises:
            RuntimeError: if campaign not in CREATED state.
        """
        if self._meta.status != CampaignStatus.CREATED:
            raise RuntimeError(f"Cannot start campaign in status {self._meta.status.value!r}")
        now = time.time_ns()
        self._meta.status = CampaignStatus.RUNNING
        self._meta.started_at_ns = now
        self._meta.updated_at_ns = now
        self._meta.run_id = run_id
        self._init_symbol_tracking(service_status)
        self._health_tracker.record_sample(service_status)
        self._persist_metadata()

    def pause(self) -> None:
        """Pause the campaign.

        Raises:
            RuntimeError: if campaign not in RUNNING state.
        """
        if self._meta.status != CampaignStatus.RUNNING:
            raise RuntimeError(f"Cannot pause campaign in status {self._meta.status.value!r}")
        now = time.time_ns()
        self._meta.status = CampaignStatus.PAUSED
        self._meta.paused_at_ns = now
        self._meta.updated_at_ns = now
        self._persist_metadata()

    def resume(self) -> None:
        """Resume a paused campaign.

        Raises:
            RuntimeError: if campaign not in PAUSED state.
        """
        if self._meta.status != CampaignStatus.PAUSED:
            raise RuntimeError(f"Cannot resume campaign in status {self._meta.status.value!r}")
        now = time.time_ns()
        if self._meta.paused_at_ns > 0:
            self._meta.total_pause_duration_ns += now - self._meta.paused_at_ns
        self._meta.status = CampaignStatus.RUNNING
        self._meta.paused_at_ns = 0
        self._meta.updated_at_ns = now
        self._persist_metadata()

    def abort(self, reason: str = "operator_abort") -> None:
        """Abort the campaign.

        Can be called from RUNNING or PAUSED.

        Args:
            reason: abort reason string.

        Raises:
            RuntimeError: if campaign already terminal.
        """
        if self._meta.status in _TERMINAL_STATUSES:
            raise RuntimeError(f"Cannot abort campaign in terminal status {self._meta.status.value!r}")
        now = time.time_ns()
        self._meta.status = CampaignStatus.ABORTED
        self._meta.completed_at_ns = now
        self._meta.updated_at_ns = now
        self._meta.verdict_reason = reason
        self._persist_metadata()

    def fail(self, reason: str = "fatal_error") -> None:
        """Mark campaign as FAILED.

        Args:
            reason: failure reason string.

        Raises:
            RuntimeError: if campaign already terminal.
        """
        if self._meta.status in _TERMINAL_STATUSES:
            raise RuntimeError(f"Cannot fail campaign in terminal status {self._meta.status.value!r}")
        now = time.time_ns()
        self._meta.status = CampaignStatus.FAILED
        self._meta.completed_at_ns = now
        self._meta.updated_at_ns = now
        self._meta.verdict_reason = reason
        self._persist_metadata()

    # ------------------------------------------------------------------
    # Update (call periodically or after events)
    # ------------------------------------------------------------------

    def update(self, service_status: ServiceStatus) -> CampaignStatus:
        """Update campaign counters from current service status.

        Checks stop conditions (max_duration, max_events, max_cycles).
        Returns the current campaign status.

        Args:
            service_status: current ServiceStatus snapshot.

        Returns:
            Current CampaignStatus.
        """
        if self._meta.status != CampaignStatus.RUNNING:
            return self._meta.status

        now = time.time_ns()
        self._meta.updated_at_ns = now

        # Track health.
        self._health_tracker.record_sample(service_status)

        # Track counters from service status.
        self._update_counters(service_status)

        # Track symbol participation.
        self._update_symbol_tracking(service_status)

        # Check stop conditions.
        cfg = self._meta.config
        if cfg.max_duration_s > 0 and self._meta.elapsed_seconds() >= cfg.max_duration_s:
            self._complete("max_duration_reached")
        elif cfg.max_events > 0 and service_status.queue.total_enqueued >= cfg.max_events:
            self._complete("max_events_reached")
        elif (
            cfg.max_cycles > 0
            and service_status.runtime_status is not None
            and service_status.runtime_status.session_status.total_cycles >= cfg.max_cycles
        ):
            self._complete("max_cycles_reached")

        return self._meta.status

    # ------------------------------------------------------------------
    # Finalize — produce verdict
    # ------------------------------------------------------------------

    def finalize(self, service_status: ServiceStatus) -> CampaignReport:
        """Finalize the campaign and produce the verdict report.

        If the campaign is still RUNNING, it is completed first.
        Evaluates acceptance policy and assigns verdict.

        Args:
            service_status: current ServiceStatus snapshot.

        Returns:
            CampaignReport with verdict evidence.

        Raises:
            RuntimeError: if campaign already finalized.
        """
        if self._finalized:
            raise RuntimeError("Campaign already finalized")

        # Auto-complete if still running.
        if self._meta.status == CampaignStatus.RUNNING:
            self.update(service_status)
            if self._meta.status == CampaignStatus.RUNNING:
                self._complete("finalize_requested")

        snap = self.snapshot(service_status)
        result = self._policy.evaluate(snap)

        self._meta.verdict = result.verdict
        self._meta.verdict_reason = result.summary

        # REJECTED status if verdict is FAIL.
        if result.verdict == AcceptanceVerdict.FAIL:
            self._meta.status = CampaignStatus.REJECTED

        self._meta.updated_at_ns = time.time_ns()
        self._finalized = True

        participation = self._build_participation(service_status)

        report = CampaignReport(
            campaign_id=self._meta.campaign_id,
            status=self._meta.status.value,
            verdict=result.verdict.value,
            started_at_ns=self._meta.started_at_ns,
            completed_at_ns=self._meta.completed_at_ns,
            elapsed_seconds=self._meta.elapsed_seconds(),
            run_id=self._meta.run_id,
            snapshot=snap,
            acceptance=result,
            symbol_participation=participation,
            config=self._meta.to_dict().get("config", {}),
        )

        self._persist_metadata()
        self._persist_report(report)
        return report

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def snapshot(self, service_status: ServiceStatus) -> CampaignSnapshot:
        """Produce a point-in-time campaign snapshot.

        Read-only — does NOT mutate campaign state.

        Args:
            service_status: current ServiceStatus.

        Returns:
            Frozen CampaignSnapshot.
        """
        ss = service_status
        meta = self._meta

        total_cycles = 0
        approved_cycles = 0
        blocked_cycles = 0
        failed_cycles = 0
        total_fills = 0
        session_mode = "unknown"
        nav_usd: float | None = None
        if ss.runtime_status is not None:
            sess = ss.runtime_status.session_status
            total_cycles = sess.total_cycles
            approved_cycles = sess.approved_cycles
            blocked_cycles = sess.blocked_cycles
            failed_cycles = sess.failed_cycles
            total_fills = sess.total_fills
            session_mode = sess.mode
            nav_usd = sess.nav_usd

        symbols_ready = sum(1 for sh in ss.symbol_health if sh.feed_ready)
        symbols_blocked = sum(1 for sh in ss.symbol_health if sh.blocked)

        readiness = self._health_tracker.readiness(ss)
        trend = self._health_tracker.trend_snapshot()
        ph = self._persistence_health.snapshot()

        return CampaignSnapshot(
            campaign_id=meta.campaign_id,
            status=meta.status.value,
            started_at_ns=meta.started_at_ns,
            updated_at_ns=meta.updated_at_ns,
            elapsed_seconds=meta.elapsed_seconds(),
            run_id=meta.run_id,
            service_mode=ss.service_mode,
            session_mode=session_mode,
            total_events_enqueued=ss.queue.total_enqueued,
            total_events_dropped=ss.queue.total_dropped,
            total_cycles=total_cycles,
            approved_cycles=approved_cycles,
            blocked_cycles=blocked_cycles,
            failed_cycles=failed_cycles,
            total_fills=total_fills,
            queue_overflows=meta.queue_overflows,
            watchdog_stalls=meta.watchdog_stalls,
            service_restarts=meta.service_restarts,
            persistence_failures=meta.persistence_failures,
            symbol_count=ss.symbol_count,
            symbols_ready=symbols_ready,
            symbols_blocked=symbols_blocked,
            symbols_with_events=sum(1 for v in self._symbol_events.values() if v),
            symbols_with_cycles=sum(1 for v in self._symbol_cycles.values() if v),
            readiness_level=readiness.level.value,
            health_trend=trend.trend.value,
            persistence_status=ph.status.value,
            nav_usd=nav_usd,
            last_error=ss.last_error,
        )

    def symbol_participation_view(self, service_status: ServiceStatus) -> tuple[SymbolParticipation, ...]:
        """Produce per-symbol participation accounting.

        Args:
            service_status: current ServiceStatus.

        Returns:
            Tuple of SymbolParticipation for all tracked symbols.
        """
        return self._build_participation(service_status)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist_state(self) -> WriteResult | None:
        """Persist campaign metadata to disk (if evidence store is set)."""
        return self._persist_metadata()

    def restore_metadata(self) -> CampaignMetadata:
        """Restore campaign metadata from disk.

        Returns:
            Restored CampaignMetadata.

        Raises:
            EvidenceStoreCorruptError: if snapshot missing or malformed.
            CampaignMetadataCorruptError: if metadata fields are invalid.
        """
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for persistence")
        envelope = self._evidence_store.load_snapshot(_CAMPAIGN_SNAPSHOT_NAME)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise CampaignMetadataCorruptError(f"Campaign metadata 'data' must be a dict, got {type(data).__name__!r}")
        meta = campaign_metadata_from_dict(data, self._meta.config)
        self._meta = meta
        return meta

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _complete(self, reason: str) -> None:
        """Move campaign to COMPLETED status."""
        now = time.time_ns()
        self._meta.status = CampaignStatus.COMPLETED
        self._meta.completed_at_ns = now
        self._meta.updated_at_ns = now
        self._meta.verdict_reason = reason

    def _update_counters(self, ss: ServiceStatus) -> None:
        """Update campaign counters from service status."""
        if ss.queue.total_dropped > 0:
            self._meta.queue_overflows = ss.queue.total_dropped

        if ss.watchdog.stall_detected:
            self._meta.watchdog_stalls += 1

        self._meta.service_restarts = ss.total_service_restarts

        ph = self._persistence_health.snapshot()
        self._meta.persistence_failures = ph.total_failures

    def _init_symbol_tracking(self, ss: ServiceStatus) -> None:
        """Initialize symbol tracking from current service status."""
        for sh in ss.symbol_health:
            key = f"{sh.exchange}:{sh.symbol}"
            self._symbol_events[key] = False
            self._symbol_cycles[key] = False

    def _update_symbol_tracking(self, ss: ServiceStatus) -> None:
        """Update symbol participation from service status."""
        for sh in ss.symbol_health:
            key = f"{sh.exchange}:{sh.symbol}"
            if key not in self._symbol_events:
                self._symbol_events[key] = False
                self._symbol_cycles[key] = False
            if sh.last_event_time_ns > 0:
                self._symbol_events[key] = True
            if sh.feed_ready and not sh.blocked:
                self._symbol_cycles[key] = True

    def _build_participation(self, ss: ServiceStatus) -> tuple[SymbolParticipation, ...]:
        """Build per-symbol participation tuples."""
        result: list[SymbolParticipation] = []
        for sh in ss.symbol_health:
            key = f"{sh.exchange}:{sh.symbol}"
            result.append(
                SymbolParticipation(
                    symbol=sh.symbol,
                    exchange=sh.exchange,
                    feed_ready=sh.feed_ready,
                    blocked=sh.blocked,
                    events_observed=self._symbol_events.get(key, False),
                    cycles_observed=self._symbol_cycles.get(key, False),
                )
            )
        return tuple(result)

    def _persist_metadata(self) -> WriteResult | None:
        """Persist campaign metadata snapshot."""
        if self._evidence_store is None:
            return None
        result = self._evidence_store.save_snapshot(
            _CAMPAIGN_SNAPSHOT_NAME,
            self._meta.to_dict(),
        )
        if result.success:
            self._persistence_health.record_success()
        else:
            self._persistence_health.record_failure(result.error or "unknown")
        return result

    def _persist_report(self, report: CampaignReport) -> WriteResult | None:
        """Persist campaign report snapshot."""
        if self._evidence_store is None:
            return None
        data = _report_to_dict(report)
        result = self._evidence_store.save_snapshot(
            _CAMPAIGN_REPORT_SNAPSHOT_NAME,
            data,
        )
        if result.success:
            self._persistence_health.record_success()
        else:
            self._persistence_health.record_failure(result.error or "unknown")
        return result


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _report_to_dict(report: CampaignReport) -> dict:
    """Serialize CampaignReport to a plain dict."""
    acceptance_dict = {
        "verdict": report.acceptance.verdict.value,
        "summary": report.acceptance.summary,
        "criteria": [
            {
                "name": c.name,
                "passed": c.passed,
                "severity": c.severity,
                "actual": c.actual,
                "threshold": c.threshold,
                "message": c.message,
            }
            for c in report.acceptance.criteria
        ],
        "failed_criteria": [c.name for c in report.acceptance.failed_criteria],
        "warning_criteria": [c.name for c in report.acceptance.warning_criteria],
        "insufficient_criteria": [c.name for c in report.acceptance.insufficient_criteria],
    }
    participation_list = [
        {
            "symbol": sp.symbol,
            "exchange": sp.exchange,
            "feed_ready": sp.feed_ready,
            "blocked": sp.blocked,
            "events_observed": sp.events_observed,
            "cycles_observed": sp.cycles_observed,
        }
        for sp in report.symbol_participation
    ]
    snapshot_dict = {
        "campaign_id": report.snapshot.campaign_id,
        "status": report.snapshot.status,
        "started_at_ns": report.snapshot.started_at_ns,
        "updated_at_ns": report.snapshot.updated_at_ns,
        "elapsed_seconds": report.snapshot.elapsed_seconds,
        "total_events_enqueued": report.snapshot.total_events_enqueued,
        "total_cycles": report.snapshot.total_cycles,
        "approved_cycles": report.snapshot.approved_cycles,
        "blocked_cycles": report.snapshot.blocked_cycles,
        "failed_cycles": report.snapshot.failed_cycles,
        "total_fills": report.snapshot.total_fills,
        "queue_overflows": report.snapshot.queue_overflows,
        "watchdog_stalls": report.snapshot.watchdog_stalls,
        "service_restarts": report.snapshot.service_restarts,
        "persistence_failures": report.snapshot.persistence_failures,
        "symbol_count": report.snapshot.symbol_count,
        "symbols_ready": report.snapshot.symbols_ready,
        "symbols_blocked": report.snapshot.symbols_blocked,
        "symbols_with_events": report.snapshot.symbols_with_events,
        "symbols_with_cycles": report.snapshot.symbols_with_cycles,
        "readiness_level": report.snapshot.readiness_level,
        "health_trend": report.snapshot.health_trend,
        "persistence_status": report.snapshot.persistence_status,
        "nav_usd": report.snapshot.nav_usd,
        "last_error": report.snapshot.last_error,
    }
    return {
        "campaign_id": report.campaign_id,
        "status": report.status,
        "verdict": report.verdict,
        "started_at_ns": report.started_at_ns,
        "completed_at_ns": report.completed_at_ns,
        "elapsed_seconds": report.elapsed_seconds,
        "run_id": report.run_id,
        "snapshot": snapshot_dict,
        "acceptance": acceptance_dict,
        "symbol_participation": participation_list,
        "config": report.config,
    }
