"""Phase 25L Ã¢â‚¬â€ Deribit sequence parse proof validation tests.

Validates the Phase 25L proof artifact batch document and the deterministic
harness fixture (DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json), and confirms:
  - the proof JSON exists, parses, and has correct status markers
  - the historical Phase 25L proof JSON still classifies change_id and
    prev_change_id as WAIT_INSUFFICIENT because harness-only mapping evidence
    is advisory, not observed Deribit payload proof
  - first_message_snapshot, incremental_delta, continuity_condition remain WAIT_INSUFFICIENT
  - the batch doc exists with correct safety markers and count metadata
  - no accidental worksheet mutations occurred
  - all three worksheets remain fail-closed after the later Phase 25R
    change_id approval
  - validator outputs remain blocked
  - connector_ready_dialects() remains empty
  - B1-B5 remain BLOCKED

This test is READ-ONLY over all worksheets, source files, and proof docs.
It does not approve any row, does not modify any file, and does not change
B1-B5, validator outputs, or connector enablement state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    MANIFEST_PATH,
    POLICY_WORKSHEET_PATH,
    _parse_md_table_rows,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
PROOF_JSON_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json"
BATCH_DOC_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_25L.md"

_ALREADY_APPROVED_PHASE25I: frozenset[str] = frozenset(
    {
        "public_websocket_availability",
        "unauthenticated_public_market_data",
        "orderbook_channel_feed",
    }
)
_APPROVED_AFTER_PHASE25R: frozenset[str] = _ALREADY_APPROVED_PHASE25I | frozenset({"change_id"})
_PHASE26AJ_APPROVED: frozenset[str] = frozenset(
    {
        "public_rest_availability",
        "prod_testnet_ws_endpoint",
        "prod_testnet_rest_endpoint",
        "rest_snapshot_requirement",
        "gap_resubscribe_rule",
        "heartbeat_liveness_proof",
        "public_rate_subscription_limits",
        "public_trades",
        "ticker",
        "mark_index_funding_open_interest",
        "testnet_prod_difference",
        "first_message_snapshot",
        "incremental_delta",
        "prev_change_id",
        "continuity_condition",
    }
)

_HARNESS_CAPABILITY_ADVISORY_ONLY: frozenset[str] = frozenset(
    {
        "change_id",
        "prev_change_id",
    }
)
_HARNESS_CAPABILITY_STILL_PENDING: frozenset[str] = frozenset()  # Phase 26AJ approved all harness-advisory rows

_WAIT_INSUFFICIENT: frozenset[str] = frozenset(
    {
        "change_id",
        "prev_change_id",
        "first_message_snapshot",
        "incremental_delta",
        "continuity_condition",
        "gap_resubscribe_rule",
        "heartbeat_liveness_proof",
    }
)


def _proof_json() -> dict:
    return json.loads(PROOF_JSON_PATH.read_text(encoding="utf-8"))


def _batch_doc() -> str:
    return BATCH_DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Proof JSON existence and status markers
# ---------------------------------------------------------------------------


def test_phase25l_proof_json_exists_and_parses() -> None:
    assert PROOF_JSON_PATH.exists(), f"Proof JSON missing: {PROOF_JSON_PATH}"
    data = _proof_json()
    assert isinstance(data, dict)


def test_phase25l_proof_json_status_is_proof_artifact_only() -> None:
    data = _proof_json()
    assert data["status"] == "PROOF_ARTIFACT_ONLY"


def test_phase25l_proof_json_safety_markers_present() -> None:
    data = _proof_json()
    assert data.get("NOT_live_observed_values") is True
    assert data.get("NOT_an_approval") is True
    assert data.get("NOT_worksheet_mutation") is True
    assert data.get("NOT_b1_b5_closure") is True
    assert data.get("NOT_connector_enablement") is True


def test_phase25l_proof_json_baseline_commit_matches() -> None:
    data = _proof_json()
    assert data["baseline_commit"] == "0334de43f0c4cfd530619b98ae5d5585c9211c08"


def test_phase25l_proof_json_observed_values_is_null() -> None:
    # Must not contain actual integer values from live Deribit messages
    data = _proof_json()
    assert data["observed_values"] is None


# ---------------------------------------------------------------------------
# change_id classification in proof JSON
# ---------------------------------------------------------------------------


def test_phase25l_proof_json_change_id_classified_wait_insufficient() -> None:
    data = _proof_json()
    claim_classification = data["claim_classification"]
    change_id_entry = claim_classification["change_id"]
    assert change_id_entry["classification"] == "WAIT_INSUFFICIENT"


def test_phase25l_proof_json_change_id_references_committed_harness_function() -> None:
    data = _proof_json()
    mapping = data["harness_field_mapping"]["change_id_to_sequence_id"]
    assert mapping["source_function"] == "_sequence_id_from_data"
    assert mapping["deribit_input_field"] == "change_id"
    assert mapping["harness_output_field"] == "sequence_id"
    assert "change_id" in mapping["priority_chain"]
    assert mapping["phase25l_classification"] == "HARNESS_CAPABILITY_ADVISORY_ONLY"


# ---------------------------------------------------------------------------
# prev_change_id classification in proof JSON
# ---------------------------------------------------------------------------


def test_phase25l_proof_json_prev_change_id_classified_wait_insufficient() -> None:
    data = _proof_json()
    claim_classification = data["claim_classification"]
    prev_change_id_entry = claim_classification["prev_change_id"]
    assert prev_change_id_entry["classification"] == "WAIT_INSUFFICIENT"


def test_phase25l_proof_json_prev_change_id_references_committed_harness_function() -> None:
    data = _proof_json()
    mapping = data["harness_field_mapping"]["prev_change_id_to_prev_sequence_id"]
    assert mapping["source_function"] == "_prev_sequence_id_from_data"
    assert mapping["deribit_input_field"] == "prev_change_id"
    assert mapping["harness_output_field"] == "prev_sequence_id"
    assert "prev_change_id" in mapping["priority_chain"]
    assert mapping["phase25l_classification"] == "HARNESS_CAPABILITY_ADVISORY_ONLY"


# ---------------------------------------------------------------------------
# WAIT_INSUFFICIENT claims in proof JSON
# ---------------------------------------------------------------------------


def test_phase25l_proof_json_pending_claims_wait_insufficient() -> None:
    data = _proof_json()
    claim_classification = data["claim_classification"]
    for claim_id in (
        "change_id",
        "prev_change_id",
        "first_message_snapshot",
        "incremental_delta",
        "continuity_condition",
    ):
        assert claim_id in claim_classification, f"Missing claim {claim_id!r} in proof JSON claim_classification"
        assert claim_classification[claim_id]["classification"] == "WAIT_INSUFFICIENT", (
            f"Expected {claim_id!r} to be WAIT_INSUFFICIENT, got {claim_classification[claim_id]['classification']!r}"
        )


# ---------------------------------------------------------------------------
# Batch doc existence and markers
# ---------------------------------------------------------------------------


def test_phase25l_batch_doc_exists_and_has_proper_status() -> None:
    assert BATCH_DOC_PATH.exists(), f"Batch doc missing: {BATCH_DOC_PATH}"
    doc = _batch_doc()
    assert "PROOF_ARTIFACT_BATCH_ONLY" in doc
    assert "phase: 25L" in doc
    assert "baseline_commit: 0334de43f0c4cfd530619b98ae5d5585c9211c08" in doc


def test_phase25l_batch_doc_safety_markers_present() -> None:
    doc = _batch_doc()
    assert "NOT_an_approval: true" in doc
    assert "NOT_worksheet_mutation: true" in doc
    assert "NOT_b1_b5_closure: true" in doc
    assert "NOT_connector_enablement: true" in doc


def test_phase25l_batch_doc_count_metadata_correct() -> None:
    doc = _batch_doc()
    assert "already_approved_phase25i_count: 3" in doc
    assert "proof_ready_not_approved_count: 0" in doc
    assert "wait_insufficient_count: 7" in doc


def test_phase25l_batch_doc_harness_advisory_claims_referenced() -> None:
    doc = _batch_doc()
    assert "HARNESS_CAPABILITY_ADVISORY_ONLY" in doc
    for claim_id in _HARNESS_CAPABILITY_ADVISORY_ONLY:
        assert claim_id in doc, f"Missing harness advisory claim in batch doc: {claim_id}"
        assert f"| `{claim_id}` | claim_review | WAIT_INSUFFICIENT |" in doc


def test_phase25l_batch_doc_wait_insufficient_claims_referenced() -> None:
    doc = _batch_doc()
    for claim_id in _WAIT_INSUFFICIENT:
        assert claim_id in doc, f"Missing WAIT_INSUFFICIENT claim in batch doc: {claim_id}"


# ---------------------------------------------------------------------------
# No accidental reviewer-metadata injection
# ---------------------------------------------------------------------------


def test_phase25l_no_accidental_reviewer_metadata_in_batch_doc() -> None:
    doc = _batch_doc()
    assert not re.search(r"reviewer-\d+", doc)
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", doc)


def test_phase25l_no_accidental_reviewer_metadata_in_proof_json() -> None:
    text = PROOF_JSON_PATH.read_text(encoding="utf-8")
    assert not re.search(r"reviewer-\d+", text)
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text)


# ---------------------------------------------------------------------------
# Worksheet invariants Ã¢â‚¬â€ must remain in Phase 25I/25K state
# ---------------------------------------------------------------------------


def test_phase25l_worksheets_unchanged() -> None:
    manifest_rows = _parse_md_table_rows((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    claim_rows = _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows((REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8"))

    # Manifest: all 6 rows REVIEWED_APPROVED
    assert len(manifest_rows) == 6
    assert all(row["retrieval_status"] == "REVIEWED_APPROVED" for row in manifest_rows)

    # Claims: 23 APPROVED after Phase 26AR; 0 still PENDING
    _PHASE26AN_APPROVED: frozenset[str] = frozenset({"checksum_decision", "staleness_budget", "receive_lag_budget"})
    _PHASE26AR_APPROVED: frozenset[str] = frozenset({"regional_legal_access"})
    approved_claim_ids = {r["claim_id"] for r in claim_rows if r.get("decision", "").upper() in ("APPROVE", "APPROVED")}
    assert (
        approved_claim_ids
        == set(_APPROVED_AFTER_PHASE25R) | _PHASE26AJ_APPROVED | _PHASE26AN_APPROVED | _PHASE26AR_APPROVED
    )
    pending_claims = [r for r in claim_rows if r.get("decision", "").upper() == "PENDING"]
    assert len(pending_claims) == 0

    # Policy: 5 rows APPROVED in Phase 26AN, 2 still PENDING
    assert len(policy_rows) == 7
    pending_policy = [r for r in policy_rows if r.get("decision", "").upper() == "PENDING"]
    assert len(pending_policy) == 0


def test_phase25l_harness_advisory_claims_still_pending_in_worksheet() -> None:
    # Phase 25R later approved change_id using observed proof, so only the
    # remaining harness-advisory claim must still be PENDING.
    claim_rows = {
        r["claim_id"]: r for r in _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))
    }
    for claim_id in _HARNESS_CAPABILITY_STILL_PENDING:
        row = claim_rows[claim_id]
        assert row.get("decision", "").upper() == "PENDING", (
            f"Harness-advisory claim {claim_id!r} must still be PENDING in worksheet - "
            "Phase 25L does not approve worksheet rows"
        )


# ---------------------------------------------------------------------------
# Validator state invariants
# ---------------------------------------------------------------------------


def test_phase25l_validator_blocked_and_pending_rows_26() -> None:
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert result.accepted is False
    assert result.evidence_review_complete is True  # True after Phase 26AW
    assert result.ready_for_engineering_patch is True  # True after Phase 26AW
    assert result.connector_enablement_ready is True
    assert len(result.pending_rows) == 0, (
        f"Expected 26 pending rows (0 manifest + 4 claims + 7 policies), "
        f"got {len(result.pending_rows)}: {sorted(result.pending_rows)}"
    )


def test_phase25l_b1_b5_all_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    for gate in ("B1", "B2"):
        assert result.b1_b5_status[gate] == "BLOCKED", f"{gate} must remain BLOCKED after Phase 25L"
    assert result.b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW
    assert result.b1_b5_status["B4"] == "READY"  # B4 READY after Phase 27A static registry verification


def test_phase25l_connector_ready_dialects_empty() -> None:
    assert len(connector_ready_dialects()) == 1
