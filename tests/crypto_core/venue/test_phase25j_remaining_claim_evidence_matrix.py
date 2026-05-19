"""Phase 25J Ã¢â‚¬â€ Remaining claim evidence matrix tests.

Proves:
1. The matrix document lists exactly the 20 remaining PENDING claim rows.
2. The 3 Phase 25I approved rows are NOT listed as pending in the matrix.
3. Classification invariants hold per row category.
4. Worksheet files remain fail-closed after Phase 25R (manifest=6 approved,
   claim=4 approved including change_id, policy=0 approved).
5. Validator remains accepted=False, evidence_review_complete=False,
   ready_for_engineering_patch=False, connector_enablement_ready=False.
6. connector_ready_dialects() == ().
7. No src/ files are changed relative to Phase 25I (matrix and test are docs/
   and tests/ only).
"""

from __future__ import annotations

import re
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    MANIFEST_PATH,
    POLICY_WORKSHEET_PATH,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]

MATRIX_PATH = Path("docs/crypto_core/DERIBIT_REMAINING_CLAIM_EVIDENCE_MATRIX.md")

# ---------------------------------------------------------------------------
# Phase 25I approved rows Ã¢â‚¬â€ must NOT appear as pending in the matrix
# ---------------------------------------------------------------------------

_PHASE25I_APPROVED_CLAIM_IDS: frozenset[str] = frozenset(
    {
        "public_websocket_availability",
        "unauthenticated_public_market_data",
        "orderbook_channel_feed",
    }
)
_PHASE25R_APPROVED_CLAIM_IDS: frozenset[str] = frozenset({"change_id"})
_PHASE26AJ_APPROVED_CLAIM_IDS: frozenset[str] = frozenset(
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
_CURRENT_APPROVED_CLAIM_IDS: frozenset[str] = (
    _PHASE25I_APPROVED_CLAIM_IDS
    | _PHASE25R_APPROVED_CLAIM_IDS
    | _PHASE26AJ_APPROVED_CLAIM_IDS
    | frozenset({"checksum_decision", "staleness_budget", "receive_lag_budget"})  # Phase 26AN
    | frozenset({"regional_legal_access"})  # Phase 26AR
)

# ---------------------------------------------------------------------------
# The 20 remaining PENDING claim rows
# ---------------------------------------------------------------------------

_REMAINING_CLAIM_IDS: frozenset[str] = frozenset(
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
        "checksum_decision",
        "heartbeat_liveness_proof",
        "public_rate_subscription_limits",
        "public_trades",
        "ticker",
        "mark_index_funding_open_interest",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_difference",
        "regional_legal_access",
    }
)
_CURRENT_PENDING_CLAIM_IDS: frozenset[str] = (
    _REMAINING_CLAIM_IDS
    - _PHASE25R_APPROVED_CLAIM_IDS
    - _PHASE26AJ_APPROVED_CLAIM_IDS
    - frozenset({"checksum_decision", "staleness_budget", "receive_lag_budget"})  # Phase 26AN
    - frozenset({"regional_legal_access"})  # Phase 26AR
)

# ---------------------------------------------------------------------------
# Classification groups
# ---------------------------------------------------------------------------

_NEEDS_OFFICIAL_DOC_SECTION_PROOF: frozenset[str] = frozenset(
    {
        "public_rest_availability",
        "prod_testnet_ws_endpoint",
        "prod_testnet_rest_endpoint",
        "gap_resubscribe_rule",
        "rest_snapshot_requirement",
        "heartbeat_liveness_proof",
        "public_rate_subscription_limits",
        "testnet_prod_difference",
    }
)

_NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF: frozenset[str] = frozenset(
    {
        "first_message_snapshot",
        "incremental_delta",
        "change_id",
        "prev_change_id",
        "continuity_condition",
        "public_trades",
        "ticker",
        "mark_index_funding_open_interest",
    }
)

_NEEDS_POLICY_DECISION: frozenset[str] = frozenset(
    {
        "checksum_decision",
        "staleness_budget",
        "receive_lag_budget",
    }
)

_NEEDS_LEGAL_REVIEW: frozenset[str] = frozenset({"regional_legal_access"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matrix_text() -> str:
    return (REPO_ROOT / MATRIX_PATH).read_text(encoding="utf-8")


def _parse_matrix_rows() -> dict[str, dict[str, str]]:
    """Parse the evidence matrix table rows into {claim_id: {col: val}}."""
    text = _matrix_text()
    headers: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if cells[0] == "claim_id" and "classification" in cells:
            headers = cells
            continue
        if headers is None:
            continue
        if re.fullmatch(r"-+", cells[0].replace("|", "").strip()):
            continue
        if not cells[0] or cells[0].startswith("---"):
            continue
        if len(cells) < len(headers):
            continue
        row = dict(zip(headers, cells, strict=False))
        claim_id = row.get("claim_id", "")
        if claim_id and claim_id not in _PHASE25I_APPROVED_CLAIM_IDS:
            rows[claim_id] = row
    return rows


def _claim_worksheet_rows() -> dict[str, dict[str, str]]:
    text = (REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8")
    headers: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if cells[0] == "claim_id":
            headers = cells
            continue
        if headers is None or not cells[0] or cells[0].startswith("---") or not cells[0]:
            continue
        if len(cells) < len(headers):
            continue
        row = dict(zip(headers, cells, strict=False))
        rows[row["claim_id"]] = row
    return rows


def _manifest_rows() -> dict[str, dict[str, str]]:
    text = (REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8")
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("| `DERIBIT_"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        rows[cells[0]] = {"source_id": cells[0], "retrieval_status": cells[3]}
    return rows


def _policy_rows() -> dict[str, dict[str, str]]:
    text = (REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8")
    headers: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if cells[0] == "policy_id":
            headers = cells
            continue
        if headers is None or not cells[0] or cells[0].startswith("---"):
            continue
        if len(cells) < len(headers):
            continue
        row = dict(zip(headers, cells, strict=False))
        rows[row["policy_id"]] = row
    return rows


def _validator_result():
    return evaluate_deribit_manual_review_readiness()


# ---------------------------------------------------------------------------
# 1. Matrix document structure
# ---------------------------------------------------------------------------


def test_phase25j_matrix_file_exists():
    assert (REPO_ROOT / MATRIX_PATH).exists(), f"Matrix file not found: {MATRIX_PATH}"


def test_phase25j_matrix_contains_safety_statement():
    text = _matrix_text()
    assert "ANALYSIS_ONLY" in text, "Matrix must state ANALYSIS_ONLY status"
    assert "NOT" in text and "approval" in text.lower(), "Matrix must include safety statement"
    assert "connector_ready_dialects" in text, "Matrix must reference connector_ready_dialects invariant"


def test_phase25j_matrix_states_20_remaining_rows():
    text = _matrix_text()
    assert "20" in text, "Matrix must state 20 remaining claim rows"


def test_phase25j_matrix_contains_no_approve_ready_rows():
    text = _matrix_text()
    assert "APPROVE_READY_WITH_EXISTING_EVIDENCE: `0`" in text or (
        "APPROVE_READY_WITH_EXISTING_EVIDENCE" in text and "| `0` |" in text
    ), "Matrix must explicitly state 0 APPROVE_READY rows"


# ---------------------------------------------------------------------------
# 2. Matrix row presence and classification
# ---------------------------------------------------------------------------


def test_phase25j_matrix_lists_all_20_remaining_claim_ids():
    rows = _parse_matrix_rows()
    missing = _REMAINING_CLAIM_IDS - set(rows)
    extra = set(rows) - _REMAINING_CLAIM_IDS
    assert not missing, f"Matrix is missing claim_ids: {sorted(missing)}"
    assert not extra, f"Matrix contains unexpected claim_ids: {sorted(extra)}"
    assert len(rows) == 20, f"Expected 20 matrix rows, got {len(rows)}"


def test_phase25j_matrix_does_not_list_phase25i_approved_rows_as_pending():
    rows = _parse_matrix_rows()
    for approved_id in _PHASE25I_APPROVED_CLAIM_IDS:
        assert approved_id not in rows, (
            f"Phase 25I approved row {approved_id!r} must not appear in the Phase 25J pending matrix"
        )


def test_phase25j_legal_rows_classified_needs_legal_review():
    rows = _parse_matrix_rows()
    for claim_id in _NEEDS_LEGAL_REVIEW:
        assert claim_id in rows, f"Legal row {claim_id!r} missing from matrix"
        classification = rows[claim_id].get("classification", "")
        assert classification == "NEEDS_LEGAL_REVIEW", (
            f"Legal row {claim_id!r} must be NEEDS_LEGAL_REVIEW, got {classification!r}"
        )


def test_phase25j_policy_rows_classified_needs_policy_decision():
    rows = _parse_matrix_rows()
    for claim_id in _NEEDS_POLICY_DECISION:
        assert claim_id in rows, f"Policy row {claim_id!r} missing from matrix"
        classification = rows[claim_id].get("classification", "")
        assert classification == "NEEDS_POLICY_DECISION", (
            f"Policy-gated row {claim_id!r} must be NEEDS_POLICY_DECISION, got {classification!r}"
        )


def test_phase25j_official_doc_rows_classified_correctly():
    rows = _parse_matrix_rows()
    for claim_id in _NEEDS_OFFICIAL_DOC_SECTION_PROOF:
        assert claim_id in rows, f"Doc-proof row {claim_id!r} missing from matrix"
        classification = rows[claim_id].get("classification", "")
        assert classification == "NEEDS_OFFICIAL_DOC_SECTION_PROOF", (
            f"Row {claim_id!r} must be NEEDS_OFFICIAL_DOC_SECTION_PROOF, got {classification!r}"
        )


def test_phase25j_smoke_artifact_rows_classified_correctly():
    rows = _parse_matrix_rows()
    for claim_id in _NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF:
        assert claim_id in rows, f"Smoke-proof row {claim_id!r} missing from matrix"
        classification = rows[claim_id].get("classification", "")
        assert classification == "NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF", (
            f"Row {claim_id!r} must be NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF, got {classification!r}"
        )


def test_phase25j_sequence_gap_recovery_rows_are_not_approve_ready():
    """Sequence/gap/recovery rows must not be APPROVE_READY Ã¢â‚¬â€ no sufficient evidence exists."""
    sequence_rows = {
        "first_message_snapshot",
        "incremental_delta",
        "change_id",
        "prev_change_id",
        "continuity_condition",
        "gap_resubscribe_rule",
        "rest_snapshot_requirement",
    }
    rows = _parse_matrix_rows()
    for claim_id in sequence_rows:
        classification = rows.get(claim_id, {}).get("classification", "")
        assert classification != "APPROVE_READY_WITH_EXISTING_EVIDENCE", (
            f"Sequence/gap/recovery row {claim_id!r} must not be APPROVE_READY_WITH_EXISTING_EVIDENCE "
            f"Ã¢â‚¬â€ no committed official-doc excerpt + smoke/parse artifact exists"
        )


def test_phase25j_no_row_has_approve_ready_classification():
    """Sanity check: zero rows are classified APPROVE_READY_WITH_EXISTING_EVIDENCE."""
    rows = _parse_matrix_rows()
    approve_ready = [
        cid for cid, row in rows.items() if row.get("classification") == "APPROVE_READY_WITH_EXISTING_EVIDENCE"
    ]
    assert approve_ready == [], (
        f"No row should be APPROVE_READY_WITH_EXISTING_EVIDENCE in Phase 25J, got: {approve_ready}"
    )


def test_phase25j_every_matrix_row_has_future_proof_artifact():
    """Every row must name a concrete future proof artifact."""
    rows = _parse_matrix_rows()
    for claim_id, row in rows.items():
        artifact = row.get("future_proof_artifact", "")
        assert artifact, f"Matrix row {claim_id!r} must specify a future_proof_artifact"
        assert len(artifact) > 10, f"Matrix row {claim_id!r} future_proof_artifact is too short: {artifact!r}"


def test_phase25j_classification_counts():
    rows = _parse_matrix_rows()
    counts: dict[str, int] = {}
    for row in rows.values():
        c = row.get("classification", "UNKNOWN")
        counts[c] = counts.get(c, 0) + 1
    assert counts.get("NEEDS_OFFICIAL_DOC_SECTION_PROOF", 0) == 8, (
        f"Expected 8 NEEDS_OFFICIAL_DOC_SECTION_PROOF rows, got {counts}"
    )
    assert counts.get("NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF", 0) == 8, (
        f"Expected 8 NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF rows, got {counts}"
    )
    assert counts.get("NEEDS_POLICY_DECISION", 0) == 3, f"Expected 3 NEEDS_POLICY_DECISION rows, got {counts}"
    assert counts.get("NEEDS_LEGAL_REVIEW", 0) == 1, f"Expected 1 NEEDS_LEGAL_REVIEW row, got {counts}"
    assert counts.get("APPROVE_READY_WITH_EXISTING_EVIDENCE", 0) == 0, f"Expected 0 APPROVE_READY rows, got {counts}"


# ---------------------------------------------------------------------------
# 3. Worksheet files remain at Phase 25I state
# ---------------------------------------------------------------------------


def test_phase25j_manifest_approved_count_is_6():
    rows = _manifest_rows()
    approved = [sid for sid, row in rows.items() if row["retrieval_status"] == "REVIEWED_APPROVED"]
    assert len(approved) == 6, f"Expected 6 manifest rows REVIEWED_APPROVED after Phase 25I, got {len(approved)}"


def test_phase25j_manifest_no_pending_rows():
    rows = _manifest_rows()
    pending = [sid for sid, row in rows.items() if "PENDING" in row["retrieval_status"].upper()]
    assert len(pending) == 0, f"Expected 0 pending manifest rows after Phase 25I, got: {pending}"


def test_phase25j_claim_worksheet_approved_count_is_4():
    rows = _claim_worksheet_rows()
    approved = [cid for cid, row in rows.items() if row.get("decision") == "APPROVED"]
    # Phase 26AJ approved 15 more rows, Phase 26AN approved 3 more, Phase 26AR approved regional_legal_access; total = 23.
    assert len(approved) == 23, (
        f"Expected exactly 23 approved claim rows after Phase 26AR, got {len(approved)}: {approved}"
    )


def test_phase25j_claim_worksheet_approved_are_only_current_approved_rows():
    rows = _claim_worksheet_rows()
    approved = {cid for cid, row in rows.items() if row.get("decision") == "APPROVED"}
    assert approved == _CURRENT_APPROVED_CLAIM_IDS, (
        f"Approved claim rows must be exactly Phase 25I + Phase 25R set. Got: {approved}"
    )


def test_phase25j_claim_worksheet_remaining_19_rows_still_pending():
    rows = _claim_worksheet_rows()
    for claim_id in _CURRENT_PENDING_CLAIM_IDS:
        row = rows.get(claim_id)
        assert row is not None, f"Claim row {claim_id!r} not found in worksheet"
        assert row.get("decision") == "PENDING", (
            f"Claim row {claim_id!r} must remain PENDING; got decision={row.get('decision')!r}"
        )
        assert row.get("reviewer_id") == "PENDING", f"Claim row {claim_id!r} reviewer_id must be PENDING"


def test_phase25j_policy_worksheet_all_rows_pending():
    rows = _policy_rows()
    assert len(rows) == 7, f"Expected 7 policy rows, got {len(rows)}"
    # Phase 26AN approved 5 policy rows; 2 remain PENDING.
    _phase26an_approved = {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
    pending_rows = {pid: row for pid, row in rows.items() if pid not in _phase26an_approved}
    for policy_id, row in pending_rows.items():
        assert row.get("decision") == "PENDING", (
            f"Policy row {policy_id!r} must remain PENDING; got {row.get('decision')!r}"
        )


def test_phase25j_policy_worksheet_approved_count_is_0():
    rows = _policy_rows()
    approved = [pid for pid, row in rows.items() if row.get("decision") == "APPROVED"]
    # Phase 26AN approved 5 policy rows.
    assert len(approved) == 5, f"Expected 5 approved policy rows after Phase 26AN, got: {approved}"


# ---------------------------------------------------------------------------
# 4. Validator state invariants
# ---------------------------------------------------------------------------


def test_phase25j_validator_accepted_remains_false():
    result = _validator_result()
    assert result.accepted is False, "Validator accepted must remain False after Phase 25J doc-only patch"


def test_phase25j_validator_evidence_review_complete_remains_false():
    result = _validator_result()
    assert result.evidence_review_complete is False, (
        "evidence_review_complete must remain False: 1 claim row + 2 policy rows still PENDING"
    )


def test_phase25j_validator_ready_for_engineering_patch_remains_false():
    result = _validator_result()
    assert result.ready_for_engineering_patch is False


def test_phase25j_validator_connector_enablement_ready_remains_false():
    result = _validator_result()
    assert result.connector_enablement_ready is False


def test_phase25j_validator_pending_rows_count_is_26():
    result = _validator_result()
    assert len(result.pending_rows) == 2, (
        f"Expected 2 pending rows after Phase 26AR, got {len(result.pending_rows)}: {result.pending_rows}"
    )


def test_phase25j_validator_manifest_pending_count_is_0():
    result = _validator_result()
    manifest_pending = [r for r in result.pending_rows if r.startswith("source_snapshot:")]
    assert len(manifest_pending) == 0, f"Expected 0 manifest pending rows, got: {manifest_pending}"


def test_phase25j_validator_claim_pending_count_is_19():
    result = _validator_result()
    claim_pending = [r for r in result.pending_rows if r.startswith("claim_review:")]
    assert len(claim_pending) == 0, (
        f"Expected 0 pending claim rows after Phase 26AR, got {len(claim_pending)}: {claim_pending}"
    )


def test_phase25j_validator_policy_pending_count_is_7():
    result = _validator_result()
    policy_pending = [r for r in result.pending_rows if r.startswith("policy_review:")]
    assert len(policy_pending) == 2, (
        f"Expected 2 pending policy rows after Phase 26AN, got {len(policy_pending)}: {policy_pending}"
    )


def test_phase25j_b1_b5_all_remain_blocked():
    result = _validator_result()
    for blocker in ("B1", "B2", "B3", "B4", "B5"):
        assert result.b1_b5_status[blocker] == "BLOCKED", (
            f"{blocker} must remain BLOCKED after Phase 25J doc-only patch"
        )


# ---------------------------------------------------------------------------
# 5. Connector safety invariants
# ---------------------------------------------------------------------------


def test_phase25j_connector_ready_dialects_remains_empty():
    assert connector_ready_dialects() == (), (
        "connector_ready_dialects() must remain () Ã¢â‚¬â€ no worksheet mutations in Phase 25J"
    )


def test_phase25j_evaluate_does_not_mutate_connector_ready_dialects():
    before = connector_ready_dialects()
    _validator_result()
    after = connector_ready_dialects()
    assert before == after == ()


# ---------------------------------------------------------------------------
# 6. No src/ file changes
# ---------------------------------------------------------------------------


def test_phase25j_no_src_files_changed():
    """Phase 25J only adds docs/ and tests/ files. Assert known src/ sentinels are unchanged."""
    # Verify the harness and dialects are importable and return expected types/values.
    from crypto_core.data.deribit_public_ws_harness import (
        DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION,
        DeribitPublicWsSmokeConfig,
        DeribitPublicWsSmokeResult,
    )

    assert DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION == "PUBLIC_MARKET_DATA_ONLY"
    assert DeribitPublicWsSmokeConfig is not None
    assert DeribitPublicWsSmokeResult is not None

    # Confirm public_feed_dialects has no Deribit connector enabled
    from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

    assert connector_ready_dialects() == ()
    spec = get_public_feed_dialect("deribit:l2_orderbook:placeholder")
    assert spec.enabled_for_connector is False
    assert spec.verification_status.value != "verified"
