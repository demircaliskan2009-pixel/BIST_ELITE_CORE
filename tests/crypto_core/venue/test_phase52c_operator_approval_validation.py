from __future__ import annotations

from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import (
    _approval,
    _approval_rejection_reasons,
    _phase49_audit,
    _phase50_evaluation,
    _phase51_proposal,
)


def test_phase52c_phase51_proposal_exists_and_validates_before_approval() -> None:
    proposal = _phase51_proposal()

    assert proposal["schema_version"] == "deribit_paper_campaign_performance_operator_review_proposal.v1"
    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["promotion_granted"] is False


def test_phase52c_phase50_and_phase49_sources_validate() -> None:
    evaluation = _phase50_evaluation()
    audit = _phase49_audit()

    assert evaluation["performance_evaluation_verdict"] == "PASS"
    assert evaluation["ready_for_operator_review"] is True
    assert evaluation["promotion_granted"] is False
    assert audit["audit_verdict"] == "PASS"
    assert audit["campaign_execution_verdict"] == "PASS"


def test_phase52c_approval_validates_without_execution_or_promotion() -> None:
    approval = _approval()

    assert _approval_rejection_reasons(_phase51_proposal(), _phase50_evaluation(), _phase49_audit(), approval) == ()
    assert approval["approval_status"] == "APPROVED"
    assert approval["promotion_granted"] is False
    assert approval["campaign_execution"] is False
    assert approval["session_execution"] is False
    assert approval["run_execution"] is False
    assert approval["ledger_mutated"] is False
    assert approval["next_blocker"] == "APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_NOT_READY"
