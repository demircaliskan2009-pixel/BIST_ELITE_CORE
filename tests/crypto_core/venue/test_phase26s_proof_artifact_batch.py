"""Phase 26S proof artifact batch classification tests.

Phase 26R produced an accepted artifact (run 26038507233, message_count=9).
Phase 26S classifies the artifact: all 9 events return prev_change_id=null
and type=null from channel book.BTC-PERPETUAL.none.10.100ms. All four
remaining open raw-sequence claims remain WAIT_INSUFFICIENT because the
required fields are absent in this channel subscription format.
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
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_26S.md"


def _proof_json() -> dict:
    return json.loads(PROOF_PATH.read_text(encoding="utf-8"))


def test_phase26s_proof_json_and_batch_doc_exist() -> None:
    assert PROOF_PATH.exists(), f"26S proof JSON not found: {PROOF_PATH}"
    assert BATCH_PATH.exists(), f"26S batch doc not found: {BATCH_PATH}"


def test_phase26s_artifact_accepted_for_classification() -> None:
    data = _proof_json()
    assert data["artifact_acceptance"]["accepted_for_classification"] is True


def test_phase26s_all_prev_change_id_null() -> None:
    data = _proof_json()
    for i, evt in enumerate(data["sanitized_sample_events"]):
        assert evt["payload_sample"]["prev_change_id"] is None, (
            f"event[{i}] expected prev_change_id=null but got {evt['payload_sample']['prev_change_id']}"
        )


def test_phase26s_all_type_null() -> None:
    data = _proof_json()
    for i, evt in enumerate(data["sanitized_sample_events"]):
        assert evt["payload_sample"]["type"] is None, (
            f"event[{i}] expected type=null but got {evt['payload_sample']['type']}"
        )


def test_phase26s_computed_counts() -> None:
    data = _proof_json()
    counts = data["computed_counts"]
    assert counts["non_null_prev_change_id_count"] == 0
    assert counts["adjacent_pair_count"] == 8
    assert counts["continuity_match_count"] == 0
    assert counts["snapshot_type_count"] == 0
    assert counts["delta_or_change_type_count"] == 0


def test_phase26s_all_claims_wait_insufficient() -> None:
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


def test_phase26s_change_id_present_in_all_events() -> None:
    data = _proof_json()
    # change_id is already approved; verify it is non-null in all events
    for i, evt in enumerate(data["sanitized_sample_events"]):
        assert isinstance(evt["payload_sample"]["change_id"], int), (
            f"event[{i}] expected change_id to be int but got {evt['payload_sample']['change_id']}"
        )
        assert evt["payload_sample"]["change_id"] > 0, f"event[{i}] expected change_id > 0"


def test_phase26s_safety_invariants() -> None:
    data = _proof_json()
    inv = data["safety_invariants"]
    assert inv["public_market_data_only"] is True
    assert inv["dry_run"] is True
    assert inv["no_private_api"] is True
    assert inv["no_credentials"] is True
    assert inv["no_orders"] is True
    assert inv["no_connector_enablement"] is True
    assert inv["no_worksheet_approval"] is True


def test_phase26s_batch_doc_status() -> None:
    content = BATCH_PATH.read_text(encoding="utf-8")
    assert "ARTIFACT_ACCEPTED_CLAIMS_WAIT_INSUFFICIENT" in content


def test_phase26s_batch_doc_no_new_proof_ready() -> None:
    content = BATCH_PATH.read_text(encoding="utf-8")
    assert "newly_proof_ready_not_approved_count: 0" in content
    assert "operator_proposal_created: NO" in content


def test_phase26s_batch_doc_not_an_approval() -> None:
    content = BATCH_PATH.read_text(encoding="utf-8")
    assert "NOT_an_approval: true" in content
    assert "NOT_worksheet_mutation: true" in content
    assert "NOT_connector_enablement: true" in content


def test_phase26s_no_worksheet_edits_and_validator_unchanged() -> None:
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
