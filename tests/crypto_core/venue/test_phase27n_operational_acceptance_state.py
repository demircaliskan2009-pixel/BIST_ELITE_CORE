"""Phase 27N operational acceptance state tests."""

from __future__ import annotations

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects


def test_phase27n_source_claim_and_policy_rows_are_approved() -> None:
    result = evaluate_deribit_manual_review_readiness()

    source_rows = [row for row in result.row_results if row.surface == "source_snapshot"]
    claim_rows = [row for row in result.row_results if row.surface == "claim_review"]
    policy_rows = [row for row in result.row_results if row.surface == "policy_review"]

    assert len(source_rows) == 6
    assert len(claim_rows) == 23
    assert len(policy_rows) == 7
    assert all(row.status == "APPROVED" for row in source_rows)
    assert all(row.status == "APPROVED" for row in claim_rows)
    assert all(row.status == "APPROVED" for row in policy_rows)


def test_phase27n_validator_reaches_operational_acceptance_without_connector_expansion() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is True
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is False
    assert result.pending_rows == ()
    assert result.deferred_rows == ()
    assert result.rejected_rows == ()
    assert result.rejection_reasons == ("INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING",)
    assert result.b1_b5_status == {
        "B1": "READY_FOR_HUMAN_GATE",
        "B2": "READY",
        "B3": "READY",
        "B4": "READY",
        "B5": "BLOCKED",
    }

    ready = connector_ready_dialects()
    assert len(ready) == 1
    assert ready[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"
