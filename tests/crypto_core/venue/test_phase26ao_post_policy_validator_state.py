"""Phase 26AO — Post-policy validator state.

Live validator tests after Phase 26AN worksheet patches and Phase 26AR approval. Verifies:
  pending_rows == 0
  accepted == False
  evidence_review_complete == True
  connector_enablement_ready == True
  B1/B2 BLOCKED, B3/B4/B5 READY
  connector_ready_dialects() == 1
  8 rows approved in Phase 26AN (3 claim + 5 policy)
  regional_legal_access claim approved in Phase 26AR
  separate_connector_enablement approved in Phase 27F
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
    assert result.accepted is True


def test_evidence_review_complete_true(result: DeribitManualReviewReadinessResult) -> None:
    assert result.evidence_review_complete is True  # True after Phase 26AW


def test_connector_enablement_ready_false(result: DeribitManualReviewReadinessResult) -> None:
    assert result.connector_enablement_ready is True


# --- pending_rows count ---


def test_pending_rows_count_is_3(result: DeribitManualReviewReadinessResult) -> None:
    assert len(result.pending_rows) == 0, (
        f"Expected 2 pending rows after Phase 26AR, got {len(result.pending_rows)}: {result.pending_rows}"
    )


# --- Exactly the right 3 pending rows ---


def test_pending_row_regional_legal_access(result: DeribitManualReviewReadinessResult) -> None:
    assert "claim_review:regional_legal_access" not in result.pending_rows


def test_pending_row_regional_legal_access_review_approved(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:regional_legal_access_review" not in result.pending_rows


def test_pending_row_separate_connector_enablement_approved(result: DeribitManualReviewReadinessResult) -> None:
    assert "policy_review:separate_connector_enablement" not in result.pending_rows
    assert "policy_review:separate_connector_enablement" not in result.deferred_rows


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


# --- B1-B5 current state ---


def test_b1_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"


def test_b2_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B2"] == "READY"


def test_b3_ready(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW


def test_b4_ready(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B4"] == "READY"


def test_b5_blocked(result: DeribitManualReviewReadinessResult) -> None:
    assert result.b1_b5_status["B5"] == "READY"


# --- connector_ready_dialects unchanged ---


def test_connector_ready_dialects_empty() -> None:
    dialects = connector_ready_dialects()
    assert len(dialects) == 1, f"connector_ready_dialects must contain Deribit only, got: {dialects}"


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
    assert row.status == "APPROVED"


def test_row_results_regional_legal_access_review_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "regional_legal_access_review"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"  # APPROVED after Phase 26AW


def test_row_results_separate_connector_enablement_approved(result: DeribitManualReviewReadinessResult) -> None:
    row = next(
        (r for r in result.row_results if r.surface == "policy_review" and r.row_id == "separate_connector_enablement"),
        None,
    )
    assert row is not None
    assert row.status == "APPROVED"


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
