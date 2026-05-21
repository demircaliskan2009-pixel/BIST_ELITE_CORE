from __future__ import annotations

from crypto_core.data.order_book import order_book_state_to_dict
from crypto_core.venue.contracts import OrderBookDelta, OrderBookLevel
from crypto_core.venue.deribit_marketevent_normalizer import normalize_deribit_public_book_parse_result
from crypto_core.venue.deribit_order_book_replay import DeribitOrderBookReplayEvent, replay_deribit_order_book_events
from crypto_core.venue.deribit_public_data_quality import (
    evaluate_deribit_normalized_book_quality,
    evaluate_deribit_public_data_quality,
)
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload
from crypto_core.venue.deribit_public_feed_ingest import ingest_deribit_public_data_quality_result

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase32c_delta_before_snapshot_fails_closed() -> None:
    delta_quality = _quality("change", change_id=102, prev_change_id=101)
    delta_ingest = ingest_deribit_public_data_quality_result(delta_quality)

    result = replay_deribit_order_book_events((_entry(delta_quality, delta_ingest),))

    assert result.accepted is False
    assert result.state is None
    assert result.applied_event_count == 0
    assert "deribit_order_book_replay:snapshot_required" in result.rejection_reasons


def test_phase32c_sequence_gap_fails_closed_and_does_not_mutate_state() -> None:
    snapshot_quality = _quality("snapshot", change_id=101, prev_change_id=100)
    snapshot_ingest = ingest_deribit_public_data_quality_result(snapshot_quality)
    ready = replay_deribit_order_book_events((_entry(snapshot_quality, snapshot_ingest),))
    assert ready.state is not None
    before = order_book_state_to_dict(ready.state)

    gap_quality = _quality("change", change_id=103, prev_change_id=100)
    gap_ingest = ingest_deribit_public_data_quality_result(gap_quality)

    result = replay_deribit_order_book_events((_entry(gap_quality, gap_ingest),), initial_state=ready.state)

    assert result.accepted is False
    assert result.state is not None
    assert order_book_state_to_dict(result.state) == before
    assert "order_book:prev_update_id_mismatch" in result.rejection_reasons


def test_phase32c_malformed_and_negative_levels_fail_closed_via_mandatory_quality_gate() -> None:
    normalized = normalize_deribit_public_book_parse_result(
        parse_deribit_public_book_payload(
            _payload("change", change_id=102, prev_change_id=101), received_at_ns=RECEIVED_AT_NS
        )
    )
    assert normalized.market_event is not None
    assert normalized.order_book_delta is not None

    malformed_delta = _unsafe_delta(normalized.order_book_delta, bid_updates=(object(),))
    malformed_quality = evaluate_deribit_public_data_quality(normalized.market_event, order_book_delta=malformed_delta)
    malformed_ingest = ingest_deribit_public_data_quality_result(malformed_quality)
    malformed = replay_deribit_order_book_events((_entry(malformed_quality, malformed_ingest),))
    assert malformed.accepted is False
    assert "deribit_public_data_quality:book_level_malformed" in malformed.rejection_reasons

    negative_delta = _unsafe_delta(
        normalized.order_book_delta,
        ask_updates=(_unsafe_level(price=50_010.0, quantity=-1.0),),
    )
    negative_quality = evaluate_deribit_public_data_quality(normalized.market_event, order_book_delta=negative_delta)
    negative_ingest = ingest_deribit_public_data_quality_result(negative_quality)
    negative = replay_deribit_order_book_events((_entry(negative_quality, negative_ingest),))
    assert negative.accepted is False
    assert "deribit_public_data_quality:book_level_invalid" in negative.rejection_reasons


def test_phase32c_crossed_resulting_state_fails_closed_and_preserves_last_good_book() -> None:
    snapshot_quality = _quality("snapshot", change_id=101, prev_change_id=100)
    snapshot_ingest = ingest_deribit_public_data_quality_result(snapshot_quality)
    ready = replay_deribit_order_book_events((_entry(snapshot_quality, snapshot_ingest),))
    assert ready.state is not None
    before = order_book_state_to_dict(ready.state)

    crossed_quality = _quality(
        "change",
        change_id=102,
        prev_change_id=101,
        bid_price=50_020.0,
        ask_price=50_030.0,
    )
    crossed_ingest = ingest_deribit_public_data_quality_result(crossed_quality)
    result = replay_deribit_order_book_events((_entry(crossed_quality, crossed_ingest),), initial_state=ready.state)

    assert result.accepted is False
    assert result.state is not None
    assert order_book_state_to_dict(result.state) == before
    assert "order_book:crossed" in result.rejection_reasons


def _entry(quality_result, ingest_result) -> DeribitOrderBookReplayEvent:
    return DeribitOrderBookReplayEvent(quality_result=quality_result, ingest_result=ingest_result)


def _quality(
    event_type: str,
    *,
    change_id: int,
    prev_change_id: int,
    bid_price: float = 50_000.0,
    ask_price: float = 50_010.0,
) -> object:
    return evaluate_deribit_normalized_book_quality(
        normalize_deribit_public_book_parse_result(
            parse_deribit_public_book_payload(
                _payload(
                    event_type,
                    change_id=change_id,
                    prev_change_id=prev_change_id,
                    bid_price=bid_price,
                    ask_price=ask_price,
                ),
                received_at_ns=RECEIVED_AT_NS,
            )
        )
    )


def _payload(
    event_type: str,
    *,
    change_id: int,
    prev_change_id: int,
    bid_price: float = 50_000.0,
    ask_price: float = 50_010.0,
) -> dict[str, object]:
    return {
        "method": "subscription",
        "params": {
            "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
            "data": {
                "type": event_type,
                "timestamp": 1_700_000_000_000,
                "instrument_name": "BTC-PERPETUAL",
                "change_id": change_id,
                "prev_change_id": prev_change_id,
                "bids": [["change", bid_price, 1.25]],
                "asks": [["change", ask_price, 0.75]],
            },
        },
    }


def _unsafe_delta(base: OrderBookDelta, **overrides: object) -> OrderBookDelta:
    delta = object.__new__(OrderBookDelta)
    values = {
        "venue_id": base.venue_id,
        "symbol": base.symbol,
        "canonical_symbol": base.canonical_symbol,
        "event_time_ns": base.event_time_ns,
        "receive_time_ns": base.receive_time_ns,
        "first_update_id": base.first_update_id,
        "final_update_id": base.final_update_id,
        "prev_update_id": base.prev_update_id,
        "bid_updates": base.bid_updates,
        "ask_updates": base.ask_updates,
        "checksum": base.checksum,
        "source": base.source,
    }
    values.update(overrides)
    for key, value in values.items():
        object.__setattr__(delta, key, value)
    return delta


def _unsafe_level(*, price: float, quantity: float) -> OrderBookLevel:
    level = object.__new__(OrderBookLevel)
    object.__setattr__(level, "price", price)
    object.__setattr__(level, "quantity", quantity)
    return level
