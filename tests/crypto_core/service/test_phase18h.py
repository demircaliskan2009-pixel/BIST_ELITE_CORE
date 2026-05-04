from __future__ import annotations

from dataclasses import replace

import pytest

import crypto_core.service.sleeve_admission_controller as admission_mod
import crypto_core.service.sleeve_candidate_workflow as workflow_mod
import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.service.sleeve_promotion_review_controller as review_mod
import crypto_core.validation as validation


def _pipeline(*reasons: str, ready: bool = False, cap: float | None = None):
    stage = validation.ValidationPipelineStageStatus("stage", True, ready, False, ())
    return validation.ValidationPipelineResult(
        ready,
        replace(stage, stage="stage2_walk_forward"),
        replace(stage, stage="pbo"),
        replace(stage, stage="stage3_stress"),
        cap,
        tuple(reasons),
        () if ready else ("stage2_walk_forward",),
    )


def _stage4(status: str, *reasons: str, passed: bool = False):
    paper_sharpe = None if "stage4:paper_sharpe_not_computable" in reasons else (1.2 if passed else 0.8)
    return validation.Stage4ComparisonResult(
        status != "INSUFFICIENT_EVIDENCE",
        passed,
        status,
        "baseline-1",
        "paper-1",
        "edge-1",
        31.0,
        30.0,
        2.0,
        paper_sharpe,
        1.0,
        None if paper_sharpe is None else paper_sharpe / 2.0,
        0.55,
        0.60,
        5.0,
        4.0,
        0.95,
        0.98,
        tuple(reasons),
    )


def _outcome(*, validation_result=None, stage4_result=None, required: bool = False):
    base = portfolio.CryptoSleeveState(
        "sleeve-microstructure",
        portfolio.CryptoSleeveType.MICROSTRUCTURE,
        portfolio.CryptoSleeveStatus.DEFINED,
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
            ("campaign-1",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=validation_result,
        stage4_comparison_result=stage4_result,
        stage4_comparison_required=required,
    )
    candidate = portfolio._build_sleeve_promotion_candidate_result(base)
    sleeve = replace(base, promotion_candidate=candidate)
    workflow = workflow_mod.SleeveCandidateWorkflowController(
        workflow_id="workflow-18h",
        created_at_ns=1,
        updated_at_ns=1,
        status=workflow_mod.SleeveCandidateWorkflowStatus.CREATED,
    )
    workflow.start(workflow_id="workflow-18h", started_at_ns=2)
    snapshot = workflow.inspect(portfolio.SleevePortfolioSnapshot(as_of_ns=3, sleeves=(sleeve,)))
    review_controller = review_mod.SleevePromotionReviewController(snapshot)
    review = review_controller.build_review_results()[0]
    admission = admission_mod.SleeveAdmissionController(
        review_controller.build_portfolio_summary((review,))
    ).build_admission_results()[0]
    return candidate, snapshot.sleeves[0], review, admission


@pytest.mark.parametrize(
    ("result", "required", "expected_blockers", "expected_verdict"),
    [
        (None, True, ("stage4:comparison_missing",), admission_mod.SleeveAdmissionVerdict.ADMITTED_UNALLOCATED),
        (None, False, (), admission_mod.SleeveAdmissionVerdict.ADMITTED_ACTIVE),
        (_stage4("PASS", passed=True), True, (), admission_mod.SleeveAdmissionVerdict.ADMITTED_ACTIVE),
    ],
)
def test_stage4_none_required_flag_and_pass_behavior(result, required, expected_blockers, expected_verdict):
    assert validation.stage4_admission_blockers(result, required=required) == expected_blockers
    candidate, entry, review, admission = _outcome(stage4_result=result, required=required)
    assert (
        candidate.missing_evidence,
        entry.missing_evidence,
        review.missing_evidence,
        admission.evidence_blockers,
        admission.verdict,
    ) == (expected_blockers, expected_blockers, expected_blockers, expected_blockers, expected_verdict)


@pytest.mark.parametrize(
    ("result", "expected_blockers"),
    [
        (_stage4("REJECT", "stage4:duration_below_minimum"), ("stage4:duration_below_minimum",)),
        (
            _stage4("INSUFFICIENT_EVIDENCE", "stage4:paper_sharpe_not_computable"),
            ("stage4:paper_sharpe_not_computable",),
        ),
        (_stage4("REJECT"), ("stage4:comparison_failed",)),
    ],
)
def test_stage4_failed_results_flow_and_block_active(result, expected_blockers):
    assert validation.stage4_admission_blockers(result, required=True) == expected_blockers
    _, entry, review, admission = _outcome(stage4_result=result, required=True)
    assert (
        entry.missing_evidence,
        review.missing_evidence,
        admission.evidence_blockers,
        admission.verdict,
    ) == (
        expected_blockers,
        expected_blockers,
        expected_blockers,
        admission_mod.SleeveAdmissionVerdict.ADMITTED_UNALLOCATED,
    )


def test_validation_and_stage4_blockers_preserve_order_and_dedupe():
    ordered, _, _, _ = _outcome(
        validation_result=_pipeline("stage2:stage2_missing"),
        stage4_result=_stage4("REJECT", "stage4:duration_below_minimum"),
        required=True,
    )
    deduped, _, _, _ = _outcome(
        validation_result=_pipeline("stage4:comparison_failed", "stage2:stage2_missing"),
        stage4_result=_stage4("REJECT"),
        required=True,
    )
    assert ordered.missing_evidence == ("stage2:stage2_missing", "stage4:duration_below_minimum")
    assert deduped.missing_evidence == ("stage4:comparison_failed", "stage2:stage2_missing")


def test_stage4_keeps_pbo_allocation_cap_and_is_deterministic():
    kwargs = {
        "validation_result": _pipeline("stage2:stage2_missing", cap=0.25),
        "stage4_result": _stage4("INSUFFICIENT_EVIDENCE", "stage4:paper_sharpe_not_computable"),
        "required": True,
    }
    first, entry, review, admission = _outcome(**kwargs)
    second, _, _, _ = _outcome(**kwargs)
    assert (
        first.pbo_allocation_cap,
        entry.pbo_allocation_cap,
        review.pbo_allocation_cap,
        admission.pbo_allocation_cap,
    ) == (0.25, 0.25, 0.25, 0.25)
    assert first.missing_evidence == second.missing_evidence
    assert first.missing_evidence == ("stage2:stage2_missing", "stage4:paper_sharpe_not_computable")
