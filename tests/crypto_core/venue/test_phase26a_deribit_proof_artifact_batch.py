"""Phase 26A Deribit proof artifact batch tests."""

from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    POLICY_WORKSHEET_PATH,
    _parse_md_table_rows,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
OBSERVED_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json"
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_26A.md"
PROPOSAL_26B_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26B.md"
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH
POLICY_PATH = REPO_ROOT / POLICY_WORKSHEET_PATH


def _observed_proof() -> dict[str, object]:
    return json.loads(OBSERVED_PATH.read_text(encoding="utf-8"))


def _batch_doc() -> str:
    return BATCH_PATH.read_text(encoding="utf-8")


def test_phase26a_current_observed_artifact_has_no_non_null_prev_change_id() -> None:
    events = _observed_proof()["observed_events"]

    assert isinstance(events, list)
    assert len(events) == 5
    assert all(event["prev_change_id"] is None for event in events)
    assert all(event["prev_sequence_id"] is None for event in events)
    assert not any(current["prev_change_id"] == prior["change_id"] for prior, current in zip(events, events[1:]))


def test_phase26a_batch_keeps_prev_change_id_and_continuity_wait_insufficient() -> None:
    doc = _batch_doc()

    assert "status: PROOF_GAP_CLASSIFICATION_BATCH_ONLY" in doc
    assert "newly_proof_ready_not_approved_count: 0" in doc
    assert "| `prev_change_id` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `continuity_condition` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "`non_null_prev_change_id_observed=false`" in doc
    assert "`continuity_pair_missing=true`" in doc
    assert "PROOF_READY_NOT_APPROVED |" not in doc


def test_phase26a_continuity_requires_exact_adjacent_equality() -> None:
    doc = _batch_doc()

    assert "current.prev_change_id == prior.change_id" in doc
    assert "| adjacent pair equality `current.prev_change_id == prior.change_id` is proven | false |" in doc
    assert "| non-null but mismatched `prev_change_id` is present | false |" in doc
    assert "future mismatch must be recorded as a gap" in doc


def test_phase26a_does_not_create_operator_proposal_or_worksheet_edits() -> None:
    doc = _batch_doc()
    claim_rows = _parse_md_table_rows(CLAIM_PATH.read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows(POLICY_PATH.read_text(encoding="utf-8"))

    assert "No Phase 26B operator-fill proposal is created" in doc
    assert not PROPOSAL_26B_PATH.exists()
    # Phase 26AJ approved 15 more rows; total approved = 19
    approved_claim_ids = {row["claim_id"] for row in claim_rows if row["decision"] == "APPROVED"}
    assert len(approved_claim_ids) == 23
    pending_policy = [r for r in policy_rows if r["decision"] == "PENDING"]
    assert len(pending_policy) == 2


def test_phase26a_validator_remains_blocked_with_26_pending_rows() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.ready_for_engineering_patch is False
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 2
    # Phase 26AJ later approved these rows
    assert "claim_review:prev_change_id" not in result.pending_rows
    assert "claim_review:continuity_condition" not in result.pending_rows
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "BLOCKED",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
