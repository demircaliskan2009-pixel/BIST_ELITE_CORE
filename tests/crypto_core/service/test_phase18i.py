"""Phase 18I tests — Stage4 required derived from validation_pipeline_result.validation_ready.

Validates:
- validation_ready=True auto-derives stage4_comparison_required=True in the promotion candidate seam.
- The derived required flag propagates through the full review/admission chain.
- validation_pipeline_result=None or validation_ready=False does not impose Stage4.
- Explicit stage4_comparison_required=True override works independently of validation_pipeline_result.
- SleevePortfolioController._resolve_effective_sleeve preserves validation/stage4 fields.
- Deterministic replay: identical input produces identical missing_evidence.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

import crypto_core.service.sleeve_admission_controller as admission_mod
import crypto_core.service.sleeve_candidate_workflow as workflow_mod
import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.service.sleeve_promotion_review_controller as review_mod
import crypto_core.validation as validation
from crypto_core.service.sleeve_portfolio_controller import SleevePortfolioController

# ---------------------------------------------------------------------------
# Helpers shared with test_phase18h.py (duplicated locally for isolation)
# ---------------------------------------------------------------------------


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


def _base_sleeve(
    *,
    validation_result=None,
    stage4_result=None,
    required: bool = False,
) -> portfolio.CryptoSleeveState:
    return portfolio.CryptoSleeveState(
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


def _outcome(*, validation_result=None, stage4_result=None, required: bool = False):
    """Build promotion candidate → workflow → review → admission for the given sleeve config."""
    base = _base_sleeve(
        validation_result=validation_result,
        stage4_result=stage4_result,
        required=required,
    )
    candidate = portfolio._build_sleeve_promotion_candidate_result(base)
    sleeve = replace(base, promotion_candidate=candidate)
    workflow = workflow_mod.SleeveCandidateWorkflowController(
        workflow_id="workflow-18i",
        created_at_ns=1,
        updated_at_ns=1,
        status=workflow_mod.SleeveCandidateWorkflowStatus.CREATED,
    )
    workflow.start(workflow_id="workflow-18i", started_at_ns=2)
    snapshot = workflow.inspect(portfolio.SleevePortfolioSnapshot(as_of_ns=3, sleeves=(sleeve,)))
    review_controller = review_mod.SleevePromotionReviewController(snapshot)
    review = review_controller.build_review_results()[0]
    admission = admission_mod.SleeveAdmissionController(
        review_controller.build_portfolio_summary((review,))
    ).build_admission_results()[0]
    return candidate, snapshot.sleeves[0], review, admission


# ---------------------------------------------------------------------------
# Tests: auto-derivation from validation_ready=True
# ---------------------------------------------------------------------------


def test_validation_ready_true_no_stage4_result_injects_missing_blocker():
    """validation_ready=True with stage4_comparison_result=None → 'stage4:comparison_missing'."""
    candidate, _, _, _ = _outcome(validation_result=_pipeline(ready=True))
    assert "stage4:comparison_missing" in candidate.missing_evidence


def test_validation_ready_true_no_stage4_blocks_admitted_active():
    """validation_ready=True with stage4_comparison_result=None → ADMITTED_UNALLOCATED, not ADMITTED_ACTIVE."""
    _, _, _, admission = _outcome(validation_result=_pipeline(ready=True))
    assert admission.verdict == admission_mod.SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert "stage4:comparison_missing" in admission.evidence_blockers


def test_validation_ready_true_stage4_pass_no_blocker_admitted_active():
    """validation_ready=True with Stage4 PASS → no Stage4 blocker, ADMITTED_ACTIVE when no other blockers."""
    candidate, _, _, admission = _outcome(
        validation_result=_pipeline(ready=True),
        stage4_result=_stage4("PASS", passed=True),
    )
    assert "stage4:comparison_missing" not in candidate.missing_evidence
    assert not any(b.startswith("stage4:") for b in candidate.missing_evidence)
    assert admission.verdict == admission_mod.SleeveAdmissionVerdict.ADMITTED_ACTIVE


def test_validation_ready_true_stage4_reject_propagates_reason():
    """validation_ready=True with Stage4 REJECT → rejection_reasons in admission evidence_blockers."""
    candidate, _, review, admission = _outcome(
        validation_result=_pipeline(ready=True),
        stage4_result=_stage4("REJECT", "stage4:duration_below_minimum"),
    )
    assert "stage4:duration_below_minimum" in candidate.missing_evidence
    assert "stage4:duration_below_minimum" in review.missing_evidence
    assert "stage4:duration_below_minimum" in admission.evidence_blockers
    assert admission.verdict == admission_mod.SleeveAdmissionVerdict.ADMITTED_UNALLOCATED


def test_validation_ready_false_does_not_require_stage4():
    """validation_ready=False with no explicit required flag → no Stage4 blocker."""
    candidate, _, _, admission = _outcome(
        validation_result=_pipeline("stage2:window[0]:oos_sharpe_below_ratio"),
    )
    assert not any(b.startswith("stage4:") for b in candidate.missing_evidence)


def test_validation_pipeline_none_does_not_require_stage4():
    """validation_pipeline_result=None with no explicit required flag → no Stage4 blocker."""
    candidate, _, _, _ = _outcome(validation_result=None)
    assert not any(b.startswith("stage4:") for b in candidate.missing_evidence)


def test_explicit_required_true_without_validation_pipeline_still_requires_stage4():
    """stage4_comparison_required=True with no validation_pipeline_result → 'stage4:comparison_missing'."""
    candidate, _, _, admission = _outcome(validation_result=None, required=True)
    assert "stage4:comparison_missing" in candidate.missing_evidence
    assert admission.verdict == admission_mod.SleeveAdmissionVerdict.ADMITTED_UNALLOCATED


# ---------------------------------------------------------------------------
# Tests: ordering and deduplication
# ---------------------------------------------------------------------------


def test_stage4_blockers_appear_after_validation_pipeline_blockers():
    """Stage4 missing evidence must come after validation pipeline rejection reasons."""
    candidate, _, _, _ = _outcome(
        validation_result=_pipeline("stage2:window[0]:oos_sharpe_below_ratio"),
        stage4_result=_stage4("REJECT", "stage4:duration_below_minimum"),
        required=True,
    )
    me = candidate.missing_evidence
    assert "stage2:window[0]:oos_sharpe_below_ratio" in me
    assert "stage4:duration_below_minimum" in me
    v_idx = me.index("stage2:window[0]:oos_sharpe_below_ratio")
    s_idx = me.index("stage4:duration_below_minimum")
    assert v_idx < s_idx


def test_deterministic_replay_identical_input_identical_missing_evidence():
    """Same sleeve input gives identical missing_evidence across two calls."""
    kwargs = {
        "validation_result": _pipeline(ready=True),
        "stage4_result": _stage4("REJECT", "stage4:duration_below_minimum"),
    }
    first, _, _, _ = _outcome(**kwargs)
    second, _, _, _ = _outcome(**kwargs)
    assert first.missing_evidence == second.missing_evidence


# ---------------------------------------------------------------------------
# Tests: SleevePortfolioController preserves validation/stage4 fields
# ---------------------------------------------------------------------------


def _controller_sleeve(*, validation_result=None, stage4_result=None, required: bool = False):
    """Build a minimal ALLOCATED sleeve for controller round-trip tests."""
    return portfolio.CryptoSleeveState(
        sleeve_id="sleeve-alpha",
        sleeve_type=portfolio.CryptoSleeveType.MICROSTRUCTURE,
        status=portfolio.CryptoSleeveStatus.ALLOCATED,
        target_allocation=0.10,
        active_allocation=0.10,
        validation_pipeline_result=validation_result,
        stage4_comparison_result=stage4_result,
        stage4_comparison_required=required,
    )


def _controller_snapshot(sleeve: portfolio.CryptoSleeveState) -> portfolio.SleevePortfolioSnapshot:
    controller = SleevePortfolioController(defined_sleeves=(sleeve,))
    return controller.current_snapshot(
        as_of_ns=1000,
        readiness_level="paper_live",
        readiness_is_supportive=True,
        escalation_allowed_next_step=None,
        external_regime_execution_blocked=None,
    )


def test_controller_preserves_validation_pipeline_result_through_resolve():
    """_resolve_effective_sleeve must not drop validation_pipeline_result."""
    vp = _pipeline(ready=True)
    sleeve = _controller_sleeve(validation_result=vp)
    snap = _controller_snapshot(sleeve)
    resolved = snap.sleeves[0]
    assert resolved.validation_pipeline_result is vp


def test_controller_preserves_stage4_comparison_result_through_resolve():
    """_resolve_effective_sleeve must not drop stage4_comparison_result."""
    s4 = _stage4("PASS", passed=True)
    sleeve = _controller_sleeve(validation_result=_pipeline(ready=True), stage4_result=s4)
    snap = _controller_snapshot(sleeve)
    resolved = snap.sleeves[0]
    assert resolved.stage4_comparison_result is s4


def test_controller_preserves_stage4_comparison_required_through_resolve():
    """_resolve_effective_sleeve must not drop stage4_comparison_required flag."""
    sleeve = _controller_sleeve(required=True)
    snap = _controller_snapshot(sleeve)
    resolved = snap.sleeves[0]
    assert resolved.stage4_comparison_required is True


def test_controller_validation_ready_true_no_stage4_blocks_active_via_promotion_candidate():
    """End-to-end via controller: validation_ready=True, no Stage4 → promotion candidate has blocker."""
    vp = _pipeline(ready=True)
    sleeve = _controller_sleeve(validation_result=vp)
    snap = _controller_snapshot(sleeve)
    resolved = snap.sleeves[0]
    # The promotion candidate missing_evidence must include the stage4 blocker
    assert "stage4:comparison_missing" in resolved.promotion_candidate.missing_evidence


def test_controller_validation_ready_true_stage4_pass_no_stage4_blocker():
    """End-to-end via controller: validation_ready=True with Stage4 PASS → no Stage4 blocker in candidate."""
    vp = _pipeline(ready=True)
    s4 = _stage4("PASS", passed=True)
    sleeve = _controller_sleeve(validation_result=vp, stage4_result=s4)
    snap = _controller_snapshot(sleeve)
    resolved = snap.sleeves[0]
    assert not any(b.startswith("stage4:") for b in resolved.promotion_candidate.missing_evidence)


@pytest.mark.parametrize(
    ("validation_result", "stage4_result", "required", "expect_stage4_blocker"),
    [
        (_pipeline(ready=True), None, False, True),
        (_pipeline(ready=True), _stage4("PASS", passed=True), False, False),
        (_pipeline(ready=True), _stage4("REJECT", "stage4:duration_below_minimum"), False, True),
        (None, None, False, False),
        (None, None, True, True),
        (_pipeline("stage2:stage2_missing"), None, False, False),
    ],
)
def test_stage4_required_derivation_parametrized(validation_result, stage4_result, required, expect_stage4_blocker):
    """Parametrized coverage of the derivation rule across all key branches."""
    candidate, _, _, _ = _outcome(
        validation_result=validation_result,
        stage4_result=stage4_result,
        required=required,
    )
    has_stage4_blocker = any(b.startswith("stage4:") for b in candidate.missing_evidence)
    assert has_stage4_blocker == expect_stage4_blocker
