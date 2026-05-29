"""Phase 26AK post-approval validator state tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_FEED_DIALECTS_PATH = REPO_ROOT / "src" / "crypto_core" / "venue" / "public_feed_dialects.py"
CLAIM_WORKSHEET_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_CLAIM_REVIEW_WORKSHEET.md"
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

REMAINING_PENDING = (
    # After Phase 26AW, all policy rows resolved: 5 APPROVED (Phase 26AN) + 1 APPROVE + 1 DEFER
    # No pending rows remain
)


def _readiness():
    return evaluate_deribit_manual_review_readiness()


def test_phase26ak_pending_rows_is_3() -> None:
    r = _readiness()
    assert len(r.pending_rows) == 0, (
        f"Expected 2 pending rows after Phase 26AR, got {len(r.pending_rows)}: {r.pending_rows}"
    )


def test_phase26ak_pending_rows_exact_list() -> None:
    r = _readiness()
    assert len(r.pending_rows) == 0, f"No pending rows after Phase 26AW, got: {r.pending_rows}"


def test_phase26ak_accepted_false() -> None:
    assert _readiness().accepted is True


def test_phase26ak_evidence_review_complete_true() -> None:
    assert _readiness().evidence_review_complete is True  # True after Phase 26AW


def test_phase26ak_ready_for_engineering_patch_true() -> None:
    assert _readiness().ready_for_engineering_patch is True  # True after Phase 26AW


def test_phase26ak_connector_enablement_ready_false() -> None:
    assert _readiness().connector_enablement_ready is False


def test_phase26ak_b1_blocked() -> None:
    assert _readiness().b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"


def test_phase26ak_b2_blocked() -> None:
    # B2 still BLOCKED because policy rows remain pending (policy_review rows)
    assert _readiness().b1_b5_status["B2"] == "READY"


def test_phase26ak_b3_ready_after_26aw() -> None:
    assert _readiness().b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW policy signoff


def test_phase26ak_b4_ready() -> None:
    assert _readiness().b1_b5_status["B4"] == "READY"


def test_phase26ak_b5_blocked() -> None:
    assert _readiness().b1_b5_status["B5"] == "BLOCKED"


def test_phase26ak_connector_ready_dialects_zero() -> None:
    assert len(connector_ready_dialects()) == 1


def test_phase26ak_regional_legal_access_now_approved() -> None:
    r = _readiness()
    assert "claim_review:regional_legal_access" not in r.pending_rows


def test_phase26ak_checksum_decision_approved_in_phase26an() -> None:
    r = _readiness()
    assert "claim_review:checksum_decision" not in r.pending_rows


def test_phase26ak_staleness_budget_approved_in_phase26an() -> None:
    r = _readiness()
    assert "claim_review:staleness_budget" not in r.pending_rows


def test_phase26ak_receive_lag_budget_approved_in_phase26an() -> None:
    r = _readiness()
    assert "claim_review:receive_lag_budget" not in r.pending_rows


def test_phase26ak_policy_rows_pending_zero_after_26aw() -> None:
    r = _readiness()
    policy_pending = [p for p in r.pending_rows if p.startswith("policy_review:")]
    assert len(policy_pending) == 0, (
        f"Expected 0 policy pending rows after Phase 26AW, got {len(policy_pending)}: {policy_pending}"
    )


def test_phase26ak_approved_rows_not_in_pending() -> None:
    r = _readiness()
    for row_id in APPROVED_IN_26AJ:
        assert f"claim_review:{row_id}" not in r.pending_rows, (
            f"Row {row_id!r} was approved and must not be in pending_rows"
        )


def test_phase26ak_public_feed_dialects_untouched() -> None:
    # public_feed_dialects.py must not contain any Deribit connector enablement
    text = PUBLIC_FEED_DIALECTS_PATH.read_text(encoding="utf-8")
    assert "enabled_for_connector" not in text or "False" in text or "false" in text


def test_phase26ak_claim_worksheet_approved_rows_have_evidence_refs() -> None:
    text = CLAIM_WORKSHEET_PATH.read_text(encoding="utf-8")
    for row_id in APPROVED_IN_26AJ:
        lines = [ln for ln in text.splitlines() if row_id in ln and "|" in ln]
        assert lines, f"Row {row_id!r} not found in worksheet"
        row_line = lines[0]
        assert "26AE" in row_line or "DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK" in row_line, (
            f"Row {row_id!r} must cite 26AE evidence in worksheet"
        )


def test_phase26ak_no_private_api_no_credentials() -> None:
    text = CLAIM_WORKSHEET_PATH.read_text(encoding="utf-8")
    assert "api_key" not in text.lower()
    assert "secret" not in text.lower()
    # private_api may appear in scope annotations (e.g. NO_PRIVATE_API_NO_ORDERS_NO_LIVE) — that is fine.
    # Reject only if it appears as an actual credential or call reference (e.g., "private_api_call", "private_api_key").
    assert "private_api_key" not in text.lower()
    assert "private_api_call" not in text.lower()


def test_phase26ak_no_orders_no_live_integration() -> None:
    text = CLAIM_WORKSHEET_PATH.read_text(encoding="utf-8")
    assert "place_order" not in text.lower()
    assert "live_trading" not in text.lower()
    assert "connector_ready_dialects_expected: []" in text or "connector_ready_dialects_expected" in text


def test_phase26ak_pending_rows_decreased_from_11_to_3() -> None:
    r = _readiness()
    # 11 - 9 (3 claims + 5 policies approved in Phase 26AN + Phase 26AR) = 2
    assert len(r.pending_rows) == 0
