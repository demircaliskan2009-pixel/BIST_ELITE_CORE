from __future__ import annotations

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_ledger import build_deribit_paper_ledger_state
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntentSide,
    validate_deribit_paper_order_intent,
)
from crypto_core.venue.deribit_paper_trade_gate import (
    DeribitPaperTradeOperatorTrigger,
    run_deribit_paper_trade_gate,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase36b_paper_ledger_contract import _frame, _intent


def test_phase37b_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1


def test_phase37b_operator_triggered_fill_applies_one_paper_trade_deterministically() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-buy",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )

    result = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)

    assert result.accepted is True
    assert result.filled is True
    assert result.ledger_mutated is True
    assert result.reason_code == "deribit_paper_trade_gate:accepted_fill_applied"
    assert result.run_id == fill_request.request_id
    assert result.request_id == fill_request.request_id
    assert result.fill_id is not None
    assert result.ledger_state is not None
    assert result.before_ledger_summary is not None
    assert result.after_ledger_summary is not None
    assert result.before_ledger_summary.cash_balance == 10_000.0
    assert result.before_ledger_summary.position_qty == 0.0
    assert result.after_ledger_summary.cash_balance == 10_000.0
    assert result.after_ledger_summary.position_qty == 0.5
    assert result.after_ledger_summary.average_entry_price == 50_010.0
    assert result.after_ledger_summary.realized_pnl == 0.0
    assert result.after_ledger_summary.applied_fill_count == 1
    assert result.audit_record.run_id == trigger.run_id
    assert result.audit_record.request_id == fill_request.request_id
    assert result.audit_record.fill_id == result.fill_id
    assert result.audit_record.ledger_mutated is True


def _ledger() -> object:
    return build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
    )


def _accepted_trade_gate_inputs(
    *,
    intent_id: str,
    side: DeribitPaperOrderIntentSide,
    limit_price: float,
    quantity: float = 0.5,
):
    ledger = _ledger()
    frame = _frame()
    intent = _intent(
        side=side,
        intent_id=intent_id,
        limit_price=limit_price,
    )
    if quantity != 0.5:
        intent = intent.__class__(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            venue_id=intent.venue_id,
            symbol=intent.symbol,
            canonical_symbol=intent.canonical_symbol,
            side=intent.side,
            order_style=intent.order_style,
            quantity=quantity,
            limit_price=intent.limit_price,
            simulation_only=intent.simulation_only,
        )
    decision = validate_deribit_paper_order_intent(frame, intent)
    assert decision.fill_request is not None
    trigger = DeribitPaperTradeOperatorTrigger(
        operator_id="operator-manual-gate",
        run_id=decision.fill_request.request_id,
        idempotency_key=intent.idempotency_key,
        simulation_only=True,
    )
    return trigger, intent, decision, decision.fill_request, frame, ledger
