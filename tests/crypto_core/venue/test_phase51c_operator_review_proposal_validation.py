from __future__ import annotations

from tests.crypto_core.venue.test_phase51b_operator_review_proposal_artifact import (
    _phase50_evaluation,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase51c_phase50_source_exists_and_validates() -> None:
    source = _phase50_evaluation()

    assert source["schema_version"] == "deribit_bounded_paper_campaign_performance_evaluation.v1"
    assert source["performance_evaluation_verdict"] == "PASS"
    assert source["ready_for_operator_review"] is True
    assert source["promotion_granted"] is False
    assert source["ready_for_live"] is False
    assert source["ready_for_shadow"] is False


def test_phase51c_proposal_validates_but_does_not_approve() -> None:
    proposal = _proposal()

    assert _proposal_rejection_reasons(_phase50_evaluation(), proposal) == ()
    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["next_blocker"] == "OPERATOR_APPROVAL_FOR_PAPER_PERFORMANCE_NOT_READY"
