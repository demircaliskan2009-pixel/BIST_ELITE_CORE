from __future__ import annotations

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_fill_model import (
    DeribitPaperFillRequest,
    DeribitPaperFillSide,
    DeribitPaperFillStyle,
    deribit_paper_fill_result_to_dict,
    evaluate_deribit_paper_limit_fill,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result


def test_phase34b_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    ready = connector_ready_dialects()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(ready) == 1


def test_phase34b_crossing_buy_limit_produces_deterministic_simulated_fill() -> None:
    result = evaluate_deribit_paper_limit_fill(_frame(), _request(side=DeribitPaperFillSide.BUY, limit_price=50_020.0))

    assert result.accepted is True
    assert result.filled is True
    assert result.reason_code == "deribit_paper_fill:filled_limit_crossed"
    assert result.simulated_price == 50_010.0
    assert result.simulated_qty == 0.5
    assert result.venue_id is VenueId.DERIBIT
    assert result.symbol == "BTC-PERPETUAL"
    assert result.canonical_symbol == "BTC-PERP"
    assert result.source_sequence_id == 102
    assert result.venue_submission_ready is False
    assert result.trade_ready is False
    assert result.position_mutation_ready is False
    assert result.strategy_signal_ready is False


def test_phase34b_crossing_sell_limit_produces_deterministic_simulated_fill() -> None:
    result = evaluate_deribit_paper_limit_fill(_frame(), _request(side=DeribitPaperFillSide.SELL, limit_price=50_000.0))

    assert result.accepted is True
    assert result.filled is True
    assert result.reason_code == "deribit_paper_fill:filled_limit_crossed"
    assert result.simulated_price == 50_001.0
    assert result.simulated_qty == 0.5


def test_phase34b_non_crossing_limit_is_deterministic_no_fill_not_error() -> None:
    result = evaluate_deribit_paper_limit_fill(_frame(), _request(side=DeribitPaperFillSide.BUY, limit_price=50_005.0))

    assert result.accepted is True
    assert result.filled is False
    assert result.reason_code == "deribit_paper_fill:no_fill_limit_not_crossed"
    assert result.rejection_reasons == ()
    assert result.simulated_price is None
    assert result.simulated_qty is None


def test_phase34b_result_serializer_is_deterministic() -> None:
    first = evaluate_deribit_paper_limit_fill(_frame(), _request(side=DeribitPaperFillSide.BUY, limit_price=50_020.0))
    second = evaluate_deribit_paper_limit_fill(_frame(), _request(side=DeribitPaperFillSide.BUY, limit_price=50_020.0))

    assert deribit_paper_fill_result_to_dict(first) == deribit_paper_fill_result_to_dict(second)


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _request(*, side: DeribitPaperFillSide, limit_price: float) -> DeribitPaperFillRequest:
    return DeribitPaperFillRequest(
        request_id="sim-req-1",
        side=side,
        style=DeribitPaperFillStyle.LIMIT,
        quantity=0.5,
        limit_price=limit_price,
        simulation_only=True,
    )
