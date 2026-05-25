from __future__ import annotations

from crypto_core.venue.deribit_bounded_paper_campaign import (
    DeribitBoundedPaperCampaignRequest,
    DeribitBoundedPaperCampaignSessionFixture,
    run_deribit_bounded_paper_campaign,
)
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_ledger import build_deribit_paper_ledger_state
from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_run_harness import DeribitPaperRunHarnessInputs
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs
from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import _approval


def _ledger():
    return build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
    )


def _trade_input(intent_id: str):
    _, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id=intent_id,
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    return DeribitPaperRunHarnessInputs(
        intent=intent,
        decision=decision,
        fill_request=fill_request,
        frame=frame,
        ledger_state=ledger,
    )


def _session_fixture(session_id: str, suffix: str) -> DeribitBoundedPaperCampaignSessionFixture:
    return DeribitBoundedPaperCampaignSessionFixture(
        session_id=session_id,
        idempotency_key=f"idem-{session_id}",
        trade_inputs=(
            _trade_input(f"phase48-{suffix}-trade-1"),
            _trade_input(f"phase48-{suffix}-trade-2"),
        ),
    )


def _phase48_request(**overrides: object) -> DeribitBoundedPaperCampaignRequest:
    values = {
        "operator_id": "demir_operator",
        "campaign_id": "phase48-bounded-paper-campaign",
        "idempotency_key": "idem-phase48-bounded-paper-campaign",
        "simulation_only": True,
        "approved_campaign": True,
        "hard_cap": 3,
        "per_session_max_trades": 2,
        "max_campaign_sessions": 3,
    }
    values.update(overrides)
    return DeribitBoundedPaperCampaignRequest(**values)


def _phase48_sessions() -> tuple[DeribitBoundedPaperCampaignSessionFixture, ...]:
    return (
        _session_fixture("phase48-session-1", "session-1"),
        _session_fixture("phase48-session-2", "session-2"),
        _session_fixture("phase48-session-3", "session-3"),
    )


def _run_phase48_campaign():
    return run_deribit_bounded_paper_campaign(
        _phase48_request(),
        _approval(),
        _phase48_sessions(),
        _ledger(),
    )


def test_phase48c_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1


def test_phase48c_approved_bounded_campaign_executes_three_explicit_sessions() -> None:
    result = _run_phase48_campaign()

    assert result.accepted is True
    assert result.campaign_id == "phase48-bounded-paper-campaign"
    assert result.sessions_requested == 3
    assert result.sessions_attempted == 3
    assert result.sessions_accepted == 3
    assert result.sessions_rejected == 0
    assert result.aggregate_trades_requested == 6
    assert result.aggregate_trades_filled == 6
    assert result.aggregate_ledger_mutations == 6
    assert result.ledger_mutated is True
    assert result.reason_code == "deribit_bounded_paper_campaign:accepted"
    assert len(result.session_results) == 3


def test_phase48c_campaign_chains_session_ledgers_and_records_campaign_markers() -> None:
    result = _run_phase48_campaign()

    assert result.final_ledger_state is not None
    assert result.before_ledger_summary is not None
    assert result.after_ledger_summary is not None
    assert result.before_ledger_summary["applied_fill_count"] == 0
    assert result.after_ledger_summary["applied_fill_count"] == 6
    assert result.after_ledger_summary["applied_request_count"] == 10
    assert result.after_ledger_summary["applied_idempotency_count"] == 10
    assert result.after_ledger_summary["position_qty"] == 3.0
    assert result.final_ledger_state.position_qty == 3.0
    assert result.final_ledger_state.applied_request_ids[-1] == "phase48-bounded-paper-campaign"
    assert result.final_ledger_state.applied_idempotency_keys[-1] == "idem-phase48-bounded-paper-campaign"
