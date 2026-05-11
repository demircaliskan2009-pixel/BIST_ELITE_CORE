"""Tests for Phase 10B — Execution Calibration + Promotion Review Surface.

Covers:
  1.  ExecutionCalibrationSummary — frozen construction, all fields populated.
  2.  build_execution_calibration — correct ratios and sufficiency from report.
  3.  build_execution_calibration — zero-fills campaign → UNAVAILABLE markout.
  4.  build_execution_calibration — high-fill campaign → SUFFICIENT markout.
  5.  CampaignAggregation — empty reports → zero aggregation.
  6.  build_campaign_aggregation — multi-report verdict distribution.
  7.  build_campaign_aggregation — symbol participation merge.
  8.  build_campaign_aggregation — consistency: STABLE when all PASS.
  9.  build_campaign_aggregation — consistency: MIXED when pass + fail.
  10. build_campaign_aggregation — consistency: INSUFFICIENT with single campaign.
  11. PromotionPolicy — PROMOTE when all criteria met.
  12. PromotionPolicy — REJECT when hard criteria breached.
  13. PromotionPolicy — HOLD when soft warnings present.
  14. PromotionPolicy — INCONCLUSIVE when coverage insufficient.
  15. PromotionPolicy — insufficient evidence: too few campaigns.
  16. build_promotion_review — full pipeline assembly.
  17. PromotionReviewStore — save + load round-trip.
  18. PromotionReviewStore — malformed snapshot → fail-closed.
  19. Reporting API — verdict_distribution.
  20. Reporting API — execution_sufficiency_summary.
  21. Reporting API — promotion_reason_summary.
  22. Readiness interaction — not_assessed is not supportive.
  23. Readiness interaction — paper_live is supportive.
  24. PromotionPolicy — single lucky campaign cannot PROMOTE.
  25. PromotionPolicy — mixed campaign history → correct aggregation.
  26. Serialization — promotion_review_to_dict round-trip.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignReport,
    CampaignSnapshot,
    CriterionResult,
    StabilityRollup,
    SymbolParticipation,
)
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.promotion_review import (
    AggregateConsistency,
    CampaignAggregation,
    EvidenceSufficiency,
    PromotionPolicy,
    PromotionReviewCorruptError,
    PromotionReviewStore,
    PromotionThresholds,
    PromotionVerdict,
    build_campaign_aggregation,
    build_execution_calibration,
    build_promotion_review,
    execution_sufficiency_summary,
    ext_regime_governance_summary,
    promotion_reason_summary,
    promotion_review_to_dict,
    symbol_participation_summary,
    verdict_distribution,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Helpers — campaign fixtures
# ---------------------------------------------------------------------------


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
) -> CampaignSnapshot:
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
        nav_usd=10_000.0,
        last_error=None,
        ei_degraded=ei_degraded,
        ei_route_blocks=ei_route_blocks,
        ei_route_abstains=ei_route_abstains,
        recovery_incidents=recovery_incidents,
        stability=stability,
    )


def _make_acceptance(
    verdict: AcceptanceVerdict = AcceptanceVerdict.PASS,
) -> AcceptanceResult:
    return AcceptanceResult(
        verdict=verdict,
        criteria=(
            CriterionResult(
                name="min_events_processed",
                passed=True,
                severity="coverage",
                actual=1000,
                threshold=100,
                message="min_events_processed: 1000 ≥ 100",
            ),
        ),
        failed_criteria=(),
        warning_criteria=(),
        insufficient_criteria=(),
        summary="All criteria met.",
    )


def _make_participation(
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    exchange: str = "binance",
) -> tuple[SymbolParticipation, ...]:
    return tuple(
        SymbolParticipation(
            symbol=s,
            exchange=exchange,
            feed_ready=True,
            blocked=False,
            events_observed=True,
            cycles_observed=True,
        )
        for s in symbols
    )


def _make_report(
    *,
    campaign_id: str = "camp-1",
    verdict: AcceptanceVerdict = AcceptanceVerdict.PASS,
    total_cycles: int = 200,
    total_fills: int = 30,
    total_events: int = 1000,
    elapsed_seconds: float = 600.0,
    completed_at_ns: int | None = None,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    ei_degraded: bool = False,
    ei_route_blocks: int = 0,
    ei_route_abstains: int = 0,
    recovery_incidents: int = 0,
    stability: StabilityRollup | None = None,
    ext_regime_available: bool = True,
    ext_regime_fresh: bool = True,
    ext_regime_high_risk: bool = False,
    ext_regime_evidence_sufficient: bool = True,
    ext_regime_scenario_available: bool = True,
    ext_regime_scenario_step_count: int = 6,
    ext_regime_activation_blocked_steps: int = 0,
    ext_regime_execution_blocked_steps: int = 0,
    ext_regime_activation_reduced_steps: int = 0,
    ext_regime_stale_steps: int = 1,
    ext_regime_unavailable_steps: int = 0,
    ext_regime_high_risk_steps: int = 1,
    ext_regime_safe_steps: int = 4,
    ext_regime_scenario_summary: str = "steps=6; safe=4; stale=1; high_risk=1; reduced=0",
) -> CampaignReport:
    snap = _make_snapshot(
        campaign_id=campaign_id,
        total_cycles=total_cycles,
        total_fills=total_fills,
        total_events=total_events,
        elapsed_seconds=elapsed_seconds,
        symbol_count=len(symbols),
        symbols_with_events=len(symbols),
        symbols_with_cycles=len(symbols),
        ei_degraded=ei_degraded,
        ei_route_blocks=ei_route_blocks,
        ei_route_abstains=ei_route_abstains,
        recovery_incidents=recovery_incidents,
        stability=stability,
    )
    return CampaignReport(
        campaign_id=campaign_id,
        status="completed",
        verdict=verdict.value,
        started_at_ns=_T0_NS,
        completed_at_ns=(_T0_NS + int(elapsed_seconds * _NS_PER_S) if completed_at_ns is None else completed_at_ns),
        elapsed_seconds=elapsed_seconds,
        run_id="run-1",
        snapshot=snap,
        acceptance=_make_acceptance(verdict),
        symbol_participation=_make_participation(symbols),
        config={},
        stability=stability,
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=ext_regime_fresh,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_summary=ext_regime_scenario_summary,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary=ext_regime_scenario_summary,
    )


# ===========================================================================
# 1. ExecutionCalibrationSummary — frozen, all fields
# ===========================================================================


class TestExecutionCalibrationSummary:
    def test_frozen(self):
        cal = build_execution_calibration(_make_report())
        with pytest.raises(AttributeError):
            cal.total_cycles = 999  # type: ignore[misc]

    def test_fields_populated(self):
        cal = build_execution_calibration(_make_report(total_cycles=200, total_fills=30))
        assert cal.campaign_id == "camp-1"
        assert cal.total_cycles == 200
        assert cal.total_fills == 30
        assert cal.markout_sufficiency == EvidenceSufficiency.SUFFICIENT


# ===========================================================================
# 2-4. build_execution_calibration — ratios and sufficiency
# ===========================================================================


class TestBuildExecutionCalibration:
    def test_correct_ratios(self):
        report = _make_report(
            total_cycles=100,
            total_fills=25,
            ei_route_blocks=5,
            ei_route_abstains=10,
        )
        cal = build_execution_calibration(report)
        assert cal.route_block_ratio == pytest.approx(0.05)
        assert cal.route_abstain_ratio == pytest.approx(0.10)
        assert cal.markout_completion_ratio == 1.0  # all fills completed proxy
        assert cal.total_events == 1000

    def test_zero_fills_unavailable(self):
        report = _make_report(total_fills=0)
        cal = build_execution_calibration(report)
        assert cal.markout_sufficiency == EvidenceSufficiency.UNAVAILABLE
        assert cal.markout_completion_ratio == -1.0

    def test_high_fills_sufficient(self):
        report = _make_report(total_fills=50)
        cal = build_execution_calibration(report)
        assert cal.markout_sufficiency == EvidenceSufficiency.SUFFICIENT

    def test_marginal_fills(self):
        report = _make_report(total_fills=8)
        cal = build_execution_calibration(report)
        assert cal.markout_sufficiency == EvidenceSufficiency.MARGINAL

    def test_insufficient_fills(self):
        report = _make_report(total_fills=2)
        cal = build_execution_calibration(report)
        assert cal.markout_sufficiency == EvidenceSufficiency.INSUFFICIENT

    def test_zero_cycles_ratios(self):
        report = _make_report(total_cycles=0)
        cal = build_execution_calibration(report)
        assert cal.route_block_ratio == -1.0
        assert cal.blocked_cycle_ratio == -1.0
        assert cal.failed_cycle_ratio == -1.0

    def test_campaign_breadth_sufficient(self):
        report = _make_report(total_cycles=200)
        cal = build_execution_calibration(report)
        assert cal.campaign_breadth_sufficiency == EvidenceSufficiency.SUFFICIENT

    def test_campaign_breadth_marginal(self):
        report = _make_report(total_cycles=50)
        cal = build_execution_calibration(report)
        assert cal.campaign_breadth_sufficiency == EvidenceSufficiency.MARGINAL

    def test_symbol_participation_sufficient(self):
        report = _make_report(symbols=("BTC", "ETH", "SOL"))
        cal = build_execution_calibration(report)
        assert cal.symbol_participation_sufficiency == EvidenceSufficiency.SUFFICIENT

    def test_symbol_participation_marginal(self):
        report = _make_report(symbols=("BTC",))
        cal = build_execution_calibration(report)
        assert cal.symbol_participation_sufficiency == EvidenceSufficiency.MARGINAL


# ===========================================================================
# 5. Empty aggregation
# ===========================================================================


class TestCampaignAggregationEmpty:
    def test_empty_reports(self):
        agg = build_campaign_aggregation(())
        assert agg.total_campaigns == 0
        assert agg.passed_count == 0
        assert agg.verdict_consistency == AggregateConsistency.INSUFFICIENT
        assert agg.calibrations == ()


# ===========================================================================
# 6-7. Multi-report aggregation
# ===========================================================================


class TestBuildCampaignAggregation:
    def test_verdict_distribution(self):
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.PASS_WITH_WARNINGS),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.FAIL),
        )
        agg = build_campaign_aggregation(reports)
        assert agg.total_campaigns == 3
        assert agg.passed_count == 1
        assert agg.warned_count == 1
        assert agg.failed_count == 1
        assert agg.inconclusive_count == 0

    def test_symbol_participation_merge(self):
        reports = (
            _make_report(campaign_id="c1", symbols=("BTC", "ETH")),
            _make_report(campaign_id="c2", symbols=("ETH", "SOL")),
        )
        agg = build_campaign_aggregation(reports)
        assert set(agg.unique_symbols) == {"BTC", "ETH", "SOL"}
        assert "binance" in agg.unique_exchanges

    def test_aggregate_metrics_sum(self):
        reports = (
            _make_report(campaign_id="c1", total_cycles=100, total_fills=10),
            _make_report(campaign_id="c2", total_cycles=150, total_fills=20),
        )
        agg = build_campaign_aggregation(reports)
        assert agg.total_cycles == 250
        assert agg.total_fills == 30

    def test_per_campaign_calibrations(self):
        reports = (
            _make_report(campaign_id="c1"),
            _make_report(campaign_id="c2"),
        )
        agg = build_campaign_aggregation(reports)
        assert len(agg.calibrations) == 2
        assert agg.calibrations[0].campaign_id == "c1"
        assert agg.calibrations[1].campaign_id == "c2"


# ===========================================================================
# 8-10. Consistency assessment
# ===========================================================================


class TestConsistency:
    def test_stable_all_pass(self):
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS_WITH_WARNINGS),
        )
        agg = build_campaign_aggregation(reports)
        assert agg.verdict_consistency == AggregateConsistency.STABLE

    def test_mixed_pass_and_fail(self):
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS),
        )
        agg = build_campaign_aggregation(reports)
        assert agg.verdict_consistency == AggregateConsistency.MIXED

    def test_insufficient_single_campaign(self):
        reports = (_make_report(campaign_id="c1"),)
        agg = build_campaign_aggregation(reports)
        assert agg.verdict_consistency == AggregateConsistency.INSUFFICIENT


# ===========================================================================
# 11-15. PromotionPolicy
# ===========================================================================


class TestPromotionPolicy:
    def _good_reports(self, n: int = 3) -> tuple[CampaignReport, ...]:
        return tuple(
            _make_report(
                campaign_id=f"c{i}",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                total_events=1000,
                elapsed_seconds=600.0,
                symbols=("BTC", "ETH", "SOL"),
            )
            for i in range(n)
        )

    def test_promote_all_criteria_met(self):
        # Phase 16M: pass min_paper_runs=3 to cover the new paper-run gate.
        thresholds = PromotionThresholds(min_paper_runs=3)
        reports = self._good_reports(3)
        agg = build_campaign_aggregation(reports, thresholds=thresholds)
        policy = PromotionPolicy(thresholds)
        result = policy.evaluate(agg)
        assert result.verdict == PromotionVerdict.PROMOTE
        assert len(result.fail_reasons) == 0
        assert len(result.insufficient_reasons) == 0

    def test_reject_hard_criteria_breached(self):
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.FAIL),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS),
        )
        agg = build_campaign_aggregation(reports)
        # Phase 16M: min_paper_runs=0 disables paper gate; test focuses on hard criteria.
        policy = PromotionPolicy(PromotionThresholds(min_paper_runs=0))
        result = policy.evaluate(agg)
        assert result.verdict == PromotionVerdict.REJECT
        assert any(c.name == "max_failed_campaigns" for c in result.fail_reasons)

    def test_hold_soft_warnings(self):
        # Create reports with high route blocks triggering soft warning but not hard fail
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                total_events=1000,
                elapsed_seconds=600.0,
                symbols=("BTC", "ETH", "SOL"),
                recovery_incidents=1,  # triggers warn_recovery_incidents > 0
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        # Total recovery = 3, warn threshold = 3 → passes at boundary
        # Use custom thresholds where warn is tight; min_paper_runs=0 disables paper gate.
        thresholds = PromotionThresholds(warn_recovery_incidents=2, min_paper_runs=0)
        policy = PromotionPolicy(thresholds)
        result = policy.evaluate(agg)
        assert result.verdict == PromotionVerdict.HOLD

    def test_inconclusive_coverage_insufficient(self):
        reports = (_make_report(campaign_id="c1"),)
        agg = build_campaign_aggregation(reports)
        policy = PromotionPolicy()
        result = policy.evaluate(agg)
        assert result.verdict == PromotionVerdict.INCONCLUSIVE
        assert any(c.name == "min_completed_campaigns" for c in result.insufficient_reasons)

    def test_too_few_campaigns_inconclusive(self):
        # Only 2 campaigns, need 3
        reports = (
            _make_report(campaign_id="c1"),
            _make_report(campaign_id="c2"),
        )
        agg = build_campaign_aggregation(reports)
        policy = PromotionPolicy()
        result = policy.evaluate(agg)
        assert result.verdict == PromotionVerdict.INCONCLUSIVE

    def test_single_lucky_campaign_cannot_promote(self):
        """One great campaign is not enough — min_completed_campaigns prevents promotion."""
        reports = (
            _make_report(
                campaign_id="lucky",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=500,
                total_fills=100,
            ),
        )
        agg = build_campaign_aggregation(reports)
        policy = PromotionPolicy()
        result = policy.evaluate(agg)
        assert result.verdict != PromotionVerdict.PROMOTE

    def test_mixed_history_correct_aggregation(self):
        """Mix of pass, warn, and inconclusive campaigns."""
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.PASS_WITH_WARNINGS),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.INCONCLUSIVE),
        )
        agg = build_campaign_aggregation(reports)
        assert agg.passed_count == 1
        assert agg.warned_count == 1
        assert agg.inconclusive_count == 1
        assert agg.verdict_consistency == AggregateConsistency.MIXED

    def test_require_stable_consistency(self):
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS),
        )
        agg = build_campaign_aggregation(reports)
        # Phase 16M: min_paper_runs=0 disables paper gate; test focuses on consistency.
        thresholds = PromotionThresholds(
            require_stable_consistency=True,
            max_failed_campaigns=2,  # relax so it doesn't hit hard fail first
            min_paper_runs=0,
        )
        policy = PromotionPolicy(thresholds)
        result = policy.evaluate(agg)
        assert result.verdict == PromotionVerdict.REJECT
        assert any(c.name == "require_stable_consistency" for c in result.fail_reasons)

    def test_ext_regime_insufficient_without_scenario_evidence(self):
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                ext_regime_available=False,
                ext_regime_fresh=False,
                ext_regime_evidence_sufficient=False,
                ext_regime_scenario_available=False,
                ext_regime_scenario_step_count=0,
                ext_regime_activation_reduced_steps=0,
                ext_regime_stale_steps=0,
                ext_regime_high_risk_steps=0,
                ext_regime_safe_steps=0,
                ext_regime_scenario_summary="",
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        result = PromotionPolicy().evaluate(agg)
        assert result.verdict == PromotionVerdict.INCONCLUSIVE
        assert any(c.name == "min_ext_regime_meaningful_campaigns" for c in result.insufficient_reasons)

    def test_stale_dominated_campaigns_trigger_hold(self):
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                ext_regime_scenario_step_count=4,
                ext_regime_stale_steps=3,
                ext_regime_safe_steps=1,
                ext_regime_high_risk_steps=0,
                ext_regime_activation_reduced_steps=0,
                ext_regime_scenario_summary="steps=4; stale=3; safe=1",
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        # Phase 16M: min_paper_runs=0 disables paper gate; test focuses on ext_regime soft warn.
        result = PromotionPolicy(PromotionThresholds(min_paper_runs=0)).evaluate(agg)
        assert result.verdict == PromotionVerdict.HOLD
        assert any(c.name == "warn_ext_regime_stale_dominated_ratio" for c in result.warning_reasons)

    def test_unavailable_dominated_campaigns_trigger_hold(self):
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                ext_regime_fresh=False,
                ext_regime_scenario_step_count=4,
                ext_regime_unavailable_steps=3,
                ext_regime_safe_steps=1,
                ext_regime_high_risk_steps=0,
                ext_regime_activation_reduced_steps=0,
                ext_regime_scenario_summary="steps=4; unavailable=3; safe=1",
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        # Phase 16M: min_paper_runs=0 disables paper gate; test focuses on ext_regime soft warn.
        result = PromotionPolicy(PromotionThresholds(min_paper_runs=0)).evaluate(agg)
        assert result.verdict == PromotionVerdict.HOLD
        assert any(c.name == "warn_ext_regime_unavailable_dominated_ratio" for c in result.warning_reasons)

    def test_high_risk_dominated_campaigns_reject(self):
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                ext_regime_high_risk=True,
                ext_regime_scenario_step_count=4,
                ext_regime_high_risk_steps=3,
                ext_regime_safe_steps=1,
                ext_regime_activation_reduced_steps=0,
                ext_regime_scenario_summary="steps=4; high_risk=3; safe=1",
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports)
        # Phase 16M: min_paper_runs=0 disables paper gate; test focuses on ext_regime hard fail.
        result = PromotionPolicy(PromotionThresholds(min_paper_runs=0)).evaluate(agg)
        assert result.verdict == PromotionVerdict.REJECT
        assert any(c.name == "max_ext_regime_high_risk_dominated_ratio" for c in result.fail_reasons)

    # Phase 16M: focused tests for the paper-run evidence coverage gate.

    def test_non_supportive_paper_evidence_blocks_promote(self):
        """Phase 16M: stale paper runs block PROMOTE even when all other metrics are strong."""
        thresholds = PromotionThresholds(min_paper_runs=3)
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                total_events=1000,
                elapsed_seconds=600.0,
                symbols=("BTC", "ETH", "SOL"),
                completed_at_ns=0,  # stale: paper gate will fail
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports, thresholds=thresholds)
        result = PromotionPolicy(thresholds).evaluate(agg)
        assert result.verdict == PromotionVerdict.INCONCLUSIVE
        assert any(c.name == "paper_run_evidence_supportive" for c in result.insufficient_reasons)

    def test_supportive_paper_evidence_allows_promote(self):
        """Phase 16M: fresh paper runs with valid timestamps allow PROMOTE."""
        thresholds = PromotionThresholds(min_paper_runs=3)
        reports = self._good_reports(3)  # default completed_at_ns is valid positive timestamp
        agg = build_campaign_aggregation(reports, thresholds=thresholds)
        result = PromotionPolicy(thresholds).evaluate(agg)
        assert result.verdict == PromotionVerdict.PROMOTE
        assert any(c.name == "paper_run_evidence_supportive" and c.passed for c in result.criteria)

    def test_min_paper_runs_zero_disables_paper_gate(self):
        """Phase 16M: min_paper_runs=0 disables gate (backward compat opt-out)."""
        thresholds = PromotionThresholds(min_paper_runs=0)
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                total_events=1000,
                elapsed_seconds=600.0,
                symbols=("BTC", "ETH", "SOL"),
                completed_at_ns=0,  # stale — would block if min_paper_runs > 0
            )
            for i in range(3)
        )
        agg = build_campaign_aggregation(reports, thresholds=thresholds)
        result = PromotionPolicy(thresholds).evaluate(agg)
        assert not any(c.name == "paper_run_evidence_supportive" for c in result.criteria)
        assert result.verdict == PromotionVerdict.PROMOTE


# ===========================================================================
# 16. build_promotion_review — full pipeline
# ===========================================================================


class TestBuildPromotionReview:
    def test_full_pipeline(self):
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                elapsed_seconds=600.0,
                symbols=("BTC", "ETH", "SOL"),
            )
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-1",
            readiness_level="paper_live",
            thresholds=PromotionThresholds(min_paper_runs=3),
            reviewed_at_ns=_T0_NS,
        )
        assert review.review_id == "rev-1"
        assert review.reviewed_at_ns == _T0_NS
        assert review.result.verdict == PromotionVerdict.PROMOTE
        assert review.readiness_is_supportive is True
        assert review.campaign_ids == ("c0", "c1", "c2")
        assert review.aggregation.total_campaigns == 3

    def test_stale_only_paper_runs_remain_non_supportive_in_review(self):
        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                elapsed_seconds=600.0,
                completed_at_ns=0,
                symbols=("BTC", "ETH", "SOL"),
            )
            for i in range(2)
        )
        thresholds = PromotionThresholds(
            min_paper_runs=2,
            min_paper_pass_ratio=1.0,
            min_paper_complete_ratio=1.0,
            max_paper_blocked_ratio=0.0,
            max_paper_run_age_ns=-1,
        )

        review = build_promotion_review(
            reports,
            review_id="rev-stale-paper",
            readiness_level="paper_live",
            thresholds=thresholds,
            reviewed_at_ns=_T0_NS,
        )

        assert review.aggregation.total_paper_runs == 2
        assert review.aggregation.fresh_paper_runs == 0
        assert review.aggregation.stale_paper_runs == 2
        assert review.aggregation.latest_paper_run_ns == 0
        assert review.aggregation.paper_run_evidence_supportive is False
        assert review.result.verdict == PromotionVerdict.INCONCLUSIVE

    def test_fresh_paper_run_thresholds_flow_through_review_and_promote(self):
        reports = (
            _make_report(
                campaign_id="c0",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                elapsed_seconds=600.0,
                completed_at_ns=100,
                symbols=("BTC", "ETH", "SOL"),
            ),
            _make_report(
                campaign_id="c1",
                verdict=AcceptanceVerdict.PASS_WITH_WARNINGS,
                total_cycles=200,
                total_fills=30,
                elapsed_seconds=600.0,
                completed_at_ns=120,
                symbols=("BTC", "ETH", "SOL"),
            ),
            _make_report(
                campaign_id="c2",
                verdict=AcceptanceVerdict.PASS,
                total_cycles=200,
                total_fills=30,
                elapsed_seconds=600.0,
                completed_at_ns=140,
                symbols=("BTC", "ETH", "SOL"),
            ),
        )
        thresholds = PromotionThresholds(
            min_paper_runs=3,
            min_paper_pass_ratio=1.0,
            min_paper_complete_ratio=1.0,
            max_paper_blocked_ratio=0.0,
            max_paper_run_age_ns=50,
        )

        review = build_promotion_review(
            reports,
            review_id="rev-fresh-paper",
            readiness_level="paper_live",
            thresholds=thresholds,
            reviewed_at_ns=_T0_NS,
        )

        assert review.aggregation.total_paper_runs == 3
        assert review.aggregation.fresh_paper_runs == 3
        assert review.aggregation.stale_paper_runs == 0
        assert review.aggregation.latest_paper_run_ns == 140
        assert review.aggregation.oldest_paper_run_ns == 100
        assert review.aggregation.paper_run_evidence_supportive is True
        assert review.result.verdict == PromotionVerdict.PROMOTE


# ===========================================================================
# 17-18. PromotionReviewStore — persistence
# ===========================================================================


class TestPromotionReviewStore:
    def test_save_load_roundtrip(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        review_store = PromotionReviewStore(store)

        reports = tuple(
            _make_report(
                campaign_id=f"c{i}",
                total_cycles=200,
                total_fills=30,
                elapsed_seconds=600.0,
                symbols=("BTC", "ETH", "SOL"),
            )
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-persist",
            readiness_level="paper_live",
            reviewed_at_ns=_T0_NS,
        )
        result = review_store.save_review(review)
        assert result.success

        loaded = review_store.load_review()
        assert loaded["review_id"] == "rev-persist"
        assert loaded["verdict"] == review.result.verdict.value
        assert loaded["readiness_level"] == "paper_live"

    def test_malformed_snapshot_fail_closed(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        # Write snapshot with non-dict data (string instead of dict)
        store.save_snapshot("promotion_review", "not-a-dict")
        review_store = PromotionReviewStore(store)
        with pytest.raises(PromotionReviewCorruptError, match="must be a dict"):
            review_store.load_review()

    def test_missing_fields_fail_closed(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        # Save a dict with only review_id — missing reviewed_at_ns and verdict
        store.save_snapshot("promotion_review", {"review_id": "x"})
        review_store = PromotionReviewStore(store)
        with pytest.raises(PromotionReviewCorruptError, match="missing required fields"):
            review_store.load_review()


# ===========================================================================
# 19-21. Reporting API
# ===========================================================================


class TestReportingAPI:
    def _make_agg(self) -> CampaignAggregation:
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS, total_fills=30),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL, total_fills=0),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS, total_fills=30),
        )
        return build_campaign_aggregation(reports)

    def test_verdict_distribution(self):
        agg = self._make_agg()
        dist = verdict_distribution(agg)
        assert dist["total"] == 3
        assert dist["passed"] == 2
        assert dist["failed"] == 1

    def test_execution_sufficiency_summary(self):
        agg = self._make_agg()
        summary = execution_sufficiency_summary(agg)
        assert summary["total_campaigns"] == 3
        assert "markout" in summary["sufficiency_distribution"]
        # Campaign c2 has 0 fills → UNAVAILABLE
        assert summary["sufficiency_distribution"]["markout"].get("unavailable", 0) >= 1

    def test_symbol_participation_summary(self):
        agg = self._make_agg()
        sp = symbol_participation_summary(agg)
        assert len(sp["unique_symbols"]) >= 1
        assert sp["total_campaigns"] == 3

    def test_promotion_reason_summary(self):
        reports = (
            _make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c2", verdict=AcceptanceVerdict.PASS),
            _make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS),
        )
        agg = build_campaign_aggregation(reports)
        policy = PromotionPolicy()
        result = policy.evaluate(agg)
        prs = promotion_reason_summary(result)
        assert prs["verdict"] == result.verdict.value
        assert isinstance(prs["pass_reasons"], list)

    def test_ext_regime_governance_summary(self):
        agg = build_campaign_aggregation(
            (
                _make_report(campaign_id="c1"),
                _make_report(
                    campaign_id="c2",
                    ext_regime_scenario_step_count=4,
                    ext_regime_stale_steps=3,
                    ext_regime_safe_steps=1,
                ),
                _make_report(
                    campaign_id="c3",
                    ext_regime_scenario_step_count=4,
                    ext_regime_high_risk_steps=3,
                    ext_regime_safe_steps=1,
                ),
            )
        )
        summary = ext_regime_governance_summary(agg)
        assert summary["campaigns_with_meaningful_ext_regime_scenario"] == 3
        assert summary["campaigns_ext_regime_stale_dominated"] == 1
        assert summary["campaigns_ext_regime_high_risk_dominated"] == 1


# ===========================================================================
# 22-23. Readiness interaction
# ===========================================================================


class TestReadinessInteraction:
    def test_not_assessed_not_supportive(self):
        reports = tuple(
            _make_report(campaign_id=f"c{i}", total_cycles=200, total_fills=30, symbols=("BTC", "ETH", "SOL"))
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-na",
            readiness_level="not_assessed",
            reviewed_at_ns=_T0_NS,
        )
        assert review.readiness_is_supportive is False

    def test_paper_live_is_supportive(self):
        reports = tuple(
            _make_report(campaign_id=f"c{i}", total_cycles=200, total_fills=30, symbols=("BTC", "ETH", "SOL"))
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-pl",
            readiness_level="paper_live",
            reviewed_at_ns=_T0_NS,
        )
        assert review.readiness_is_supportive is True

    def test_research_only_not_supportive(self):
        reports = tuple(
            _make_report(campaign_id=f"c{i}", total_cycles=200, total_fills=30, symbols=("BTC", "ETH", "SOL"))
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-ro",
            readiness_level="research_only",
            reviewed_at_ns=_T0_NS,
        )
        assert review.readiness_is_supportive is False


# ===========================================================================
# 26. Serialization
# ===========================================================================


class TestSerialization:
    def test_promotion_review_to_dict(self):
        reports = tuple(
            _make_report(campaign_id=f"c{i}", total_cycles=200, total_fills=30, symbols=("BTC", "ETH", "SOL"))
            for i in range(3)
        )
        review = build_promotion_review(
            reports,
            review_id="rev-ser",
            readiness_level="paper_live",
            thresholds=PromotionThresholds(min_paper_runs=3),
            reviewed_at_ns=_T0_NS,
        )
        d = promotion_review_to_dict(review)
        assert d["review_id"] == "rev-ser"
        assert d["verdict"] == "promote"
        assert d["readiness_level"] == "paper_live"
        assert d["readiness_is_supportive"] is True
        assert len(d["campaign_ids"]) == 3
        assert "aggregation" in d
        assert "result" in d
        assert d["aggregation"]["total_campaigns"] == 3
        assert isinstance(d["result"]["criteria"], list)
