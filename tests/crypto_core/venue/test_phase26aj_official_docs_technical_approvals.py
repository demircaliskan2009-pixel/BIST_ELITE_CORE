"""Phase 26AJ official docs technical row approval worksheet tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSHEET_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_CLAIM_REVIEW_WORKSHEET.md"
)
POLICY_WORKSHEET_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)

APPROVED_IN_26AJ = (
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

STILL_PENDING_CLAIM: tuple[str, ...] = (
    # regional_legal_access was approved in Phase 26AR
    # checksum_decision, staleness_budget, receive_lag_budget were approved in Phase 26AN
    # All 23 claim rows are now APPROVED
)

PRIOR_APPROVED_ROWS = (
    "public_websocket_availability",
    "unauthenticated_public_market_data",
    "orderbook_channel_feed",
    "change_id",
)


def _worksheet() -> str:
    return WORKSHEET_PATH.read_text(encoding="utf-8")


def _policy_worksheet() -> str:
    return POLICY_WORKSHEET_PATH.read_text(encoding="utf-8")


def test_phase26aj_worksheet_exists() -> None:
    assert WORKSHEET_PATH.exists()


def test_phase26aj_approved_rows_count_15() -> None:
    assert len(APPROVED_IN_26AJ) == 15


def test_phase26aj_all_15_rows_have_approved_status() -> None:
    text = _worksheet()
    for row_id in APPROVED_IN_26AJ:
        # Each approved row line must contain APPROVED and demir_operator
        lines = [ln for ln in text.splitlines() if row_id in ln and "|" in ln]
        assert lines, f"Row {row_id!r} not found in worksheet"
        row_line = lines[0]
        assert "APPROVED" in row_line, f"Row {row_id!r} must be APPROVED"
        assert "demir_operator" in row_line, f"Row {row_id!r} must have reviewer_id demir_operator"
        assert "2026-05-19T00:00:00Z" in row_line, f"Row {row_id!r} must have reviewed_at_iso 2026-05-19T00:00:00Z"


def test_phase26aj_all_15_rows_cite_26ai_scope() -> None:
    text = _worksheet()
    for row_id in APPROVED_IN_26AJ:
        lines = [ln for ln in text.splitlines() if row_id in ln and "|" in ln]
        assert lines
        row_line = lines[0]
        assert "Phase26AI_OFFICIAL_DOCS_TECHNICAL_ROWS_ONLY" in row_line, (
            f"Row {row_id!r} must cite Phase26AI_OFFICIAL_DOCS_TECHNICAL_ROWS_ONLY"
        )


def test_phase26aj_all_15_rows_cite_evidence_refs() -> None:
    text = _worksheet()
    for row_id in APPROVED_IN_26AJ:
        lines = [ln for ln in text.splitlines() if row_id in ln and "|" in ln]
        assert lines
        row_line = lines[0]
        assert "DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE" in row_line, f"Row {row_id!r} must cite 26AE evidence"


def test_phase26aj_all_15_rows_preserve_source_hash() -> None:
    text = _worksheet()
    source_hash = "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"
    for row_id in APPROVED_IN_26AJ:
        lines = [ln for ln in text.splitlines() if row_id in ln and "|" in ln]
        assert lines
        row_line = lines[0]
        assert source_hash in row_line, f"Row {row_id!r} must preserve source_hash_refs"


def test_phase26aj_still_pending_claim_rows() -> None:
    text = _worksheet()
    for row_id in STILL_PENDING_CLAIM:
        lines = [ln for ln in text.splitlines() if row_id in ln and "|" in ln]
        assert lines, f"Row {row_id!r} must still be in worksheet"
        row_line = lines[0]
        assert "PENDING" in row_line, f"Row {row_id!r} must remain PENDING"


def test_phase26aj_regional_legal_access_now_approved_in_phase26ar() -> None:
    text = _worksheet()
    lines = [ln for ln in text.splitlines() if "regional_legal_access" in ln and "|" in ln]
    assert lines
    for line in lines:
        if "regional_legal_access" in line:
            assert "APPROVED" in line, "regional_legal_access must be APPROVED after Phase 26AR"


def test_phase26aj_checksum_decision_approved_in_phase26an() -> None:
    # checksum_decision was approved in Phase 26AN (after Phase 26AJ)
    text = _worksheet()
    lines = [ln for ln in text.splitlines() if "checksum_decision" in ln and "|" in ln]
    assert lines
    approved_lines = [ln for ln in lines if "APPROVED" in ln]
    assert approved_lines, "checksum_decision claim row must be APPROVED (Phase 26AN)"


def test_phase26aj_prior_approved_rows_unchanged() -> None:
    text = _worksheet()
    for row_id in PRIOR_APPROVED_ROWS:
        lines = [ln for ln in text.splitlines() if row_id in ln and "|" in ln]
        assert lines, f"Prior approved row {row_id!r} must still be in worksheet"
        row_line = lines[0]
        assert "APPROVED" in row_line, f"Prior approved row {row_id!r} must remain APPROVED"


def test_phase26aj_policy_worksheet_untouched() -> None:
    text = _policy_worksheet()
    # Phase 26AN approved 5 policy rows; Phase 26AW resolved the remaining 2
    _phase26an_approved = {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
    for policy_id in (
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
        "regional_legal_access_review",
        "separate_connector_enablement",
    ):
        lines = [ln for ln in text.splitlines() if policy_id in ln and "|" in ln]
        assert lines, f"Policy row {policy_id!r} must exist"
        row_line = lines[0]
        if policy_id in _phase26an_approved:
            assert "APPROVED" in row_line, f"Policy row {policy_id!r} was approved in Phase 26AN"
        elif policy_id == "regional_legal_access_review":
            assert "APPROVE" in row_line, f"Policy row {policy_id!r} must be APPROVED after Phase 26AW"
        elif policy_id == "separate_connector_enablement":
            assert "APPROVE" in row_line, f"Policy row {policy_id!r} must be APPROVED after Phase 27F"


def test_phase26aj_no_enabled_for_connector_true() -> None:
    text = _worksheet()
    assert "enabled_for_connector: true" not in text.lower()
    assert "`enabled_for_connector`: `true`" not in text


def test_phase26aj_no_static_registry_verified_true() -> None:
    text = _worksheet()
    assert "static_registry_verified: true" not in text.lower()


def test_phase26aj_enabled_for_connector_false() -> None:
    text = _worksheet()
    assert "enabled_for_connector" in text
    # Must remain false
    lines = [ln for ln in text.splitlines() if "enabled_for_connector" in ln]
    for line in lines:
        assert "false" in line.lower(), "enabled_for_connector must remain false"


def test_phase26aj_total_approved_claim_rows_19() -> None:
    """4 prior + 15 new = 19 approved claim rows."""
    text = _worksheet()
    # Count rows with APPROVED status and demir_operator
    approved_lines = [
        ln for ln in text.splitlines() if "|" in ln and "APPROVED" in ln and "demir_operator" in ln and "`" in ln
    ]
    # 4 prior + 15 new = 19
    assert len(approved_lines) >= 19, f"Expected at least 19 approved claim rows, got {len(approved_lines)}"
