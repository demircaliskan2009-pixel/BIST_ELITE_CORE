from __future__ import annotations

from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowController,
    SleeveCandidateWorkflowEntry,
    SleeveCandidateWorkflowStatus,
    sleeve_candidate_workflow_entry_from_dict,
    sleeve_candidate_workflow_entry_to_dict,
)
from crypto_core.service.sleeve_portfolio import (
    CryptoSleeveState,
    CryptoSleeveStatus,
    CryptoSleeveType,
    SleeveCampaignEvidenceResult,
    SleeveCampaignEvidenceStatus,
    SleeveDecisionPackStatus,
    SleevePortfolioSnapshot,
    SleevePromotionCandidateResult,
    SleevePromotionCandidateStatus,
    SleevePromotionSupportResult,
    SleevePromotionSupportStatus,
    SleeveQualificationResult,
    SleeveQualificationStatus,
    SleeveRecommendationResult,
    SleeveRecommendationStatus,
    _build_sleeve_promotion_candidate_result,
    sleeve_promotion_candidate_result_from_dict,
    sleeve_promotion_candidate_result_to_dict,
)
from crypto_core.validation.pipeline import ValidationPipelineResult, ValidationPipelineStageStatus, validate_pipeline
from crypto_core.validation.stage4_comparator import Stage4ComparisonResult


def _passing_stage4() -> Stage4ComparisonResult:
    """Minimal passing Stage4 result for tests that require validation_ready=True."""
    return Stage4ComparisonResult(
        evaluated=True,
        passed=True,
        status="PASS",
        baseline_id="baseline-1",
        paper_id="paper-1",
        edge_id="edge-1",
        session_duration_days=30.0,
        required_duration_days=2.0,
        backtest_sharpe=1.0,
        paper_sharpe=1.2,
        required_min_paper_sharpe=0.6,
        sharpe_retention_ratio=1.2,
        paper_hit_rate=0.60,
        backtest_hit_rate=0.55,
        paper_slippage_bps=4.0,
        backtest_slippage_bps=5.0,
        paper_fill_rate=0.98,
        backtest_fill_rate=0.95,
        rejection_reasons=(),
    )


def _stage_status(stage: str, *, passed: bool = True) -> ValidationPipelineStageStatus:
    return ValidationPipelineStageStatus(
        stage=stage,
        ran=True,
        passed=passed,
        skipped=False,
        rejection_reasons=(),
    )


def _pipeline_result(
    *rejection_reasons: str,
    validation_ready: bool = False,
    pbo_allocation_cap: float | None = None,
) -> ValidationPipelineResult:
    return ValidationPipelineResult(
        validation_ready=validation_ready,
        stage2_status=_stage_status("stage2_walk_forward", passed=validation_ready),
        pbo_status=_stage_status("pbo", passed=validation_ready),
        stage3_status=_stage_status("stage3_stress", passed=validation_ready),
        pbo_allocation_cap=pbo_allocation_cap,
        rejection_reasons=tuple(rejection_reasons),
        missing_stages=() if validation_ready else ("stage2_walk_forward",),
    )


def _sleeve(
    *,
    validation_pipeline_result: ValidationPipelineResult | None = None,
    promotion_missing: tuple[str, ...] = (),
    campaign_missing: tuple[str, ...] = (),
    qualification_missing: tuple[str, ...] = (),
    recommendation_missing: tuple[str, ...] = (),
    promotion_candidate: SleevePromotionCandidateResult | None = None,
    stage4_comparison_result=None,
) -> CryptoSleeveState:
    return CryptoSleeveState(
        sleeve_id="sleeve-microstructure",
        sleeve_type=CryptoSleeveType.MICROSTRUCTURE,
        status=CryptoSleeveStatus.DEFINED,
        qualification=SleeveQualificationResult(
            status=SleeveQualificationStatus.PAPER_QUALIFIED,
            qualified_for_paper_allocation=True,
            missing_evidence=qualification_missing,
        ),
        recommendation=SleeveRecommendationResult(
            status=SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            recommended_active=True,
            currently_eligible=True,
            qualification_status=SleeveQualificationStatus.PAPER_QUALIFIED,
            missing_evidence=recommendation_missing,
        ),
        campaign_evidence=SleeveCampaignEvidenceResult(
            status=SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            campaign_evidence_available=True,
            explicit_link_available=True,
            linked_in_campaign=True,
            supporting_campaign_ids=("campaign-1",),
            missing_evidence=campaign_missing,
        ),
        promotion_support=SleevePromotionSupportResult(
            status=SleevePromotionSupportStatus.SUPPORTIVE,
            can_be_considered_later=True,
            campaign_evidence_status=SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            qualification_status=SleeveQualificationStatus.PAPER_QUALIFIED,
            recommendation_status=SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            missing_evidence=promotion_missing,
        ),
        promotion_candidate=promotion_candidate or SleevePromotionCandidateResult(),
        validation_pipeline_result=validation_pipeline_result,
        stage4_comparison_result=stage4_comparison_result,
    )


def _workflow_entry(*, pbo_allocation_cap: float | None = None) -> SleeveCandidateWorkflowEntry:
    return SleeveCandidateWorkflowEntry(
        sleeve_id="sleeve-microstructure",
        candidate_status=SleevePromotionCandidateStatus.SUPPORTED,
        promotion_support_status=SleevePromotionSupportStatus.SUPPORTIVE,
        decision_pack_status=SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
        candidate_for_future_review=True,
        strongly_supported=True,
        missing_evidence=("stage2:stage2_missing",),
        reason_summary="Ready for review.",
        next_step="Continue paper monitoring.",
        pbo_allocation_cap=pbo_allocation_cap,
    )


def _workflow_snapshot_for(sleeve: CryptoSleeveState):
    controller = SleeveCandidateWorkflowController(
        workflow_id="workflow-17h",
        created_at_ns=1,
        updated_at_ns=1,
        status=SleeveCandidateWorkflowStatus.CREATED,
    )
    controller.start(workflow_id="workflow-17h", started_at_ns=2)
    return controller.inspect(SleevePortfolioSnapshot(as_of_ns=3, sleeves=(sleeve,)))


def test_validation_pipeline_none_preserves_existing_missing_evidence_behavior():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(
            promotion_missing=("support_missing",),
            campaign_missing=("campaign_missing",),
            qualification_missing=("qualification_missing",),
            recommendation_missing=("recommendation_missing",),
        )
    )
    assert result.missing_evidence == (
        "support_missing",
        "campaign_missing",
        "qualification_missing",
        "recommendation_missing",
    )
    assert result.pbo_allocation_cap is None


def test_validation_ready_true_injects_no_validation_reasons_into_missing_evidence():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(
            validation_pipeline_result=_pipeline_result(validation_ready=True, pbo_allocation_cap=0.5),
            promotion_missing=("support_missing",),
            stage4_comparison_result=_passing_stage4(),
        )
    )
    assert result.missing_evidence == ("support_missing",)


def test_missing_stage2_result_injects_stage2_missing_evidence():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(validation_pipeline_result=validate_pipeline(None, None, None))
    )
    assert result.missing_evidence == ("stage2:stage2_missing",)


def test_failed_stage2_injects_stage2_prefixed_reason():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(validation_pipeline_result=_pipeline_result("stage2:window[0]:oos_sharpe_below_ratio"))
    )
    assert result.missing_evidence == ("stage2:window[0]:oos_sharpe_below_ratio",)


def test_pbo_rejected_injects_pbo_prefixed_reason():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(validation_pipeline_result=_pipeline_result("pbo:pbo_rejected"))
    )
    assert result.missing_evidence == ("pbo:pbo_rejected",)


def test_stage3_failed_injects_stage3_prefixed_reason():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(validation_pipeline_result=_pipeline_result("stage3:high_vol:negative_expectancy"))
    )
    assert result.missing_evidence == ("stage3:high_vol:negative_expectancy",)


def test_validation_reasons_preserve_order_after_existing_evidence_blockers():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(
            validation_pipeline_result=_pipeline_result("stage2:stage2_missing", "pbo:pbo_missing"),
            promotion_missing=("support_missing",),
            campaign_missing=("campaign_missing",),
            qualification_missing=("qualification_missing",),
            recommendation_missing=("recommendation_missing",),
        )
    )
    assert result.missing_evidence == (
        "support_missing",
        "campaign_missing",
        "qualification_missing",
        "recommendation_missing",
        "stage2:stage2_missing",
        "pbo:pbo_missing",
    )


def test_duplicate_validation_and_existing_reasons_are_deduped_deterministically():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(
            validation_pipeline_result=_pipeline_result("pbo:pbo_rejected", "stage3:high_vol:negative_expectancy"),
            promotion_missing=("pbo:pbo_rejected",),
            campaign_missing=("campaign_missing", "campaign_missing"),
        )
    )
    assert result.missing_evidence == (
        "pbo:pbo_rejected",
        "campaign_missing",
        "stage3:high_vol:negative_expectancy",
    )


def test_pbo_allocation_cap_propagates_to_sleeve_promotion_candidate_result():
    result = _build_sleeve_promotion_candidate_result(
        _sleeve(validation_pipeline_result=_pipeline_result(validation_ready=True, pbo_allocation_cap=0.5))
    )
    assert result.pbo_allocation_cap == 0.5


def test_pbo_allocation_cap_serializes_and_deserializes_on_candidate_result():
    result = SleevePromotionCandidateResult(pbo_allocation_cap=0.5)
    payload = sleeve_promotion_candidate_result_to_dict(result)
    assert payload["pbo_allocation_cap"] == 0.5
    restored = sleeve_promotion_candidate_result_from_dict(payload)
    assert restored.pbo_allocation_cap == 0.5


def test_pbo_allocation_cap_propagates_to_sleeve_candidate_workflow_entry():
    candidate = SleevePromotionCandidateResult(
        status=SleevePromotionCandidateStatus.SUPPORTED,
        candidate_for_future_review=True,
        strongly_supported=True,
        pbo_allocation_cap=0.5,
    )
    snapshot = _workflow_snapshot_for(_sleeve(promotion_candidate=candidate))
    assert snapshot.sleeves[0].pbo_allocation_cap == 0.5


def test_pbo_allocation_cap_serializes_and_deserializes_on_workflow_entry():
    entry = _workflow_entry(pbo_allocation_cap=0.5)
    payload = sleeve_candidate_workflow_entry_to_dict(entry)
    assert payload["pbo_allocation_cap"] == 0.5
    restored = sleeve_candidate_workflow_entry_from_dict(payload)
    assert restored.pbo_allocation_cap == 0.5


def test_old_candidate_result_payload_without_pbo_allocation_cap_loads_safely():
    payload = sleeve_promotion_candidate_result_to_dict(SleevePromotionCandidateResult(pbo_allocation_cap=0.5))
    payload.pop("pbo_allocation_cap")
    restored = sleeve_promotion_candidate_result_from_dict(payload)
    assert restored.pbo_allocation_cap is None


def test_old_workflow_entry_payload_without_pbo_allocation_cap_loads_safely():
    payload = sleeve_candidate_workflow_entry_to_dict(_workflow_entry(pbo_allocation_cap=0.5))
    payload.pop("pbo_allocation_cap")
    restored = sleeve_candidate_workflow_entry_from_dict(payload)
    assert restored.pbo_allocation_cap is None


def test_deterministic_replay_same_sleeve_input_produces_same_candidate_evidence_and_cap():
    sleeve = _sleeve(
        validation_pipeline_result=_pipeline_result("pbo:pbo_rejected", pbo_allocation_cap=0.5),
        promotion_missing=("support_missing",),
    )
    first = _build_sleeve_promotion_candidate_result(sleeve)
    second = _build_sleeve_promotion_candidate_result(sleeve)
    assert first.missing_evidence == second.missing_evidence
    assert first.pbo_allocation_cap == second.pbo_allocation_cap


def test_no_optimistic_admission_evidence_failed_validation_remains_visible_in_candidate_workflow():
    candidate = _build_sleeve_promotion_candidate_result(
        _sleeve(validation_pipeline_result=_pipeline_result("pbo:pbo_rejected", pbo_allocation_cap=0.5))
    )
    snapshot = _workflow_snapshot_for(_sleeve(promotion_candidate=candidate))
    assert snapshot.sleeves[0].missing_evidence == ("pbo:pbo_rejected",)
    assert snapshot.sleeves[0].pbo_allocation_cap == 0.5
