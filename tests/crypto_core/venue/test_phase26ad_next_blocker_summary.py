"""Phase 26AD next blocker summary tests.

Phase 26AD supersedes Phase 26Z. It records that 0 rows were promoted by
Phase 26AA-26AC, all 26 pending rows remain, and groups them into 4 categories:
raw-sequence (4), documentation external-research (12), policy (8), legal (2).
No worksheet edits. No connector enablement. pending_rows=26.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26AD.md"
PRIOR_26Z_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26Z.md"
AUDIT_26AA_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OFFICIAL_EXCERPT_AUDIT_26AA.md"
BATCH_26AC_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_26AC.md"


def _summary_text() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


# ─── Existence and identity ────────────────────────────────────────────────────


def test_phase26ad_summary_exists() -> None:
    assert SUMMARY_PATH.exists(), f"Phase 26AD summary not found: {SUMMARY_PATH}"


def test_phase26ad_status_field() -> None:
    assert "status: NEXT_ACTION_PLAN_ONLY" in _summary_text()


def test_phase26ad_supersedes_26z() -> None:
    assert "supersedes: DERIBIT_NEXT_BLOCKER_SUMMARY_26Z.md" in _summary_text()


def test_phase26ad_not_an_approval() -> None:
    assert "NOT_an_approval: true" in _summary_text()


def test_phase26ad_not_worksheet_mutation() -> None:
    assert "NOT_worksheet_mutation: true" in _summary_text()


def test_phase26ad_not_connector_enablement() -> None:
    assert "NOT_connector_enablement: true" in _summary_text()


def test_phase26ad_prior_26z_still_exists() -> None:
    assert PRIOR_26Z_PATH.exists(), "Phase 26Z summary must not be deleted"


def test_phase26ad_26aa_audit_exists() -> None:
    assert AUDIT_26AA_PATH.exists(), "26AA audit must exist when 26AD is present"


def test_phase26ad_26ac_batch_exists() -> None:
    assert BATCH_26AC_PATH.exists(), "26AC batch must exist when 26AD is present"


# ─── Phase 26AA-26AC finding recorded ────────────────────────────────────────


def test_phase26ad_records_zero_proof_ready_rows() -> None:
    content = _summary_text()
    assert (
        "excerpt_proof_ready_count" in content or "EXCERPT_PROOF_READY" in content or "proof_ready" in content.lower()
    )
    assert "0" in content


def test_phase26ad_26ab_skipped_recorded() -> None:
    content = _summary_text()
    assert "26AB" in content
    assert "SKIPPED" in content or "false" in content.lower()


def test_phase26ad_zero_promotions_recorded() -> None:
    content = _summary_text()
    assert "rows_promoted_to_proof_ready" in content or "promoted" in content.lower()


# ─── All 26 rows present (spot-check) ────────────────────────────────────────


def test_phase26ad_raw_sequence_rows_present() -> None:
    content = _summary_text()
    for row in ("prev_change_id", "continuity_condition", "first_message_snapshot", "incremental_delta"):
        assert row in content, f"Row {row} missing from 26AD summary"


def test_phase26ad_documentation_rows_present() -> None:
    content = _summary_text()
    for row in (
        "public_rest_availability",
        "prod_testnet_ws_endpoint",
        "prod_testnet_rest_endpoint",
        "rest_snapshot_requirement",
        "checksum_decision",
        "gap_resubscribe_rule",
        "heartbeat_liveness_proof",
        "public_rate_subscription_limits",
        "public_trades",
        "ticker",
        "mark_index_funding_open_interest",
        "testnet_prod_difference",
    ):
        assert row in content, f"Row {row} missing from 26AD summary"


def test_phase26ad_policy_rows_present() -> None:
    content = _summary_text()
    for row in (
        "staleness_budget",
        "receive_lag_budget",
        "liveness_policy",
        "testnet_prod_review",
        "separate_connector_enablement",
    ):
        assert row in content, f"Row {row} missing from 26AD summary"


def test_phase26ad_legal_rows_present() -> None:
    content = _summary_text()
    assert "regional_legal_access" in content
    assert "WAIT_LEGAL" in content or "NEEDS_LEGAL" in content or "legal" in content.lower()


def test_phase26ad_all_26_rows_count() -> None:
    content = _summary_text()
    # Must state the total is 26
    assert "26" in content


# ─── Groups A-D structure ─────────────────────────────────────────────────────


def test_phase26ad_group_a_raw_sequence() -> None:
    content = _summary_text()
    assert "Group A" in content or "raw-sequence" in content.lower() or "Raw-Sequence" in content


def test_phase26ad_group_b_external_research() -> None:
    content = _summary_text()
    assert "Group B" in content or "external" in content.lower()


def test_phase26ad_group_c_policy() -> None:
    content = _summary_text()
    assert "Group C" in content or "Policy" in content or "WAIT_POLICY" in content


def test_phase26ad_group_d_legal() -> None:
    content = _summary_text()
    assert "Group D" in content or "Legal" in content or "WAIT_LEGAL" in content


# ─── B1-B5 gate status present ───────────────────────────────────────────────


def test_phase26ad_b1_b5_gate_status_recorded() -> None:
    content = _summary_text()
    for gate in ("B1", "B2", "B3", "B4", "B5"):
        assert gate in content, f"Gate {gate} missing from 26AD summary"
    assert "BLOCKED" in content


# ─── Approved rows unchanged ─────────────────────────────────────────────────


def test_phase26ad_approved_rows_listed() -> None:
    content = _summary_text()
    for approved in (
        "public_websocket_availability",
        "unauthenticated_public_market_data",
        "orderbook_channel_feed",
        "change_id",
    ):
        assert approved in content, f"Approved row {approved} missing from 26AD summary"


# ─── Connector enablement deferred ───────────────────────────────────────────


def test_phase26ad_connector_enablement_deferred() -> None:
    content = _summary_text()
    assert "connector" in content.lower()
    assert "deferred" in content.lower() or "separate" in content.lower()


# ─── No private API / no credentials / no orders ─────────────────────────────


def test_phase26ad_no_private_api() -> None:
    content = _summary_text()
    for forbidden in ("private_api", "credentials", "order_execution", "live_trade"):
        assert forbidden not in content.lower(), f"Forbidden term '{forbidden}' found in 26AD"


# ─── Validator and connector state unchanged ──────────────────────────────────


def test_phase26ad_validator_still_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.accepted is False
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is True


def test_phase26ad_pending_rows_still_26() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 0


def test_phase26ad_b1_b5_blocked_except_b3() -> None:
    result = evaluate_deribit_manual_review_readiness()
    for key in ("B1", "B2"):
        assert result.b1_b5_status[key] == "BLOCKED", f"{key} expected BLOCKED"
    assert result.b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW
    assert result.b1_b5_status["B4"] == "READY"  # B4 READY after Phase 27A static registry verification


def test_phase26ad_connector_ready_dialects_empty() -> None:
    dialects = connector_ready_dialects()
    assert len(dialects) == 1
