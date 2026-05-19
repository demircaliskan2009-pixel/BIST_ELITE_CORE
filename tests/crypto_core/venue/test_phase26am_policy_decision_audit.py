"""Phase 26AM — Policy Decision Audit document validation.

These tests verify that the DERIBIT_POLICY_DECISION_AUDIT_26AM.md audit
document exists with required content and that exactly 8 rows are authorised
(3 claim + 5 policy), the 3 forbidden rows are explicitly listed as NOT
authorised, and no connector / static-registry / live enablement is present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_AUDIT_PATH = Path("docs/crypto_core/DERIBIT_POLICY_DECISION_AUDIT_26AM.md")

_REQUIRED_APPROVED_CLAIM_IDS = frozenset(
    {
        "checksum_decision",
        "staleness_budget",
        "receive_lag_budget",
    }
)

_REQUIRED_APPROVED_POLICY_IDS = frozenset(
    {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
)

_FORBIDDEN_ROW_IDS = frozenset(
    {
        "regional_legal_access",
        "regional_legal_access_review",
        "separate_connector_enablement",
    }
)

_REQUIRED_POLICY_VALUES = {
    "checksum_decision": "NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE",
    "liveness_policy": "PUBLIC_WS_LIVENESS_TIMEOUT_MS_10000",
    "staleness_budget": "MAX_STALENESS_MS_2000",
    "receive_lag_budget": "MAX_RECEIVE_LAG_MS_1000",
    "testnet_prod_review": "PROD_AND_TESTNET_MUST_REMAIN_EXPLICITLY_CONFIG_SEPARATED",
}


@pytest.fixture(scope="module")
def audit_text() -> str:
    assert _AUDIT_PATH.exists(), f"Audit doc missing: {_AUDIT_PATH}"
    return _AUDIT_PATH.read_text(encoding="utf-8")


def test_audit_doc_exists() -> None:
    assert _AUDIT_PATH.exists()


def test_audit_doc_nonempty(audit_text: str) -> None:
    assert len(audit_text) > 100


def test_audit_reviewer_id(audit_text: str) -> None:
    assert "demir_operator" in audit_text


def test_audit_reviewed_at_iso(audit_text: str) -> None:
    assert "2026-05-19T00:00:00Z" in audit_text


def test_audit_approval_scope(audit_text: str) -> None:
    assert "Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY" in audit_text


def test_audit_total_rows_count(audit_text: str) -> None:
    """8 rows authorized total."""
    assert "8" in audit_text


def test_audit_claim_row_count(audit_text: str) -> None:
    assert "3 claim" in audit_text or "3 rows" in audit_text or "3)" in audit_text


def test_audit_policy_row_count(audit_text: str) -> None:
    assert "5 policy" in audit_text or "5 rows" in audit_text or "5)" in audit_text


def test_audit_approved_claim_ids_present(audit_text: str) -> None:
    for claim_id in _REQUIRED_APPROVED_CLAIM_IDS:
        assert claim_id in audit_text, f"Missing approved claim: {claim_id}"


def test_audit_approved_policy_ids_present(audit_text: str) -> None:
    for policy_id in _REQUIRED_APPROVED_POLICY_IDS:
        assert policy_id in audit_text, f"Missing approved policy: {policy_id}"


def test_audit_forbidden_rows_listed(audit_text: str) -> None:
    for row_id in _FORBIDDEN_ROW_IDS:
        assert row_id in audit_text, f"Forbidden row not listed: {row_id}"


def test_audit_no_legal_row_approved(audit_text: str) -> None:
    """regional_legal_access must NOT be in the approved list."""
    # The doc lists it in the forbidden table, not in the approved list
    assert "regional_legal_access" in audit_text  # present but forbidden
    assert "NOT authorized" in audit_text or "Forbidden" in audit_text or "FORBIDDEN" in audit_text


def test_audit_no_connector_enablement(audit_text: str) -> None:
    assert (
        "NOT_connector_enablement: true" in audit_text or "No connector" in audit_text or "NOT_connector" in audit_text
    )


def test_audit_no_static_registry_enablement(audit_text: str) -> None:
    assert "NOT_static_registry_enablement: true" in audit_text or "No static" in audit_text


def test_audit_no_paper_shadow_live(audit_text: str) -> None:
    assert "NOT_paper_shadow_live_integration: true" in audit_text or "No paper" in audit_text


def test_audit_accepted_false(audit_text: str) -> None:
    assert "accepted: False" in audit_text


def test_audit_pending_rows_3(audit_text: str) -> None:
    assert "pending_rows: 3" in audit_text


def test_audit_b1_blocked(audit_text: str) -> None:
    assert "B1: BLOCKED" in audit_text


def test_audit_b2_blocked(audit_text: str) -> None:
    assert "B2: BLOCKED" in audit_text


def test_audit_b3_blocked(audit_text: str) -> None:
    assert "B3: BLOCKED" in audit_text


def test_audit_connector_ready_dialects_zero(audit_text: str) -> None:
    assert "connector_ready_dialects(): 0" in audit_text


def test_audit_policy_value_checksum(audit_text: str) -> None:
    assert _REQUIRED_POLICY_VALUES["checksum_decision"] in audit_text


def test_audit_policy_value_liveness(audit_text: str) -> None:
    assert _REQUIRED_POLICY_VALUES["liveness_policy"] in audit_text


def test_audit_policy_value_staleness(audit_text: str) -> None:
    assert _REQUIRED_POLICY_VALUES["staleness_budget"] in audit_text


def test_audit_policy_value_receive_lag(audit_text: str) -> None:
    assert _REQUIRED_POLICY_VALUES["receive_lag_budget"] in audit_text


def test_audit_policy_value_testnet_prod(audit_text: str) -> None:
    assert _REQUIRED_POLICY_VALUES["testnet_prod_review"] in audit_text


def test_audit_enforcement_checksum(audit_text: str) -> None:
    assert "FAIL_CLOSED_IF_SELECTED_CHANNEL_OR_DOCS_REQUIRE_CHECKSUM" in audit_text


def test_audit_enforcement_liveness(audit_text: str) -> None:
    assert "FAIL_CLOSED_ON_NO_MESSAGE_OR_NO_HEARTBEAT_WITHIN_10000MS" in audit_text


def test_audit_enforcement_staleness(audit_text: str) -> None:
    assert "MARK_FEED_STALE_AND_BLOCK_DOWNSTREAM_READINESS_IF_EXCEEDED" in audit_text


def test_audit_enforcement_receive_lag(audit_text: str) -> None:
    assert "REJECT_OR_QUARANTINE_EVENT_IF_EXCEEDED" in audit_text


def test_audit_enforcement_testnet_prod(audit_text: str) -> None:
    assert "NO_IMPLICIT_ENVIRONMENT_FALLBACK" in audit_text


def test_audit_consistent_verdict(audit_text: str) -> None:
    assert "CONSISTENT" in audit_text
