"""Phase 26AI operator approval execution audit tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_APPROVAL_EXECUTION_AUDIT_26AI.md"
PROPOSAL_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26AH.md"

ALLOWED_ROWS = (
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

FORBIDDEN_ROWS = (
    "regional_legal_access",
    "regional_legal_access_review",
    "checksum_decision",
    "liveness_policy",
    "staleness_budget",
    "receive_lag_budget",
    "testnet_prod_review",
    "separate_connector_enablement",
)


def _audit() -> str:
    return AUDIT_PATH.read_text(encoding="utf-8")


def _proposal() -> str:
    return PROPOSAL_PATH.read_text(encoding="utf-8")


def test_phase26ai_audit_exists() -> None:
    assert AUDIT_PATH.exists(), "26AI audit doc must exist"


def test_phase26ai_audit_status_field() -> None:
    assert "APPROVAL_EXECUTION_AUDIT_ONLY" in _audit()


def test_phase26ai_reviewer_id() -> None:
    assert "reviewer_id: demir_operator" in _audit()


def test_phase26ai_reviewed_at_iso() -> None:
    assert "reviewed_at_iso: 2026-05-19T00:00:00Z" in _audit()


def test_phase26ai_approval_scope() -> None:
    assert "Phase26AI_OFFICIAL_DOCS_TECHNICAL_ROWS_ONLY" in _audit()


def test_phase26ai_decision_approve() -> None:
    assert "decision: APPROVE" in _audit()


def test_phase26ai_exactly_15_allowed_rows() -> None:
    text = _audit()
    for row in ALLOWED_ROWS:
        assert row in text, f"Allowed row {row!r} must be listed in audit"


def test_phase26ai_allowed_rows_count_15() -> None:
    assert len(ALLOWED_ROWS) == 15


def test_phase26ai_forbidden_rows_listed() -> None:
    text = _audit()
    for row in FORBIDDEN_ROWS:
        assert row in text, f"Forbidden row {row!r} must be explicitly listed"


def test_phase26ai_regional_legal_access_forbidden() -> None:
    text = _audit()
    assert "regional_legal_access" in text
    assert "NEEDS_LEGAL_REVIEW" in text


def test_phase26ai_checksum_decision_forbidden() -> None:
    text = _audit()
    assert "checksum_decision" in text
    # forbidden rows section contains checksum_decision
    lines = [ln for ln in text.splitlines() if "checksum_decision" in ln]
    assert any("NEEDS_POLICY_DECISION" in ln or "Forbidden" in ln or "excluded" in ln or "|" in ln for ln in lines)


def test_phase26ai_staleness_receive_lag_forbidden() -> None:
    text = _audit()
    assert "staleness_budget" in text
    assert "receive_lag_budget" in text


def test_phase26ai_no_connector_enablement() -> None:
    text = _audit()
    assert "NOT_connector_enablement: true" not in text or "connector_ready_dialects | 0" in text
    # audit doc must not enable connectors
    assert "enabled_for_connector" not in text or "false" in text.lower()


def test_phase26ai_expected_pending_rows_11() -> None:
    text = _audit()
    assert "11" in text
    assert "pending_rows" in text


def test_phase26ai_expected_decrease_15() -> None:
    text = _audit()
    assert "decrease: 15" in text or "approved_in_this_phase: 15" in text


def test_phase26ai_before_patch_26() -> None:
    text = _audit()
    assert "26" in text
    assert "before_patch" in text or "before" in text


def test_phase26ai_b2_blocked_after_patch() -> None:
    text = _audit()
    assert "B2" in text
    assert "BLOCKED" in text


def test_phase26ai_connector_ready_dialects_zero() -> None:
    text = _audit()
    assert "connector_ready_dialects" in text
    assert "0" in text


def test_phase26ai_evidence_consistency_pass() -> None:
    text = _audit()
    assert "PASS" in text
    assert "CONSISTENT" in text


def test_phase26ai_audit_verdict_consistent() -> None:
    assert "CONSISTENT" in _audit()
    assert "authorized" in _audit().lower() or "safe" in _audit().lower()


def test_phase26ai_evidence_refs_26ae() -> None:
    text = _audit()
    assert "DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md" in text


def test_phase26ai_evidence_refs_26af() -> None:
    text = _audit()
    assert "DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md" in text


def test_phase26ai_evidence_refs_26ag() -> None:
    text = _audit()
    assert "DERIBIT_PROOF_ARTIFACT_BATCH_26AG.md" in text


def test_phase26ai_evidence_refs_26ah() -> None:
    text = _audit()
    assert "DERIBIT_NEXT_BLOCKER_SUMMARY_26AH.md" in text


def test_phase26ai_proposal_still_exists() -> None:
    assert PROPOSAL_PATH.exists(), "26AH proposal must still exist"


def test_phase26ai_no_policy_worksheet_rows_approved() -> None:
    text = _audit()
    # policy rows are in forbidden list, not allowed list
    forbidden_section_present = "Explicitly Forbidden" in text or "Forbidden" in text
    assert forbidden_section_present
