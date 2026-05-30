from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import _approval as _phase47_approval
from tests.crypto_core.venue.test_phase48c_campaign_execution_contract import _run_phase48_campaign

ARTIFACT = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json")
PROPOSAL = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_46B.json")
APPROVAL = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_47B.json")
REPORT_PACK = Path("docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json")


def _artifact() -> dict[str, object]:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_phase48b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PROPOSAL.exists()
    assert APPROVAL.exists()
    assert REPORT_PACK.exists()
    assert artifact["schema_version"] == "deribit_bounded_repeated_paper_campaign_execution.v1"
    assert artifact["phase"] == "48"
    assert artifact["source"] == "deribit_bounded_paper_campaign_v1"
    assert artifact["source_phase47_approval"] == str(APPROVAL).replace("\\", "/")
    assert artifact["source_phase46_proposal"] == str(PROPOSAL).replace("\\", "/")
    assert artifact["source_phase44_report_pack"] == str(REPORT_PACK).replace("\\", "/")


def test_phase48b_artifact_matches_deterministic_campaign_output() -> None:
    result = _run_phase48_campaign()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase48b_artifact_records_approved_bounded_campaign_execution() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    approval = _phase47_approval()
    artifact = _artifact()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert artifact["approval_status"] == approval["approval_status"] == "APPROVED"
    assert artifact["approval_decision"] == approval["approval_decision"]
    assert artifact["campaign_id"] == "phase48-bounded-paper-campaign"
    assert artifact["operator_id"] == "demir_operator"
    assert artifact["hard_cap"] == 3
    assert artifact["per_session_max_trades"] == 2
    assert artifact["max_campaign_sessions"] == 3
    assert artifact["sessions_requested"] == 3
    assert artifact["sessions_accepted"] == 3
    assert artifact["aggregate_trades_requested"] == 6
    assert artifact["aggregate_trades_filled"] == 6
    assert artifact["aggregate_ledger_mutations"] == 6
    assert artifact["duplicate_mutation_blocked"] is True
    assert artifact["campaign_execution_verdict"] == "PASS"
    assert artifact["live_ready"] is False
    assert artifact["next_blocker"] == "CAMPAIGN_TELEMETRY_AUDIT_NOT_READY"
