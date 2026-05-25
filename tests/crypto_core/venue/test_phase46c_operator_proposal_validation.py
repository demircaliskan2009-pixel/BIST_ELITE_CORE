from __future__ import annotations

from tests.crypto_core.venue.test_phase46b_operator_proposal_artifact import (
    _phase44_report_pack,
    _phase45_evaluation,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase46c_phase45_evaluation_exists_and_validates() -> None:
    evaluation = _phase45_evaluation()

    assert evaluation["schema_version"] == "deribit_paper_session_promotion_evaluation.v1"
    assert evaluation["promotion_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert evaluation["promotion_granted"] is False
    assert evaluation["operator_approval_required"] is True


def test_phase46c_phase44_report_pack_exists_and_validates() -> None:
    report_pack = _phase44_report_pack()

    assert report_pack["schema_version"] == "deribit_repeated_hard_capped_session_report_pack.v1"
    assert report_pack["report_pack_verdict"] == "PASS"
    assert report_pack["promotion_granted"] is False
    assert report_pack["hard_cap"] == 3
    assert report_pack["per_session_max_trades"] == 2


def test_phase46c_proposal_validates_but_does_not_approve() -> None:
    proposal = _proposal()

    assert _proposal_rejection_reasons(_phase45_evaluation(), _phase44_report_pack(), proposal) == ()
    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["next_blocker"] == "OPERATOR_APPROVAL_METADATA_REQUIRED"
