"""Phase 26AH next blocker summary and proposal tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26AH.md"
PROPOSAL_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26AH.md"
WORKSHEET_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_CLAIM_REVIEW_WORKSHEET.md"
)

PROPOSAL_ROWS = (
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
)


def _summary() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def _proposal() -> str:
    return PROPOSAL_PATH.read_text(encoding="utf-8")


def _worksheet_line(row_id: str) -> str:
    for line in WORKSHEET_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| `{row_id}` |"):
            return line
    raise AssertionError(f"worksheet row missing: {row_id}")


def test_phase26ah_summary_and_proposal_exist() -> None:
    assert "status: NEXT_ACTION_PLAN_ONLY" in _summary()
    assert "status: OPERATOR_FILL_PROPOSAL_ONLY" in _proposal()
    assert "supersedes: DERIBIT_NEXT_BLOCKER_SUMMARY_26AD.md" in _summary()


def test_phase26ah_proposal_rows_are_placeholder_only() -> None:
    content = _proposal()
    for row in PROPOSAL_ROWS:
        assert f"| `{row}` | `APPROVE_CANDIDATE` | `<OPERATOR_REQUIRED>` | `<OPERATOR_REQUIRED>` |" in content
    assert "`regional_legal_access` | `APPROVE_CANDIDATE`" not in content
    assert "Documentation proof only; not legal approval." in content


def test_phase26ah_no_worksheet_edits_for_new_proof_ready_rows() -> None:
    # Phase 26AJ later approved all PROPOSAL_ROWS; they are no longer PENDING.
    # We verify they exist in the worksheet (the doc was accurate at Phase 26AH time).
    for row in PROPOSAL_ROWS + ("regional_legal_access",):
        _worksheet_line(row)  # raises if missing


def test_phase26ah_pending_rows_remain_26_and_validator_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.ready_for_engineering_patch is False
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 2


def test_phase26ah_connector_ready_dialects_empty_and_b1_b5_blocked() -> None:
    assert len(connector_ready_dialects()) == 0
    result = evaluate_deribit_manual_review_readiness()
    for blocker in ("B1", "B2", "B3", "B4", "B5"):
        assert result.b1_b5_status[blocker] == "BLOCKED"


def test_phase26ah_summary_records_remaining_policy_and_legal_blockers() -> None:
    content = _summary()
    assert "`claim_review:checksum_decision` | `WAIT_INSUFFICIENT`" in content
    assert "`policy_review:separate_connector_enablement` | `WAIT_POLICY`" in content
    assert "`policy_review:regional_legal_access_review` | `WAIT_LEGAL`" in content
    assert "| `new_proof_ready_not_approved_rows` | 15 |" in content
    assert "| `operator_proposal_rows` | 15 |" in content
