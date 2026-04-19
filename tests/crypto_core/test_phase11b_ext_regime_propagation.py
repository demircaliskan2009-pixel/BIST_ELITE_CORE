"""Phase 11B — External regime evidence propagation into campaign / promotion / readiness.

Tests that external regime evidence correctly flows from ExternalRegimeSnapshot
through campaign snapshots/reports, promotion review aggregation, and readiness
flags — with explicit unavailable/stale/degraded/partial semantics preserved.
"""

from __future__ import annotations

import time

from crypto_core.execution.regime_contracts import (
    DataFreshness,
    EventRegimeLevel,
    EventRegimeState,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
)
from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignReport,
    CampaignSnapshot,
)
from crypto_core.service.campaign_controller import (
    CampaignController,
    _report_to_dict,
    campaign_readiness_flags,
)
from crypto_core.service.external_regime import (
    DimensionFreshness,
    ExternalRegimeSnapshot,
)
from crypto_core.service.promotion_review import (
    PromotionPolicy,
    PromotionThresholds,
    build_campaign_aggregation,
)
from crypto_core.service.promotion_review_controller import (
    CurrentReviewSnapshot,
    FinalReviewReport,
    PromotionReviewController,
    _classify_ext_regime_quality,
    current_review_snapshot_to_dict,
    final_review_report_to_dict,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fresh_regime_snapshot(*, now_ns: int = 0) -> ExternalRegimeSnapshot:
    """Build a fully fresh, non-extreme external regime snapshot."""
    return ExternalRegimeSnapshot(
        snapshot_ns=now_ns,
        options=OptionsRegimeState(
            symbol="BTCUSDT",
            level=OptionsRegimeLevel.NORMAL,
            snapshot_ns=now_ns,
            source="test",
        ),
        event=EventRegimeState(
            level=EventRegimeLevel.QUIET,
            snapshot_ns=now_ns,
            source="test",
        ),
        on_chain=OnChainRegimeState(
            symbol="BTCUSDT",
            level=OnChainRegimeLevel.NORMAL,
            snapshot_ns=now_ns,
            source="test",
        ),
        options_freshness=DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=now_ns,
            staleness_seconds=0.0,
            source="test",
        ),
        event_freshness=DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=now_ns,
            staleness_seconds=0.0,
            source="test",
        ),
        on_chain_freshness=DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=now_ns,
            staleness_seconds=0.0,
            source="test",
        ),
        any_extreme=False,
        any_unavailable_critical=False,
        high_risk_regime_present=False,
        evidence_sufficient=True,
        available_dimensions=("options", "event", "on_chain"),
        unavailable_dimensions=(),
        stale_dimensions=(),
        regime_summary="All dimensions fresh, normal regime.",
    )


def _stale_regime_snapshot(*, now_ns: int = 0) -> ExternalRegimeSnapshot:
    """Build a snapshot where evidence is stale → evidence_sufficient=False."""
    return ExternalRegimeSnapshot(
        snapshot_ns=now_ns,
        options=None,
        event=None,
        on_chain=None,
        options_freshness=DimensionFreshness(
            freshness=DataFreshness.STALE,
            last_update_ns=now_ns - 600_000_000_000,
            staleness_seconds=600.0,
            source="test",
        ),
        event_freshness=DimensionFreshness(
            freshness=DataFreshness.UNAVAILABLE,
            last_update_ns=None,
            staleness_seconds=None,
            source=None,
        ),
        on_chain_freshness=DimensionFreshness(
            freshness=DataFreshness.UNAVAILABLE,
            last_update_ns=None,
            staleness_seconds=None,
            source=None,
        ),
        any_extreme=False,
        any_unavailable_critical=True,
        high_risk_regime_present=False,
        evidence_sufficient=False,
        available_dimensions=(),
        unavailable_dimensions=("event", "on_chain"),
        stale_dimensions=("options",),
        regime_summary="No fresh data. Stale options, unavailable event/on_chain.",
    )


def _high_risk_regime_snapshot(*, now_ns: int = 0) -> ExternalRegimeSnapshot:
    """Fresh data but high risk regime detected."""
    return ExternalRegimeSnapshot(
        snapshot_ns=now_ns,
        options=OptionsRegimeState(
            symbol="BTCUSDT",
            level=OptionsRegimeLevel.EXTREME,
            snapshot_ns=now_ns,
            source="test",
        ),
        event=EventRegimeState(
            level=EventRegimeLevel.ACTIVE,
            snapshot_ns=now_ns,
            source="test",
            event_label="CPI_RELEASE",
        ),
        on_chain=OnChainRegimeState(
            symbol="BTCUSDT",
            level=OnChainRegimeLevel.NORMAL,
            snapshot_ns=now_ns,
            source="test",
        ),
        options_freshness=DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=now_ns,
            staleness_seconds=0.0,
            source="test",
        ),
        event_freshness=DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=now_ns,
            staleness_seconds=0.0,
            source="test",
        ),
        on_chain_freshness=DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=now_ns,
            staleness_seconds=0.0,
            source="test",
        ),
        any_extreme=True,
        any_unavailable_critical=False,
        high_risk_regime_present=True,
        evidence_sufficient=True,
        available_dimensions=("options", "event", "on_chain"),
        unavailable_dimensions=(),
        stale_dimensions=(),
        regime_summary="High risk: extreme options IV, active event.",
    )


def _make_service_status():
    """Minimal ServiceStatus for campaign controller."""
    from crypto_core.service.models import (
        QueuePressure,
        QueueSnapshot,
        ServiceStatus,
        WatchdogStatus,
    )

    now_ns = time.time_ns()
    return ServiceStatus(
        service_mode="paper",
        runtime_status=None,
        queue=QueueSnapshot(
            current_depth=0,
            max_size=1000,
            pressure=QueuePressure.NORMAL,
            total_enqueued=100,
            total_dropped=0,
            total_processed=100,
        ),
        watchdog=WatchdogStatus(
            consumer_alive=True,
            last_event_time_ns=now_ns,
            last_cycle_time_ns=now_ns,
            seconds_since_event=0.0,
            seconds_since_cycle=0.0,
            stall_detected=False,
            stall_threshold_s=60.0,
        ),
        symbol_health=(),
        symbol_count=0,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
    )


def _make_campaign_controller(*, campaign_id: str = "c-test") -> CampaignController:
    """Build a minimal campaign controller for testing."""
    from crypto_core.service.campaign import CampaignConfig

    config = CampaignConfig(campaign_id=campaign_id)
    ctrl = CampaignController(config=config)
    return ctrl


def _make_minimal_snapshot(
    *,
    campaign_id: str = "c-1",
    status: str = "completed",
    ext_regime_available: bool = False,
    ext_regime_fresh: bool = False,
    ext_regime_high_risk: bool = False,
    ext_regime_any_unavailable: bool = False,
    ext_regime_evidence_sufficient: bool = False,
    ext_regime_summary: str = "",
) -> CampaignSnapshot:
    """Build a minimal CampaignSnapshot with all required fields."""
    return CampaignSnapshot(
        campaign_id=campaign_id,
        status=status,
        started_at_ns=0,
        updated_at_ns=0,
        elapsed_seconds=100.0,
        run_id="run-1",
        service_mode="paper",
        session_mode="autonomous",
        total_events_enqueued=100,
        total_events_dropped=0,
        total_cycles=50,
        approved_cycles=48,
        blocked_cycles=2,
        failed_cycles=0,
        total_fills=5,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=2,
        symbols_ready=2,
        symbols_blocked=0,
        symbols_with_events=2,
        symbols_with_cycles=2,
        readiness_level="paper_live",
        health_trend="stable",
        persistence_status="ok",
        nav_usd=10000.0,
        last_error=None,
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=ext_regime_fresh,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_any_unavailable=ext_regime_any_unavailable,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_summary=ext_regime_summary,
    )


def _make_minimal_report(
    *,
    campaign_id: str = "c-1",
    ext_regime_available: bool = False,
    ext_regime_fresh: bool = False,
    ext_regime_high_risk: bool = False,
    ext_regime_any_unavailable: bool = False,
    ext_regime_evidence_sufficient: bool = False,
    ext_regime_summary: str = "",
) -> CampaignReport:
    """Build a minimal CampaignReport with ext_regime fields."""
    snap = _make_minimal_snapshot(
        campaign_id=campaign_id,
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=ext_regime_fresh,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_any_unavailable=ext_regime_any_unavailable,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_summary=ext_regime_summary,
    )
    return CampaignReport(
        campaign_id=campaign_id,
        status="completed",
        verdict="pass",
        started_at_ns=0,
        completed_at_ns=100_000_000_000,
        elapsed_seconds=100.0,
        run_id="run-1",
        snapshot=snap,
        acceptance=AcceptanceResult(
            verdict=AcceptanceVerdict.PASS,
            criteria=(),
            failed_criteria=(),
            warning_criteria=(),
            insufficient_criteria=(),
            summary="pass",
        ),
        symbol_participation=(),
        config={},
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=ext_regime_fresh,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_any_unavailable=ext_regime_any_unavailable,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_summary=ext_regime_summary,
    )


# ===========================================================================
# 1. Campaign snapshot ext_regime fields
# ===========================================================================


class TestCampaignSnapshotExtRegime:
    """CampaignSnapshot carries external regime evidence."""

    def test_default_values(self):
        snap = _make_minimal_snapshot()
        assert snap.ext_regime_available is False
        assert snap.ext_regime_fresh is False
        assert snap.ext_regime_high_risk is False
        assert snap.ext_regime_any_unavailable is False
        assert snap.ext_regime_evidence_sufficient is False
        assert snap.ext_regime_summary == ""

    def test_explicit_values_propagate(self):
        snap = _make_minimal_snapshot(
            ext_regime_available=True,
            ext_regime_fresh=True,
            ext_regime_evidence_sufficient=True,
            ext_regime_summary="All fresh.",
        )
        assert snap.ext_regime_available is True
        assert snap.ext_regime_fresh is True
        assert snap.ext_regime_evidence_sufficient is True
        assert snap.ext_regime_summary == "All fresh."


# ===========================================================================
# 2. Campaign report ext_regime fields
# ===========================================================================


class TestCampaignReportExtRegime:
    """CampaignReport carries external regime evidence."""

    def test_default_values(self):
        report = _make_minimal_report()
        assert report.ext_regime_available is False
        assert report.ext_regime_evidence_sufficient is False
        assert report.ext_regime_summary == ""

    def test_explicit_values_propagate(self):
        report = _make_minimal_report(
            ext_regime_available=True,
            ext_regime_fresh=True,
            ext_regime_evidence_sufficient=True,
            ext_regime_summary="Fresh.",
        )
        assert report.ext_regime_available is True
        assert report.ext_regime_fresh is True
        assert report.ext_regime_evidence_sufficient is True


# ===========================================================================
# 3. Campaign controller propagation
# ===========================================================================


class TestCampaignControllerPropagation:
    """Campaign controller threads ext_regime through snapshot/finalize."""

    def test_snapshot_without_ext_regime(self):
        ctrl = _make_campaign_controller()
        ss = _make_service_status()
        ctrl.start(ss)
        snap = ctrl.snapshot(ss)
        assert snap.ext_regime_available is False
        assert snap.ext_regime_evidence_sufficient is False
        assert snap.ext_regime_summary == ""

    def test_snapshot_with_fresh_regime(self):
        ctrl = _make_campaign_controller()
        ss = _make_service_status()
        ctrl.start(ss)
        regime = _fresh_regime_snapshot()
        snap = ctrl.snapshot(ss, ext_regime=regime)
        assert snap.ext_regime_available is True
        assert snap.ext_regime_fresh is True
        assert snap.ext_regime_high_risk is False
        assert snap.ext_regime_any_unavailable is False
        assert snap.ext_regime_evidence_sufficient is True
        assert snap.ext_regime_summary != ""

    def test_snapshot_with_stale_regime(self):
        ctrl = _make_campaign_controller()
        ss = _make_service_status()
        ctrl.start(ss)
        regime = _stale_regime_snapshot()
        snap = ctrl.snapshot(ss, ext_regime=regime)
        assert snap.ext_regime_available is False  # no available dimensions
        assert snap.ext_regime_fresh is False
        assert snap.ext_regime_evidence_sufficient is False
        assert snap.ext_regime_any_unavailable is True

    def test_finalize_with_fresh_regime(self):
        ctrl = _make_campaign_controller()
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.update(ss)
        regime = _fresh_regime_snapshot()
        report = ctrl.finalize(ss, ext_regime=regime)
        assert report.ext_regime_available is True
        assert report.ext_regime_fresh is True
        assert report.ext_regime_evidence_sufficient is True
        assert report.snapshot.ext_regime_available is True

    def test_finalize_without_ext_regime_preserves_defaults(self):
        ctrl = _make_campaign_controller()
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.update(ss)
        report = ctrl.finalize(ss)
        assert report.ext_regime_available is False
        assert report.ext_regime_evidence_sufficient is False

    def test_finalize_with_high_risk_regime(self):
        ctrl = _make_campaign_controller()
        ss = _make_service_status()
        ctrl.start(ss)
        ctrl.update(ss)
        regime = _high_risk_regime_snapshot()
        report = ctrl.finalize(ss, ext_regime=regime)
        assert report.ext_regime_available is True
        assert report.ext_regime_high_risk is True
        assert report.ext_regime_evidence_sufficient is True


# ===========================================================================
# 4. Stale/unavailable truth
# ===========================================================================


class TestStaleUnavailableTruth:
    """Stale or unavailable ext_regime evidence is explicitly surfaced."""

    def test_no_regime_is_not_sufficient(self):
        report = _make_minimal_report()
        assert report.ext_regime_available is False
        assert report.ext_regime_evidence_sufficient is False

    def test_stale_regime_is_not_sufficient(self):
        report = _make_minimal_report(
            ext_regime_available=False,
            ext_regime_fresh=False,
            ext_regime_any_unavailable=True,
            ext_regime_evidence_sufficient=False,
            ext_regime_summary="Stale data.",
        )
        assert report.ext_regime_evidence_sufficient is False
        assert report.ext_regime_any_unavailable is True


# ===========================================================================
# 5. Promotion review consumption
# ===========================================================================


class TestPromotionReviewExtRegimeCoverage:
    """Promotion review aggregation and policy consume ext_regime."""

    def test_aggregation_with_all_fresh(self):
        reports = tuple(
            _make_minimal_report(
                campaign_id=f"c-{i}",
                ext_regime_available=True,
                ext_regime_fresh=True,
                ext_regime_evidence_sufficient=True,
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        assert agg.campaigns_with_ext_regime == 3
        assert agg.campaigns_ext_regime_fresh == 3
        assert agg.ext_regime_coverage_ratio == 1.0

    def test_aggregation_with_no_regime(self):
        reports = tuple(_make_minimal_report(campaign_id=f"c-{i}") for i in range(3))
        agg = build_campaign_aggregation(reports)
        assert agg.campaigns_with_ext_regime == 0
        assert agg.ext_regime_coverage_ratio == 0.0

    def test_policy_insufficient_when_no_regime(self):
        reports = tuple(_make_minimal_report(campaign_id=f"c-{i}") for i in range(3))
        agg = build_campaign_aggregation(reports)
        policy = PromotionPolicy(
            PromotionThresholds(
                min_ext_regime_coverage_ratio=0.5,
            )
        )
        result = policy.evaluate(agg)
        # ext_regime coverage below threshold → INCONCLUSIVE
        insufficient_names = [c.name for c in result.insufficient_reasons]
        assert "min_ext_regime_coverage_ratio" in insufficient_names

    def test_policy_sufficient_when_regime_present(self):
        reports = tuple(
            _make_minimal_report(
                campaign_id=f"c-{i}",
                ext_regime_available=True,
                ext_regime_fresh=True,
                ext_regime_evidence_sufficient=True,
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        policy = PromotionPolicy(
            PromotionThresholds(
                min_ext_regime_coverage_ratio=0.5,
            )
        )
        result = policy.evaluate(agg)
        insufficient_names = [c.name for c in result.insufficient_reasons]
        assert "min_ext_regime_coverage_ratio" not in insufficient_names

    def test_policy_disabled_when_negative(self):
        """min_ext_regime_coverage_ratio < 0 → criterion skipped."""
        reports = tuple(_make_minimal_report(campaign_id=f"c-{i}") for i in range(3))
        agg = build_campaign_aggregation(reports)
        policy = PromotionPolicy(
            PromotionThresholds(
                min_ext_regime_coverage_ratio=-1.0,
            )
        )
        result = policy.evaluate(agg)
        criterion_names = [c.name for c in result.criteria]
        assert "min_ext_regime_coverage_ratio" not in criterion_names


# ===========================================================================
# 6. Mixed quality campaigns
# ===========================================================================


class TestMixedQualityCampaigns:
    """Aggregation handles mixed ext_regime quality across campaigns."""

    def test_partial_coverage(self):
        reports = (
            _make_minimal_report(
                campaign_id="c-1",
                ext_regime_available=True,
                ext_regime_fresh=True,
                ext_regime_evidence_sufficient=True,
            ),
            _make_minimal_report(campaign_id="c-2"),  # no regime
            _make_minimal_report(
                campaign_id="c-3",
                ext_regime_available=True,
                ext_regime_fresh=False,
                ext_regime_evidence_sufficient=False,
            ),
        )
        agg = build_campaign_aggregation(reports)
        assert agg.campaigns_with_ext_regime == 2
        assert agg.campaigns_ext_regime_fresh == 1
        assert abs(agg.ext_regime_coverage_ratio - 2.0 / 3.0) < 1e-9

    def test_high_risk_campaigns_tracked(self):
        reports = (
            _make_minimal_report(
                campaign_id="c-1",
                ext_regime_available=True,
                ext_regime_high_risk=True,
            ),
            _make_minimal_report(campaign_id="c-2"),
        )
        agg = build_campaign_aggregation(reports)
        assert agg.campaigns_ext_regime_high_risk == 1


# ===========================================================================
# 7. Readiness/supportive truth
# ===========================================================================


class TestReadinessExtRegimeFlag:
    """campaign_readiness_flags includes external_regime_evidence_available."""

    def test_flag_true_when_sufficient(self):
        report = _make_minimal_report(
            ext_regime_evidence_sufficient=True,
        )
        flags = campaign_readiness_flags(report)
        assert flags["external_regime_evidence_available"] is True

    def test_flag_false_when_absent(self):
        report = _make_minimal_report()
        flags = campaign_readiness_flags(report)
        assert flags["external_regime_evidence_available"] is False


# ===========================================================================
# 8. Serialization
# ===========================================================================


class TestSerializationExtRegime:
    """Serialization helpers include ext_regime fields."""

    def test_report_to_dict_includes_ext_regime(self):
        report = _make_minimal_report(
            ext_regime_available=True,
            ext_regime_fresh=True,
            ext_regime_evidence_sufficient=True,
            ext_regime_summary="Fresh data.",
        )
        d = _report_to_dict(report)
        assert d["ext_regime_available"] is True
        assert d["ext_regime_fresh"] is True
        assert d["ext_regime_evidence_sufficient"] is True
        assert d["ext_regime_summary"] == "Fresh data."
        # Snapshot dict also has ext_regime
        assert d["snapshot"]["ext_regime_available"] is True

    def test_review_snapshot_to_dict_includes_quality(self):
        snap = CurrentReviewSnapshot(
            review_id="r-1",
            status="collecting",
            created_at_ns=0,
            updated_at_ns=0,
            campaign_count=0,
            campaign_ids=(),
            verdict_distribution={},
            execution_sufficiency={},
            symbol_breadth={},
            provisional_verdict=None,
            provisional_summary="",
            insufficient_evidence=(),
            readiness_level="not_assessed",
            readiness_is_supportive=False,
            is_ready_to_finalize=False,
            ext_regime_quality="unavailable",
        )
        d = current_review_snapshot_to_dict(snap)
        assert d["ext_regime_quality"] == "unavailable"

    def test_final_review_report_to_dict_includes_quality(self):
        report = FinalReviewReport(
            review_id="r-1",
            finalized_at_ns=0,
            verdict="promote",
            summary="OK",
            campaign_ids=(),
            campaign_count=0,
            pass_criteria=(),
            warning_criteria=(),
            fail_criteria=(),
            insufficient_evidence=(),
            execution_calibration_quality={},
            coverage_stability_breadth={},
            readiness_level="paper_live",
            readiness_is_supportive=True,
            reason_codes={},
            ext_regime_quality="sufficient",
        )
        d = final_review_report_to_dict(report)
        assert d["ext_regime_quality"] == "sufficient"


# ===========================================================================
# 9. Persistence/restore round-trip
# ===========================================================================


class TestCampaignMetadataExtRegimePersistence:
    """CampaignMetadata ext_regime fields round-trip through to_dict/from_dict."""

    def test_round_trip(self):
        from crypto_core.service.campaign import (
            CampaignConfig,
            CampaignMetadata,
            campaign_metadata_from_dict,
        )

        meta = CampaignMetadata(campaign_id="c-1", config=CampaignConfig())
        meta.ext_regime_available = True
        meta.ext_regime_fresh = True
        meta.ext_regime_high_risk = False
        meta.ext_regime_any_unavailable = False
        meta.ext_regime_evidence_sufficient = True
        meta.ext_regime_summary = "All fresh."

        d = meta.to_dict()
        assert d["ext_regime_available"] is True
        assert d["ext_regime_evidence_sufficient"] is True

        restored = campaign_metadata_from_dict(d)
        assert restored.ext_regime_available is True
        assert restored.ext_regime_fresh is True
        assert restored.ext_regime_evidence_sufficient is True
        assert restored.ext_regime_summary == "All fresh."

    def test_backward_compat_missing_keys(self):
        from crypto_core.service.campaign import campaign_metadata_from_dict

        old_dict = {
            "campaign_id": "c-old",
            "status": "completed",
            "run_id": "run-old",
            "created_at_ns": 0,
            "started_at_ns": 0,
            "updated_at_ns": 0,
        }
        restored = campaign_metadata_from_dict(old_dict)
        assert restored.ext_regime_available is False
        assert restored.ext_regime_evidence_sufficient is False
        assert restored.ext_regime_summary == ""


# ===========================================================================
# 10. Ext regime quality classification
# ===========================================================================


class TestExtRegimeQualityClassification:
    """_classify_ext_regime_quality returns correct quality levels."""

    def test_unavailable_when_no_campaigns(self):
        agg = build_campaign_aggregation(())
        assert _classify_ext_regime_quality(agg) == "unavailable"

    def test_unavailable_when_no_regime_evidence(self):
        reports = tuple(_make_minimal_report(campaign_id=f"c-{i}") for i in range(3))
        agg = build_campaign_aggregation(reports)
        assert _classify_ext_regime_quality(agg) == "unavailable"

    def test_sufficient_when_most_fresh(self):
        reports = tuple(
            _make_minimal_report(
                campaign_id=f"c-{i}",
                ext_regime_available=True,
                ext_regime_fresh=True,
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        assert _classify_ext_regime_quality(agg) == "sufficient"

    def test_marginal_when_partial_fresh(self):
        reports = (
            _make_minimal_report(
                campaign_id="c-1",
                ext_regime_available=True,
                ext_regime_fresh=True,
            ),
            _make_minimal_report(campaign_id="c-2"),
            _make_minimal_report(campaign_id="c-3"),
        )
        agg = build_campaign_aggregation(reports)
        assert _classify_ext_regime_quality(agg) == "marginal"

    def test_insufficient_when_available_but_not_fresh(self):
        reports = (
            _make_minimal_report(
                campaign_id="c-1",
                ext_regime_available=True,
                ext_regime_fresh=False,
            ),
            _make_minimal_report(campaign_id="c-2"),
            _make_minimal_report(campaign_id="c-3"),
            _make_minimal_report(campaign_id="c-4"),
        )
        agg = build_campaign_aggregation(reports)
        # 1 available, 0 fresh, ratio = 0/4 = 0.0 but available > 0
        assert _classify_ext_regime_quality(agg) == "insufficient"


# ===========================================================================
# 11. Promotion review controller ext_regime_quality integration
# ===========================================================================


class TestReviewControllerExtRegimeQuality:
    """PromotionReviewController surfaces ext_regime_quality."""

    def test_snapshot_quality_sufficient(self):
        ctrl = PromotionReviewController(review_id="r-1")
        for i in range(3):
            ctrl.add_campaign_report(
                _make_minimal_report(
                    campaign_id=f"c-{i}",
                    ext_regime_available=True,
                    ext_regime_fresh=True,
                    ext_regime_evidence_sufficient=True,
                )
            )
        snap = ctrl.current_snapshot()
        assert snap.ext_regime_quality == "sufficient"

    def test_snapshot_quality_unavailable(self):
        ctrl = PromotionReviewController(review_id="r-1")
        for i in range(3):
            ctrl.add_campaign_report(_make_minimal_report(campaign_id=f"c-{i}"))
        snap = ctrl.current_snapshot()
        assert snap.ext_regime_quality == "unavailable"

    def test_finalize_includes_quality(self):
        ctrl = PromotionReviewController(
            review_id="r-1",
            thresholds=PromotionThresholds(
                min_completed_campaigns=1,
                min_total_cycles=1,
                min_total_events=1,
                min_total_fills=0,
                min_unique_symbols=0,
                min_total_elapsed_seconds=0,
                min_ext_regime_coverage_ratio=-1.0,  # disable for this test
            ),
        )
        ctrl.add_campaign_report(
            _make_minimal_report(
                campaign_id="c-1",
                ext_regime_available=True,
                ext_regime_fresh=True,
            )
        )
        final = ctrl.finalize_review()
        assert final.ext_regime_quality == "sufficient"
