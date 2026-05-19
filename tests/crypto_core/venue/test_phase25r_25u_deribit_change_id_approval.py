"""Phase 25R-25U Deribit change_id approval and next proof spec tests."""

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
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH
POLICY_PATH = REPO_ROOT / POLICY_WORKSHEET_PATH
SPEC_25T_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_OBSERVED_SEQUENCE_PROOF_SPEC_25T.md"
SUMMARY_25U_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_25U.md"
CANDIDATES_25O_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_EVIDENCE_BASED_APPROVAL_CANDIDATES_25O.md"

_PHASE25I_APPROVED = {
    "public_websocket_availability",
    "unauthenticated_public_market_data",
    "orderbook_channel_feed",
}
_PHASE25R_APPROVED = {"change_id"}
_PHASE26AJ_APPROVED = {
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
_PHASE26AN_APPROVED = frozenset({"checksum_decision", "staleness_budget", "receive_lag_budget"})
_PHASE26AR_APPROVED = frozenset({"regional_legal_access"})
_EXPECTED_APPROVED = (
    _PHASE25I_APPROVED | _PHASE25R_APPROVED | _PHASE26AJ_APPROVED | _PHASE26AN_APPROVED | _PHASE26AR_APPROVED
)


def _claim_rows() -> dict[str, dict[str, str]]:
    return {row["claim_id"]: row for row in _parse_md_table_rows(CLAIM_PATH.read_text(encoding="utf-8"))}


def _policy_rows() -> dict[str, dict[str, str]]:
    return {row["policy_id"]: row for row in _parse_md_table_rows(POLICY_PATH.read_text(encoding="utf-8"))}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase25r_change_id_is_the_only_new_approved_claim_row() -> None:
    rows = _claim_rows()

    row = rows["change_id"]
    assert row["review_status"] == "APPROVED"
    assert row["reviewer_id"] == "demir_operator"
    assert row["reviewed_at_iso"] == "2026-05-11T00:00:00Z"
    assert row["decision"] == "APPROVED"
    assert "Phase25R_CHANGE_ID_ONLY" in row["rejection_reason_if_pending"]
    assert "DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json" in row["rejection_reason_if_pending"]
    assert "DERIBIT_PROOF_ARTIFACT_BATCH_25N.md" in row["rejection_reason_if_pending"]

    approved = {claim_id for claim_id, value in rows.items() if value["decision"] == "APPROVED"}
    assert approved == _EXPECTED_APPROVED


def test_phase25s_pending_counts_decrease_by_one_claim_only() -> None:
    claim_rows = _claim_rows()
    policy_rows = _policy_rows()

    claim_pending = [row for row in claim_rows.values() if row["decision"] == "PENDING"]
    policy_pending = [row for row in policy_rows.values() if row["decision"] == "PENDING"]

    assert len(claim_pending) == 0
    assert len(policy_pending) == 0  # 0 after Phase 26AW

    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 0
    assert "claim_review:change_id" not in result.pending_rows
    # Phase 26AJ later approved prev_change_id; it is no longer pending
    assert "claim_review:prev_change_id" not in result.pending_rows


def test_phase25s_validator_remains_blocked_after_change_id_only_approval() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is True
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "READY",
        "B4": "READY",
        "B5": "READY",
    }


def test_phase25s_connector_ready_dialects_remains_empty() -> None:
    assert len(connector_ready_dialects()) == 1


def test_phase25s_candidate_doc_reflects_change_id_approved_not_candidate() -> None:
    doc = _text(CANDIDATES_25O_PATH)

    assert "APPROVED_PHASE25R_CHANGE_ID_ONLY" in doc
    assert "newly_approved_phase25r_claim_count: 1" in doc
    assert "newly_proof_ready_not_approved_claim_count: 0" in doc
    assert "| PROOF_READY_NOT_APPROVED | claim_review | `change_id` |" not in doc


def test_phase25t_next_observed_sequence_spec_requires_real_adjacent_events() -> None:
    doc = _text(SPEC_25T_PATH)

    assert "status: SPEC_ONLY_NO_NETWORK_CHANGE" in doc
    assert "`dry_run=true`" in doc
    assert "`operator_authorization=PUBLIC_MARKET_DATA_ONLY`" in doc
    assert "At least two adjacent book events" in doc
    assert "`prev_change_id[i] == change_id[i-1]`" in doc
    assert "null keeps `prev_change_id` and `continuity_condition` blocked" in doc
    assert "does not enable `connector_ready_dialects()`" in doc


def test_phase25u_summary_lists_remaining_blockers_and_deferred_connector_enablement() -> None:
    doc = _text(SUMMARY_25U_PATH)

    assert "| `change_id` | claim_review | `Phase25R_CHANGE_ID_ONLY` | `demir_operator` |" in doc
    for row_id in ("prev_change_id", "first_message_snapshot", "incremental_delta", "continuity_condition"):
        assert f"| `{row_id}` |" in doc
    assert "| `gap_resubscribe_rule` | `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md`. |" in doc
    assert "| `heartbeat_liveness_proof` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |" in doc
    assert "| `regional_legal_access` | External legal/access review required. |" in doc
    assert "`separate_connector_enablement` remains deferred" in doc
    assert "pending_rows: 26" in doc
