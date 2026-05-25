from __future__ import annotations

from tests.crypto_core.venue.test_phase54b_approved_execution_telemetry_artifact import (
    _artifact,
    _phase52_approval,
    _phase53_execution,
    _telemetry_result,
)


def test_phase54c_phase53_source_exists_and_validates() -> None:
    source = _phase53_execution()

    assert source["schema_version"] == "deribit_approved_paper_performance_campaign_execution.v1"
    assert source["campaign_execution_status"] == "EXECUTED"
    assert source["execution_mode"] == "OFFLINE_DETERMINISTIC_PAPER_ONLY"
    assert source["execution_verdict"] == "PASS"
    assert source["sessions_requested"] == source["sessions_attempted"] == source["sessions_accepted"] == 3
    assert source["sessions_rejected"] == 0
    assert source["aggregate_ledger_mutations"] == source["aggregate_trades_filled"] == 6


def test_phase54c_phase52_source_exists_and_validates() -> None:
    source = _phase52_approval()

    assert source["schema_version"] == "deribit_paper_campaign_performance_operator_approval.v1"
    assert source["approval_status"] == "APPROVED"
    assert source["approval_decision"] == "APPROVE_PAPER_CAMPAIGN_PERFORMANCE"
    assert source["operator_id"] == "demir_operator"
    assert source["promotion_granted"] is False


def test_phase54c_telemetry_audit_validates_metrics_without_reexecution() -> None:
    result = _telemetry_result()
    artifact = _artifact()
    metrics = artifact["execution_metrics"]

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["telemetry_audit_verdict"] == "PASS"
    assert artifact["report_only"] is True
    assert artifact["campaign_execution_replayed"] is False
    assert artifact["session_execution_replayed"] is False
    assert artifact["run_execution_replayed"] is False
    assert artifact["ledger_mutated"] is False
    assert isinstance(metrics, dict)
    assert metrics["fill_rate"] == 1.0
    assert metrics["rejection_rate"] == 0.0
    assert metrics["ledger_mutation_rate"] == 1.0
    assert metrics["session_acceptance_rate"] == 1.0
    assert metrics["avg_fills_per_session"] == 2.0
