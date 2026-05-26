from __future__ import annotations

from crypto_core.venue.deribit_approved_paper_promotion_execution import execute_deribit_approved_paper_promotion
from tests.crypto_core.venue.test_phase58b_approved_paper_promotion_execution_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _phase55_readiness,
    _phase57_approval,
)


def test_phase58c_sources_validate_before_paper_promotion_execution() -> None:
    phase57 = _phase57_approval()
    phase55 = _phase55_readiness()

    assert phase57["approval_status"] == "APPROVED"
    assert phase57["approval_decision"] == "APPROVE_PAPER_PROMOTION_REVIEW"
    assert phase57["operator_id"] == "demir_operator"
    assert phase57["promotion_granted"] is False
    assert phase55["ready_for_operator_promotion_review"] is True
    assert phase55["promotion_granted"] is False


def test_phase58c_approved_paper_promotion_execution_accepts_without_running_campaign() -> None:
    result = execute_deribit_approved_paper_promotion(_phase57_approval(), _phase55_readiness())
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["promotion_execution_status"] == "EXECUTED"
    assert artifact["promotion_granted"] is True
    assert artifact["paper_promoted"] is True
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
