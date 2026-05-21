from __future__ import annotations

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_fill_model import evaluate_deribit_paper_limit_fill
from crypto_core.venue.deribit_paper_ledger import (
    apply_deribit_paper_fill_to_ledger,
    build_deribit_paper_ledger_state,
    normalize_deribit_paper_ledger_intent_reference,
)
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
    validate_deribit_paper_order_intent,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result


def test_phase36b_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1


def test_phase36b_accepted_filled_buy_mutates_isolated_ledger_deterministically() -> None:
    ledger = build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0, symbol="BTC-PERPETUAL", canonical_symbol="BTC-PERP"
    )
    frame = _frame()
    intent = _intent(side=DeribitPaperOrderIntentSide.BUY, intent_id="paper-buy", limit_price=50_020.0)
    decision = validate_deribit_paper_order_intent(frame, intent)
    reference = normalize_deribit_paper_ledger_intent_reference(intent, decision)
    fill_result = evaluate_deribit_paper_limit_fill(frame, decision.fill_request)
    result = apply_deribit_paper_fill_to_ledger(ledger, reference, fill_result)

    assert result.accepted is True
    assert result.ledger_mutated is True
    assert result.audit_entry is not None
    assert result.ledger_state is not None
    assert result.ledger_state.venue_id is VenueId.DERIBIT
    assert result.ledger_state.cash_balance == 10_000.0
    assert result.ledger_state.position_qty == 0.5
    assert result.ledger_state.average_entry_price == 50_010.0
    assert result.ledger_state.realized_pnl == 0.0
    assert result.ledger_state.applied_fill_ids == (fill_result.fill_id,)
    assert result.ledger_state.audit_entries == (result.audit_entry,)


def test_phase36b_accepted_filled_sell_mutates_isolated_ledger_deterministically() -> None:
    ledger = build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0, symbol="BTC-PERPETUAL", canonical_symbol="BTC-PERP"
    )
    frame = _frame()
    intent = _intent(side=DeribitPaperOrderIntentSide.SELL, intent_id="paper-sell", limit_price=50_000.0)
    decision = validate_deribit_paper_order_intent(frame, intent)
    reference = normalize_deribit_paper_ledger_intent_reference(intent, decision)
    fill_result = evaluate_deribit_paper_limit_fill(frame, decision.fill_request)
    result = apply_deribit_paper_fill_to_ledger(ledger, reference, fill_result)

    assert result.accepted is True
    assert result.ledger_state is not None
    assert result.ledger_state.position_qty == -0.5
    assert result.ledger_state.average_entry_price == 50_001.0
    assert result.ledger_state.cash_balance == 10_000.0
    assert result.ledger_state.realized_pnl == 0.0


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _intent(*, side: DeribitPaperOrderIntentSide, intent_id: str, limit_price: float) -> DeribitPaperOrderIntent:
    return DeribitPaperOrderIntent(
        intent_id=intent_id,
        idempotency_key=f"idem-{intent_id}",
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        side=side,
        order_style=DeribitPaperOrderStyle.LIMIT,
        quantity=0.5,
        limit_price=limit_price,
        simulation_only=True,
    )
