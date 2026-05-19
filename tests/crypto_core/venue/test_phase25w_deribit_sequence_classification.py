"""Phase 25W Deribit proof-gap classification tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    POLICY_WORKSHEET_PATH,
    _parse_md_table_rows,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_25W.md"
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH
POLICY_PATH = REPO_ROOT / POLICY_WORKSHEET_PATH


def _batch_doc() -> str:
    return BATCH_PATH.read_text(encoding="utf-8")


def test_phase25w_batch_classifies_no_new_rows_as_proof_ready() -> None:
    doc = _batch_doc()

    assert "status: PROOF_GAP_CLASSIFICATION_BATCH_ONLY" in doc
    assert "newly_proof_ready_not_approved_count: 0" in doc
    assert "| `prev_change_id` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `continuity_condition` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `incremental_delta` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "PROOF_READY_NOT_APPROVED |" not in doc


def test_phase25w_classification_explains_observed_gap_not_harness_only_proof() -> None:
    doc = _batch_doc()

    assert "source_gap_artifact: `docs/crypto_core/DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md`" in doc
    assert "synthetic or harness-only values are used for classification" in doc
    assert "all current `prev_change_id` values are null" in doc
    assert "No actual current observed event has non-null `prev_change_id`" in doc
    assert "No committed official documentation excerpt proves the gap recovery" in doc


def test_phase25w_does_not_create_operator_metadata_or_worksheet_edits() -> None:
    doc = _batch_doc()
    claim_rows = _parse_md_table_rows(CLAIM_PATH.read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows(POLICY_PATH.read_text(encoding="utf-8"))

    assert "No reviewer_id or reviewed_at_iso value is filled." in doc
    assert "No Phase 25X operator-fill proposal is created" in doc
    # Phase 26AJ approved 15 more rows; Phase 26AN approved 3 more; Phase 26AR approved 1 more; total = 23
    approved_claim_ids = {row["claim_id"] for row in claim_rows if row["decision"] == "APPROVED"}
    assert len(approved_claim_ids) == 23
    pending_policy = [row for row in policy_rows if row["decision"] == "PENDING"]
    assert len(pending_policy) == 0


def test_phase25w_validator_remains_blocked_with_26_pending_rows() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 0
    # Phase 26AJ later approved prev_change_id and continuity_condition
    assert "claim_review:prev_change_id" not in result.pending_rows
    assert "claim_review:continuity_condition" not in result.pending_rows
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "READY",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
