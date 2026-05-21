from __future__ import annotations

from crypto_core.data.public_data_readiness import public_data_ready_for_paper
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_feed import (
    build_deribit_paper_feed_input,
    deribit_paper_feed_frame_to_dict,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result


def test_phase33b_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    ready = connector_ready_dialects()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(ready) == 1
    assert ready[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"


def test_phase33b_accepted_replay_state_produces_read_only_paper_feed_input() -> None:
    replay = accepted_replay_result()
    result = build_deribit_paper_feed_input(replay)

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.frame is not None
    assert result.readiness_snapshot is not None
    assert public_data_ready_for_paper(result.readiness_snapshot) is True
    assert result.frame.venue_id is VenueId.DERIBIT
    assert result.frame.symbol == "BTC-PERPETUAL"
    assert result.frame.canonical_symbol == "BTC-PERP"
    assert result.frame.feed_type is PublicFeedType.L2_ORDERBOOK
    assert result.frame.sequence_id == 102
    assert result.frame.best_bid_price == 50_001.0
    assert result.frame.best_bid_quantity == 2.25
    assert result.frame.best_ask_price == 50_010.0
    assert result.frame.read_only_market_data is True
    assert result.frame.accepted_for_paper_input is True
    assert result.frame.paper_execution_ready is False
    assert result.frame.trade_ready is False


def test_phase33b_paper_feed_frame_is_deterministic() -> None:
    first = build_deribit_paper_feed_input(accepted_replay_result())
    second = build_deribit_paper_feed_input(accepted_replay_result())

    assert first.frame is not None
    assert second.frame is not None
    assert deribit_paper_feed_frame_to_dict(first.frame) == deribit_paper_feed_frame_to_dict(second.frame)
