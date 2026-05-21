from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_order_intent import (
    ACCOUNTING_LEDGER_NOT_READY,
    ACCOUNTING_PRECHECK_ONLY,
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
    DeribitPaperPreFillRiskPolicy,
    validate_deribit_paper_order_intent,
)
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result


def test_phase35d_kill_switch_true_rejects_intent() -> None:
    decision = validate_deribit_paper_order_intent(_frame(), _intent(), kill_switch_active=True)

    assert decision.accepted is False
    assert decision.kill_switch_active is True
    assert "deribit_paper_order_intent:kill_switch_active" in decision.rejection_reasons
    assert "kill_switch_blocking" in decision.risk_checks


def test_phase35d_max_order_qty_breach_rejects_intent() -> None:
    decision = validate_deribit_paper_order_intent(
        _frame(),
        replace(_intent(), quantity=2.0),
        policy=DeribitPaperPreFillRiskPolicy(max_order_qty=1.0, max_order_notional=200_000.0),
    )

    assert decision.accepted is False
    assert "deribit_paper_order_intent:max_order_qty_breached" in decision.rejection_reasons


def test_phase35d_max_order_notional_breach_rejects_intent() -> None:
    decision = validate_deribit_paper_order_intent(
        _frame(),
        _intent(),
        policy=DeribitPaperPreFillRiskPolicy(max_order_qty=1.0, max_order_notional=10_000.0),
    )

    assert decision.accepted is False
    assert decision.intent_notional == 25_010.0
    assert "deribit_paper_order_intent:max_order_notional_breached" in decision.rejection_reasons


def test_phase35d_absent_accounting_state_is_not_faked_into_ledger_approval() -> None:
    decision = validate_deribit_paper_order_intent(_frame(), _intent())

    assert decision.accepted is True
    assert decision.accounting_state_present is False
    assert decision.accounting_gate_status == ACCOUNTING_LEDGER_NOT_READY
    assert decision.ledger_mutation_ready is False
    assert "accounting_not_ready_for_ledger" in decision.risk_checks


def test_phase35d_required_accounting_state_absence_rejects_intent() -> None:
    decision = validate_deribit_paper_order_intent(
        _frame(),
        _intent(),
        policy=DeribitPaperPreFillRiskPolicy(require_accounting_state=True),
    )

    assert decision.accepted is False
    assert "deribit_paper_order_intent:accounting_state_required" in decision.rejection_reasons


def test_phase35d_present_accounting_state_is_prefill_only_not_mutation_ready() -> None:
    decision = validate_deribit_paper_order_intent(_frame(), _intent(), accounting_state_present=True)

    assert decision.accepted is True
    assert decision.accounting_gate_status == ACCOUNTING_PRECHECK_ONLY
    assert decision.ledger_mutation_ready is False
    assert decision.position_mutation_ready is False


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _intent() -> DeribitPaperOrderIntent:
    return DeribitPaperOrderIntent(
        intent_id="paper-intent-risk",
        idempotency_key="idem-paper-intent-risk",
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        side=DeribitPaperOrderIntentSide.BUY,
        order_style=DeribitPaperOrderStyle.LIMIT,
        quantity=0.5,
        limit_price=50_020.0,
        simulation_only=True,
    )
