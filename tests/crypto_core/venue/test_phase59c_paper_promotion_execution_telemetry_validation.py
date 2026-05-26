from __future__ import annotations

from crypto_core.venue.deribit_paper_promotion_telemetry_audit import (
    audit_deribit_paper_promotion_execution_telemetry,
)
from tests.crypto_core.venue.test_phase59b_paper_promotion_execution_telemetry_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _phase55_readiness,
    _phase58_execution,
)


def test_phase59c_sources_validate_before_telemetry_audit() -> None:
    phase58 = _phase58_execution()
    phase55 = _phase55_readiness()

    assert phase58["promotion_execution_status"] == "EXECUTED"
    assert phase58["promotion_granted"] is True
    assert phase58["paper_promoted"] is True
    assert phase58["next_blocker"] == "PAPER_PROMOTION_EXECUTION_TELEMETRY_NOT_READY"
    assert phase55["ready_for_operator_promotion_review"] is True


def test_phase59c_telemetry_audit_accepts_without_new_execution() -> None:
    result = audit_deribit_paper_promotion_execution_telemetry(_phase58_execution(), _phase55_readiness())
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["telemetry_audit_status"] == "AUDITED"
    assert artifact["no_new_execution"] is True
    assert artifact["report_only"] is True
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
