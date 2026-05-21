from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_fill_model import (
    DeribitPaperFillRequest,
    DeribitPaperFillSide,
    DeribitPaperFillStyle,
    evaluate_deribit_paper_limit_fill,
)
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import (
    EVENT_TIME_NS,
    accepted_replay_result,
    rejected_replay_result,
)


def test_phase34c_rejected_paper_feed_frame_fails_closed() -> None:
    paper_feed = build_deribit_paper_feed_input(rejected_replay_result())

    result = evaluate_deribit_paper_limit_fill(paper_feed.frame, _request())

    assert result.accepted is False
    assert result.filled is False
    assert "deribit_paper_fill:frame_malformed" in result.rejection_reasons


def test_phase34c_stale_or_lag_breached_frame_fails_closed() -> None:
    result = evaluate_deribit_paper_limit_fill(_frame(), _request(), now_ns=EVENT_TIME_NS + 3_000_000_000)

    assert result.accepted is False
    assert "deribit_paper_fill:stale_frame" in result.rejection_reasons
    assert "deribit_paper_fill:receive_lag_breach" in result.rejection_reasons


def test_phase34c_missing_best_bid_or_ask_fails_closed() -> None:
    frame = replace(_frame(), bid_levels=())

    result = evaluate_deribit_paper_limit_fill(frame, _request())

    assert result.accepted is False
    assert "deribit_paper_fill:bid_levels_missing" in result.rejection_reasons


def test_phase34c_crossed_book_fails_closed() -> None:
    frame = replace(_frame(), best_bid_price=50_020.0, best_ask_price=50_010.0)

    result = evaluate_deribit_paper_limit_fill(frame, _request())

    assert result.accepted is False
    assert "deribit_paper_fill:book_crossed" in result.rejection_reasons


def test_phase34c_zero_or_negative_quantity_fails_closed() -> None:
    result = evaluate_deribit_paper_limit_fill(_frame(), replace(_request(), quantity=0.0))
    negative = evaluate_deribit_paper_limit_fill(_frame(), replace(_request(), quantity=-1.0))

    assert result.accepted is False
    assert negative.accepted is False
    assert "deribit_paper_fill:quantity_invalid" in result.rejection_reasons
    assert "deribit_paper_fill:quantity_invalid" in negative.rejection_reasons


def test_phase34c_zero_or_negative_limit_price_fails_closed() -> None:
    result = evaluate_deribit_paper_limit_fill(_frame(), replace(_request(), limit_price=0.0))
    negative = evaluate_deribit_paper_limit_fill(_frame(), replace(_request(), limit_price=-1.0))

    assert result.accepted is False
    assert negative.accepted is False
    assert "deribit_paper_fill:limit_price_invalid" in result.rejection_reasons
    assert "deribit_paper_fill:limit_price_invalid" in negative.rejection_reasons


def test_phase34c_scope_contamination_fails_closed() -> None:
    frame = replace(_frame(), source="private-account-source")

    result = evaluate_deribit_paper_limit_fill(frame, _request())

    assert result.accepted is False
    assert "deribit_paper_fill:scope_contamination" in result.rejection_reasons


def test_phase34c_market_style_is_not_implemented_fail_closed() -> None:
    result = evaluate_deribit_paper_limit_fill(
        _frame(),
        replace(_request(), style=DeribitPaperFillStyle.MARKET, limit_price=None),
    )

    assert result.accepted is False
    assert result.reason_code == "deribit_paper_fill:market_not_implemented"


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _request() -> DeribitPaperFillRequest:
    return DeribitPaperFillRequest(
        request_id="sim-req-fail",
        side=DeribitPaperFillSide.BUY,
        style=DeribitPaperFillStyle.LIMIT,
        quantity=0.5,
        limit_price=50_020.0,
        simulation_only=True,
    )
