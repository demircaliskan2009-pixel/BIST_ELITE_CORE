from __future__ import annotations

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_fill_model import DeribitPaperFillSide, DeribitPaperFillStyle
from crypto_core.venue.deribit_paper_order_intent import (
    ACCOUNTING_LEDGER_NOT_READY,
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
    deribit_paper_order_intent_decision_to_dict,
    validate_deribit_paper_order_intent,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result


def test_phase35b_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    ready = connector_ready_dialects()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(ready) == 1


def test_phase35b_valid_limit_buy_intent_produces_fill_model_request() -> None:
    decision = validate_deribit_paper_order_intent(_frame(), _intent(side=DeribitPaperOrderIntentSide.BUY))

    assert decision.accepted is True
    assert decision.reason_code == "deribit_paper_order_intent:accepted_for_fill_model_request"
    assert decision.fill_request is not None
    assert decision.fill_request.request_id == "paper-intent-buy"
    assert decision.fill_request.side is DeribitPaperFillSide.BUY
    assert decision.fill_request.style is DeribitPaperFillStyle.LIMIT
    assert decision.fill_request.quantity == 0.5
    assert decision.fill_request.limit_price == 50_020.0
    assert decision.fill_request.simulation_only is True
    assert decision.intent_notional == 25_010.0
    assert decision.accounting_gate_status == ACCOUNTING_LEDGER_NOT_READY
    assert decision.exchange_order_ready is False
    assert decision.venue_submission_ready is False
    assert decision.trade_ready is False


def test_phase35b_valid_limit_sell_intent_produces_fill_model_request() -> None:
    decision = validate_deribit_paper_order_intent(
        _frame(),
        _intent(side=DeribitPaperOrderIntentSide.SELL, intent_id="paper-intent-sell", limit_price=50_000.0),
    )

    assert decision.accepted is True
    assert decision.fill_request is not None
    assert decision.fill_request.side is DeribitPaperFillSide.SELL
    assert decision.fill_request.limit_price == 50_000.0


def test_phase35b_decision_serializer_is_deterministic() -> None:
    first = validate_deribit_paper_order_intent(_frame(), _intent(side=DeribitPaperOrderIntentSide.BUY))
    second = validate_deribit_paper_order_intent(_frame(), _intent(side=DeribitPaperOrderIntentSide.BUY))

    assert deribit_paper_order_intent_decision_to_dict(first) == deribit_paper_order_intent_decision_to_dict(second)


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _intent(
    *,
    side: DeribitPaperOrderIntentSide,
    intent_id: str = "paper-intent-buy",
    limit_price: float = 50_020.0,
) -> DeribitPaperOrderIntent:
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
