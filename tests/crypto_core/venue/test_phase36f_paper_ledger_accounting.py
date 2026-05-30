from __future__ import annotations

from crypto_core.venue.deribit_paper_fill_model import evaluate_deribit_paper_limit_fill
from crypto_core.venue.deribit_paper_ledger import (
    NOT_IMPLEMENTED,
    REALIZED_PNL_ON_CLOSE_ONLY,
    apply_deribit_paper_fill_to_ledger,
    build_deribit_paper_ledger_state,
    normalize_deribit_paper_ledger_intent_reference,
)
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntentSide,
    validate_deribit_paper_order_intent,
)
from tests.crypto_core.venue.test_phase36b_paper_ledger_contract import _frame, _intent


def test_phase36f_realized_pnl_and_cash_balance_update_deterministically_on_close() -> None:
    ledger = build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0, symbol="BTC-PERPETUAL", canonical_symbol="BTC-PERP"
    )
    frame = _frame()

    buy_intent = _intent(side=DeribitPaperOrderIntentSide.BUY, intent_id="paper-open", limit_price=50_020.0)
    buy_decision = validate_deribit_paper_order_intent(frame, buy_intent)
    buy_reference = normalize_deribit_paper_ledger_intent_reference(buy_intent, buy_decision)
    buy_fill = evaluate_deribit_paper_limit_fill(frame, buy_decision.fill_request)
    opened = apply_deribit_paper_fill_to_ledger(ledger, buy_reference, buy_fill)

    sell_intent = _intent(side=DeribitPaperOrderIntentSide.SELL, intent_id="paper-close", limit_price=50_000.0)
    sell_decision = validate_deribit_paper_order_intent(frame, sell_intent)
    sell_reference = normalize_deribit_paper_ledger_intent_reference(sell_intent, sell_decision)
    sell_fill = evaluate_deribit_paper_limit_fill(frame, sell_decision.fill_request)
    closed = apply_deribit_paper_fill_to_ledger(opened.ledger_state, sell_reference, sell_fill)

    assert closed.accepted is True
    assert closed.audit_entry is not None
    assert closed.audit_entry.realized_pnl_delta == -4.5
    assert closed.ledger_state is not None
    assert closed.ledger_state.cash_balance == 9_995.5
    assert closed.ledger_state.position_qty == 0.0
    assert closed.ledger_state.average_entry_price is None
    assert closed.ledger_state.realized_pnl == -4.5
    assert closed.ledger_state.accounting_policy == REALIZED_PNL_ON_CLOSE_ONLY
    assert closed.ledger_state.fees_policy == NOT_IMPLEMENTED
    assert closed.ledger_state.slippage_policy == NOT_IMPLEMENTED
    assert closed.ledger_state.margin_policy == NOT_IMPLEMENTED
    assert closed.ledger_state.funding_policy == NOT_IMPLEMENTED
    assert len(closed.ledger_state.audit_entries) == 2
