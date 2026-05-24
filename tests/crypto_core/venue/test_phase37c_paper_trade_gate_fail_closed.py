from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_paper_fill_model import DeribitPaperFillSide, evaluate_deribit_paper_limit_fill
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
    validate_deribit_paper_order_intent,
)
from crypto_core.venue.deribit_paper_trade_gate import DeribitPaperTradeOperatorTrigger, run_deribit_paper_trade_gate
from tests.crypto_core.venue.test_phase36b_paper_ledger_contract import _frame
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs, _ledger


def test_phase37c_no_fill_remains_no_fill_without_position_mutation() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-no-fill",
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


def test_phase37c_rejected_intent_and_rejected_fill_application_fail_closed() -> None:
    frame = _frame()
    intent = DeribitPaperOrderIntent(
        intent_id="paper-trade-gate-rejected-intent",
        idempotency_key="idem-paper-trade-gate-rejected-intent",
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        side=DeribitPaperOrderIntentSide.BUY,
        order_style=DeribitPaperOrderStyle.LIMIT,
        quantity=3.0,
        limit_price=50_020.0,
        simulation_only=True,
    )
    decision = validate_deribit_paper_order_intent(frame, intent)
    trigger = DeribitPaperTradeOperatorTrigger(
        operator_id="operator-manual-gate",
        run_id=intent.intent_id,
        idempotency_key=intent.idempotency_key,
        simulation_only=True,
    )
    rejected_intent = run_deribit_paper_trade_gate(trigger, intent, decision, None, frame, _ledger())

    good_trigger, good_intent, good_decision, fill_request, good_frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-dup-fill",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    fill_result = evaluate_deribit_paper_limit_fill(good_frame, fill_request)
    duplicate_fill_ledger = replace(ledger, applied_fill_ids=(fill_result.fill_id,))
    rejected_fill_application = run_deribit_paper_trade_gate(
        good_trigger,
        good_intent,
        good_decision,
        fill_request,
        good_frame,
        duplicate_fill_ledger,
    )

    assert rejected_intent.accepted is False
    assert "deribit_paper_trade_gate:intent_decision_rejected" in rejected_intent.rejection_reasons
    assert rejected_fill_application.accepted is False
    assert rejected_fill_application.filled is True
    assert rejected_fill_application.ledger_mutated is False
    assert rejected_fill_application.reason_code == "deribit_paper_ledger:duplicate_fill_id"
    assert "deribit_paper_trade_gate:ledger_application_rejected" in rejected_fill_application.rejection_reasons


def test_phase37c_kill_switch_active_rejects_gate() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-kill-switch",
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
    assert result.ledger_mutated is False
    assert "deribit_paper_trade_gate:kill_switch_active" in result.rejection_reasons


def test_phase37c_fill_request_side_must_match_validated_intent_side() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-side-mismatch",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    mutated_fill_request = replace(fill_request, side=DeribitPaperFillSide.SELL)
    mutated_decision = replace(decision, fill_request=mutated_fill_request)

    result = run_deribit_paper_trade_gate(trigger, intent, mutated_decision, mutated_fill_request, frame, ledger)

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert "deribit_paper_trade_gate:request_side_mismatch" in result.rejection_reasons


def test_phase37c_invalid_operator_trigger_flags_fail_closed() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-invalid-trigger",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    cases = (
        (replace(trigger, simulation_only=False), "deribit_paper_trade_gate:not_simulation_only"),
        (replace(trigger, live_enabled=True), "deribit_paper_trade_gate:live_enabled"),
        (replace(trigger, shadow_enabled=True), "deribit_paper_trade_gate:shadow_enabled"),
        (replace(trigger, auto_loop_enabled=True), "deribit_paper_trade_gate:auto_loop_enabled"),
        (replace(trigger, operator_id=""), "deribit_paper_trade_gate:operator_id_missing"),
        (replace(trigger, run_id=""), "deribit_paper_trade_gate:run_id_missing"),
        (replace(trigger, idempotency_key=""), "deribit_paper_trade_gate:idempotency_key_missing"),
    )

    for bad_trigger, expected_reason in cases:
        result = run_deribit_paper_trade_gate(bad_trigger, intent, decision, fill_request, frame, ledger)

        assert result.accepted is False
        assert result.ledger_mutated is False
        assert expected_reason in result.rejection_reasons
