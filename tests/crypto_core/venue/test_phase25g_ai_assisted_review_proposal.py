from __future__ import annotations

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
PROPOSAL_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_AI_ASSISTED_REVIEW_PROPOSAL.md"


def _proposal_text() -> str:
    return PROPOSAL_PATH.read_text(encoding="utf-8")


def _expected_row_ids() -> tuple[str, ...]:
    manifest_rows = _parse_md_table_rows((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    claim_rows = _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows((REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8"))

    row_ids = [row["source_id"] for row in manifest_rows]
    row_ids.extend(row["claim_id"] for row in claim_rows)
    row_ids.extend(row["policy_id"] for row in policy_rows)
    return tuple(row_ids)


def test_phase25g_proposal_file_exists_and_is_proposal_only():
    assert PROPOSAL_PATH.exists()

    proposal = _proposal_text()
    proposal_lower = proposal.lower()

    assert "proposal only" in proposal_lower
    assert "not approval" in proposal_lower
    assert "Human must fill this block manually" in proposal
    assert "No source file changes are required." in proposal
    assert "reviewer_id" not in proposal
    assert "reviewed_at_iso" not in proposal
    assert "decision=APPROVE" not in proposal
    assert "decision = APPROVE" not in proposal


def test_phase25g_proposal_contains_all_36_rows_and_required_labels():
    proposal = _proposal_text()
    expected_row_ids = _expected_row_ids()

    assert len(expected_row_ids) == 36
    for row_id in expected_row_ids:
        assert row_id in proposal, f"Missing row_id in proposal: {row_id}"

    for label in (
        "PROPOSE_APPROVE",
        "PROPOSE_REJECT",
        "PROPOSE_DEFER",
        "NEEDS_EXTERNAL_LEGAL_REVIEW",
        "NEEDS_OPERATOR_POLICY_DECISION",
    ):
        assert label in proposal, f"Missing proposal label: {label}"

    assert (
        "| claim_review | regional_legal_access | DERIBIT_RESTRICTED | PENDING | NEEDS_EXTERNAL_LEGAL_REVIEW |"
        in proposal
    )
    assert (
        "| policy_review | regional_legal_access_review | DERIBIT_RESTRICTED | PENDING | NEEDS_EXTERNAL_LEGAL_REVIEW |"
        in proposal
    )
    assert (
        "| policy_review | separate_connector_enablement | DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST | PENDING | PROPOSE_DEFER |"
        in proposal
    )


def test_phase25g_runtime_validator_state_remains_blocked_and_connector_empty():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 3  # Phase 26AN reduced from 11 to 3
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "BLOCKED",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
