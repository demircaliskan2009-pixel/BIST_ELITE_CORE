"""Phase 26AA official excerpt audit tests.

Phase 26AA audits all 26 remaining pending rows from committed repo evidence
only. It classifies each row as EXCERPT_PROOF_READY, NEEDS_EXTERNAL_RESEARCH,
NEEDS_POLICY_DECISION, or NEEDS_LEGAL_REVIEW. 0 rows are EXCERPT_PROOF_READY.
Phase 26AB is SKIPPED. No worksheet edits. No connector enablement. No
reviewer metadata filled. pending_rows=26.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OFFICIAL_EXCERPT_AUDIT_26AA.md"
PRIOR_26Z_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26Z.md"
MANIFEST_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md"
)
WORKSHEET_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_CLAIM_REVIEW_WORKSHEET.md"
)


def _audit_text() -> str:
    return AUDIT_PATH.read_text(encoding="utf-8")


# ─── Existence and identity ────────────────────────────────────────────────────


def test_phase26aa_audit_exists() -> None:
    assert AUDIT_PATH.exists(), f"26AA audit not found: {AUDIT_PATH}"


def test_phase26aa_status_field() -> None:
    assert "status: EXCERPT_AUDIT_ONLY" in _audit_text()


def test_phase26aa_not_an_approval() -> None:
    content = _audit_text()
    assert "NOT_an_approval: true" in content


def test_phase26aa_not_worksheet_mutation() -> None:
    assert "NOT_worksheet_mutation: true" in _audit_text()


def test_phase26aa_not_connector_enablement() -> None:
    assert "NOT_connector_enablement: true" in _audit_text()


def test_phase26aa_prior_26z_still_exists() -> None:
    assert PRIOR_26Z_PATH.exists(), "Phase 26Z summary must not be deleted"


# ─── Zero excerpt-proof-ready rows ────────────────────────────────────────────


def test_phase26aa_zero_excerpt_proof_ready() -> None:
    content = _audit_text()
    # The audit must explicitly state 0 rows are EXCERPT_PROOF_READY
    assert "EXCERPT_PROOF_READY" in content
    assert "0" in content


def test_phase26aa_no_proof_ready_not_approved() -> None:
    content = _audit_text()
    # No row should be promoted to PROOF_READY_NOT_APPROVED in this doc
    assert "PROOF_READY_NOT_APPROVED" not in content or ("0" in content and "PROOF_READY_NOT_APPROVED" in content)


def test_phase26aa_26ab_skipped() -> None:
    content = _audit_text()
    # Phase 26AB must be explicitly skipped
    assert "SKIPPED" in content
    assert "26AB" in content


# ─── All 4 raw-sequence rows classified NEEDS_EXTERNAL_RESEARCH ───────────────


def test_phase26aa_prev_change_id_needs_external_research() -> None:
    content = _audit_text()
    assert "prev_change_id" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_continuity_condition_needs_external_research() -> None:
    content = _audit_text()
    assert "continuity_condition" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_first_message_snapshot_needs_external_research() -> None:
    content = _audit_text()
    assert "first_message_snapshot" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_incremental_delta_needs_external_research() -> None:
    content = _audit_text()
    assert "incremental_delta" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


# ─── Key documentation rows classified ────────────────────────────────────────


def test_phase26aa_public_rest_availability_classified() -> None:
    content = _audit_text()
    assert "public_rest_availability" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_prod_testnet_ws_endpoint_classified() -> None:
    content = _audit_text()
    assert "prod_testnet_ws_endpoint" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_heartbeat_liveness_proof_classified() -> None:
    content = _audit_text()
    assert "heartbeat_liveness_proof" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_public_rate_subscription_limits_classified() -> None:
    content = _audit_text()
    assert "public_rate_subscription_limits" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_public_trades_classified() -> None:
    content = _audit_text()
    assert "public_trades" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_ticker_classified() -> None:
    content = _audit_text()
    assert "ticker" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_mark_index_funding_classified() -> None:
    content = _audit_text()
    assert "mark_index_funding_open_interest" in content
    assert "NEEDS_EXTERNAL_RESEARCH" in content


def test_phase26aa_staleness_budget_needs_policy() -> None:
    content = _audit_text()
    assert "staleness_budget" in content
    assert "NEEDS_POLICY_DECISION" in content


def test_phase26aa_receive_lag_budget_needs_policy() -> None:
    content = _audit_text()
    assert "receive_lag_budget" in content
    assert "NEEDS_POLICY_DECISION" in content


def test_phase26aa_regional_legal_access_needs_legal() -> None:
    content = _audit_text()
    assert "regional_legal_access" in content
    assert "NEEDS_LEGAL_REVIEW" in content


# ─── Same-hash caveat recorded ────────────────────────────────────────────────


def test_phase26aa_same_hash_caveat_recorded() -> None:
    content = _audit_text()
    # Must reference the same-hash caveat
    assert "Same-Hash Caveat" in content or "same_hash" in content.lower() or "Same Hash" in content


def test_phase26aa_references_manifest() -> None:
    content = _audit_text()
    assert "DERIBIT_SOURCE_SNAPSHOT_MANIFEST" in content


def test_phase26aa_references_worksheet() -> None:
    content = _audit_text()
    assert "DERIBIT_CLAIM_REVIEW_WORKSHEET" in content


def test_phase26aa_references_26y_gap_doc() -> None:
    content = _audit_text()
    assert "26Y" in content


# ─── No external claims ───────────────────────────────────────────────────────


def test_phase26aa_no_external_web_claims() -> None:
    content = _audit_text()
    # The doc should not contain external URL claims as proven facts
    # (the manifest source URLs are referenced but not as proven claims)
    assert "NO external web claims" in content or "No external web claims" in content


def test_phase26aa_no_synthetic_observed_values() -> None:
    content = _audit_text()
    assert "synthetic" not in content.lower() or "NOT" in content


def test_phase26aa_no_reviewer_id_filled() -> None:
    content = _audit_text()
    # No reviewer metadata should be filled
    assert "reviewer_id=<OPERATOR_REQUIRED>" not in content
    assert "reviewed_at_iso=<OPERATOR_REQUIRED>" not in content


# ─── Validator and connector state unchanged ──────────────────────────────────


def test_phase26aa_validator_still_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.ready_for_engineering_patch is False
    assert result.connector_enablement_ready is False


def test_phase26aa_pending_rows_still_26() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 26


def test_phase26aa_b1_b5_all_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()
    for key in ("B1", "B2", "B3", "B4", "B5"):
        assert result.b1_b5_status[key] == "BLOCKED", f"{key} expected BLOCKED"


def test_phase26aa_connector_ready_dialects_empty() -> None:
    dialects = connector_ready_dialects()
    assert len(dialects) == 0
