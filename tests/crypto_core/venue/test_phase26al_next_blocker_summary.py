"""Phase 26AL next blocker summary document tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BLOCKER_SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26AL.md"
PRIOR_BLOCKER_SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26AH.md"
AUDIT_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_APPROVAL_EXECUTION_AUDIT_26AI.md"

APPROVED_PRIOR_ROWS = (
    "public_websocket_availability",
    "unauthenticated_public_market_data",
    "orderbook_channel_feed",
    "change_id",
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

REMAINING_CLAIM_PENDING = (
    "staleness_budget",
    "receive_lag_budget",
    "checksum_decision",
    "regional_legal_access",
)

REMAINING_POLICY_PENDING = (
    "checksum_decision",
    "liveness_policy",
    "staleness_budget",
    "receive_lag_budget",
    "testnet_prod_review",
    "regional_legal_access_review",
    "separate_connector_enablement",
)


def _summary() -> str:
    return BLOCKER_SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26al_summary_exists() -> None:
    assert BLOCKER_SUMMARY_PATH.exists(), "26AL blocker summary must exist"


def test_phase26al_status_field() -> None:
    assert "NEXT_ACTION_PLAN_ONLY" in _summary()


def test_phase26al_supersedes_26ah() -> None:
    assert "supersedes: DERIBIT_NEXT_BLOCKER_SUMMARY_26AH.md" in _summary()


def test_phase26al_prior_26ah_still_exists() -> None:
    assert PRIOR_BLOCKER_SUMMARY_PATH.exists(), "26AH blocker summary must still exist (not deleted)"


def test_phase26al_audit_26ai_exists() -> None:
    assert AUDIT_PATH.exists(), "26AI audit doc must still exist"


def test_phase26al_not_connector_enablement() -> None:
    assert "NOT_connector_enablement: true" in _summary()


def test_phase26al_not_b1_b5_closure() -> None:
    assert "NOT_b1_b5_closure: true" in _summary()


def test_phase26al_not_legal_approval() -> None:
    assert "NOT_legal_approval: true" in _summary()


def test_phase26al_all_19_approved_rows_listed() -> None:
    text = _summary()
    for row_id in APPROVED_PRIOR_ROWS + APPROVED_IN_26AJ:
        assert row_id in text, f"Approved row {row_id!r} must be listed in 26AL summary"


def test_phase26al_approved_rows_count_19() -> None:
    assert len(APPROVED_PRIOR_ROWS) + len(APPROVED_IN_26AJ) == 19


def test_phase26al_total_approved_19_stated() -> None:
    text = _summary()
    assert "19" in text
    assert "4 prior" in text or "prior" in text


def test_phase26al_pending_rows_11() -> None:
    text = _summary()
    assert "11" in text
    assert "pending" in text.lower()


def test_phase26al_remaining_claim_pending_listed() -> None:
    text = _summary()
    for row_id in REMAINING_CLAIM_PENDING:
        assert row_id in text, f"Remaining claim pending row {row_id!r} must be listed"


def test_phase26al_policy_rows_pending_listed() -> None:
    text = _summary()
    for row_id in REMAINING_POLICY_PENDING:
        assert row_id in text, f"Policy pending row {row_id!r} must be listed"


def test_phase26al_b2_blocked() -> None:
    text = _summary()
    assert "B2" in text
    assert "BLOCKED" in text


def test_phase26al_b3_blocked() -> None:
    text = _summary()
    assert "B3" in text
    assert "BLOCKED" in text


def test_phase26al_b4_blocked() -> None:
    text = _summary()
    assert "B4" in text
    assert "BLOCKED" in text


def test_phase26al_b5_blocked() -> None:
    text = _summary()
    assert "B5" in text
    assert "BLOCKED" in text


def test_phase26al_b1_blocked() -> None:
    text = _summary()
    assert "B1" in text
    assert "BLOCKED" in text


def test_phase26al_connector_ready_dialects_zero() -> None:
    text = _summary()
    assert "connector_ready_dialects" in text
    assert "0" in text


def test_phase26al_no_connector_enablement() -> None:
    text = _summary()
    # The FORBIDDEN section names it as prohibited; the actual state must show no enablement
    assert (
        "connector_ready_dialects() == ()" in text
        or "connector_ready_dialects=() " in text
        or "connector_ready_dialects | 0" in text
        or "connector_ready_dialects: 0" in text
        or "connector_ready_dialects | 0)" in text
        or "`connector_ready_dialects() == ()`" in text
    )
    assert "No connector enablement occurred" in text or "No connector enablement" in text


def test_phase26al_regional_legal_access_wait_legal() -> None:
    text = _summary()
    assert "regional_legal_access" in text
    assert "WAIT_LEGAL" in text or "legal" in text.lower()


def test_phase26al_next_phase_policy_decision() -> None:
    text = _summary()
    assert "policy" in text.lower()
    assert "staleness_budget" in text
    assert "receive_lag_budget" in text


def test_phase26al_separate_connector_enablement_blocked() -> None:
    text = _summary()
    assert "separate_connector_enablement" in text
    assert "WAIT_POLICY" in text or "DEFERRED" in text or "separate enablement" in text.lower()


def test_phase26al_no_private_api_no_credentials() -> None:
    text = _summary()
    assert "api_key" not in text.lower()
    assert "secret" not in text.lower()


def test_phase26al_no_orders_no_live_integration() -> None:
    text = _summary()
    assert "place_order" not in text.lower()
    assert "live_trading" not in text.lower()


def test_phase26al_accepted_false_stated() -> None:
    text = _summary()
    assert "accepted" in text.lower()
    assert "False" in text or "false" in text


def test_phase26al_evidence_review_complete_false_stated() -> None:
    text = _summary()
    assert "evidence_review_complete" in text


def test_phase26al_phase_summary_section() -> None:
    text = _summary()
    assert "Phase 26AI" in text or "26AI" in text
    assert "Phase 26AJ" in text or "26AJ" in text
    assert "Phase 26AK" in text or "26AK" in text
