from __future__ import annotations

from tests.crypto_core.venue.test_phase49b_campaign_telemetry_audit_artifact import (
    _audit_result,
    _phase48_artifact,
)


def test_phase49c_helper_accepts_existing_phase48_artifact_only() -> None:
    result = _audit_result()

    assert result.accepted is True
    assert result.reason_code == "deribit_campaign_telemetry_audit:accepted"
    assert result.rejection_reasons == ()
    assert result.artifact_payload["report_only"] is True
    assert result.artifact_payload["campaign_execution_replayed"] is False
    assert result.artifact_payload["session_execution_replayed"] is False
    assert result.artifact_payload["run_execution_replayed"] is False


def test_phase49c_helper_derives_phase49_counts_from_phase48_without_mutation() -> None:
    phase48 = _phase48_artifact()
    payload = _audit_result().artifact_payload

    for field in (
        "campaign_execution_verdict",
        "sessions_requested",
        "sessions_attempted",
        "sessions_accepted",
        "sessions_rejected",
        "aggregate_trades_requested",
        "aggregate_trades_filled",
        "aggregate_ledger_mutations",
        "duplicate_mutation_blocked",
        "hard_cap",
        "per_session_max_trades",
        "max_campaign_sessions",
    ):
        assert payload[field] == phase48[field]
