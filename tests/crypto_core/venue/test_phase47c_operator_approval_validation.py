from __future__ import annotations

from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import (
    _approval,
    _approval_rejection_reasons,
    _phase44_report_pack,
    _phase45_evaluation,
    _phase46_proposal,
)


def test_phase47c_phase46_proposal_exists_and_validates() -> None:
    proposal = _phase46_proposal()

    assert proposal["schema_version"] == "deribit_bounded_repeated_paper_campaign_operator_proposal.v1"
    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["promotion_granted"] is False


def test_phase47c_phase45_and_phase44_sources_validate() -> None:
    evaluation = _phase45_evaluation()
    report_pack = _phase44_report_pack()

    assert evaluation["promotion_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert evaluation["promotion_granted"] is False
    assert report_pack["report_pack_verdict"] == "PASS"
    assert report_pack["promotion_granted"] is False
    assert report_pack["session_count"] == 3


def test_phase47c_approval_validates_and_does_not_execute_campaign() -> None:
    approval = _approval()

    assert (
        _approval_rejection_reasons(_phase46_proposal(), _phase45_evaluation(), _phase44_report_pack(), approval) == ()
    )
    assert approval["approval_status"] == "APPROVED"
    assert approval["campaign_execution_status"] == "NOT_EXECUTED"
    assert approval["session_execution_status"] == "NOT_EXECUTED"
    assert approval["run_execution_status"] == "NOT_EXECUTED"
    assert approval["next_blocker"] == "BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_NOT_READY"
