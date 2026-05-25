from __future__ import annotations

from tests.crypto_core.venue.test_phase55b_promotion_readiness_artifact import (
    _artifact,
    _phase54_audit,
    _promotion_result,
)


def test_phase55c_phase54_source_exists_and_validates() -> None:
    source = _phase54_audit()

    assert source["schema_version"] == "deribit_approved_paper_performance_execution_telemetry_audit.v1"
    assert source["telemetry_audit_verdict"] == "PASS"
    assert source["execution_verdict"] == "PASS"
    assert source["promotion_granted"] is False
    assert source["ready_for_live"] is False
    assert source["ready_for_shadow"] is False


def test_phase55c_promotion_readiness_validates_but_does_not_promote() -> None:
    result = _promotion_result()
    artifact = _artifact()
    criteria = artifact["criteria_results"]

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["promotion_readiness_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert artifact["ready_for_operator_promotion_review"] is True
    assert artifact["promotion_granted"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
    assert isinstance(criteria, dict)
    assert all(criteria.values())


def test_phase55c_metrics_are_copied_from_phase54_and_consistent() -> None:
    artifact = _artifact()

    assert artifact["telemetry_audit_verdict"] == "PASS"
    assert artifact["execution_verdict"] == "PASS"
    assert artifact["fill_rate"] == 1.0
    assert artifact["rejection_rate"] == 0.0
    assert artifact["session_acceptance_rate"] == 1.0
    assert artifact["ledger_mutation_rate"] == 1.0
