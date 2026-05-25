from __future__ import annotations

from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import (
    _artifact,
    _performance_result,
    _phase49_audit,
)


def test_phase50c_helper_accepts_existing_phase49_artifact_only() -> None:
    result = _performance_result()

    assert result.accepted is True
    assert result.reason_code == "deribit_campaign_performance_evaluation:accepted"
    assert result.rejection_reasons == ()
    assert result.artifact_payload["report_only"] is True
    assert result.artifact_payload["campaign_execution_replayed"] is False
    assert result.artifact_payload["session_execution_replayed"] is False
    assert result.artifact_payload["run_execution_replayed"] is False
    assert result.artifact_payload["ledger_mutated"] is False


def test_phase50c_helper_derives_phase50_counts_from_phase49_without_mutation() -> None:
    phase49 = _phase49_audit()
    payload = _performance_result().artifact_payload

    for field in (
        "audit_verdict",
        "campaign_execution_verdict",
        "sessions_requested",
        "sessions_accepted",
        "sessions_rejected",
        "aggregate_trades_requested",
        "aggregate_trades_filled",
        "aggregate_ledger_mutations",
        "duplicate_mutation_blocked",
        "hard_cap",
        "per_session_max_trades",
    ):
        assert payload[field] == phase49[field]


def test_phase50c_artifact_records_expected_performance_metrics() -> None:
    metrics = _artifact()["performance_metrics"]

    assert isinstance(metrics, dict)
    assert metrics["fill_rate"] == 1.0
    assert metrics["reject_rate"] == 0.0
    assert metrics["ledger_mutation_count"] == 6
    assert metrics["session_acceptance_rate"] == 1.0
