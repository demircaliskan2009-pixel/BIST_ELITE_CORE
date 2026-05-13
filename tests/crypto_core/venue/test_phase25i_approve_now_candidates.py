"""Phase 25I — Approve-now-candidate rows worksheet patch tests.

Proves:
1. Exactly the 9 APPROVE_NOW_CANDIDATE rows are no longer pending in the real
   worksheets (6 manifest source rows REVIEWED, 3 claim rows APPROVED).
2. All WAIT_POLICY, WAIT_LEGAL, MUST_DEFER, and WAIT_INSUFFICIENT rows remain
   PENDING in the real worksheets.
3. Operator reviewer metadata is correctly set on the 9 approved rows.
4. Validator still returns accepted=False, evidence_review_complete=False,
   ready_for_engineering_patch=False, connector_enablement_ready=False.
5. connector_ready_dialects() remains empty.
6. B1-B5 all remain BLOCKED.
"""

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

# The exact 9 rows approved in Phase 25I.
_APPROVED_MANIFEST_IDS: frozenset[str] = frozenset(
    {
        "DERIBIT_NOTIFICATIONS",
        "DERIBIT_ENVIRONMENT",
        "DERIBIT_RATE_LIMITS",
        "DERIBIT_INSTRUMENTS",
        "DERIBIT_TICKER",
        "DERIBIT_RESTRICTED",
    }
)
_APPROVED_CLAIM_IDS: frozenset[str] = frozenset(
    {
        "public_websocket_availability",
        "unauthenticated_public_market_data",
        "orderbook_channel_feed",
    }
)
_OPERATOR_REVIEWER_ID = "demir_operator"
_OPERATOR_REVIEWED_AT = "2026-05-11T00:00:00Z"
_EXPECTED_APPROVAL_SCOPE_SUBSTR = "Phase25I_APPROVE_NOW_CANDIDATES_ONLY"

# WAIT_POLICY claim rows (must remain PENDING).
_WAIT_POLICY_CLAIM_IDS: frozenset[str] = frozenset({"checksum_decision", "staleness_budget", "receive_lag_budget"})

# WAIT_POLICY policy rows (must remain PENDING).
_WAIT_POLICY_POLICY_IDS: frozenset[str] = frozenset(
    {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
)

# WAIT_LEGAL rows (must remain PENDING).
_WAIT_LEGAL_CLAIM_IDS: frozenset[str] = frozenset({"regional_legal_access"})
_WAIT_LEGAL_POLICY_IDS: frozenset[str] = frozenset({"regional_legal_access_review"})

# MUST_DEFER row (must remain PENDING in worksheets; never approved in Phase 25).
_MUST_DEFER_POLICY_IDS: frozenset[str] = frozenset({"separate_connector_enablement"})

# WAIT_INSUFFICIENT claim rows (must remain PENDING).
_WAIT_INSUFFICIENT_CLAIM_IDS: frozenset[str] = frozenset(
    {
        "public_rest_availability",
        "prod_testnet_ws_endpoint",
        "prod_testnet_rest_endpoint",
        "first_message_snapshot",
        "incremental_delta",
        "change_id",
        "prev_change_id",
        "continuity_condition",
        "gap_resubscribe_rule",
        "rest_snapshot_requirement",
        "heartbeat_liveness_proof",
        "public_rate_subscription_limits",
        "public_trades",
        "ticker",
        "mark_index_funding_open_interest",
        "testnet_prod_difference",
    }
)


# ---------------------------------------------------------------------------
# Helper readers
# ---------------------------------------------------------------------------


def _manifest_rows() -> list[dict[str, str]]:
    return _parse_md_table_rows((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))


def _claim_rows() -> list[dict[str, str]]:
    return _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))


def _policy_rows() -> list[dict[str, str]]:
    return _parse_md_table_rows((REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8"))


def _validator_result():
    return evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )


# ---------------------------------------------------------------------------
# 1. Manifest: all 6 approved rows are REVIEWED_APPROVED (not PENDING)
# ---------------------------------------------------------------------------


def test_phase25i_approved_manifest_rows_are_reviewed_approved():
    rows = {row["source_id"]: row for row in _manifest_rows()}
    assert set(rows) == _APPROVED_MANIFEST_IDS, f"Manifest must contain exactly the 6 approved IDs. Got: {set(rows)}"
    for source_id in _APPROVED_MANIFEST_IDS:
        assert rows[source_id]["retrieval_status"] == "REVIEWED_APPROVED", (
            f"{source_id} retrieval_status must be REVIEWED_APPROVED, got {rows[source_id]['retrieval_status']!r}"
        )


def test_phase25i_approved_manifest_rows_preserve_hash_and_url():
    rows = {row["source_id"]: row for row in _manifest_rows()}
    for source_id in _APPROVED_MANIFEST_IDS:
        assert rows[source_id]["content_sha256"] == "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"
        assert int(rows[source_id]["content_size_bytes"]) > 0


# ---------------------------------------------------------------------------
# 2. Claim worksheet: exactly 3 approved rows; remaining 20 still PENDING
# ---------------------------------------------------------------------------


def test_phase25i_approved_claim_rows_have_correct_decision_and_reviewer():
    rows = {row["claim_id"]: row for row in _claim_rows()}
    for claim_id in _APPROVED_CLAIM_IDS:
        assert claim_id in rows, f"Approved claim row {claim_id!r} missing from worksheet"
        row = rows[claim_id]
        assert row["decision"] == "APPROVED", f"{claim_id} decision must be APPROVED, got {row['decision']!r}"
        assert row["reviewer_id"] == _OPERATOR_REVIEWER_ID, (
            f"{claim_id} reviewer_id must be {_OPERATOR_REVIEWER_ID!r}, got {row['reviewer_id']!r}"
        )
        assert row["reviewed_at_iso"] == _OPERATOR_REVIEWED_AT, (
            f"{claim_id} reviewed_at_iso must be {_OPERATOR_REVIEWED_AT!r}, got {row['reviewed_at_iso']!r}"
        )
        assert row["review_status"] == "APPROVED", (
            f"{claim_id} review_status must be APPROVED, got {row['review_status']!r}"
        )
        assert _EXPECTED_APPROVAL_SCOPE_SUBSTR in row["rejection_reason_if_pending"], (
            f"{claim_id} last cell must contain {_EXPECTED_APPROVAL_SCOPE_SUBSTR!r}"
        )


def test_phase25i_non_approved_claim_rows_remain_pending():
    rows = {row["claim_id"]: row for row in _claim_rows()}
    non_approved = {cid: row for cid, row in rows.items() if cid not in _APPROVED_CLAIM_IDS}
    assert len(non_approved) == 20, f"Expected 20 non-approved claim rows, got {len(non_approved)}"
    for claim_id, row in non_approved.items():
        assert row["reviewer_id"] == "PENDING", f"Non-approved claim {claim_id!r} reviewer_id must be PENDING"
        assert row["reviewed_at_iso"] == "PENDING", f"Non-approved claim {claim_id!r} reviewed_at_iso must be PENDING"
        assert row["decision"] == "PENDING", f"Non-approved claim {claim_id!r} decision must be PENDING"


def test_phase25i_wait_policy_claim_rows_remain_pending():
    rows = {row["claim_id"]: row for row in _claim_rows()}
    for claim_id in _WAIT_POLICY_CLAIM_IDS:
        assert rows[claim_id]["decision"] == "PENDING"
        assert rows[claim_id]["reviewer_id"] == "PENDING"


def test_phase25i_wait_legal_claim_row_remains_pending():
    rows = {row["claim_id"]: row for row in _claim_rows()}
    for claim_id in _WAIT_LEGAL_CLAIM_IDS:
        assert rows[claim_id]["decision"] == "PENDING"
        assert rows[claim_id]["reviewer_id"] == "PENDING"


def test_phase25i_wait_insufficient_claim_rows_remain_pending():
    rows = {row["claim_id"]: row for row in _claim_rows()}
    for claim_id in _WAIT_INSUFFICIENT_CLAIM_IDS:
        assert rows[claim_id]["decision"] == "PENDING", f"WAIT_INSUFFICIENT claim {claim_id!r} must remain PENDING"
        assert rows[claim_id]["reviewer_id"] == "PENDING", (
            f"WAIT_INSUFFICIENT claim {claim_id!r} reviewer_id must remain PENDING"
        )


# ---------------------------------------------------------------------------
# 3. Policy worksheet: all 7 rows remain entirely PENDING
# ---------------------------------------------------------------------------


def test_phase25i_all_policy_rows_remain_entirely_pending():
    rows = {row["policy_id"]: row for row in _policy_rows()}
    assert len(rows) == 7
    for policy_id, row in rows.items():
        assert row["reviewer_id"] == "PENDING", f"Policy row {policy_id!r} reviewer_id must remain PENDING"
        assert row["reviewed_at_iso"] == "PENDING", f"Policy row {policy_id!r} reviewed_at_iso must remain PENDING"
        assert row["decision"] == "PENDING", f"Policy row {policy_id!r} decision must remain PENDING"


def test_phase25i_wait_policy_policy_rows_remain_pending():
    rows = {row["policy_id"]: row for row in _policy_rows()}
    for policy_id in _WAIT_POLICY_POLICY_IDS:
        assert rows[policy_id]["decision"] == "PENDING"


def test_phase25i_wait_legal_policy_row_remains_pending():
    rows = {row["policy_id"]: row for row in _policy_rows()}
    for policy_id in _WAIT_LEGAL_POLICY_IDS:
        assert rows[policy_id]["decision"] == "PENDING"


def test_phase25i_separate_connector_enablement_remains_pending_not_approved():
    rows = {row["policy_id"]: row for row in _policy_rows()}
    for policy_id in _MUST_DEFER_POLICY_IDS:
        row = rows[policy_id]
        assert row["decision"] == "PENDING", (
            f"{policy_id!r} must remain PENDING; connector enablement is a separate phase"
        )
        assert row["reviewer_id"] == "PENDING"


# ---------------------------------------------------------------------------
# 4. Validator state: accepted=False, evidence_review_complete=False
# ---------------------------------------------------------------------------


def test_phase25i_validator_accepted_remains_false():
    result = _validator_result()
    assert result.accepted is False


def test_phase25i_validator_evidence_review_complete_remains_false():
    """evidence_review_complete stays False: 20 claim rows + 7 policy rows still PENDING."""
    result = _validator_result()
    assert result.evidence_review_complete is False


def test_phase25i_validator_ready_for_engineering_patch_remains_false():
    result = _validator_result()
    assert result.ready_for_engineering_patch is False


def test_phase25i_validator_connector_enablement_ready_remains_false():
    result = _validator_result()
    assert result.connector_enablement_ready is False


def test_phase25i_validator_pending_rows_count_is_27():
    """After Phase 25I: 0 manifest pending + 20 claim pending + 7 policy pending = 27."""
    result = _validator_result()
    assert len(result.pending_rows) == 27, (
        f"Expected 27 pending rows after Phase 25I, got {len(result.pending_rows)}: {result.pending_rows}"
    )


def test_phase25i_manifest_rows_not_in_pending_rows():
    """All 6 manifest rows are REVIEWED (not PENDING) after Phase 25I."""
    result = _validator_result()
    manifest_pending = [r for r in result.pending_rows if r.startswith("source_snapshot:")]
    assert len(manifest_pending) == 0, (
        f"Expected 0 pending source_snapshot rows after Phase 25I, got: {manifest_pending}"
    )


def test_phase25i_approved_claim_rows_not_in_pending_rows():
    result = _validator_result()
    for claim_id in _APPROVED_CLAIM_IDS:
        assert f"claim_review:{claim_id}" not in result.pending_rows, (
            f"Approved claim {claim_id!r} must not appear in pending_rows"
        )


def test_phase25i_non_approved_claim_rows_still_in_pending_rows():
    result = _validator_result()
    claim_pending = {r for r in result.pending_rows if r.startswith("claim_review:")}
    assert len(claim_pending) == 20, (
        f"Expected 20 pending claim rows after Phase 25I, got {len(claim_pending)}: {claim_pending}"
    )


def test_phase25i_all_policy_rows_still_in_pending_rows():
    result = _validator_result()
    policy_pending = [r for r in result.pending_rows if r.startswith("policy_review:")]
    assert len(policy_pending) == 7, (
        f"Expected 7 pending policy rows after Phase 25I, got {len(policy_pending)}: {policy_pending}"
    )


def test_phase25i_b1_b5_all_remain_blocked():
    result = _validator_result()
    for blocker in ("B1", "B2", "B3", "B4", "B5"):
        assert result.b1_b5_status[blocker] == "BLOCKED", f"{blocker} must remain BLOCKED after Phase 25I"


# ---------------------------------------------------------------------------
# 5. Connector and registry safety invariants
# ---------------------------------------------------------------------------


def test_phase25i_connector_ready_dialects_remains_empty():
    assert connector_ready_dialects() == ()


def test_phase25i_evaluate_does_not_mutate_connector_ready_dialects():
    before = connector_ready_dialects()
    _validator_result()
    after = connector_ready_dialects()
    assert before == after == ()
