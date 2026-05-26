from __future__ import annotations

from crypto_core.venue.deribit_paper_promotion_post_audit import (
    audit_deribit_paper_promotion_execution_post_audit,
)
from tests.crypto_core.venue.test_phase60b_paper_promotion_post_audit_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _phase58_execution,
    _phase59_audit,
)


def test_phase60c_sources_validate_before_post_audit() -> None:
    phase59 = _phase59_audit()
    phase58 = _phase58_execution()

    assert phase59["telemetry_audit_verdict"] == "PASS"
    assert phase59["promotion_execution_status"] == "EXECUTED"
    assert phase59["promotion_granted"] is True
    assert phase59["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert phase59["paper_promoted"] is True
    assert phase59["next_blocker"] == "PAPER_PROMOTION_EXECUTION_POST_AUDIT_NOT_READY"
    assert phase58["promotion_execution_status"] == "EXECUTED"
    assert phase58["paper_promoted"] is True


def test_phase60c_post_audit_accepts_without_scope_widening() -> None:
    result = audit_deribit_paper_promotion_execution_post_audit(_phase59_audit(), _phase58_execution())
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["post_audit_status"] == "POST_AUDITED"
    assert artifact["post_audit_verdict"] == "PASS"
    assert artifact["promotion_telemetry_audit_verdict"] == "PASS"
    assert artifact["report_only"] is True
    assert artifact["no_new_execution"] is True
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
