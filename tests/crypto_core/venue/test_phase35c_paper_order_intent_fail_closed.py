from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
    validate_deribit_paper_order_intent,
)
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import (
    EVENT_TIME_NS,
    accepted_replay_result,
    rejected_replay_result,
)


def test_phase35c_market_and_non_limit_styles_are_rejected() -> None:
    market = validate_deribit_paper_order_intent(
        _frame(),
        replace(_intent(), order_style=DeribitPaperOrderStyle.MARKET, limit_price=None),
    )
    stop = validate_deribit_paper_order_intent(_frame(), replace(_intent(), order_style=DeribitPaperOrderStyle.STOP))

    assert market.accepted is False
    assert stop.accepted is False
    assert "deribit_paper_order_intent:non_limit_style_not_supported" in market.rejection_reasons
    assert "deribit_paper_order_intent:non_limit_style_not_supported" in stop.rejection_reasons


def test_phase35c_simulation_only_false_is_rejected() -> None:
    decision = validate_deribit_paper_order_intent(_frame(), replace(_intent(), simulation_only=False))

    assert decision.accepted is False
    assert "deribit_paper_order_intent:not_simulation_only" in decision.rejection_reasons


def test_phase35c_zero_or_negative_quantity_is_rejected() -> None:
    zero = validate_deribit_paper_order_intent(_frame(), replace(_intent(), quantity=0.0))
    negative = validate_deribit_paper_order_intent(_frame(), replace(_intent(), quantity=-1.0))

    assert zero.accepted is False
    assert negative.accepted is False
    assert "deribit_paper_order_intent:quantity_invalid" in zero.rejection_reasons
    assert "deribit_paper_order_intent:quantity_invalid" in negative.rejection_reasons


def test_phase35c_zero_or_negative_limit_price_is_rejected() -> None:
    zero = validate_deribit_paper_order_intent(_frame(), replace(_intent(), limit_price=0.0))
    negative = validate_deribit_paper_order_intent(_frame(), replace(_intent(), limit_price=-1.0))

    assert zero.accepted is False
    assert negative.accepted is False
    assert "deribit_paper_order_intent:limit_price_invalid" in zero.rejection_reasons
    assert "deribit_paper_order_intent:limit_price_invalid" in negative.rejection_reasons


def test_phase35c_venue_or_instrument_mismatch_is_rejected() -> None:
    venue = validate_deribit_paper_order_intent(_frame(), replace(_intent(), venue_id=VenueId.BINANCE_USDM))
    symbol = validate_deribit_paper_order_intent(_frame(), replace(_intent(), symbol="ETH-PERPETUAL"))

    assert venue.accepted is False
    assert symbol.accepted is False
    assert "deribit_paper_order_intent:venue_mismatch" in venue.rejection_reasons
    assert "deribit_paper_order_intent:instrument_mismatch" in symbol.rejection_reasons


def test_phase35c_stale_or_unhealthy_paper_feed_frame_is_rejected() -> None:
    stale = validate_deribit_paper_order_intent(_frame(), _intent(), now_ns=EVENT_TIME_NS + 3_000_000_000)
    rejected = validate_deribit_paper_order_intent(
        build_deribit_paper_feed_input(rejected_replay_result()).frame, _intent()
    )

    assert stale.accepted is False
    assert "deribit_paper_order_intent:stale_frame" in stale.rejection_reasons
    assert "deribit_paper_order_intent:receive_lag_breach" in stale.rejection_reasons
    assert rejected.accepted is False
    assert "deribit_paper_order_intent:frame_malformed" in rejected.rejection_reasons


def test_phase35c_live_shadow_and_scope_contamination_are_rejected() -> None:
    live = validate_deribit_paper_order_intent(_frame(), replace(_intent(), live_trading_requested=True))
    shadow = validate_deribit_paper_order_intent(_frame(), replace(_intent(), shadow_trading_requested=True))
    contaminated = validate_deribit_paper_order_intent(_frame(), replace(_intent(), intent_id="private-account-intent"))

    assert live.accepted is False
    assert shadow.accepted is False
    assert contaminated.accepted is False
    assert "deribit_paper_order_intent:live_or_shadow_requested" in live.rejection_reasons
    assert "deribit_paper_order_intent:live_or_shadow_requested" in shadow.rejection_reasons
    assert "deribit_paper_order_intent:scope_contamination" in contaminated.rejection_reasons


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _intent() -> DeribitPaperOrderIntent:
    return DeribitPaperOrderIntent(
        intent_id="paper-intent-fail",
        idempotency_key="idem-paper-intent-fail",
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        side=DeribitPaperOrderIntentSide.BUY,
        order_style=DeribitPaperOrderStyle.LIMIT,
        quantity=0.5,
        limit_price=50_020.0,
        simulation_only=True,
    )
