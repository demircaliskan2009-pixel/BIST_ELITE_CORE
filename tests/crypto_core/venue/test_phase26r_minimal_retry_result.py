"""Phase 26R minimal smoke retry result tests.

Phase 26R was the minimal retry of the Deribit public smoke workflow with
reduced parameters: duration_seconds=10, max_messages=10, sample_limit=10.
Run 26038507233 concluded with success and accepted=true, capturing 9 events.
This test validates the Phase 26R result captured in the Phase 26S proof JSON.
No worksheet edits, no connector enablement, no classifier advancement.
"""

from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
PROOF_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json"


def _proof_json() -> dict:
    return json.loads(PROOF_PATH.read_text(encoding="utf-8"))


def test_phase26r_proof_json_exists() -> None:
    assert PROOF_PATH.exists(), f"Phase 26S proof JSON not found: {PROOF_PATH}"


def test_phase26r_proof_json_phase() -> None:
    data = _proof_json()
    assert data["phase"] == "26S"


def test_phase26r_run_id() -> None:
    data = _proof_json()
    assert data["run_id"] == 26038507233


def test_phase26r_run_conclusion_success() -> None:
    data = _proof_json()
    assert data["run_conclusion"] == "success"


def test_phase26r_accepted_true() -> None:
    data = _proof_json()
    assert data["accepted"] is True
    assert data["artifact_payload"]["accepted"] is True


def test_phase26r_rejection_reasons_empty() -> None:
    data = _proof_json()
    assert data["rejection_reasons"] == []
    assert data["artifact_payload"]["rejection_reasons"] == []


def test_phase26r_message_count_nine() -> None:
    data = _proof_json()
    assert data["message_count"] == 9
    assert data["artifact_payload"]["message_count"] == 9


def test_phase26r_sample_events_nine() -> None:
    data = _proof_json()
    assert len(data["artifact_payload"]["sample_events"]) == 9
    assert len(data["sanitized_sample_events"]) == 9


def test_phase26r_duration_seconds_ten() -> None:
    data = _proof_json()
    assert data["duration_seconds"] == 10.0
    assert data["artifact_payload"]["duration_seconds"] == 10.0


def test_phase26r_max_messages_ten() -> None:
    data = _proof_json()
    assert data["max_messages"] == 10
    assert data["artifact_payload"]["max_messages"] == 10


def test_phase26r_artifact_accepted_for_classification() -> None:
    data = _proof_json()
    assert data["artifact_acceptance"]["accepted_for_classification"] is True
    assert data["artifact_acceptance"]["rejection_reasons"] == []


def test_phase26r_head_sha_matches_pr59_merge_commit() -> None:
    data = _proof_json()
    # Phase 26R ran on HEAD after PR #59 merged
    assert data["head_sha"] == "6884356b8fb4cb2e6d5c4d59860d6ed156383c74"


def test_phase26r_no_worksheet_edits_and_validator_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 26
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "BLOCKED",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
