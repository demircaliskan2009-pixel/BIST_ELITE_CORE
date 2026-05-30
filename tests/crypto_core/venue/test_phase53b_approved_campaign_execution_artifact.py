from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase53c_approved_campaign_execution_contract import _run_phase53

ARTIFACT = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53B.json")
PHASE52_APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_52B.json")
PHASE50_EVALUATION = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json")
PHASE48_EXECUTION = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json")


def _artifact() -> dict[str, object]:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_phase53b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PHASE52_APPROVAL.exists()
    assert PHASE50_EVALUATION.exists()
    assert PHASE48_EXECUTION.exists()
    assert artifact["schema_version"] == "deribit_approved_paper_performance_campaign_execution.v1"
    assert artifact["phase"] == "53"
    assert artifact["source"] == "deribit_approved_paper_performance_campaign_v1"
    assert artifact["source_phase52_approval"] == str(PHASE52_APPROVAL).replace("\\", "/")
    assert artifact["source_phase50_performance_evaluation"] == str(PHASE50_EVALUATION).replace("\\", "/")
    assert artifact["source_phase48_campaign_execution"] == str(PHASE48_EXECUTION).replace("\\", "/")


def test_phase53b_artifact_matches_deterministic_execution_output() -> None:
    result = _run_phase53()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase53b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    artifact = _artifact()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert artifact["connector_ready_dialects_count"] == 1
    assert artifact["campaign_execution_status"] == "EXECUTED"
    assert artifact["execution_verdict"] == "PASS"
    assert artifact["promotion_granted"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
