from __future__ import annotations

from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_trade_gate import run_deribit_paper_trade_gate
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs


def test_phase38f_duplicate_run_id_and_idempotency_key_cannot_double_mutate_ledger() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-idempotency",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )

    first = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)
    assert first.ledger_state is not None
    second = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, first.ledger_state)

    assert first.accepted is True
    assert first.ledger_mutated is True
    assert second.accepted is False
    assert second.ledger_mutated is False
    assert second.ledger_state == first.ledger_state
    assert "deribit_paper_trade_gate:duplicate_run_id" in second.rejection_reasons
    assert "deribit_paper_trade_gate:duplicate_gate_idempotency_key" in second.rejection_reasons
