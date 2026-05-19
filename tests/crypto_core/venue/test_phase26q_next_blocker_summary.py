"""Phase 26Q Deribit next blocker summary tests.

Phase 26Q records the post-Phase-26N blocker state. Both smoke runs timed out.
No classification advances. Validator remains blocked at pending_rows=26.
"""

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
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26Q.md"
PROPOSAL_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26Q.md"
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH
POLICY_PATH = REPO_ROOT / POLICY_WORKSHEET_PATH


def _summary_doc() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26q_summary_doc_exists() -> None:
    assert SUMMARY_PATH.exists(), f"Phase 26Q summary doc not found: {SUMMARY_PATH}"


def test_phase26q_summary_status_next_action_only() -> None:
    doc = _summary_doc()
    assert "status: NEXT_ACTION_PLAN_ONLY" in doc


def test_phase26q_summary_records_both_failed_runs() -> None:
    doc = _summary_doc()
    assert "26033502712" in doc
    assert "26035089720" in doc
    assert "deribit_ws:timeout" in doc


def test_phase26q_no_operator_proposal_without_proof_ready_rows() -> None:
    doc = _summary_doc()
    assert "NO_PROPOSAL" in doc or "no rows are newly proof-ready" in doc.lower()
    assert not PROPOSAL_PATH.exists()


def test_phase26q_summary_lists_remaining_raw_sequence_requirements() -> None:
    doc = _summary_doc()
    assert "`prev_change_id`" in doc
    assert "`continuity_condition`" in doc
    assert "`first_message_snapshot`" in doc
    assert "`incremental_delta`" in doc


def test_phase26q_summary_records_persistent_timeout_blocker() -> None:
    doc = _summary_doc()
    assert "persistent" in doc.lower() or "2 consecutive" in doc.lower() or "both" in doc.lower()
    assert "accepted=true" in doc or "accepted" in doc


def test_phase26q_no_worksheet_edits_and_validator_remains_blocked() -> None:
    claim_rows = _parse_md_table_rows(CLAIM_PATH.read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows(POLICY_PATH.read_text(encoding="utf-8"))
    result = evaluate_deribit_manual_review_readiness()

    # Phase 26AJ approved 15 more rows; total approved = 19
    approved_claim_ids = {row["claim_id"] for row in claim_rows if row["decision"] == "APPROVED"}
    assert len(approved_claim_ids) == 23
    pending_policy = [r for r in policy_rows if r["decision"] == "PENDING"]
    assert len(pending_policy) == 0
    assert result.accepted is False
    assert result.evidence_review_complete is True  # True after Phase 26AW
    assert result.ready_for_engineering_patch is True  # True after Phase 26AW
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 0
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "READY",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()


def test_phase26q_no_connector_or_live_enablement_language() -> None:
    doc = _summary_doc()
    assert "`separate_connector_enablement` remains deferred" in doc
    assert "connector_ready_dialects()` changes" in doc
    assert "enabled_for_connector=True" not in doc
    assert "static_registry_verified: true" not in doc
