from __future__ import annotations

from tests.crypto_core.venue.test_phase45b_paper_session_promotion_evaluation_artifact import (
    _evaluation,
    _evaluation_rejection_reasons,
    _promotion_readiness,
    _report_pack,
)


def test_phase45c_phase43_artifact_exists_and_validates() -> None:
    promotion = _promotion_readiness()

    assert promotion["schema_version"] == "deribit_paper_session_promotion_readiness.v1"
    assert promotion["promotion_verdict"] == "NOT_READY"
    assert promotion["required_future_sessions_minimum"] == 3


def test_phase45c_phase44_report_pack_exists_and_validates() -> None:
    pack = _report_pack()

    assert pack["schema_version"] == "deribit_repeated_hard_capped_session_report_pack.v1"
    assert pack["report_pack_verdict"] == "PASS"
    assert pack["session_count"] == 3
    assert pack["promotion_granted"] is False


def test_phase45c_operator_review_ready_does_not_grant_promotion() -> None:
    evaluation = _evaluation()

    assert _evaluation_rejection_reasons(_promotion_readiness(), _report_pack(), evaluation) == ()
    assert evaluation["ready_for_operator_review"] is True
    assert evaluation["promotion_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert evaluation["promotion_granted"] is False
    assert evaluation["operator_approval_required"] is True
