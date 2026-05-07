from __future__ import annotations

from dataclasses import replace

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    WatchdogStatus,
)

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20e"
_SLEEVE_ID = "sleeve-20e"


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _Service:
    def status(self) -> ServiceStatus:
        return ServiceStatus(
            service_mode="running",
            runtime_status=None,
            queue=QueueSnapshot(
                current_depth=0,
                max_size=100,
                pressure=QueuePressure.NORMAL,
                total_enqueued=10,
                total_dropped=0,
                total_processed=10,
            ),
            watchdog=WatchdogStatus(
                consumer_alive=True,
                last_event_time_ns=31 * _DAY_NS,
                last_cycle_time_ns=31 * _DAY_NS,
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
            execution_intelligence=ExecutionIntelligenceStatus(
                mode="optional",
                route_binding_enabled=True,
                tca_loop_enabled=True,
                tca_store_available=True,
                replay_dedup_bootstrapped=True,
                degraded=False,
                degraded_reasons=(),
            ),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _pipeline_ready() -> validation.ValidationPipelineResult:
    stage = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=True,
        skipped=False,
        rejection_reasons=(),
    )
    return validation.ValidationPipelineResult(
        validation_ready=True,
        stage2_status=replace(stage, stage="stage2_walk_forward"),
        pbo_status=replace(stage, stage="pbo"),
        stage3_status=replace(stage, stage="stage3_stress"),
        pbo_allocation_cap=None,
        rejection_reasons=(),
        missing_stages=(),
    )


def _baseline() -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-20e",
        edge_id=_EDGE_ID,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary() -> validation.Stage4PaperSummary:
    return validation.Stage4PaperSummary(
        paper_id="paper-20e",
        edge_id=_EDGE_ID,
        started_at_ns=1,
        stopped_at_ns=31 * _DAY_NS + 1,
        paper_sharpe=1.2,
        paper_hit_rate=0.58,
        paper_slippage_bps=4.5,
        paper_fill_rate=0.97,
        paper_trade_count=42,
    )


def _stage4_pass() -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(), _paper_summary())


def _stage5_gate(**overrides: object) -> portfolio.Stage5LiveReadinessGate:
    """Build a Stage5 gate; all fields passing by default."""
    values: dict[str, object] = {
        "edge_id": _EDGE_ID,
        "allocation_tier_pct": 10.0,
        "weeks_at_tier": 0,
        "as_of_ns": 100,
        "stage4_passed": True,
        "operator_approval_recorded": True,
        "live_api_credentials_valid": True,
        "kill_switch_clear": True,
        "risk_governance_clear": True,
    }
    values.update(overrides)
    return portfolio.build_stage5_live_readiness_gate(**values)  # type: ignore[arg-type]


def _sleeve(
    *,
    stage5_gate: portfolio.Stage5LiveReadinessGate | None = None,
) -> portfolio.CryptoSleeveState:
    """Sleeve with RECOMMENDED_ACTIVE recommendation and passing Stage4."""
    return portfolio.CryptoSleeveState(
        sleeve_id=_SLEEVE_ID,
        sleeve_type=portfolio.CryptoSleeveType.MICROSTRUCTURE,
        status=portfolio.CryptoSleeveStatus.DEFINED,
        qualification=portfolio.SleeveQualificationResult(
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            True,
        ),
        recommendation=portfolio.SleeveRecommendationResult(
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            True,
            True,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
        ),
        campaign_evidence=portfolio.SleeveCampaignEvidenceResult(
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            True,
            True,
            True,
            ("campaign-20e",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=_pipeline_ready(),
        stage4_backtest_baseline=_baseline(),
        stage4_comparison_result=_stage4_pass(),
        stage5_entry_gate=stage5_gate,
    )


def _sleeve_eligible(
    *,
    stage5_gate: portfolio.Stage5LiveReadinessGate | None = None,
) -> portfolio.CryptoSleeveState:
    """Sleeve with ELIGIBLE_BUT_NOT_SELECTED recommendation and passing Stage4."""
    return portfolio.CryptoSleeveState(
        sleeve_id=_SLEEVE_ID,
        sleeve_type=portfolio.CryptoSleeveType.MICROSTRUCTURE,
        status=portfolio.CryptoSleeveStatus.DEFINED,
        qualification=portfolio.SleeveQualificationResult(
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            True,
        ),
        recommendation=portfolio.SleeveRecommendationResult(
            portfolio.SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
            False,
            True,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
        ),
        campaign_evidence=portfolio.SleeveCampaignEvidenceResult(
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            True,
            True,
            True,
            ("campaign-20e",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        ),
        validation_pipeline_result=_pipeline_ready(),
        stage4_backtest_baseline=_baseline(),
        stage4_comparison_result=_stage4_pass(),
        stage5_entry_gate=stage5_gate,
    )


def _decision_pack(sleeve: portfolio.CryptoSleeveState) -> portfolio.SleeveDecisionPackResult:
    """Run promotion candidate then decision pack build (mirrors _apply_sleeve_decision_pack)."""
    promotion_candidate = portfolio._build_sleeve_promotion_candidate_result(sleeve)  # type: ignore[attr-defined]
    enriched = replace(sleeve, promotion_candidate=promotion_candidate)
    return portfolio._build_sleeve_decision_pack_result(enriched)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_failed_stage5_demotes_decision_pack_status_to_blocked():
    # RECOMMENDED_ACTIVE sleeve with a failed Stage5 gate must be demoted to BLOCKED.
    gate = _stage5_gate(operator_approval_recorded=False)
    sleeve = _sleeve(stage5_gate=gate)

    result = _decision_pack(sleeve)

    assert result.status == portfolio.SleeveDecisionPackStatus.BLOCKED


def test_failed_stage5_decision_pack_contains_stage5_blocking_reason():
    # Stage5 blocking reason must be present in decision pack blocking_reasons after demotion.
    gate = _stage5_gate(live_api_credentials_valid=False)
    sleeve = _sleeve(stage5_gate=gate)

    result = _decision_pack(sleeve)

    assert any(r.startswith("stage5:") for r in result.blocking_reasons)


def test_failed_stage5_decision_pack_preserves_stage5_metadata():
    # stage5_live_ready and stage5_live_readiness_blockers must reflect gate state.
    gate = _stage5_gate(kill_switch_clear=False)
    sleeve = _sleeve(stage5_gate=gate)

    result = _decision_pack(sleeve)

    assert result.stage5_live_ready is False
    assert len(result.stage5_live_readiness_blockers) > 0


def test_missing_stage5_gate_does_not_demote_decision_pack_status():
    # gate=None must not add blocking reasons → RECOMMENDED_ACTIVE must be preserved.
    sleeve = _sleeve(stage5_gate=None)

    result = _decision_pack(sleeve)

    assert result.status == portfolio.SleeveDecisionPackStatus.RECOMMENDED_ACTIVE


def test_passing_stage5_gate_does_not_demote_decision_pack_status():
    # A fully passing Stage5 gate must not add blocking reasons → status unchanged.
    gate = _stage5_gate()
    sleeve = _sleeve(stage5_gate=gate)

    result = _decision_pack(sleeve)

    assert result.status == portfolio.SleeveDecisionPackStatus.RECOMMENDED_ACTIVE


def test_eligible_with_failed_stage5_gate_not_demoted_to_blocked():
    # Only RECOMMENDED_ACTIVE is subject to demotion.
    # ELIGIBLE_BUT_NOT_SELECTED + Stage5 failure → status must remain ELIGIBLE_BUT_NOT_SELECTED.
    gate = _stage5_gate(operator_approval_recorded=False)
    sleeve = _sleeve_eligible(stage5_gate=gate)

    result = _decision_pack(sleeve)

    assert result.status == portfolio.SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED


def test_demotion_is_deterministic():
    # Same sleeve input must produce the same decision pack status on repeated calls.
    gate = _stage5_gate(risk_governance_clear=False)
    sleeve = _sleeve(stage5_gate=gate)

    result_a = _decision_pack(sleeve)
    result_b = _decision_pack(sleeve)

    assert result_a.status == result_b.status
    assert result_a.blocking_reasons == result_b.blocking_reasons


def test_build_sleeve_with_stage5_gate_edge_id_mismatch_raises():
    # build_sleeve_with_stage5_live_readiness_gate must reject a gate whose edge_id
    # does not match the sleeve's Stage4 evidence edge_id.
    sleeve_with_stage4 = _sleeve(stage5_gate=None)
    gate = _stage5_gate(edge_id="wrong-edge-for-20e")

    with pytest.raises(ValueError, match="stage5 gate edge_id does not match"):
        portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve_with_stage4, gate)


def test_demoted_decision_pack_retains_recommendation_layer_flag():
    # After status demotion, the raw recommendation layer field recommended_active
    # must still be True (it reflects the recommendation, not the computed status).
    gate = _stage5_gate(operator_approval_recorded=False)
    sleeve = _sleeve(stage5_gate=gate)

    result = _decision_pack(sleeve)

    assert result.status == portfolio.SleeveDecisionPackStatus.BLOCKED
    assert result.recommended_active is True


def test_multiple_stage5_blockers_all_present_in_blocking_reasons():
    # When multiple Stage5 fields fail, all resulting blockers must appear in
    # decision pack blocking_reasons and status must be BLOCKED.
    gate = _stage5_gate(
        operator_approval_recorded=False,
        live_api_credentials_valid=False,
        kill_switch_clear=False,
    )
    sleeve = _sleeve(stage5_gate=gate)

    result = _decision_pack(sleeve)

    assert result.status == portfolio.SleeveDecisionPackStatus.BLOCKED
    stage5_in_blocking = [r for r in result.blocking_reasons if r.startswith("stage5:")]
    assert len(stage5_in_blocking) >= 2
