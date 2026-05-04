from __future__ import annotations

from crypto_core.service.sleeve_admission_controller import SleeveAdmissionController, SleeveAdmissionVerdict
from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowEntry,
    SleeveCandidateWorkflowSnapshot,
)
from crypto_core.service.sleeve_portfolio import (
    SleeveDecisionPackStatus,
    SleevePromotionCandidateStatus,
    SleevePromotionSupportStatus,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewController,
)


def _candidate_entry(
    *,
    missing_evidence: tuple[str, ...] = (),
    pbo_allocation_cap: float | None = None,
) -> SleeveCandidateWorkflowEntry:
    return SleeveCandidateWorkflowEntry(
        sleeve_id="sleeve-microstructure",
        candidate_status=SleevePromotionCandidateStatus.SUPPORTED,
        promotion_support_status=SleevePromotionSupportStatus.SUPPORTIVE,
        decision_pack_status=SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
        candidate_for_future_review=True,
        strongly_supported=True,
        missing_evidence=missing_evidence,
        blocking_reasons=(),
        reason_summary="Supportive sleeve candidate evidence.",
        next_step="Continue paper monitoring.",
        pbo_allocation_cap=pbo_allocation_cap,
    )


def _workflow_snapshot(entry: SleeveCandidateWorkflowEntry) -> SleeveCandidateWorkflowSnapshot:
    return SleeveCandidateWorkflowSnapshot(
        workflow_id="workflow-17i",
        status="active",
        as_of_ns=1,
        sleeves=(entry,),
    )


def _review_and_admission(entry: SleeveCandidateWorkflowEntry):
    review_controller = SleevePromotionReviewController(_workflow_snapshot(entry))
    review_result = review_controller.build_review_results()[0]
    review_summary = review_controller.build_portfolio_summary((review_result,))
    admission_result = SleeveAdmissionController(review_summary).build_admission_results()[0]
    return review_result, admission_result


def _assert_validation_reason_reaches_admission(reason: str) -> None:
    review_result, admission_result = _review_and_admission(
        _candidate_entry(missing_evidence=(reason,), pbo_allocation_cap=0.5)
    )
    assert reason in review_result.missing_evidence
    assert reason in admission_result.evidence_blockers
    assert admission_result.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert admission_result.verdict != SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert review_result.pbo_allocation_cap == 0.5
    assert admission_result.pbo_allocation_cap == 0.5


def test_validation_missing_evidence_reaches_admission_evidence_blockers():
    _assert_validation_reason_reaches_admission("pbo:pbo_rejected")


def test_stage2_validation_reason_reaches_admission_evidence_blockers():
    _assert_validation_reason_reaches_admission("stage2:stage2_missing")


def test_stage3_validation_reason_reaches_admission_evidence_blockers():
    _assert_validation_reason_reaches_admission("stage3:stress_failed")


def test_pbo_allocation_cap_reaches_review_and_admission_metadata():
    review_result, admission_result = _review_and_admission(_candidate_entry(pbo_allocation_cap=0.5))
    assert review_result.pbo_allocation_cap == 0.5
    assert admission_result.pbo_allocation_cap == 0.5


def test_no_missing_evidence_can_still_admit_active_when_other_inputs_supportive():
    review_result, admission_result = _review_and_admission(_candidate_entry())
    assert review_result.missing_evidence == ()
    assert admission_result.evidence_blockers == ()
    assert admission_result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE


def test_pbo_cap_metadata_does_not_change_verdict():
    _, uncapped_admission = _review_and_admission(_candidate_entry(pbo_allocation_cap=None))
    _, capped_admission = _review_and_admission(_candidate_entry(pbo_allocation_cap=0.5))
    assert capped_admission.verdict == uncapped_admission.verdict
    assert uncapped_admission.pbo_allocation_cap is None
    assert capped_admission.pbo_allocation_cap == 0.5
