"""Phase 26AO — Post-policy validator state.

Live validator tests after Phase 26AN worksheet patches. Verifies:
  pending_rows == 3
  pending == claim_review:regional_legal_access + policy_review:regional_legal_access_review
           + policy_review:separate_connector_enablement
  accepted == False
  evidence_review_complete == False
  connector_enablement_ready == False
  B1-B5 all BLOCKED
  connector_ready_dialects() == 0
  8 rows approved in this phase (3 claim + 5 policy)
  no legal row approved
  no connector enablement row approved
"""

from __future__ import annotations

import pytest

from crypto_core.venue.deribit_manual_review_readiness import (
    DeribitManualReviewReadinessResult,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects


@pytest.fixture(scope="module")
def result() -> DeribitManualReviewReadinessResult:
    return evaluate_deribit_manual_review_readiness()


# --- Core state ---


def test_accepted_false(result: DeribitManualReviewReadinessResult) -> None:
    assert result.accepted is False


def test_evidence_review_complete_false(result: DeribitManualReviewReadinessResult) -> None:
    assert result.evidence_review_complete is False


def test_connector_enablement_ready_false(result: DeribitManualReviewReadinessResult) -> None:
    assert result.connector_enablement_ready is False


# --- pending_rows count ---


def test_pending_rows_count_is_3(result: DeribitManualReviewReadinessResult) -> None:
    assert len(result.pending_rows) == 3, (
        f"Expected 3 pending rows, got {len(result.pending_rows)}: {result.pending_rows}"
    )


# --- Exactly the right 3 pending rows ---


def test_pending_row_regional_legal_access(result: DeribitManualReviewReadinessResult) -> None:
    assert "claim_review:regional_legal_access" in result.pending_rows


def test_pending_row_regional_legal_access_review(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:regional_legal_access_review" in result.pending_rows


def test_pending_row_separate_connector_enablement(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:separate_connector_enablement" in result.pending_rows


# --- Phase 26AN approved rows not in pending ---


def test_claim_checksum_decision_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "claim_review:checksum_decision" not in result.pending_rows


def test_claim_staleness_budget_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "claim_review:staleness_budget" not in result.pending_rows


def test_claim_receive_lag_budget_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "claim_review:receive_lag_budget" not in result.pending_rows


def test_policy_checksum_decision_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:checksum_decision" not in result.pending_rows


def test_policy_liveness_policy_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:liveness_policy" not in result.pending_rows


def test_policy_staleness_budget_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:staleness_budget" not in result.pending_rows


def test_policy_receive_lag_budget_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:receive_lag_budget" not in result.pending_rows


def test_policy_testnet_prod_review_not_pending(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:testnet_prod_review" not in result.pending_rows


# --- B1-B5 all BLOCKED ---


def test_b1_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B1"] == "BLOCKED"


def test_b2_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B2"] == "BLOCKED"


def test_b3_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B3"] == "BLOCKED"


def test_b4_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B4"] == "BLOCKED"


def test_b5_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B5"] == "BLOCKED"


# --- connector_ready_dialects unchanged ---


def test_connector_ready_dialects_empty() -> None:
    dialects = connector_ready_dialects()
    assert len(dialects) == 0, f"connector_ready_dialects must remain empty, got: {dialects}"


# --- No rejected rows ---


def test_no_rejected_rows(result: DeribitManualReviewReadinessResult) -> None:
    assert len(result.rejected_rows) == 0


# --- Row-level approved checks from row_results ---


def test_row_results_claim_checksum_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "claim_review" and r.row_id == "checksum_decision"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_claim_staleness_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "claim_review" and r.row_id == "staleness_budget"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_claim_receive_lag_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "claim_review" and r.row_id == "receive_lag_budget"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_policy_checksum_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "checksum_decision"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_policy_liveness_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "liveness_policy"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_policy_staleness_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "staleness_budget"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_policy_receive_lag_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "receive_lag_budget"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_policy_testnet_prod_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "testnet_prod_review"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


def test_row_results_regional_legal_access_pending(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "claim_review" and r.row_id == "regional_legal_access"),
        None,
    )
    assert row is not None
    assert row.status == "PENDING"


def test_row_results_regional_legal_access_review_pending(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "regional_legal_access_review"),
        None,
    )
    assert row is not None
    assert row.status == "PENDING"


def test_row_results_separate_connector_enablement_pending(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "separate_connector_enablement"),
        None,
    )
    assert row is not None
    assert row.status in ("PENDING", "DEFERRED")


# --- Exactly 8 rows newly approved in phase 26AN across all surfaces ---


def test_exactly_8_phase26an_approved_rows(result: DeribitManualReviewReadinessResult) -> None:
    """3 claim + 5 policy approved by phase 26AN."""
    phase26an_claim_ids = {"checksum_decision", "staleness_budget", "receive_lag_budget"}
    phase26an_policy_ids = {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
    found = 0
    for r in result.row_results:
        if r.status == "APPROVED" and r.surface == "claim_review" and r.row_id in phase26an_claim_ids:
            found += 1
        elif r.status == "APPROVED" and r.surface == "policy_review" and r.row_id in phase26an_policy_ids:
            found += 1
    assert found == 8, f"Expected 8 Phase26AN approved rows, found {found}"
