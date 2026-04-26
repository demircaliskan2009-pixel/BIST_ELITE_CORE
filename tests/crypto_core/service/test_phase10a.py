# from __future__ import annotations must be the first line, no BOM or whitespace before
from __future__ import annotations

import pytest

from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignReport,
    CampaignSnapshot,
    SymbolParticipation,
)
from crypto_core.service.promotion_review import build_campaign_aggregation, paper_run_summary, verdict_distribution


def make_report(verdict, fills=1):
    snap = CampaignSnapshot(
        campaign_id="c1",
        status="completed",
        started_at_ns=1,
        updated_at_ns=2,
        elapsed_seconds=10.0,
        run_id="r1",
        service_mode="paper",
        session_mode="test",
        total_events_enqueued=100,
        total_events_dropped=0,
        total_cycles=10,
        approved_cycles=10,
        blocked_cycles=0,
        failed_cycles=0,
        total_fills=fills,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=1,
        symbols_ready=1,
        symbols_blocked=0,
        symbols_with_events=1,
        symbols_with_cycles=1,
        readiness_level="paper_live",
        health_trend="good",
        persistence_status="ok",
        nav_usd=None,
        last_error=None,
        ei_degraded=False,
        ei_route_blocks=0,
        ei_route_abstains=0,
        recovery_incidents=0,
        stability=None,
        pending_markout_count=0,
        completed_markout_count=0,
        persisted_tca_count=0,
        persisted_attribution_count=0,
        registered_fill_count=0,
        ext_regime_available=False,
        ext_regime_fresh=False,
        ext_regime_high_risk=False,
        ext_regime_any_unavailable=False,
        ext_regime_evidence_sufficient=False,
        ext_regime_summary="",
        ext_regime_scenario_available=False,
        ext_regime_scenario_step_count=0,
        ext_regime_scenario_accepted_steps=0,
        ext_regime_scenario_rejected_steps=0,
        ext_regime_scenario_replayed_steps=0,
        ext_regime_activation_blocked_steps=0,
        ext_regime_execution_blocked_steps=0,
        ext_regime_activation_reduced_steps=0,
        ext_regime_stale_steps=0,
        ext_regime_unavailable_steps=0,
        ext_regime_high_risk_steps=0,
        ext_regime_safe_steps=0,
        ext_regime_scenario_summary="",
    )
    acc = AcceptanceResult(
        verdict=verdict,
        criteria=(),
        failed_criteria=(),
        warning_criteria=(),
        insufficient_criteria=(),
        summary="",
    )
    return CampaignReport(
        campaign_id="c1",
        status="completed",
        verdict=verdict.value,
        started_at_ns=1,
        completed_at_ns=2,
        elapsed_seconds=10.0,
        run_id="r1",
        snapshot=snap,
        acceptance=acc,
        symbol_participation=(
            SymbolParticipation(
                symbol="BTCUSDT",
                exchange="binance",
                feed_ready=True,
                blocked=False,
                events_observed=True,
                cycles_observed=True,
            ),
        ),
        config={},
    )


def test_paper_run_aggregation_pass():
    reports = (
        make_report(AcceptanceVerdict.PASS),
        make_report(AcceptanceVerdict.PASS_WITH_WARNINGS),
        make_report(AcceptanceVerdict.PASS),
        make_report(AcceptanceVerdict.PASS),
        make_report(AcceptanceVerdict.PASS),
    )
    agg = build_campaign_aggregation(reports)
    vdist = verdict_distribution(agg)
    psum = paper_run_summary(agg)
    assert agg.total_paper_runs == 5
    assert agg.passed_runs == 4
    assert agg.warned_runs == 1
    assert agg.blocked_runs == 0
    assert agg.inconclusive_runs == 0
    assert agg.complete_runs == 5
    assert agg.paper_run_pass_ratio == 1.0
    assert agg.paper_run_complete_ratio == 1.0
    assert agg.paper_run_evidence_supportive is True
    # Check reporting surfaces
    assert vdist["total_paper_runs"] == 5
    assert vdist["passed_runs"] == 4
    assert vdist["warned_runs"] == 1
    assert vdist["blocked_runs"] == 0
    assert vdist["inconclusive_runs"] == 0
    assert vdist["complete_runs"] == 5
    assert vdist["paper_run_pass_ratio"] == 1.0
    assert vdist["paper_run_complete_ratio"] == 1.0
    assert vdist["paper_run_evidence_supportive"] is True
    assert psum["total_paper_runs"] == 5
    assert psum["passed_runs"] == 4
    assert psum["warned_runs"] == 1
    assert psum["blocked_runs"] == 0
    assert psum["inconclusive_runs"] == 0
    assert psum["complete_runs"] == 5
    assert psum["paper_run_pass_ratio"] == 1.0
    assert psum["paper_run_complete_ratio"] == 1.0
    assert psum["paper_run_evidence_supportive"] is True


def test_paper_run_aggregation_mixed():
    reports = (
        make_report(AcceptanceVerdict.PASS),
        make_report(AcceptanceVerdict.FAIL),
        make_report(AcceptanceVerdict.PASS_WITH_WARNINGS),
        make_report(AcceptanceVerdict.INCONCLUSIVE),
    )
    agg = build_campaign_aggregation(reports)
    vdist = verdict_distribution(agg)
    psum = paper_run_summary(agg)
    assert agg.total_paper_runs == 4
    assert agg.passed_runs == 1
    assert agg.warned_runs == 1
    assert agg.blocked_runs == 1
    assert agg.inconclusive_runs == 1
    assert agg.complete_runs == 2
    assert agg.paper_run_pass_ratio == 0.5
    assert agg.paper_run_complete_ratio == 0.5
    assert agg.paper_run_evidence_supportive is False
    # Check reporting surfaces
    assert vdist["total_paper_runs"] == 4
    assert vdist["passed_runs"] == 1
    assert vdist["warned_runs"] == 1
    assert vdist["blocked_runs"] == 1
    assert vdist["inconclusive_runs"] == 1
    assert vdist["complete_runs"] == 2
    assert vdist["paper_run_pass_ratio"] == 0.5
    assert vdist["paper_run_complete_ratio"] == 0.5
    assert vdist["paper_run_evidence_supportive"] is False
    assert psum["total_paper_runs"] == 4
    assert psum["passed_runs"] == 1
    assert psum["warned_runs"] == 1
    assert psum["blocked_runs"] == 1
    assert psum["inconclusive_runs"] == 1
    assert psum["complete_runs"] == 2
    assert psum["paper_run_pass_ratio"] == 0.5
    assert psum["paper_run_complete_ratio"] == 0.5
    assert psum["paper_run_evidence_supportive"] is False


def test_paper_run_aggregation_empty():
    agg = build_campaign_aggregation(())
    vdist = verdict_distribution(agg)
    psum = paper_run_summary(agg)
    assert agg.total_paper_runs == 0
    assert agg.passed_runs == 0
    assert agg.warned_runs == 0
    assert agg.blocked_runs == 0
    assert agg.inconclusive_runs == 0
    assert agg.complete_runs == 0
    assert agg.paper_run_pass_ratio == 0.0
    assert agg.paper_run_complete_ratio == 0.0
    assert agg.paper_run_evidence_supportive is False
    # Check reporting surfaces
    assert vdist["total_paper_runs"] == 0
    assert vdist["passed_runs"] == 0
    assert vdist["warned_runs"] == 0
    assert vdist["blocked_runs"] == 0
    assert vdist["inconclusive_runs"] == 0
    assert vdist["complete_runs"] == 0
    assert vdist["paper_run_pass_ratio"] == 0.0
    assert vdist["paper_run_complete_ratio"] == 0.0
    assert vdist["paper_run_evidence_supportive"] is False
    assert psum["total_paper_runs"] == 0
    assert psum["passed_runs"] == 0
    assert psum["warned_runs"] == 0
    assert psum["blocked_runs"] == 0
    assert psum["inconclusive_runs"] == 0
    assert psum["complete_runs"] == 0
    assert psum["paper_run_pass_ratio"] == 0.0
    assert psum["paper_run_complete_ratio"] == 0.0
    assert psum["paper_run_evidence_supportive"] is False


# Tests for Phase 10A — EI-aware campaign gates + stability rollup.
# (see original docstring for details)

from pathlib import Path

from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.campaign import (
    AcceptancePolicy,
    AcceptanceThresholds,
    CampaignConfig,
    CampaignMetadata,
    CampaignSleeveLinkSummary,
    StabilityRollup,
    campaign_metadata_from_dict,
)
from crypto_core.service.campaign_controller import CampaignController, _report_to_dict, campaign_readiness_flags
from crypto_core.service.evidence_store import EvidenceStore
from crypto_core.service.external_regime import ExternalRegimeScenarioResult
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    SymbolHealth,
    WatchdogStatus,
)
from crypto_core.service.readiness import CriterionStatus, ReadinessEvaluator
from crypto_core.session.models import PaperSessionStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Helpers
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
) -> PaperSessionStatus:
    return PaperSessionStatus(
        session_id="test-10a",
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
    )


def _make_runtime_status(
    *,
    total_cycles: int = 50,
    total_fills: int = 5,
    route_block_count: int = 0,
    route_abstain_count: int = 0,
) -> RuntimeStatus:
    return RuntimeStatus(
        session_status=_make_session_status(
            total_cycles=total_cycles,
            total_fills=total_fills,
            route_block_count=route_block_count,
            route_abstain_count=route_abstain_count,
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
    ei_degraded_reasons: tuple[str, ...] = (),
    route_block_count: int = 0,
    route_abstain_count: int = 0,
) -> ServiceStatus:
    runtime = _make_runtime_status(
        total_cycles=total_cycles,
        total_fills=total_fills,
        route_block_count=route_block_count,
        route_abstain_count=route_abstain_count,
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
    ei = _make_ei_status(degraded=ei_degraded, degraded_reasons=ei_degraded_reasons)
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


def _healthy_snapshot(
    *,
    ei_degraded: bool = False,
    ei_route_blocks: int = 0,
    ei_route_abstains: int = 0,
    recovery_incidents: int = 0,
    stability: StabilityRollup | None = None,
    total_fills: int = 5,
) -> CampaignSnapshot:
    """Campaign snapshot with healthy defaults + optional EI overrides."""
    return CampaignSnapshot(
        campaign_id="test-campaign",
        status="running",
        started_at_ns=_T0_NS,
        updated_at_ns=_T0_NS + 100 * _NS_PER_S,
        elapsed_seconds=100.0,
        run_id="run-1",
        service_mode="running",
        session_mode="running",
        total_events_enqueued=200,
        total_events_dropped=0,
        total_cycles=50,
        approved_cycles=40,
        blocked_cycles=8,
        failed_cycles=2,
        total_fills=total_fills,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=1,
        symbols_ready=1,
        symbols_blocked=0,
        symbols_with_events=1,
        symbols_with_cycles=1,
        readiness_level="ready",
        health_trend="stable",
        persistence_status="healthy",
        nav_usd=10_500.0,
        last_error=None,
        ei_degraded=ei_degraded,
        ei_route_blocks=ei_route_blocks,
        ei_route_abstains=ei_route_abstains,
        recovery_incidents=recovery_incidents,
        stability=stability,
    )


# ===========================================================================
# 1. StabilityRollup
# ===========================================================================


class TestStabilityRollup:
    def test_frozen(self):
        sr = StabilityRollup(
            degraded_intervals=0,
            blocked_intervals=0,
            recovery_incidents=0,
            queue_overflow_incidents=0,
            queue_pressure_warnings=0,
            persistence_failure_count=0,
            ei_degraded=False,
        )
        with pytest.raises(AttributeError):
            sr.degraded_intervals = 5  # type: ignore[misc]

    def test_defaults(self):
        sr = StabilityRollup(
            degraded_intervals=3,
            blocked_intervals=1,
            recovery_incidents=2,
            queue_overflow_incidents=0,
            queue_pressure_warnings=0,
            persistence_failure_count=0,
            ei_degraded=True,
            ei_degraded_reasons=("tca_store_unavailable",),
            ei_route_blocks=10,
            ei_route_abstains=20,
        )
        assert sr.degraded_intervals == 3
        assert sr.ei_degraded is True
        assert sr.ei_degraded_reasons == ("tca_store_unavailable",)
        assert sr.ei_route_blocks == 10
        assert sr.ei_route_abstains == 20


# ===========================================================================
# 2. CampaignSnapshot — new EI + stability fields
# ===========================================================================


class TestCampaignSnapshotEI:
    def test_default_ei_fields(self):
        snap = _healthy_snapshot()
        assert snap.ei_degraded is False
        assert snap.ei_route_blocks == 0
        assert snap.ei_route_abstains == 0
        assert snap.recovery_incidents == 0
        assert snap.stability is None

    def test_ei_fields_set(self):
        sr = StabilityRollup(
            degraded_intervals=5,
            blocked_intervals=2,
            recovery_incidents=1,
            queue_overflow_incidents=0,
            queue_pressure_warnings=0,
            persistence_failure_count=0,
            ei_degraded=True,
        )
        snap = _healthy_snapshot(
            ei_degraded=True,
            ei_route_blocks=15,
            ei_route_abstains=30,
            recovery_incidents=3,
            stability=sr,
        )
        assert snap.ei_degraded is True
        assert snap.ei_route_blocks == 15
        assert snap.ei_route_abstains == 30
        assert snap.recovery_incidents == 3
        assert snap.stability is not None
        assert snap.stability.degraded_intervals == 5


# ===========================================================================
# 3. AcceptanceThresholds — EI threshold defaults
# ===========================================================================


class TestAcceptanceThresholdsEI:
    def test_ei_thresholds_present(self):
        t = AcceptanceThresholds()
        assert hasattr(t, "max_ei_route_blocks")
        assert hasattr(t, "max_ei_route_abstains")
        assert hasattr(t, "ei_degraded_is_hard_fail")
        assert hasattr(t, "max_recovery_incidents")
        assert hasattr(t, "max_degraded_intervals")
        assert hasattr(t, "warn_ei_route_blocks")
        assert hasattr(t, "warn_ei_route_abstains")

    def test_default_values_sane(self):
        t = AcceptanceThresholds()
        assert t.max_ei_route_blocks >= 1
        assert t.max_ei_route_abstains >= 1
        assert t.max_recovery_incidents >= 1
        assert t.max_degraded_intervals >= 1
        assert t.ei_degraded_is_hard_fail is False


# ===========================================================================
# 4-10. AcceptancePolicy — EI + stability criteria
# ===========================================================================


class TestAcceptancePolicyEI:
    def test_pass_when_ei_healthy(self):
        policy = AcceptancePolicy()
        snap = _healthy_snapshot(ei_degraded=False, ei_route_blocks=0, ei_route_abstains=0)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.PASS

    def test_fail_when_max_ei_route_blocks_breached(self):
        policy = AcceptancePolicy(thresholds=AcceptanceThresholds(max_ei_route_blocks=10))
        snap = _healthy_snapshot(ei_route_blocks=15)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        failed_names = {c.name for c in result.failed_criteria}
        assert "max_ei_route_blocks" in failed_names

    def test_fail_when_max_ei_route_abstains_breached(self):
        policy = AcceptancePolicy(thresholds=AcceptanceThresholds(max_ei_route_abstains=50))
        snap = _healthy_snapshot(ei_route_abstains=60)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        failed_names = {c.name for c in result.failed_criteria}
        assert "max_ei_route_abstains" in failed_names

    def test_fail_when_ei_degraded_is_hard_fail(self):
        policy = AcceptancePolicy(thresholds=AcceptanceThresholds(ei_degraded_is_hard_fail=True))
        snap = _healthy_snapshot(ei_degraded=True)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        failed_names = {c.name for c in result.failed_criteria}
        assert "ei_degraded" in failed_names

    def test_pass_when_ei_degraded_but_not_hard_fail(self):
        """ei_degraded_is_hard_fail=False (default) — degraded snapshot still PASS."""
        policy = AcceptancePolicy(thresholds=AcceptanceThresholds(ei_degraded_is_hard_fail=False))
        snap = _healthy_snapshot(ei_degraded=True)
        result = policy.evaluate(snap)
        # Should still pass (or warn) but not FAIL from ei_degraded alone.
        assert result.verdict in (AcceptanceVerdict.PASS, AcceptanceVerdict.PASS_WITH_WARNINGS)

    def test_warn_when_soft_ei_thresholds_breached(self):
        policy = AcceptancePolicy(
            thresholds=AcceptanceThresholds(
                warn_ei_route_blocks=5,
                max_ei_route_blocks=100,
                warn_ei_route_abstains=10,
                max_ei_route_abstains=200,
            )
        )
        snap = _healthy_snapshot(ei_route_blocks=8, ei_route_abstains=15)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.PASS_WITH_WARNINGS
        warning_names = {c.name for c in result.warning_criteria}
        assert "warn_ei_route_blocks" in warning_names
        assert "warn_ei_route_abstains" in warning_names

    def test_fail_when_max_recovery_incidents_breached(self):
        policy = AcceptancePolicy(thresholds=AcceptanceThresholds(max_recovery_incidents=3))
        snap = _healthy_snapshot(recovery_incidents=5)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        failed_names = {c.name for c in result.failed_criteria}
        assert "max_recovery_incidents" in failed_names

    def test_fail_when_max_degraded_intervals_breached(self):
        sr = StabilityRollup(
            degraded_intervals=100,
            blocked_intervals=0,
            recovery_incidents=0,
            queue_overflow_incidents=0,
            queue_pressure_warnings=0,
            persistence_failure_count=0,
            ei_degraded=False,
        )
        policy = AcceptancePolicy(thresholds=AcceptanceThresholds(max_degraded_intervals=50))
        snap = _healthy_snapshot(stability=sr)
        result = policy.evaluate(snap)
        assert result.verdict == AcceptanceVerdict.FAIL
        failed_names = {c.name for c in result.failed_criteria}
        assert "max_degraded_intervals" in failed_names


# ===========================================================================
# 11-12. CampaignMetadata — EI fields round-trip
# ===========================================================================


class TestCampaignMetadataEI:
    def test_ei_fields_default_zero(self):
        meta = CampaignMetadata(campaign_id="m1", config=CampaignConfig())
        assert meta.ei_degraded is False
        assert meta.ei_degraded_reasons == ()
        assert meta.ei_route_blocks == 0
        assert meta.ei_route_abstains == 0
        assert meta.recovery_incidents == 0
        assert meta.degraded_intervals == 0
        assert meta.blocked_intervals == 0
        assert meta.queue_pressure_warnings == 0

    def test_round_trip_serialization(self):
        meta = CampaignMetadata(campaign_id="m2", config=CampaignConfig())
        meta.ei_degraded = True
        meta.ei_degraded_reasons = ("tca_store_fail",)
        meta.ei_route_blocks = 7
        meta.ei_route_abstains = 12
        meta.recovery_incidents = 3
        meta.degraded_intervals = 5
        meta.blocked_intervals = 2
        meta.queue_pressure_warnings = 4
        d = meta.to_dict()
        assert d["ei_degraded"] is True
        assert d["ei_degraded_reasons"] == ["tca_store_fail"]
        assert d["ei_route_blocks"] == 7
        assert d["ei_route_abstains"] == 12
        assert d["recovery_incidents"] == 3
        assert d["degraded_intervals"] == 5
        assert d["blocked_intervals"] == 2
        assert d["queue_pressure_warnings"] == 4

        restored = campaign_metadata_from_dict(d, CampaignConfig())
        assert restored.ei_degraded is True
        assert restored.ei_degraded_reasons == ("tca_store_fail",)
        assert restored.ei_route_blocks == 7
        assert restored.ei_route_abstains == 12
        assert restored.recovery_incidents == 3
        assert restored.degraded_intervals == 5
        assert restored.blocked_intervals == 2
        assert restored.queue_pressure_warnings == 4


# ===========================================================================
# 13-17. CampaignController — EI tracking + stability rollup
# ===========================================================================


class TestCampaignControllerEI:
    def _make_controller(self, tmp_path: Path) -> CampaignController:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        return CampaignController(
            config=CampaignConfig(max_duration_s=600),
            evidence_store=store,
        )

    def test_update_tracks_ei_degradation(self, tmp_path: Path):
        ctrl = self._make_controller(tmp_path)
        ss = _make_service_status(ei_degraded=False)
        ctrl.start(ss, run_id="r1")

        # First update: EI healthy.
        ctrl.update(ss)
        assert ctrl._meta.degraded_intervals == 0

        # Second update: EI degraded.
        ss_degraded = _make_service_status(
            ei_degraded=True,
            ei_degraded_reasons=("tca_store_unavailable",),
        )
        ctrl.update(ss_degraded)
        assert ctrl._meta.degraded_intervals == 1
        assert ctrl._meta.ei_degraded is True
        assert ctrl._meta.ei_degraded_reasons == ("tca_store_unavailable",)

    def test_update_tracks_recovery_incidents(self, tmp_path: Path):
        ctrl = self._make_controller(tmp_path)
        ss_healthy = _make_service_status(ei_degraded=False)
        ctrl.start(ss_healthy, run_id="r1")

        # Degrade.
        ss_degraded = _make_service_status(ei_degraded=True)
        ctrl.update(ss_degraded)
        assert ctrl._meta.recovery_incidents == 0

        # Recover.
        ctrl.update(ss_healthy)
        assert ctrl._meta.recovery_incidents == 1

    def test_update_tracks_route_blocks_from_session(self, tmp_path: Path):
        ctrl = self._make_controller(tmp_path)
        ss = _make_service_status(route_block_count=5, route_abstain_count=12)
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        assert ctrl._meta.ei_route_blocks == 5
        assert ctrl._meta.ei_route_abstains == 12

    def test_snapshot_populates_ei_fields(self, tmp_path: Path):
        ctrl = self._make_controller(tmp_path)
        ss = _make_service_status(
            ei_degraded=True,
            route_block_count=3,
            route_abstain_count=7,
        )
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        snap = ctrl.snapshot(ss)
        assert snap.ei_degraded is True
        assert snap.ei_route_blocks == 3
        assert snap.ei_route_abstains == 7
        assert snap.recovery_incidents == 0

    def test_snapshot_includes_stability_rollup(self, tmp_path: Path):
        ctrl = self._make_controller(tmp_path)
        ss = _make_service_status()
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        snap = ctrl.snapshot(ss)
        assert snap.stability is not None
        assert isinstance(snap.stability, StabilityRollup)
        assert snap.stability.degraded_intervals == 0
        assert snap.stability.ei_degraded is False

    def test_finalize_report_includes_stability(self, tmp_path: Path):
        ctrl = self._make_controller(tmp_path)
        ss = _make_service_status()
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        report = ctrl.finalize(ss)
        assert report.stability is not None
        assert isinstance(report.stability, StabilityRollup)


# ===========================================================================
# 19. _report_to_dict — EI + stability serialization
# ===========================================================================


class TestReportToDictEI:
    def test_serializes_ei_and_stability(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        ctrl = CampaignController(
            config=CampaignConfig(max_duration_s=600),
            evidence_store=store,
        )
        ss = _make_service_status(
            ei_degraded=True,
            ei_degraded_reasons=("tca_store_down",),
            route_block_count=5,
        )
        ctrl.start(ss, run_id="r1")
        ctrl.update(ss)
        report = ctrl.finalize(ss)
        d = _report_to_dict(report)

        assert d["snapshot"]["ei_degraded"] is True
        assert d["snapshot"]["ei_route_blocks"] == 5
        assert d["stability"] is not None
        assert d["stability"]["ei_degraded"] is True
        assert d["stability"]["ei_degraded_reasons"] == ["tca_store_down"]


# ===========================================================================
# 20-22. campaign_readiness_flags
# ===========================================================================


class TestCampaignReadinessFlags:
    def _make_report(
        self,
        verdict: AcceptanceVerdict,
        total_fills: int = 5,
    ) -> CampaignReport:
        snap = _healthy_snapshot(total_fills=total_fills)
        from crypto_core.service.campaign import AcceptanceResult, CriterionResult

        result = AcceptanceResult(
            verdict=verdict,
            criteria=(
                CriterionResult(
                    name="dummy",
                    passed=True,
                    severity="hard",
                    actual=0.0,
                    threshold=100.0,
                    message="ok",
                ),
            ),
            failed_criteria=(),
            warning_criteria=(),
            insufficient_criteria=(),
            summary="test",
        )
        return CampaignReport(
            campaign_id="c1",
            status="completed",
            verdict=verdict.value,
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 100 * _NS_PER_S,
            elapsed_seconds=100.0,
            run_id="r1",
            snapshot=snap,
            acceptance=result,
            symbol_participation=(),
            config={},
        )

    def test_pass_verdict_sets_paper_campaign_completed(self):
        report = self._make_report(AcceptanceVerdict.PASS)
        flags = campaign_readiness_flags(report)
        assert flags["paper_campaign_completed"] is True

    def test_pass_with_warnings_sets_paper_campaign_completed(self):
        report = self._make_report(AcceptanceVerdict.PASS_WITH_WARNINGS)
        flags = campaign_readiness_flags(report)
        assert flags["paper_campaign_completed"] is True

    def test_fail_verdict_blocks_paper_campaign_completed(self):
        report = self._make_report(AcceptanceVerdict.FAIL)
        flags = campaign_readiness_flags(report)
        assert flags["paper_campaign_completed"] is False

    def test_inconclusive_blocks_paper_campaign_completed(self):
        report = self._make_report(AcceptanceVerdict.INCONCLUSIVE)
        flags = campaign_readiness_flags(report)
        assert flags["paper_campaign_completed"] is False

    def test_fills_observed_sets_calibration_flag(self):
        report = self._make_report(AcceptanceVerdict.PASS, total_fills=10)
        flags = campaign_readiness_flags(report)
        assert flags["paper_fill_calibration_available"] is True

    def test_no_fills_clears_calibration_flag(self):
        report = self._make_report(AcceptanceVerdict.PASS, total_fills=0)
        flags = campaign_readiness_flags(report)
        assert flags["paper_fill_calibration_available"] is False

    def test_ext_regime_scenario_flags_truthful(self):
        report = self._make_report(AcceptanceVerdict.PASS, total_fills=10)
        report = CampaignReport(
            campaign_id=report.campaign_id,
            status=report.status,
            verdict=report.verdict,
            started_at_ns=report.started_at_ns,
            completed_at_ns=report.completed_at_ns,
            elapsed_seconds=report.elapsed_seconds,
            run_id=report.run_id,
            snapshot=report.snapshot,
            acceptance=report.acceptance,
            symbol_participation=report.symbol_participation,
            config=report.config,
            ext_regime_available=True,
            ext_regime_evidence_sufficient=True,
            ext_regime_scenario_available=True,
            ext_regime_scenario_step_count=6,
            ext_regime_activation_blocked_steps=1,
            ext_regime_execution_blocked_steps=1,
            ext_regime_activation_reduced_steps=1,
            ext_regime_stale_steps=1,
            ext_regime_unavailable_steps=0,
            ext_regime_high_risk_steps=1,
            ext_regime_safe_steps=4,
            ext_regime_scenario_summary="steps=6; safe=4; blocked=2",
        )
        flags = campaign_readiness_flags(report)
        assert flags["external_regime_evidence_available"] is True
        assert flags["external_regime_evidence_sufficient"] is True
        assert flags["external_regime_scenario_nontrivial_coverage"] is True
        assert flags["external_regime_not_stale_dominated"] is True
        assert flags["external_regime_not_high_risk_dominated"] is True

    def test_readiness_evaluator_surfaces_ext_regime_criteria(self):
        report = self._make_report(AcceptanceVerdict.PASS, total_fills=10)
        report = CampaignReport(
            campaign_id=report.campaign_id,
            status=report.status,
            verdict=report.verdict,
            started_at_ns=report.started_at_ns,
            completed_at_ns=report.completed_at_ns,
            elapsed_seconds=report.elapsed_seconds,
            run_id=report.run_id,
            snapshot=report.snapshot,
            acceptance=report.acceptance,
            symbol_participation=report.symbol_participation,
            config=report.config,
            ext_regime_available=False,
            ext_regime_evidence_sufficient=False,
            ext_regime_scenario_available=False,
            ext_regime_scenario_step_count=0,
        )
        evaluator = ReadinessEvaluator()
        status = evaluator.evaluate(campaign_readiness_flags(report), assessed_at_ns=_T0_NS)
        criteria = {criterion.name: criterion for criterion in status.criteria}
        assert criteria["external_regime_evidence_available"].status == CriterionStatus.NOT_MET
        assert criteria["external_regime_scenario_nontrivial_coverage"].status == CriterionStatus.NOT_MET


# ===========================================================================
# 23. CampaignReport — stability field
# ===========================================================================


class TestCampaignReportStability:
    def test_stability_field_default_none(self):
        snap = _healthy_snapshot()
        from crypto_core.service.campaign import AcceptanceResult

        result = AcceptanceResult(
            verdict=AcceptanceVerdict.PASS,
            criteria=(),
            failed_criteria=(),
            warning_criteria=(),
            insufficient_criteria=(),
            summary="ok",
        )
        report = CampaignReport(
            campaign_id="c1",
            status="completed",
            verdict="pass",
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 100 * _NS_PER_S,
            elapsed_seconds=100.0,
            run_id="r1",
            snapshot=snap,
            acceptance=result,
            symbol_participation=(),
            config={},
        )
        assert report.stability is None

    def test_stability_field_with_rollup(self):
        sr = StabilityRollup(
            degraded_intervals=3,
            blocked_intervals=1,
            recovery_incidents=2,
            queue_overflow_incidents=0,
            queue_pressure_warnings=0,
            persistence_failure_count=0,
            ei_degraded=False,
        )
        snap = _healthy_snapshot(stability=sr)
        from crypto_core.service.campaign import AcceptanceResult

        result = AcceptanceResult(
            verdict=AcceptanceVerdict.PASS,
            criteria=(),
            failed_criteria=(),
            warning_criteria=(),
            insufficient_criteria=(),
            summary="ok",
        )
        report = CampaignReport(
            campaign_id="c1",
            status="completed",
            verdict="pass",
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 100 * _NS_PER_S,
            elapsed_seconds=100.0,
            run_id="r1",
            snapshot=snap,
            acceptance=result,
            symbol_participation=(),
            config={},
            stability=sr,
        )
        assert report.stability is not None
        assert report.stability.degraded_intervals == 3


class TestCampaignControllerExternalRegimeScenarioEvidence:
    def test_snapshot_carries_external_regime_scenario_counts(self, tmp_path: Path):
        ctrl = CampaignController(
            config=CampaignConfig(max_duration_s=600),
            evidence_store=EvidenceStore(evidence_dir=tmp_path / "evidence"),
        )
        ss = _make_service_status()
        ctrl.start(ss, run_id="r-scenario")
        scenario = ExternalRegimeScenarioResult(
            scenario_id="campaign-scenario",
            status="completed",
            step_count=6,
            accepted_steps=4,
            rejected_steps=1,
            replayed_steps=1,
            partially_accepted_steps=1,
            execution_blocked_steps=2,
            activation_blocked_steps=1,
            activation_reduced_steps=2,
            stale_steps=1,
            unavailable_steps=0,
            high_risk_steps=3,
            safe_steps=2,
            last_step_ns=_T0_NS + 10 * _NS_PER_S,
            summary="steps=6; execution_blocked=2; activation_blocked=1; activation_reduced=2",
            step_records=(),
            final_snapshot=None,
        )

        snap = ctrl.snapshot(ss, ext_regime_scenario=scenario)

        assert snap.ext_regime_scenario_available is True
        assert snap.ext_regime_scenario_step_count == 6
        assert snap.ext_regime_execution_blocked_steps == 2
        assert snap.ext_regime_activation_reduced_steps == 2

    def test_finalize_and_report_dict_include_external_regime_scenario_counts(self, tmp_path: Path):
        ctrl = CampaignController(
            config=CampaignConfig(max_duration_s=600),
            evidence_store=EvidenceStore(evidence_dir=tmp_path / "evidence-report"),
        )
        ss = _make_service_status()
        ctrl.start(ss, run_id="r-scenario-report")
        scenario = ExternalRegimeScenarioResult(
            scenario_id="campaign-scenario-report",
            status="completed",
            step_count=5,
            accepted_steps=3,
            rejected_steps=1,
            replayed_steps=1,
            partially_accepted_steps=1,
            execution_blocked_steps=1,
            activation_blocked_steps=1,
            activation_reduced_steps=1,
            stale_steps=1,
            unavailable_steps=1,
            high_risk_steps=2,
            safe_steps=1,
            last_step_ns=_T0_NS + 5 * _NS_PER_S,
            summary="steps=5; execution_blocked=1; activation_blocked=1; activation_reduced=1",
            step_records=(),
            final_snapshot=None,
        )

        report = ctrl.finalize(ss, ext_regime_scenario=scenario)
        serialized = _report_to_dict(report)

        assert report.ext_regime_scenario_available is True
        assert report.ext_regime_execution_blocked_steps == 1
        assert serialized["snapshot"]["ext_regime_scenario_step_count"] == 5
        assert serialized["ext_regime_activation_blocked_steps"] == 1
        assert serialized["ext_regime_scenario_summary"].startswith("steps=5")


class TestCampaignControllerSleeveLinkEvidence:
    def test_snapshot_defaults_sleeve_link_unavailable(self, tmp_path: Path):
        ctrl = CampaignController(
            config=CampaignConfig(max_duration_s=600),
            evidence_store=EvidenceStore(evidence_dir=tmp_path / "evidence-sleeve-default"),
        )
        ss = _make_service_status()

        ctrl.start(ss, run_id="r-sleeve-default")
        snap = ctrl.snapshot(ss)

        assert snap.sleeve_link.linkage_available is False
        assert snap.sleeve_link.configured_sleeve_ids == ()

    def test_finalize_and_report_dict_include_sleeve_link(self, tmp_path: Path):
        ctrl = CampaignController(
            config=CampaignConfig(max_duration_s=600),
            evidence_store=EvidenceStore(evidence_dir=tmp_path / "evidence-sleeve-report"),
        )
        ss = _make_service_status()
        ctrl.start(ss, run_id="r-sleeve-report")

        link = CampaignSleeveLinkSummary(
            linkage_available=True,
            configured_sleeve_ids=("micro-1", "carry-1"),
            qualified_sleeve_ids=("micro-1",),
            recommended_sleeve_ids=("micro-1",),
            blocked_sleeve_ids=("carry-1",),
            summary="sleeves=2; recommended=micro-1",
        )

        report = ctrl.finalize(ss, sleeve_link=link)
        serialized = _report_to_dict(report)

        assert report.sleeve_link == link
        assert report.snapshot.sleeve_link == link
        assert serialized["snapshot"]["sleeve_link"]["configured_sleeve_ids"] == ["micro-1", "carry-1"]
        assert serialized["sleeve_link"]["recommended_sleeve_ids"] == ["micro-1"]
