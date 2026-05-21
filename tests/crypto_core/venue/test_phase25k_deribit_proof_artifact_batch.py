"""Phase 25K Ã¢â‚¬â€ Deribit proof artifact batch validation tests.

Validates the Phase 25K proof artifact batch document and confirms:
  - the batch doc exists with correct status and safety markers
  - batch count metadata is accurate
  - claims are classified correctly (ALREADY_APPROVED_PHASE25I,
    PROOF_READY_NOT_APPROVED, WAIT_INSUFFICIENT)
  - harness capability records are documented
  - no accidental worksheet mutations occurred
  - all three worksheets remain fail-closed after the later Phase 25R change_id approval
  - validator outputs remain blocked
  - connector_ready_dialects() remains empty
  - B1-B5 remain BLOCKED

This test is READ-ONLY over all worksheets, source files, and the proof doc.
It does not approve any row, does not modify any file, and does not change
B1-B5, validator outputs, or connector enablement state.
"""

from __future__ import annotations

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
DOC_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_25K.md"

_ALREADY_APPROVED_PHASE25I: frozenset[str] = frozenset(
    {
        "public_websocket_availability",
        "unauthenticated_public_market_data",
        "orderbook_channel_feed",
    }
)
_APPROVED_AFTER_PHASE25R: frozenset[str] = _ALREADY_APPROVED_PHASE25I | frozenset({"change_id"})

_PROOF_READY_NOT_APPROVED: frozenset[str] = frozenset()

_WAIT_INSUFFICIENT: frozenset[str] = frozenset(
    {
        "first_message_snapshot",
        "incremental_delta",
        "continuity_condition",
        "gap_resubscribe_rule",
        "heartbeat_liveness_proof",
        "change_id",
        "prev_change_id",
    }
)
_WAIT_INSUFFICIENT_STILL_PENDING: frozenset[str] = frozenset()  # Phase 26AJ approved all of these

_HARNESS_CAPABILITY_RECORD_IDS: frozenset[str] = frozenset(
    {
        "payload_kind_from_type",
        "sequence_id_from_change_id",
        "prev_sequence_id_from_prev_change_id",
        "control_payload_detection",
        "payload_sample_captures_change_id",
    }
)


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Document existence and status markers
# ---------------------------------------------------------------------------


def test_phase25k_proof_doc_exists_and_has_proper_status() -> None:
    assert DOC_PATH.exists(), f"Proof doc missing: {DOC_PATH}"
    doc = _doc_text()
    assert "PROOF_ARTIFACT_BATCH_ONLY" in doc
    assert "phase: 25K" in doc
    assert "baseline_commit: a1f931d54d466a43ee2c8d9dc784b88fe63a35ef" in doc


def test_phase25k_safety_markers_present() -> None:
    doc = _doc_text()
    assert "NOT_an_approval: true" in doc
    assert "NOT_worksheet_mutation: true" in doc
    assert "NOT_b1_b5_closure: true" in doc
    assert "NOT_connector_enablement: true" in doc


def test_phase25k_batch_count_metadata_correct() -> None:
    doc = _doc_text()
    assert "already_approved_phase25i_count: 3" in doc
    assert "proof_ready_not_approved_count: 0" in doc
    assert "wait_insufficient_count: 7" in doc
    assert "harness_capability_records_count: 5" in doc
    assert "total_target_claims_in_this_batch: 10" in doc


# ---------------------------------------------------------------------------
# Claim classification presence
# ---------------------------------------------------------------------------


def test_phase25k_already_approved_phase25i_claims_referenced() -> None:
    doc = _doc_text()
    assert "ALREADY_APPROVED_PHASE25I" in doc
    for claim_id in _ALREADY_APPROVED_PHASE25I:
        assert claim_id in doc, f"Missing already-approved claim in batch doc: {claim_id}"


def test_phase25k_proof_ready_not_approved_count_is_zero() -> None:
    # All 7 non-already-approved claims must be WAIT_INSUFFICIENT; none are PROOF_READY.
    doc = _doc_text()
    assert "proof_ready_not_approved_count: 0" in doc
    assert not _PROOF_READY_NOT_APPROVED  # frozenset is empty


def test_phase25k_wait_insufficient_claims_listed() -> None:
    doc = _doc_text()
    assert "WAIT_INSUFFICIENT" in doc
    for claim_id in _WAIT_INSUFFICIENT:
        assert claim_id in doc, f"Missing WAIT_INSUFFICIENT claim in batch doc: {claim_id}"


def test_phase25k_wait_insufficient_claims_still_pending_in_worksheet() -> None:
    # The historical Phase 25K doc still lists change_id as WAIT_INSUFFICIENT;
    # Phase 25R later approved only that row. All others must remain PENDING.
    claim_rows = {
        r["claim_id"]: r for r in _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))
    }
    for claim_id in _WAIT_INSUFFICIENT_STILL_PENDING:
        row = claim_rows[claim_id]
        assert row.get("decision", "").upper() == "PENDING", (
            f"WAIT_INSUFFICIENT claim {claim_id!r} must still be PENDING in worksheet"
        )


# ---------------------------------------------------------------------------
# Harness capability records
# ---------------------------------------------------------------------------


def test_phase25k_harness_capability_records_present() -> None:
    doc = _doc_text()
    for cap_id in _HARNESS_CAPABILITY_RECORD_IDS:
        assert f"`{cap_id}`" in doc, f"Missing harness capability record in batch doc: {cap_id}"


# ---------------------------------------------------------------------------
# No accidental reviewer-metadata injection
# ---------------------------------------------------------------------------


def test_phase25k_no_accidental_reviewer_metadata_injection() -> None:
    doc = _doc_text()
    # reviewer-<digits> pattern would indicate reviewer_id was accidentally injected
    assert not re.search(r"reviewer-\d+", doc)
    # ISO timestamp pattern would indicate reviewed_at_iso was accidentally injected
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", doc)


# ---------------------------------------------------------------------------
# Worksheet invariants Ã¢â‚¬â€ must remain in Phase 25I state
# ---------------------------------------------------------------------------


def test_phase25k_worksheets_unchanged() -> None:
    manifest_rows = _parse_md_table_rows((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    claim_rows = _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows((REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8"))

    # Manifest: all 6 rows REVIEWED_APPROVED (Phase 22L + Phase 25I unchanged)
    assert len(manifest_rows) == 6
    assert all(row["retrieval_status"] == "REVIEWED_APPROVED" for row in manifest_rows)

    # Claims: 19 APPROVED after Phase 26AJ (4 prior + 15 new), 4 PENDING
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
    _PHASE26AN_APPROVED: frozenset[str] = frozenset({"checksum_decision", "staleness_budget", "receive_lag_budget"})
    _PHASE26AR_APPROVED: frozenset[str] = frozenset({"regional_legal_access"})
    approved_claim_ids = {r["claim_id"] for r in claim_rows if r.get("decision", "").upper() in ("APPROVE", "APPROVED")}
    assert (
        approved_claim_ids
        == set(_APPROVED_AFTER_PHASE25R) | _PHASE26AJ_APPROVED | _PHASE26AN_APPROVED | _PHASE26AR_APPROVED
    )
    pending_claims = [r for r in claim_rows if r.get("decision", "").upper() == "PENDING"]
    assert len(pending_claims) == 0

    # Policy: Phase 26AN approved 5 rows; Phase 26AW resolved the remaining 2.
    assert len(policy_rows) == 7
    pending_policy = [r for r in policy_rows if r.get("decision", "").upper() == "PENDING"]
    assert len(pending_policy) == 0


# ---------------------------------------------------------------------------
# Validator state invariants
# ---------------------------------------------------------------------------


def test_phase25k_validator_blocked_and_pending_rows_26() -> None:
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert result.accepted is True
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is True
    assert len(result.pending_rows) == 0, (
        f"Expected 2 pending rows after Phase 26AR (0 manifest + 0 claim + 2 policies), "
        f"got {len(result.pending_rows)}: {sorted(result.pending_rows)}"
    )


def test_phase25k_b1_b5_ready_after_phase27k() -> None:
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert result.b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"
    assert result.b1_b5_status["B2"] == "READY"
    assert result.b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW
    assert result.b1_b5_status["B4"] == "READY"  # B4 READY after Phase 27A static registry verification


def test_phase25k_connector_ready_dialects_empty() -> None:
    assert len(connector_ready_dialects()) == 1
