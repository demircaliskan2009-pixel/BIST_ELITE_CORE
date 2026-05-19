"""Phase 26N Deribit raw sequence capture proof tests.

Phase 26N was the retry dispatch of the Deribit public smoke workflow.
The retry run (26035089720) also timed out with message_count=0.
This test validates the Phase 26N capture proof JSON is correctly recorded.
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
PROOF_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26N.json"


def _proof_json() -> dict:
    return json.loads(PROOF_PATH.read_text(encoding="utf-8"))


def test_phase26n_proof_json_exists() -> None:
    assert PROOF_PATH.exists(), f"Phase 26N proof JSON not found: {PROOF_PATH}"


def test_phase26n_proof_json_schema() -> None:
    data = _proof_json()
    assert data["schema"] == "deribit_raw_sequence_capture_proof_26n"
    assert data["phase"] == "26N"


def test_phase26n_proof_json_run_id() -> None:
    data = _proof_json()
    assert data["run_id"] == 26035089720


def test_phase26n_proof_json_conclusion_failure() -> None:
    data = _proof_json()
    assert data["run_conclusion"] == "failure"


def test_phase26n_proof_json_message_count_zero() -> None:
    data = _proof_json()
    assert data["message_count"] == 0
    assert data["artifact_payload"]["message_count"] == 0


def test_phase26n_proof_json_rejection_reason_timeout() -> None:
    data = _proof_json()
    assert "deribit_ws:timeout" in data["rejection_reasons"]
    assert "deribit_ws:timeout" in data["artifact_payload"]["rejection_reasons"]


def test_phase26n_proof_json_no_sample_events() -> None:
    data = _proof_json()
    assert data["artifact_payload"]["sample_events"] == []
    assert data["sanitized_sample_events"] == []


def test_phase26n_proof_json_not_accepted_for_classification() -> None:
    data = _proof_json()
    assert data["accepted"] is False
    assert data["artifact_acceptance"]["accepted_for_classification"] is False


def test_phase26n_proof_json_all_claims_wait_insufficient() -> None:
    data = _proof_json()
    effect = data["classification_effect"]
    for claim_id in (
        "prev_change_id",
        "continuity_condition",
        "first_message_snapshot",
        "incremental_delta",
    ):
        assert effect[claim_id] == "WAIT_INSUFFICIENT", (
            f"claim_id={claim_id} expected WAIT_INSUFFICIENT got {effect[claim_id]}"
        )


def test_phase26n_proof_json_computed_counts_all_zero() -> None:
    data = _proof_json()
    counts = data["computed_counts"]
    for key, value in counts.items():
        assert value == 0, f"expected count {key}=0 got {value}"


def test_phase26n_proof_json_safety_invariants() -> None:
    data = _proof_json()
    inv = data["safety_invariants"]
    assert inv["public_market_data_only"] is True
    assert inv["dry_run"] is True
    assert inv["no_private_api"] is True
    assert inv["no_credentials"] is True
    assert inv["no_orders"] is True
    assert inv["no_connector_enablement"] is True
    assert inv["no_worksheet_approval"] is True


def test_phase26n_head_sha_matches_current_main() -> None:
    data = _proof_json()
    # Phase 26N ran on HEAD de838f0e (PR #58 merged)
    assert data["head_sha"] == "de838f0e9e1aa12b6d5ef327bf57bb06881cc309"


def test_phase26n_no_worksheet_edits_and_validator_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is True  # True after Phase 26AW
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 0
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "READY",
        "B4": "READY",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
