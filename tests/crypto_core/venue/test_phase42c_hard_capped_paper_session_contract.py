from __future__ import annotations

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase42b_hard_capped_paper_session_artifact import _run_phase42_session


def test_phase42c_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()

    assert readiness.accepted is True
    assert readiness.evidence_review_complete is True
    assert readiness.connector_enablement_ready is False
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1


def test_phase42c_explicit_session_applies_two_bounded_trade_inputs() -> None:
    result = _run_phase42_session()

    assert result.accepted is True
    assert result.session_id == "phase42-hard-capped-paper-session"
    assert result.trades_requested == 2
    assert result.trades_attempted == 2
    assert result.trades_filled == 2
    assert result.trades_rejected == 0
    assert result.ledger_mutated is True
    assert result.reason_code == "deribit_hard_capped_paper_session:accepted"
    assert len(result.run_results) == 2
    assert all(run.accepted for run in result.run_results)


def test_phase42c_session_chains_immutable_ledger_between_explicit_trade_inputs() -> None:
    result = _run_phase42_session()

    assert result.final_ledger_state is not None
    assert result.before_ledger_summary is not None
    assert result.after_ledger_summary is not None
    assert result.before_ledger_summary["applied_fill_count"] == 0
    assert result.after_ledger_summary["applied_fill_count"] == 2
    assert result.after_ledger_summary["position_qty"] == 1.0
    assert result.final_ledger_state.position_qty == 1.0
    assert result.final_ledger_state.applied_request_ids == (
        "phase42-session-trade-1",
        "phase42-session-trade-2",
        "phase42-hard-capped-paper-session",
    )
    assert result.final_ledger_state.applied_idempotency_keys[-1] == "idem-phase42-hard-capped-paper-session"
