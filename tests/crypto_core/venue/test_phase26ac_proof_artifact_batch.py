"""Phase 26AC proof artifact batch tests.

Phase 26AC records that 0 rows are promoted to PROOF_READY_NOT_APPROVED.
All 26 rows remain at WAIT_INSUFFICIENT / WAIT_POLICY / WAIT_LEGAL.
Phase 26AB was SKIPPED (no excerpt-proof-ready rows).
No operator fill proposal was created.
No worksheet edits. No connector enablement. pending_rows=26.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_26AC.md"
AUDIT_26AA_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OFFICIAL_EXCERPT_AUDIT_26AA.md"
PRIOR_26Z_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26Z.md"
# Phase 26AB should NOT exist
BATCH_26AB_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OFFICIAL_EXCERPT_PROOF_BATCH_26AB.md"
# Operator fill proposal should NOT exist
OPERATOR_PROPOSAL_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26AC.md"


def _batch_text() -> str:
    return BATCH_PATH.read_text(encoding="utf-8")


# ─── Existence and identity ────────────────────────────────────────────────────


def test_phase26ac_batch_exists() -> None:
    assert BATCH_PATH.exists(), f"26AC batch not found: {BATCH_PATH}"


def test_phase26ac_status_field() -> None:
    assert "status: CLASSIFICATION_BATCH_ONLY" in _batch_text()


def test_phase26ac_not_an_approval() -> None:
    assert "NOT_an_approval: true" in _batch_text()


def test_phase26ac_not_worksheet_mutation() -> None:
    assert "NOT_worksheet_mutation: true" in _batch_text()


def test_phase26ac_not_connector_enablement() -> None:
    assert "NOT_connector_enablement: true" in _batch_text()


def test_phase26ac_26aa_exists() -> None:
    assert AUDIT_26AA_PATH.exists(), "26AA audit must exist before 26AC batch"


def test_phase26ac_prior_26z_still_exists() -> None:
    assert PRIOR_26Z_PATH.exists(), "Phase 26Z summary must not be deleted"


# ─── Phase 26AB not created ───────────────────────────────────────────────────


def test_phase26ab_not_created() -> None:
    """Phase 26AB excerpt proof batch must NOT exist — no proof-ready rows."""
    assert not BATCH_26AB_PATH.exists(), f"Phase 26AB must not exist (no proof-ready rows): {BATCH_26AB_PATH}"


def test_phase26ac_26ab_skipped_noted_in_batch() -> None:
    content = _batch_text()
    assert "26AB" in content
    assert "SKIPPED" in content


# ─── Operator fill proposal not created ───────────────────────────────────────


def test_phase26ac_operator_fill_proposal_not_created() -> None:
    """No operator fill proposal because 0 proof-ready rows."""
    assert not OPERATOR_PROPOSAL_PATH.exists(), (
        f"Operator fill proposal must not exist (no proof-ready rows): {OPERATOR_PROPOSAL_PATH}"
    )


# ─── Zero promotions ─────────────────────────────────────────────────────────


def test_phase26ac_zero_proof_ready_not_approved() -> None:
    content = _batch_text()
    assert "PROOF_READY_NOT_APPROVED" in content
    # Must state 0 rows promoted
    assert "0" in content


def test_phase26ac_no_reviewer_id_filled() -> None:
    content = _batch_text()
    assert "reviewer_id=<OPERATOR_REQUIRED>" not in content
    assert "reviewed_at_iso=<OPERATOR_REQUIRED>" not in content


# ─── All 4 raw-sequence rows recorded WAIT_INSUFFICIENT ──────────────────────


def test_phase26ac_raw_sequence_rows_wait_insufficient() -> None:
    content = _batch_text()
    for row in (
        "prev_change_id",
        "continuity_condition",
        "first_message_snapshot",
        "incremental_delta",
    ):
        assert row in content, f"Row {row} missing from 26AC batch"
    assert "WAIT_INSUFFICIENT" in content


# ─── Key documentation rows recorded ─────────────────────────────────────────


def test_phase26ac_documentation_rows_recorded() -> None:
    content = _batch_text()
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
        assert row in content, f"Row {row} missing from 26AC batch"


def test_phase26ac_policy_rows_wait_policy() -> None:
    content = _batch_text()
    assert "staleness_budget" in content
    assert "receive_lag_budget" in content
    assert "WAIT_POLICY" in content


def test_phase26ac_legal_rows_wait_legal() -> None:
    content = _batch_text()
    assert "regional_legal_access" in content
    assert "WAIT_LEGAL" in content


def test_phase26ac_separate_connector_enablement_wait_policy() -> None:
    content = _batch_text()
    assert "separate_connector_enablement" in content


# ─── Total 26 rows ────────────────────────────────────────────────────────────


def test_phase26ac_total_26_rows() -> None:
    content = _batch_text()
    assert "26" in content


# ─── Validator and connector state unchanged ──────────────────────────────────


def test_phase26ac_validator_still_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.accepted is False
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is False


def test_phase26ac_pending_rows_still_26() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 0


def test_phase26ac_b1_b5_blocked_except_b3() -> None:
    result = evaluate_deribit_manual_review_readiness()
    for key in ("B1", "B2", "B4", "B5"):
        assert result.b1_b5_status[key] == "BLOCKED", f"{key} expected BLOCKED"
    assert result.b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW


def test_phase26ac_connector_ready_dialects_empty() -> None:
    dialects = connector_ready_dialects()
    assert len(dialects) == 0
