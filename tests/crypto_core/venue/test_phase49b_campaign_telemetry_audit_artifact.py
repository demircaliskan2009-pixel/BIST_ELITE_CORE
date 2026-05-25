from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_campaign_telemetry_audit import run_deribit_campaign_telemetry_audit
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

ARTIFACT = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49B.json")
PHASE48_ARTIFACT = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json")
APPROVAL = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_47B.json")


def _phase48_artifact() -> dict[str, object]:
    return json.loads(PHASE48_ARTIFACT.read_text(encoding="utf-8"))


def _phase47_approval() -> dict[str, object]:
    return json.loads(APPROVAL.read_text(encoding="utf-8"))


def _audit_result():
    return run_deribit_campaign_telemetry_audit(_phase48_artifact(), _phase47_approval())


def _artifact() -> dict[str, object]:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_phase49b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PHASE48_ARTIFACT.exists()
    assert APPROVAL.exists()
    assert artifact["schema_version"] == "deribit_bounded_paper_campaign_telemetry_audit.v1"
    assert artifact["phase"] == "49"
    assert artifact["source"] == "deribit_bounded_paper_campaign_telemetry_audit_v1"
    assert artifact["source_phase48_campaign_execution"] == str(PHASE48_ARTIFACT).replace("\\", "/")
    assert artifact["source_phase47_approval"] == str(APPROVAL).replace("\\", "/")


def test_phase49b_artifact_matches_deterministic_audit_output() -> None:
    result = _audit_result()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase49b_artifact_records_report_only_audit_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    artifact = _artifact()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert artifact["audit_verdict"] == "PASS"
    assert artifact["campaign_execution_verdict"] == "PASS"
    assert artifact["sessions_requested"] == 3
    assert artifact["sessions_attempted"] == 3
    assert artifact["sessions_accepted"] == 3
    assert artifact["sessions_rejected"] == 0
    assert artifact["aggregate_trades_requested"] == 6
    assert artifact["aggregate_trades_filled"] == 6
    assert artifact["aggregate_ledger_mutations"] == 6
    assert artifact["duplicate_mutation_blocked"] is True
    assert artifact["hard_cap"] == 3
    assert artifact["per_session_max_trades"] == 2
    assert artifact["max_campaign_sessions"] == 3
    assert artifact["simulation_only"] is True
    assert artifact["live_ready"] is False
    assert artifact["next_blocker"] == "PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_NOT_READY"
