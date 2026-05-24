from __future__ import annotations

from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_trade_gate import run_deribit_paper_trade_gate
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs


def test_phase38c_one_explicit_operator_trigger_produces_one_paper_fill_and_ledger_mutation() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-explicit-paper-fill",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )

    result = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)

    assert result.accepted is True
    assert result.filled is True
    assert result.ledger_mutated is True
    assert result.ledger_state is not None
    assert result.before_ledger_summary is not None
    assert result.after_ledger_summary is not None
    assert result.before_ledger_summary.position_qty == 0.0
    assert result.after_ledger_summary.position_qty == 0.5
    assert result.after_ledger_summary.average_entry_price == 50_010.0
    assert result.after_ledger_summary.applied_fill_count == 1
    assert result.after_ledger_summary.applied_request_count == 1
    assert result.after_ledger_summary.applied_idempotency_count == 1


def test_phase38c_no_fill_scenario_is_deterministic_and_does_not_mutate_position() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-no-fill",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_005.0,
    )

    result = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)

    assert result.accepted is True
    assert result.filled is False
    assert result.ledger_mutated is False
    assert result.reason_code == "deribit_paper_fill:no_fill_limit_not_crossed"
    assert result.ledger_state == ledger
    assert result.before_ledger_summary == result.after_ledger_summary
