from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_trade_gate import run_deribit_paper_trade_gate
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs


def test_phase38d_kill_switch_rejects_without_ledger_mutation() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-kill-switch",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )

    result = run_deribit_paper_trade_gate(
        trigger,
        intent,
        decision,
        fill_request,
        frame,
        ledger,
        kill_switch_active=True,
    )

    assert result.accepted is False
    assert result.filled is False
    assert result.ledger_mutated is False
    assert "deribit_paper_trade_gate:kill_switch_active" in result.rejection_reasons


def test_phase38d_simulation_only_false_rejects_without_ledger_mutation() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-not-simulation-only",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    trigger = replace(trigger, simulation_only=False)

    result = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert "deribit_paper_trade_gate:not_simulation_only" in result.rejection_reasons


def test_phase38d_reconstructed_side_mismatch_fails_closed() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-side-mismatch",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    fill_request = replace(fill_request, side=fill_request.side.__class__.SELL)
    decision = replace(decision, fill_request=fill_request)

    result = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert "deribit_paper_trade_gate:request_side_mismatch" in result.rejection_reasons
