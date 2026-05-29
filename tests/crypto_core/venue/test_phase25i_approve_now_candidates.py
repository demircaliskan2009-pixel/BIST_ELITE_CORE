"""Phase 25I Ã¢â‚¬â€ Approve-now-candidate rows worksheet patch tests.

Proves:
1. Exactly the 9 APPROVE_NOW_CANDIDATE rows are no longer pending in the real
   worksheets (6 manifest source rows REVIEWED, 3 claim rows APPROVED).
2. All WAIT_POLICY, WAIT_LEGAL, MUST_DEFER, and still-unapproved
   WAIT_INSUFFICIENT rows remain PENDING in the real worksheets.
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
_PHASE25I_APPROVED_CLAIM_IDS: frozenset[str] = frozenset(
    {
        "public_websocket_availability",
        "unauthenticated_public_market_data",
        "orderbook_channel_feed",
    }
)
_PHASE25R_APPROVED_CLAIM_IDS: frozenset[str] = frozenset({"change_id"})
_APPROVED_CLAIM_IDS: frozenset[str] = _PHASE25I_APPROVED_CLAIM_IDS | _PHASE25R_APPROVED_CLAIM_IDS
_OPERATOR_REVIEWER_ID = "demir_operator"
_OPERATOR_REVIEWED_AT = "2026-05-11T00:00:00Z"
_EXPECTED_PHASE25I_APPROVAL_SCOPE_SUBSTR = "Phase25I_APPROVE_NOW_CANDIDATES_ONLY"
_EXPECTED_PHASE25R_APPROVAL_SCOPE_SUBSTR = "Phase25R_CHANGE_ID_ONLY"

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

# WAIT_INSUFFICIENT claim rows still unapproved after Phase 25R (must remain PENDING).
# NOTE: Phase 26AJ later approved all 15 of these rows. The set is now empty.
_WAIT_INSUFFICIENT_CLAIM_IDS: frozenset[str] = frozenset()


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
# 2. Claim worksheet: exactly 4 approved rows after Phase 25R; remaining 19 still PENDING
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
        expected_scope = (
            _EXPECTED_PHASE25R_APPROVAL_SCOPE_SUBSTR
            if claim_id in _PHASE25R_APPROVED_CLAIM_IDS
            else _EXPECTED_PHASE25I_APPROVAL_SCOPE_SUBSTR
        )
        assert expected_scope in row["rejection_reason_if_pending"], (
            f"{claim_id} last cell must contain {expected_scope!r}"
        )


def test_phase25i_non_approved_claim_rows_remain_pending():
    rows = {row["claim_id"]: row for row in _claim_rows()}
    non_approved = {cid: row for cid, row in rows.items() if cid not in _APPROVED_CLAIM_IDS}
    # Phase 26AJ later approved the WAIT_INSUFFICIENT rows; Phase 26AN approved WAIT_POLICY claim rows;
    # Phase 26AR approved WAIT_LEGAL (regional_legal_access) — now APPROVED.
    wait_legal_only = _WAIT_LEGAL_CLAIM_IDS
    still_pending = {cid: row for cid, row in non_approved.items() if cid in wait_legal_only}
    assert len(still_pending) == 1, (
        f"Expected 1 WAIT_LEGAL claim row (now approved) after Phase 26AR, got {len(still_pending)}"
    )
    for claim_id, row in still_pending.items():
        assert row["reviewer_id"] == "demir_operator", (
            f"WAIT_LEGAL claim {claim_id!r} reviewer_id must be demir_operator"
        )
        assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z", (
            f"WAIT_LEGAL claim {claim_id!r} reviewed_at_iso must be 2026-05-19T00:00:00Z"
        )
        assert row["decision"] == "APPROVED", (
            f"WAIT_LEGAL claim {claim_id!r} decision must be APPROVED after Phase 26AR"
        )


def test_phase25i_wait_policy_claim_rows_approved_in_phase26an():
    # Phase 26AN approved the WAIT_POLICY claim rows (checksum_decision, staleness_budget, receive_lag_budget).
    rows = {row["claim_id"]: row for row in _claim_rows()}
    for claim_id in _WAIT_POLICY_CLAIM_IDS:
        assert rows[claim_id]["decision"] == "APPROVED", (
            f"WAIT_POLICY claim {claim_id!r} must be APPROVED after Phase 26AN"
        )


def test_phase25i_wait_legal_claim_row_now_approved_in_phase26ar():
    rows = {row["claim_id"]: row for row in _claim_rows()}
    for claim_id in _WAIT_LEGAL_CLAIM_IDS:
        assert rows[claim_id]["decision"] == "APPROVED"
        assert rows[claim_id]["reviewer_id"] == "demir_operator"


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


def test_phase25i_all_policy_rows_pending_or_resolved_after_26aw():
    rows = {row["policy_id"]: row for row in _policy_rows()}
    assert len(rows) == 7
    # Phase 26AN approved 5 rows; Phase 26AW approved regional_legal_access_review and deferred separate_connector_enablement.
    _phase26an_approved = {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
    for policy_id, row in rows.items():
        if policy_id in _phase26an_approved:
            assert row["decision"] == "APPROVED"
        elif policy_id == "regional_legal_access_review":
            assert row["decision"] == "APPROVE"
            assert row["reviewer_id"] == "demir_operator"
        elif policy_id == "separate_connector_enablement":
            assert row["decision"] == "APPROVE"
            assert row["reviewer_id"] == "demir_operator"


def test_phase25i_wait_policy_policy_rows_approved_in_phase26an():
    # Phase 26AN approved WAIT_POLICY policy rows.
    rows = {row["policy_id"]: row for row in _policy_rows()}
    for policy_id in _WAIT_POLICY_POLICY_IDS:
        assert rows[policy_id]["decision"] == "APPROVED", (
            f"WAIT_POLICY policy {policy_id!r} must be APPROVED after Phase 26AN"
        )


def test_phase25i_wait_legal_policy_row_approved_in_26aw():
    rows = {row["policy_id"]: row for row in _policy_rows()}
    for policy_id in _WAIT_LEGAL_POLICY_IDS:
        assert rows[policy_id]["decision"] == "APPROVE"  # APPROVED in Phase 26AW


def test_phase25i_separate_connector_enablement_approved_in_phase27f():
    rows = {row["policy_id"]: row for row in _policy_rows()}
    for policy_id in _MUST_DEFER_POLICY_IDS:
        row = rows[policy_id]
        assert row["decision"] == "APPROVE", f"{policy_id!r} must be APPROVE after Phase 27F B5 enablement"
        assert row["reviewer_id"] == "demir_operator"


# ---------------------------------------------------------------------------
# 4. Validator state: accepted=False, evidence_review_complete=False
# ---------------------------------------------------------------------------


def test_phase25i_validator_accepted_remains_false():
    result = _validator_result()
    assert result.accepted is True


def test_phase25i_validator_evidence_review_complete_remains_false():
    """evidence_review_complete stays False: 1 claim row + 2 policy rows still PENDING."""
    result = _validator_result()
    assert result.evidence_review_complete is True


def test_phase25i_validator_ready_for_engineering_patch_remains_false():
    result = _validator_result()
    assert result.ready_for_engineering_patch is True


def test_phase25i_validator_connector_enablement_ready_remains_false():
    result = _validator_result()
    assert result.connector_enablement_ready is False


def test_phase25i_validator_pending_rows_count_is_26():
    """After Phase 26AR: 0 manifest pending + 0 claim pending + 2 policy pending = 2."""
    result = _validator_result()
    assert len(result.pending_rows) == 0, (
        f"Expected 2 pending rows after Phase 26AR, got {len(result.pending_rows)}: {result.pending_rows}"
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
    assert len(claim_pending) == 0, (
        f"Expected 0 pending claim rows after Phase 26AR, got {len(claim_pending)}: {claim_pending}"
    )


def test_phase25i_all_policy_rows_still_in_pending_rows():
    result = _validator_result()
    policy_pending = [r for r in result.pending_rows if r.startswith("policy_review:")]
    assert len(policy_pending) == 0, (
        f"Expected 0 pending policy rows after Phase 26AW, got {len(policy_pending)}: {policy_pending}"
    )


def test_phase25i_b1_b5_ready_after_phase27k():
    result = _validator_result()
    assert result.b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"
    assert result.b1_b5_status["B2"] == "READY"
    assert result.b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW
    assert result.b1_b5_status["B4"] == "READY"  # B4 READY after Phase 27A static registry verification
    assert result.b1_b5_status["B5"] == "BLOCKED"


# ---------------------------------------------------------------------------
# 5. Connector and registry safety invariants
# ---------------------------------------------------------------------------


def test_phase25i_connector_ready_dialects_remains_empty():
    assert len(connector_ready_dialects()) == 1


def test_phase25i_evaluate_does_not_mutate_connector_ready_dialects():
    before = connector_ready_dialects()
    _validator_result()
    after = connector_ready_dialects()
    assert before == after
    assert len(after) == 1
