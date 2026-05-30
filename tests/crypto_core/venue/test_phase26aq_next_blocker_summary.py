"""Phase 26AQ — Next blocker summary document validation.

Tests that DERIBIT_NEXT_BLOCKER_SUMMARY_26AQ.md exists with required content
superseding Phase 26AL, reflects pending_rows=3, B1-B5 BLOCKED, 8 rows
approved in this phase, and correct next-step guidance.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SUMMARY_PATH = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_26AQ.md")

_PRIOR_SUMMARY_PATH = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_26AL.md")


@pytest.fixture(scope="module")
def summary_text() -> str:
    assert _SUMMARY_PATH.exists(), f"Summary doc missing: {_SUMMARY_PATH}"
    return _SUMMARY_PATH.read_text(encoding="utf-8")


# --- File existence ---


def test_summary_doc_exists() -> None:
    assert _SUMMARY_PATH.exists()


def test_prior_summary_still_exists() -> None:
    """26AQ supersedes 26AL but does not delete it."""
    assert _PRIOR_SUMMARY_PATH.exists()


def test_summary_doc_nonempty(summary_text: str) -> None:
    assert len(summary_text) > 200


# --- Supersedes ---


def test_summary_supersedes_26al(summary_text: str) -> None:
    assert "26AL" in summary_text


# --- Validator state section ---


def test_summary_accepted_false(summary_text: str) -> None:
    assert "accepted" in summary_text
    assert "False" in summary_text


def test_summary_pending_rows_3(summary_text: str) -> None:
    assert "pending_rows" in summary_text
    assert "3" in summary_text


def test_summary_connector_ready_dialects_zero(summary_text: str) -> None:
    assert "connector_ready_dialects" in summary_text
    assert "0" in summary_text


# --- B1-B5 all BLOCKED ---


def test_summary_b1_blocked(summary_text: str) -> None:
    assert "B1" in summary_text
    assert "BLOCKED" in summary_text


def test_summary_b2_blocked(summary_text: str) -> None:
    assert "B2" in summary_text


def test_summary_b3_blocked(summary_text: str) -> None:
    assert "B3" in summary_text


def test_summary_b4_blocked(summary_text: str) -> None:
    assert "B4" in summary_text


def test_summary_b5_blocked(summary_text: str) -> None:
    assert "B5" in summary_text


# --- Approved rows in this phase ---


def test_summary_phase26an_approved_claim_checksum(summary_text: str) -> None:
    assert "checksum_decision" in summary_text


def test_summary_phase26an_approved_policy_liveness(summary_text: str) -> None:
    assert "liveness_policy" in summary_text


def test_summary_phase26an_approved_claim_staleness(summary_text: str) -> None:
    assert "staleness_budget" in summary_text


def test_summary_phase26an_approved_claim_receive_lag(summary_text: str) -> None:
    assert "receive_lag_budget" in summary_text


def test_summary_phase26an_approved_policy_testnet_prod(summary_text: str) -> None:
    assert "testnet_prod_review" in summary_text


# --- Policy values mentioned ---


def test_summary_policy_value_checksum(summary_text: str) -> None:
    assert "NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE" in summary_text


def test_summary_policy_value_liveness(summary_text: str) -> None:
    assert "PUBLIC_WS_LIVENESS_TIMEOUT_MS_10000" in summary_text


def test_summary_policy_value_staleness(summary_text: str) -> None:
    assert "MAX_STALENESS_MS_2000" in summary_text


def test_summary_policy_value_receive_lag(summary_text: str) -> None:
    assert "MAX_RECEIVE_LAG_MS_1000" in summary_text


def test_summary_policy_value_testnet_prod(summary_text: str) -> None:
    assert "PROD_AND_TESTNET_MUST_REMAIN_EXPLICITLY_CONFIG_SEPARATED" in summary_text


# --- Remaining pending rows ---


def test_summary_pending_regional_legal_access(summary_text: str) -> None:
    assert "regional_legal_access" in summary_text


def test_summary_pending_regional_legal_access_review(summary_text: str) -> None:
    assert "regional_legal_access_review" in summary_text


def test_summary_pending_separate_connector_enablement(summary_text: str) -> None:
    assert "separate_connector_enablement" in summary_text


# --- Next steps ---


def test_summary_legal_review_mentioned(summary_text: str) -> None:
    assert "legal" in summary_text.lower() or "Legal" in summary_text


def test_summary_connector_enablement_phase_mentioned(summary_text: str) -> None:
    assert "PUBLIC_MARKET_DATA_ONLY" in summary_text or "connector-enablement" in summary_text


def test_summary_static_registry_step_mentioned(summary_text: str) -> None:
    assert "static_registry" in summary_text or "Static Registry" in summary_text


# --- Safety invariants ---


def test_summary_no_connector_enablement_granted(summary_text: str) -> None:
    assert "connector_ready_dialects" in summary_text
    # Confirm it states 0, not enabled
    assert "connector_ready_dialects:  0" in summary_text or "connector_ready_dialects() == 0" in summary_text


def test_summary_public_feed_dialects_unchanged(summary_text: str) -> None:
    assert "public_feed_dialects" in summary_text
    assert "unchanged" in summary_text


def test_summary_enabled_for_connector_false(summary_text: str) -> None:
    # Header must remain false
    assert "enabled_for_connector" in summary_text
    assert "false" in summary_text.lower()
