from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.contracts import VenueId
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
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result


def test_phase36c_no_fill_or_rejected_fill_do_not_mutate_ledger() -> None:
    ledger = _ledger()
    no_fill = _result(limit_price=50_005.0)
    no_fill_apply = apply_deribit_paper_fill_to_ledger(ledger, no_fill[2], no_fill[3])
    rejected = _result(quantity=3.0)
    rejected_apply = apply_deribit_paper_fill_to_ledger(ledger, rejected[2], rejected[3])

    assert no_fill_apply.accepted is False
    assert no_fill_apply.ledger_mutated is False
    assert no_fill_apply.ledger_state == ledger
    assert "deribit_paper_ledger:no_fill_result" in no_fill_apply.rejection_reasons
    assert rejected_apply.accepted is False
    assert rejected_apply.ledger_mutated is False
    assert rejected_apply.ledger_state == ledger
    assert "deribit_paper_ledger:fill_result_rejected" in rejected_apply.rejection_reasons


def test_phase36c_missing_ledger_and_instrument_mismatch_fail_closed() -> None:
    _, _, reference, fill_result = _result()
    missing = apply_deribit_paper_fill_to_ledger(None, reference, fill_result)
    mismatch = apply_deribit_paper_fill_to_ledger(
        _ledger(),
        reference,
        replace(fill_result, venue_id=VenueId.DERIBIT, symbol="ETH-PERPETUAL", canonical_symbol="ETH-PERP"),
    )

    assert missing.accepted is False
    assert "deribit_paper_ledger:absent_required_ledger_state" in missing.rejection_reasons
    assert mismatch.accepted is False
    assert "deribit_paper_ledger:instrument_mismatch" in mismatch.rejection_reasons


def test_phase36c_zero_or_negative_qty_or_price_fail_closed() -> None:
    ledger = _ledger()
    _, _, reference, fill_result = _result()
    zero_qty = apply_deribit_paper_fill_to_ledger(ledger, reference, replace(fill_result, simulated_qty=0.0))
    neg_qty = apply_deribit_paper_fill_to_ledger(ledger, reference, replace(fill_result, simulated_qty=-1.0))
    zero_price = apply_deribit_paper_fill_to_ledger(ledger, reference, replace(fill_result, simulated_price=0.0))
    neg_price = apply_deribit_paper_fill_to_ledger(ledger, reference, replace(fill_result, simulated_price=-1.0))

    assert "deribit_paper_ledger:fill_result_invalid" in zero_qty.rejection_reasons
    assert "deribit_paper_ledger:fill_result_invalid" in neg_qty.rejection_reasons
    assert "deribit_paper_ledger:fill_result_invalid" in zero_price.rejection_reasons
    assert "deribit_paper_ledger:fill_result_invalid" in neg_price.rejection_reasons


def test_phase36c_private_live_or_exchange_like_fill_fails_closed() -> None:
    ledger = _ledger()
    _, _, reference, fill_result = _result()
    contaminated = apply_deribit_paper_fill_to_ledger(
        ledger, reference, replace(fill_result, fill_id="private-live-fill")
    )
    exchange_like = apply_deribit_paper_fill_to_ledger(
        ledger, reference, replace(fill_result, venue_submission_ready=True)
    )

    assert contaminated.accepted is False
    assert (
        "deribit_paper_ledger:fill_result_invalid" in contaminated.rejection_reasons
        or "deribit_paper_ledger:fill_request_mismatch" in contaminated.rejection_reasons
    )
    assert exchange_like.accepted is False
    assert "deribit_paper_ledger:fill_result_invalid" in exchange_like.rejection_reasons


def _ledger():
    return build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0, symbol="BTC-PERPETUAL", canonical_symbol="BTC-PERP"
    )


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _intent(*, limit_price: float = 50_020.0, quantity: float = 0.5) -> DeribitPaperOrderIntent:
    return DeribitPaperOrderIntent(
        intent_id="paper-fail-closed",
        idempotency_key="idem-paper-fail-closed",
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        side=DeribitPaperOrderIntentSide.BUY,
        order_style=DeribitPaperOrderStyle.LIMIT,
        quantity=quantity,
        limit_price=limit_price,
        simulation_only=True,
    )


def _result(*, limit_price: float = 50_020.0, quantity: float = 0.5):
    frame = _frame()
    intent = _intent(limit_price=limit_price, quantity=quantity)
    decision = validate_deribit_paper_order_intent(frame, intent)
    reference = normalize_deribit_paper_ledger_intent_reference(intent, decision)
    return frame, decision, reference, evaluate_deribit_paper_limit_fill(frame, decision.fill_request)
