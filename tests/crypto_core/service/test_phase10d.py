"""Tests for Phase 10D — Execution Evidence Propagation + Calibration Fidelity.

Covers:
  1.  CampaignSnapshot carries propagated execution evidence fields.
  2.  CampaignReport carries propagated execution evidence via snapshot.
  3.  CampaignController updates execution evidence from session status.
  4.  Backward-compatible defaults for missing evidence fields.
  5.  build_execution_calibration uses real propagated evidence.
  6.  TCA sufficiency becomes non-UNAVAILABLE when evidence exists.
  7.  Markout completion ratio is real when EI registered fills exist.
  8.  Still UNAVAILABLE when evidence truly does not exist.
  9.  Reporting / serialization includes new fields.
  10. Persistence / restore preserves execution evidence.
  11. Promotion review aggregation reflects richer evidence.
  12. campaign_readiness_flags includes tca_records_sufficient.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignConfig,
    CampaignMetadata,
    CampaignReport,
    CampaignSnapshot,
    CriterionResult,
    StabilityRollup,
    SymbolParticipation,
    campaign_metadata_from_dict,
)
from crypto_core.service.campaign_controller import (
    CampaignController,
    _report_to_dict,
    campaign_readiness_flags,
)
from crypto_core.service.evidence_store import (
    EvidenceStore,
    EvidenceStoreConfig,
)
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    SymbolHealth,
    WatchdogStatus,
)
from crypto_core.service.promotion_review import (
    EvidenceSufficiency,
    PromotionThresholds,
    PromotionVerdict,
    build_campaign_aggregation,
    build_execution_calibration,
    build_promotion_review,
    execution_sufficiency_summary,
)
from crypto_core.session.models import PaperSessionStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Helpers — build fixtures
# ---------------------------------------------------------------------------


def _make_session_status(
    *,
    total_cycles: int = 50,
    total_fills: int = 5,
    approved_cycles: int = 40,
    blocked_cycles: int = 8,
    failed_cycles: int = 2,
    nav_usd: float | None = 10_500.0,
    route_block_count: int = 0,
    route_abstain_count: int = 0,
    pending_markout_count: int = 0,
    persisted_tca_count: int = 0,
    persisted_attribution_count: int = 0,
    registered_fill_count: int = 0,
) -> PaperSessionStatus:
    return PaperSessionStatus(
        session_id="test-10d",
        mode="running",
        start_time_ns=_T0_NS,
        current_cycle_time_ns=_T0_NS + 100 * _NS_PER_S,
        total_cycles=total_cycles,
        total_fills=total_fills,
        approved_cycles=approved_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        recovery_status="clean_start",
        unresolved_order_count=0,
        open_positions_count=1,
        nav_usd=nav_usd,
        gross_exposure_pct=10.0,
        net_exposure_pct=3.0,
        last_cycle_approved=True,
        last_error=None,
        trading_blocked=False,
        route_block_count=route_block_count,
        route_abstain_count=route_abstain_count,
        pending_markout_count=pending_markout_count,
        persisted_tca_count=persisted_tca_count,
        persisted_attribution_count=persisted_attribution_count,
        registered_fill_count=registered_fill_count,
    )


def _make_runtime_status(
    *,
    total_cycles: int = 50,
    total_fills: int = 5,
    route_block_count: int = 0,
    route_abstain_count: int = 0,
    pending_markout_count: int = 0,
    persisted_tca_count: int = 0,
    persisted_attribution_count: int = 0,
    registered_fill_count: int = 0,
) -> RuntimeStatus:
    return RuntimeStatus(
        session_status=_make_session_status(
            total_cycles=total_cycles,
            total_fills=total_fills,
            route_block_count=route_block_count,
            route_abstain_count=route_abstain_count,
            pending_markout_count=pending_markout_count,
            persisted_tca_count=persisted_tca_count,
            persisted_attribution_count=persisted_attribution_count,
            registered_fill_count=registered_fill_count,
        ),
        total_event_count=200,
        total_trigger_count=50,
        total_suppressed_count=10,
        per_symbol_ready={"BTCUSDT": True},
        per_symbol_last_trigger_ns={"BTCUSDT": _T0_NS + 100 * _NS_PER_S},
        recovery_in_progress=False,
        blocked_reason=None,
    )


def _make_ei_status(
    *,
    degraded: bool = False,
    degraded_reasons: tuple[str, ...] = (),
) -> ExecutionIntelligenceStatus:
    return ExecutionIntelligenceStatus(
        mode="live",
        route_binding_enabled=True,
        tca_loop_enabled=True,
        tca_store_available=True,
        replay_dedup_bootstrapped=True,
        degraded=degraded,
        degraded_reasons=degraded_reasons,
    )


def _make_service_status(
    *,
    total_enqueued: int = 200,
    total_dropped: int = 0,
    total_cycles: int = 50,
    total_fills: int = 5,
    stall_detected: bool = False,
    service_mode: str = "running",
    total_service_restarts: int = 0,
    ei_degraded: bool = False,
    route_block_count: int = 0,
    route_abstain_count: int = 0,
    pending_markout_count: int = 0,
    persisted_tca_count: int = 0,
    persisted_attribution_count: int = 0,
    registered_fill_count: int = 0,
) -> ServiceStatus:
    runtime = _make_runtime_status(
        total_cycles=total_cycles,
        total_fills=total_fills,
        route_block_count=route_block_count,
        route_abstain_count=route_abstain_count,
        pending_markout_count=pending_markout_count,
        persisted_tca_count=persisted_tca_count,
        persisted_attribution_count=persisted_attribution_count,
        registered_fill_count=registered_fill_count,
    )
    queue = QueueSnapshot(
        current_depth=10,
        max_size=1000,
        pressure=QueuePressure.NORMAL,
        total_enqueued=total_enqueued,
        total_dropped=total_dropped,
        total_processed=total_enqueued - total_dropped,
    )
    watchdog = WatchdogStatus(
        consumer_alive=True,
        last_event_time_ns=_T0_NS + 100 * _NS_PER_S,
        last_cycle_time_ns=_T0_NS + 100 * _NS_PER_S,
        seconds_since_event=0.5,
        seconds_since_cycle=0.5,
        stall_detected=stall_detected,
        stall_threshold_s=60.0,
    )
    sym = SymbolHealth(
        symbol="BTCUSDT",
        exchange="binance",
        feed_connected=True,
        feed_ready=True,
        feed_key="binance:BTCUSDT",
        last_event_time_ns=_T0_NS + 100 * _NS_PER_S,
        blocked=False,
        block_reason=None,
    )
    ei = _make_ei_status(degraded=ei_degraded)
    return ServiceStatus(
        service_mode=service_mode,
        runtime_status=runtime,
        queue=queue,
        watchdog=watchdog,
        symbol_health=(sym,),
        symbol_count=1,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
        total_service_restarts=total_service_restarts,
        execution_intelligence=ei,
    )


def _make_snapshot(
    *,
    campaign_id: str = "camp-1",
    total_cycles: int = 200,
    total_fills: int = 30,
    total_events: int = 1000,
    symbol_count: int = 3,
    symbols_with_events: int = 3,
    symbols_with_cycles: int = 3,
    elapsed_seconds: float = 600.0,
    blocked_cycles: int = 5,
    failed_cycles: int = 2,
    ei_degraded: bool = False,
    ei_route_blocks: int = 0,
    ei_route_abstains: int = 0,
    recovery_incidents: int = 0,
    stability: StabilityRollup | None = None,
    pending_markout_count: int = 0,
    completed_markout_count: int = 0,
    persisted_tca_count: int = 0,
    persisted_attribution_count: int = 0,
    registered_fill_count: int = 0,
) -> CampaignSnapshot:
    if stability is None:
        stability = StabilityRollup(
            degraded_intervals=0,
            blocked_intervals=0,
            recovery_incidents=recovery_incidents,
            queue_overflow_incidents=0,
            queue_pressure_warnings=0,
            persistence_failure_count=0,
            ei_degraded=ei_degraded,
        )
    return CampaignSnapshot(
        campaign_id=campaign_id,
        status="completed",
        started_at_ns=_T0_NS,
        updated_at_ns=_T0_NS + int(elapsed_seconds * _NS_PER_S),
        elapsed_seconds=elapsed_seconds,
        run_id="run-1",
        service_mode="running",
        session_mode="running",
        total_events_enqueued=total_events,
        total_events_dropped=0,
        total_cycles=total_cycles,
        approved_cycles=total_cycles - blocked_cycles - failed_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        total_fills=total_fills,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=symbol_count,
        symbols_ready=symbol_count,
        symbols_blocked=0,
        symbols_with_events=symbols_with_events,
        symbols_with_cycles=symbols_with_cycles,
        readiness_level="paper_live",
        health_trend="stable",
        persistence_status="healthy",
        nav_usd=10_500.0,
        last_error=None,
        ei_degraded=ei_degraded,
        ei_route_blocks=ei_route_blocks,
        ei_route_abstains=ei_route_abstains,
        recovery_incidents=recovery_incidents,
        stability=stability,
        pending_markout_count=pending_markout_count,
        completed_markout_count=completed_markout_count,
        persisted_tca_count=persisted_tca_count,
        persisted_attribution_count=persisted_attribution_count,
        registered_fill_count=registered_fill_count,
    )


def _make_acceptance(
    verdict: AcceptanceVerdict = AcceptanceVerdict.PASS,
    summary: str = "All acceptance criteria met.",
) -> AcceptanceResult:
    return AcceptanceResult(
        verdict=verdict,
        criteria=(
            CriterionResult(
                name="min_cycles_processed",
                passed=True,
                severity="coverage",
                actual=200.0,
                threshold=10.0,
                message="ok",
            ),
        ),
        failed_criteria=(),
        warning_criteria=(),
        insufficient_criteria=(),
        summary=summary,
    )


def _make_participation() -> tuple[SymbolParticipation, ...]:
    return (
        SymbolParticipation(
            symbol="BTCUSDT",
            exchange="binance",
            feed_ready=True,
            blocked=False,
            events_observed=True,
            cycles_observed=True,
        ),
        SymbolParticipation(
            symbol="ETHUSDT",
            exchange="binance",
            feed_ready=True,
            blocked=False,
            events_observed=True,
            cycles_observed=True,
        ),
    )


def _make_report(
    *,
    campaign_id: str = "camp-1",
    status: str = "completed",
    verdict: str = "pass",
    total_fills: int = 30,
    pending_markout_count: int = 0,
    completed_markout_count: int = 0,
    persisted_tca_count: int = 0,
    persisted_attribution_count: int = 0,
    registered_fill_count: int = 0,
    total_cycles: int = 200,
    total_events: int = 1000,
    symbols_with_events: int = 3,
    elapsed_seconds: float = 600.0,
) -> CampaignReport:
    snap = _make_snapshot(
        campaign_id=campaign_id,
        total_fills=total_fills,
        total_cycles=total_cycles,
        total_events=total_events,
        symbols_with_events=symbols_with_events,
        elapsed_seconds=elapsed_seconds,
        pending_markout_count=pending_markout_count,
        completed_markout_count=completed_markout_count,
        persisted_tca_count=persisted_tca_count,
        persisted_attribution_count=persisted_attribution_count,
        registered_fill_count=registered_fill_count,
    )
    av = AcceptanceVerdict(verdict)
    return CampaignReport(
        campaign_id=campaign_id,
        status=status,
        verdict=verdict,
        started_at_ns=snap.started_at_ns,
        completed_at_ns=snap.updated_at_ns,
        elapsed_seconds=snap.elapsed_seconds,
        run_id=snap.run_id,
        snapshot=snap,
        acceptance=_make_acceptance(av),
        symbol_participation=_make_participation(),
        config={},
        stability=snap.stability,
    )


# ===========================================================================
# 1. CampaignSnapshot carries execution evidence fields
# ===========================================================================


class TestCampaignSnapshotEvidence:
    """CampaignSnapshot includes execution evidence with backward-compat defaults."""

    def test_new_fields_present_with_defaults(self):
        snap = CampaignSnapshot(
            campaign_id="c",
            status="running",
            started_at_ns=0,
            updated_at_ns=0,
            elapsed_seconds=0.0,
            run_id="",
            service_mode="running",
            session_mode="running",
            total_events_enqueued=0,
            total_events_dropped=0,
            total_cycles=0,
            approved_cycles=0,
            blocked_cycles=0,
            failed_cycles=0,
            total_fills=0,
            queue_overflows=0,
            watchdog_stalls=0,
            service_restarts=0,
            persistence_failures=0,
            symbol_count=0,
            symbols_ready=0,
            symbols_blocked=0,
            symbols_with_events=0,
            symbols_with_cycles=0,
            readiness_level="not_assessed",
            health_trend="stable",
            persistence_status="healthy",
            nav_usd=None,
            last_error=None,
        )
        assert snap.pending_markout_count == 0
        assert snap.completed_markout_count == 0
        assert snap.persisted_tca_count == 0
        assert snap.persisted_attribution_count == 0
        assert snap.registered_fill_count == 0

    def test_new_fields_populated(self):
        snap = _make_snapshot(
            pending_markout_count=2,
            completed_markout_count=18,
            persisted_tca_count=15,
            persisted_attribution_count=12,
            registered_fill_count=20,
        )
        assert snap.pending_markout_count == 2
        assert snap.completed_markout_count == 18
        assert snap.persisted_tca_count == 15
        assert snap.persisted_attribution_count == 12
        assert snap.registered_fill_count == 20

    def test_frozen(self):
        snap = _make_snapshot(registered_fill_count=10)
        with pytest.raises(AttributeError):
            snap.registered_fill_count = 99  # type: ignore[misc]


# ===========================================================================
# 2. CampaignController propagates execution evidence
# ===========================================================================


class TestControllerPropagation:
    """CampaignController._update_counters propagates EI evidence from session."""

    def test_update_propagates_counters(self):
        ctrl = CampaignController(config=CampaignConfig(max_cycles=0))
        ss = _make_service_status(
            pending_markout_count=3,
            persisted_tca_count=7,
            persisted_attribution_count=5,
            registered_fill_count=10,
        )
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        snap = ctrl.snapshot(ss)
        assert snap.pending_markout_count == 3
        assert snap.persisted_tca_count == 7
        assert snap.persisted_attribution_count == 5
        assert snap.registered_fill_count == 10
        assert snap.completed_markout_count == 7  # 10 - 3

    def test_completed_markout_never_negative(self):
        """When pending > registered (transient), completed is clamped to 0."""
        ctrl = CampaignController(config=CampaignConfig(max_cycles=0))
        ss = _make_service_status(
            pending_markout_count=15,
            registered_fill_count=10,
        )
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        snap = ctrl.snapshot(ss)
        assert snap.completed_markout_count == 0

    def test_zero_registered_fills(self):
        """When no fills registered with EI, evidence stays at defaults."""
        ctrl = CampaignController(config=CampaignConfig(max_cycles=0))
        ss = _make_service_status(
            pending_markout_count=0,
            persisted_tca_count=0,
            persisted_attribution_count=0,
            registered_fill_count=0,
        )
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        snap = ctrl.snapshot(ss)
        assert snap.registered_fill_count == 0
        assert snap.persisted_tca_count == 0
        assert snap.completed_markout_count == 0

    def test_finalize_report_carries_evidence(self):
        """Finalized CampaignReport carries propagated evidence via snapshot."""
        ctrl = CampaignController(config=CampaignConfig(max_cycles=10))
        ss = _make_service_status(
            total_cycles=10,
            total_fills=5,
            pending_markout_count=1,
            persisted_tca_count=4,
            persisted_attribution_count=3,
            registered_fill_count=5,
        )
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        report = ctrl.finalize(ss)
        assert report.snapshot.pending_markout_count == 1
        assert report.snapshot.persisted_tca_count == 4
        assert report.snapshot.persisted_attribution_count == 3
        assert report.snapshot.registered_fill_count == 5
        assert report.snapshot.completed_markout_count == 4  # 5 - 1

    def test_snapshot_evidence_updates_on_subsequent_update(self):
        """Evidence counters update as session progresses."""
        ctrl = CampaignController(config=CampaignConfig(max_cycles=0))
        ss1 = _make_service_status(
            pending_markout_count=5,
            registered_fill_count=5,
            persisted_tca_count=0,
        )
        ctrl.start(ss1, run_id="r1")
        ctrl.update(ss1)
        snap1 = ctrl.snapshot(ss1)
        assert snap1.pending_markout_count == 5
        assert snap1.completed_markout_count == 0
        assert snap1.persisted_tca_count == 0

        ss2 = _make_service_status(
            pending_markout_count=1,
            registered_fill_count=5,
            persisted_tca_count=4,
            persisted_attribution_count=3,
        )
        ctrl.update(ss2)
        snap2 = ctrl.snapshot(ss2)
        assert snap2.pending_markout_count == 1
        assert snap2.completed_markout_count == 4  # 5 - 1
        assert snap2.persisted_tca_count == 4


# ===========================================================================
# 3. build_execution_calibration with real evidence
# ===========================================================================


class TestCalibrationWithRealEvidence:
    """build_execution_calibration uses propagated evidence from snapshot."""

    def test_real_tca_ratio(self):
        """When registered_fill_count > 0 and persisted_tca_count > 0,
        TCA ratio is real, not -1."""
        report = _make_report(
            total_fills=30,
            registered_fill_count=20,
            persisted_tca_count=16,
            persisted_attribution_count=14,
            pending_markout_count=2,
            completed_markout_count=18,
        )
        cal = build_execution_calibration(report)
        assert cal.persisted_tca_count == 16
        assert cal.persisted_tca_ratio == pytest.approx(16 / 20)
        assert cal.persisted_attribution_count == 14

    def test_real_markout_ratio(self):
        """When registered_fill_count > 0, markout ratio uses real data."""
        report = _make_report(
            total_fills=30,
            registered_fill_count=20,
            pending_markout_count=4,
            completed_markout_count=16,
        )
        cal = build_execution_calibration(report)
        assert cal.completed_markout_count == 16
        assert cal.pending_markout_count == 4
        assert cal.markout_completion_ratio == pytest.approx(16 / 20)

    def test_tca_sufficiency_sufficient(self):
        """With high TCA ratio, tca_sufficiency becomes SUFFICIENT."""
        report = _make_report(
            total_fills=30,
            registered_fill_count=20,
            persisted_tca_count=18,
        )
        cal = build_execution_calibration(report, min_tca_ratio_sufficient=0.7)
        assert cal.persisted_tca_ratio == pytest.approx(18 / 20)
        assert cal.tca_sufficiency == EvidenceSufficiency.SUFFICIENT

    def test_tca_sufficiency_marginal(self):
        """With moderate TCA ratio, tca_sufficiency becomes MARGINAL."""
        report = _make_report(
            total_fills=30,
            registered_fill_count=20,
            persisted_tca_count=8,
        )
        cal = build_execution_calibration(
            report,
            min_tca_ratio_sufficient=0.7,
            min_tca_ratio_marginal=0.3,
        )
        assert cal.persisted_tca_ratio == pytest.approx(8 / 20)
        assert cal.tca_sufficiency == EvidenceSufficiency.MARGINAL

    def test_tca_sufficiency_insufficient(self):
        """With low TCA ratio, tca_sufficiency becomes INSUFFICIENT."""
        report = _make_report(
            total_fills=30,
            registered_fill_count=20,
            persisted_tca_count=2,
        )
        cal = build_execution_calibration(
            report,
            min_tca_ratio_sufficient=0.7,
            min_tca_ratio_marginal=0.3,
        )
        assert cal.persisted_tca_ratio == pytest.approx(2 / 20)
        assert cal.tca_sufficiency == EvidenceSufficiency.INSUFFICIENT

    def test_tca_still_unavailable_no_evidence(self):
        """With no registered fills and no TCA, remains UNAVAILABLE."""
        report = _make_report(
            total_fills=30,
            registered_fill_count=0,
            persisted_tca_count=0,
        )
        cal = build_execution_calibration(report)
        assert cal.persisted_tca_ratio == -1.0
        assert cal.tca_sufficiency == EvidenceSufficiency.UNAVAILABLE

    def test_fallback_proxy_when_no_ei_fills(self):
        """When no registered_fill_count but total_fills > 0, uses proxy."""
        report = _make_report(
            total_fills=30,
            registered_fill_count=0,
            pending_markout_count=0,
            completed_markout_count=0,
        )
        cal = build_execution_calibration(report)
        # Proxy: completed_markout_count = total_fills
        assert cal.completed_markout_count == 30
        assert cal.markout_completion_ratio == 1.0

    def test_zero_fills_no_evidence(self):
        """Zero fills → markout completion ratio is -1 (unavailable)."""
        report = _make_report(
            total_fills=0,
            registered_fill_count=0,
            pending_markout_count=0,
        )
        cal = build_execution_calibration(report)
        assert cal.markout_completion_ratio == -1.0
        assert cal.markout_sufficiency == EvidenceSufficiency.UNAVAILABLE

    def test_all_fills_still_pending(self):
        """All registered fills still pending → completion ratio = 0."""
        report = _make_report(
            total_fills=10,
            registered_fill_count=10,
            pending_markout_count=10,
            completed_markout_count=0,
        )
        cal = build_execution_calibration(report)
        assert cal.completed_markout_count == 0
        assert cal.markout_completion_ratio == pytest.approx(0.0)


# ===========================================================================
# 4. Backward compatibility — defaults
# ===========================================================================


class TestBackwardCompatibility:
    """CampaignMetadata persistence with missing new fields restores safely."""

    def test_metadata_from_dict_missing_new_fields(self):
        """Old persisted dict without new fields → defaults to 0."""
        d = {
            "campaign_id": "old-camp",
            "status": "completed",
            "run_id": "r1",
            "started_at_ns": _T0_NS,
            "updated_at_ns": _T0_NS + 100 * _NS_PER_S,
        }
        meta = campaign_metadata_from_dict(d)
        assert meta.pending_markout_count == 0
        assert meta.completed_markout_count == 0
        assert meta.persisted_tca_count == 0
        assert meta.persisted_attribution_count == 0
        assert meta.registered_fill_count == 0

    def test_metadata_to_dict_includes_new_fields(self):
        """CampaignMetadata.to_dict() includes execution evidence fields."""
        meta = CampaignMetadata(
            campaign_id="c1",
            config=CampaignConfig(),
            pending_markout_count=3,
            completed_markout_count=7,
            persisted_tca_count=5,
            persisted_attribution_count=4,
            registered_fill_count=10,
        )
        d = meta.to_dict()
        assert d["pending_markout_count"] == 3
        assert d["completed_markout_count"] == 7
        assert d["persisted_tca_count"] == 5
        assert d["persisted_attribution_count"] == 4
        assert d["registered_fill_count"] == 10

    def test_metadata_roundtrip(self):
        """to_dict → from_dict preserves execution evidence fields."""
        meta = CampaignMetadata(
            campaign_id="c1",
            config=CampaignConfig(),
            pending_markout_count=3,
            completed_markout_count=7,
            persisted_tca_count=5,
            persisted_attribution_count=4,
            registered_fill_count=10,
        )
        d = meta.to_dict()
        restored = campaign_metadata_from_dict(d, CampaignConfig())
        assert restored.pending_markout_count == 3
        assert restored.completed_markout_count == 7
        assert restored.persisted_tca_count == 5
        assert restored.persisted_attribution_count == 4
        assert restored.registered_fill_count == 10


# ===========================================================================
# 5. Report serialization includes new fields
# ===========================================================================


class TestReportSerialization:
    """_report_to_dict includes new execution evidence fields."""

    def test_snapshot_dict_includes_evidence(self):
        report = _make_report(
            pending_markout_count=2,
            completed_markout_count=18,
            persisted_tca_count=15,
            persisted_attribution_count=12,
            registered_fill_count=20,
        )
        d = _report_to_dict(report)
        snap_d = d["snapshot"]
        assert snap_d["pending_markout_count"] == 2
        assert snap_d["completed_markout_count"] == 18
        assert snap_d["persisted_tca_count"] == 15
        assert snap_d["persisted_attribution_count"] == 12
        assert snap_d["registered_fill_count"] == 20


# ===========================================================================
# 6. Promotion review aggregation with richer evidence
# ===========================================================================


class TestPromotionAggregationEvidence:
    """Promotion aggregation reflects richer calibration data."""

    def _good_reports(self, n: int = 3) -> tuple[CampaignReport, ...]:
        return tuple(
            _make_report(
                campaign_id=f"camp-{i}",
                total_fills=30,
                registered_fill_count=25,
                persisted_tca_count=20,
                persisted_attribution_count=18,
                pending_markout_count=2,
                completed_markout_count=23,
            )
            for i in range(n)
        )

    def test_calibrations_have_real_tca(self):
        """Aggregation calibrations have real TCA ratios (not -1)."""
        reports = self._good_reports(3)
        agg = build_campaign_aggregation(reports)
        for cal in agg.calibrations:
            assert cal.persisted_tca_ratio > 0
            assert cal.tca_sufficiency != EvidenceSufficiency.UNAVAILABLE

    def test_calibrations_have_real_markout(self):
        """Aggregation calibrations have real markout completion ratios."""
        reports = self._good_reports(3)
        agg = build_campaign_aggregation(reports)
        for cal in agg.calibrations:
            assert cal.markout_completion_ratio > 0
            assert cal.completed_markout_count > 0
            assert cal.pending_markout_count >= 0

    def test_sufficiency_summary_no_unavailable(self):
        """When all campaigns have real evidence, no TCA UNAVAILABLE."""
        reports = self._good_reports(3)
        agg = build_campaign_aggregation(reports)
        summary = execution_sufficiency_summary(agg)
        tca_dist = summary["sufficiency_distribution"]["tca"]
        assert tca_dist.get("unavailable", 0) == 0
        assert sum(tca_dist.values()) == 3

    def test_mixed_evidence_campaigns(self):
        """Mix of campaigns with and without EI evidence."""
        r1 = _make_report(
            campaign_id="with-ei",
            total_fills=30,
            registered_fill_count=25,
            persisted_tca_count=20,
        )
        r2 = _make_report(
            campaign_id="without-ei",
            total_fills=30,
            registered_fill_count=0,
            persisted_tca_count=0,
        )
        agg = build_campaign_aggregation((r1, r2))
        cals = {c.campaign_id: c for c in agg.calibrations}
        assert cals["with-ei"].tca_sufficiency != EvidenceSufficiency.UNAVAILABLE
        assert cals["without-ei"].tca_sufficiency == EvidenceSufficiency.UNAVAILABLE


# ===========================================================================
# 7. Promotion verdict with real evidence
# ===========================================================================


class TestPromotionVerdictEvidence:
    """Promotion review uses richer evidence in verdict."""

    def test_promote_with_real_tca(self):
        """With real TCA evidence across campaigns, verdict can be PROMOTE."""
        reports = tuple(
            _make_report(
                campaign_id=f"camp-{i}",
                total_fills=30,
                registered_fill_count=25,
                persisted_tca_count=20,
                persisted_attribution_count=18,
                pending_markout_count=2,
                completed_markout_count=23,
                symbols_with_events=3,
            )
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-10d",
            readiness_level="paper_live",
            thresholds=PromotionThresholds(
                min_persisted_tca_ratio=0.5,
                min_markout_completion_ratio=0.5,
            ),
        )
        assert review.result.verdict == PromotionVerdict.PROMOTE

    def test_tca_ratio_enforced_when_threshold_set(self):
        """When min_persisted_tca_ratio threshold is set, it is evaluated."""
        reports = tuple(
            _make_report(
                campaign_id=f"camp-{i}",
                total_fills=30,
                registered_fill_count=25,
                persisted_tca_count=2,  # low TCA
                symbols_with_events=3,
            )
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-10d",
            readiness_level="paper_live",
            thresholds=PromotionThresholds(
                min_persisted_tca_ratio=0.5,
            ),
        )
        # TCA ratio is 2/25 = 0.08 < 0.5 → coverage insufficient → INCONCLUSIVE
        assert review.result.verdict == PromotionVerdict.INCONCLUSIVE
        insufficient_names = [c.name for c in review.result.insufficient_reasons]
        assert "min_persisted_tca_ratio" in insufficient_names


# ===========================================================================
# 8. campaign_readiness_flags enhancement
# ===========================================================================


class TestReadinessFlags:
    """campaign_readiness_flags includes tca_records_sufficient."""

    def test_tca_sufficient_when_present(self):
        report = _make_report(
            persisted_tca_count=10,
            registered_fill_count=15,
        )
        flags = campaign_readiness_flags(report)
        assert flags["tca_records_sufficient"] is True

    def test_tca_not_sufficient_when_zero(self):
        report = _make_report(
            persisted_tca_count=0,
            registered_fill_count=0,
        )
        flags = campaign_readiness_flags(report)
        assert flags["tca_records_sufficient"] is False

    def test_all_flags_present(self):
        report = _make_report()
        flags = campaign_readiness_flags(report)
        assert "paper_campaign_completed" in flags
        assert "paper_fill_calibration_available" in flags
        assert "tca_records_sufficient" in flags


# ===========================================================================
# 9. Controller persistence with evidence store
# ===========================================================================


class TestControllerPersistence:
    """Campaign controller persistence preserves execution evidence."""

    def test_persist_restore_evidence(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        ctrl = CampaignController(
            config=CampaignConfig(max_cycles=0),
            evidence_store=store,
        )
        ss = _make_service_status(
            pending_markout_count=3,
            persisted_tca_count=7,
            persisted_attribution_count=5,
            registered_fill_count=10,
        )
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        ctrl.persist_state()

        # Restore
        ctrl2 = CampaignController(
            config=CampaignConfig(
                campaign_id=ctrl.campaign_id,
                max_cycles=0,
            ),
            evidence_store=store,
        )
        meta = ctrl2.restore_metadata()
        assert meta.pending_markout_count == 3
        assert meta.persisted_tca_count == 7
        assert meta.persisted_attribution_count == 5
        assert meta.registered_fill_count == 10
        assert meta.completed_markout_count == 7  # 10 - 3


# ===========================================================================
# 10. Promotion review controller with richer evidence
# ===========================================================================


class TestPromotionReviewControllerEvidence:
    """PromotionReviewController consumes richer campaign evidence."""

    def test_controller_snapshot_reflects_tca(self):
        from crypto_core.service.promotion_review_controller import (
            PromotionReviewController,
        )

        ctrl = PromotionReviewController(
            readiness_level="paper_live",
            thresholds=PromotionThresholds(min_persisted_tca_ratio=0.5),
        )
        for i in range(3):
            ctrl.add_campaign_report(
                _make_report(
                    campaign_id=f"camp-{i}",
                    total_fills=30,
                    registered_fill_count=25,
                    persisted_tca_count=20,
                    persisted_attribution_count=18,
                    pending_markout_count=2,
                    completed_markout_count=23,
                    symbols_with_events=3,
                )
            )

        snap = ctrl.current_snapshot()
        # Execution sufficiency should reflect real evidence
        assert snap.execution_sufficiency is not None
        tca_dist = snap.execution_sufficiency.get("sufficiency_distribution", {}).get("tca", {})
        assert tca_dist.get("unavailable", 0) == 0

    def test_controller_finalize_with_real_evidence(self):
        from crypto_core.service.promotion_review_controller import (
            PromotionReviewController,
        )

        ctrl = PromotionReviewController(
            readiness_level="paper_live",
            thresholds=PromotionThresholds(
                min_persisted_tca_ratio=0.5,
                min_markout_completion_ratio=0.5,
            ),
        )
        for i in range(3):
            ctrl.add_campaign_report(
                _make_report(
                    campaign_id=f"camp-{i}",
                    total_fills=30,
                    registered_fill_count=25,
                    persisted_tca_count=20,
                    persisted_attribution_count=18,
                    pending_markout_count=2,
                    completed_markout_count=23,
                    symbols_with_events=3,
                )
            )

        report = ctrl.finalize_review()
        assert report.verdict == PromotionVerdict.PROMOTE.value


# ===========================================================================
# 11. Edge cases and determinism
# ===========================================================================


class TestEdgeCases:
    """Edge cases for execution evidence propagation."""

    def test_registered_exceeds_total_fills(self):
        """registered_fill_count can differ from total_fills (different counters)."""
        cal = build_execution_calibration(
            _make_report(
                total_fills=10,
                registered_fill_count=15,
                pending_markout_count=3,
                completed_markout_count=12,
            )
        )
        assert cal.markout_completion_ratio == pytest.approx(12 / 15)
        assert cal.persisted_tca_ratio == pytest.approx(0.0)  # 0 TCA / 15 registered

    def test_tca_from_total_fills_when_no_registered(self):
        """TCA ratio falls back to total_fills denominator when no registered."""
        report = _make_report(
            total_fills=20,
            registered_fill_count=0,
            persisted_tca_count=10,
        )
        cal = build_execution_calibration(report)
        assert cal.persisted_tca_ratio == pytest.approx(10 / 20)

    def test_deterministic_replay(self):
        """Same inputs → same calibration output."""
        r = _make_report(
            registered_fill_count=20,
            persisted_tca_count=15,
            pending_markout_count=3,
            completed_markout_count=17,
        )
        cal1 = build_execution_calibration(r)
        cal2 = build_execution_calibration(r)
        assert cal1 == cal2
