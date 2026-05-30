from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot, PublicMarketDataEvent
from crypto_core.venue.deribit_marketevent_normalizer import (
    normalize_deribit_public_book_observation,
    normalize_deribit_public_book_parse_result,
)
from crypto_core.venue.deribit_public_data_quality import evaluate_deribit_public_data_quality
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase30c_stale_and_receive_lag_breach_fail_closed() -> None:
    normalized = _normalized_snapshot()
    assert normalized.market_event is not None
    assert normalized.order_book_snapshot is not None

    event = replace(normalized.market_event, receive_time_ns=EVENT_TIME_NS + 2_500_000_000)
    snapshot = replace(normalized.order_book_snapshot, receive_time_ns=EVENT_TIME_NS + 2_500_000_000)

    result = evaluate_deribit_public_data_quality(event, order_book_snapshot=snapshot)

    assert result.accepted is False
    assert "deribit_public_data_quality:receive_lag_breach" in result.rejection_reasons
    assert "deribit_public_data_quality:stale_event" in result.rejection_reasons


def test_phase30c_detectable_sequence_gap_fails_closed() -> None:
    normalized = _normalized_delta()
    assert normalized.market_event is not None
    assert normalized.order_book_delta is not None
    delta = replace(normalized.order_book_delta, prev_update_id=99, first_update_id=100)

    result = evaluate_deribit_public_data_quality(
        normalized.market_event,
        order_book_delta=delta,
        prior_sequence_id=100,
    )

    assert result.accepted is False
    assert "deribit_public_data_quality:sequence_gap_detected" in result.rejection_reasons


def test_phase30c_missing_timestamps_fail_closed() -> None:
    normalized = _normalized_snapshot()
    assert normalized.market_event is not None
    assert normalized.order_book_snapshot is not None
    event = _unsafe_event(normalized.market_event, event_time_ns=0, receive_time_ns=0)
    snapshot = _unsafe_snapshot(normalized.order_book_snapshot, event_time_ns=0, receive_time_ns=0)

    result = evaluate_deribit_public_data_quality(event, order_book_snapshot=snapshot)

    assert result.accepted is False
    assert "deribit_public_data_quality:timestamp_invalid" in result.rejection_reasons


def test_phase30c_malformed_levels_and_negative_size_fail_closed() -> None:
    normalized = _normalized_delta()
    assert normalized.market_event is not None
    assert normalized.order_book_delta is not None

    malformed_delta = _unsafe_delta(normalized.order_book_delta, bid_updates=(object(),))
    malformed = evaluate_deribit_public_data_quality(normalized.market_event, order_book_delta=malformed_delta)
    assert malformed.accepted is False
    assert "deribit_public_data_quality:book_level_malformed" in malformed.rejection_reasons

    negative_level = _unsafe_level(price=50_000.0, quantity=-1.0)
    negative_delta = _unsafe_delta(normalized.order_book_delta, bid_updates=(negative_level,))
    negative = evaluate_deribit_public_data_quality(normalized.market_event, order_book_delta=negative_delta)
    assert negative.accepted is False
    assert "deribit_public_data_quality:book_level_invalid" in negative.rejection_reasons

    negative_price_level = _unsafe_level(price=-1.0, quantity=1.0)
    negative_price_delta = _unsafe_delta(normalized.order_book_delta, ask_updates=(negative_price_level,))
    negative_price = evaluate_deribit_public_data_quality(
        normalized.market_event, order_book_delta=negative_price_delta
    )
    assert negative_price.accepted is False
    assert "deribit_public_data_quality:book_level_invalid" in negative_price.rejection_reasons


def test_phase30c_crossed_book_and_checksum_assumption_fail_closed() -> None:
    normalized = _normalized_snapshot()
    assert normalized.market_event is not None
    assert normalized.order_book_snapshot is not None

    crossed_snapshot = _unsafe_snapshot(
        normalized.order_book_snapshot,
        bids=(OrderBookLevel(price=50_020.0, quantity=1.0),),
        asks=(OrderBookLevel(price=50_010.0, quantity=1.0),),
    )
    crossed = evaluate_deribit_public_data_quality(normalized.market_event, order_book_snapshot=crossed_snapshot)
    assert crossed.accepted is False
    assert "deribit_public_data_quality:book_crossed" in crossed.rejection_reasons

    checksummed_snapshot = _unsafe_snapshot(normalized.order_book_snapshot, checksum="abc123")
    checksummed = evaluate_deribit_public_data_quality(
        normalized.market_event, order_book_snapshot=checksummed_snapshot
    )
    assert checksummed.accepted is False
    assert "deribit_public_data_quality:checksum_unsupported" in checksummed.rejection_reasons


def test_phase30c_private_like_contamination_fails_closed() -> None:
    normalized = _normalized_snapshot()
    assert normalized.market_event is not None
    assert normalized.order_book_snapshot is not None
    contaminated_event = replace(normalized.market_event, raw_payload_ref="private/order:BTC-PERPETUAL")

    result = evaluate_deribit_public_data_quality(
        contaminated_event, order_book_snapshot=normalized.order_book_snapshot
    )

    assert result.accepted is False
    assert "deribit_public_data_quality:private_or_execution_contamination" in result.rejection_reasons


def _normalized_snapshot():
    return normalize_deribit_public_book_parse_result(
        parse_deribit_public_book_payload(_payload("snapshot"), received_at_ns=RECEIVED_AT_NS)
    )


def _normalized_delta():
    parsed = parse_deribit_public_book_payload(_payload("change"), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None
    return normalize_deribit_public_book_observation(parsed.observation, prior_change_id=100)


def _payload(event_type: str) -> dict[str, object]:
    return {
        "method": "subscription",
        "params": {
            "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
            "data": {
                "type": event_type,
                "timestamp": 1_700_000_000_000,
                "instrument_name": "BTC-PERPETUAL",
                "change_id": 101,
                "prev_change_id": 100,
                "bids": [["change", 50_000.0, 1.25]],
                "asks": [["change", 50_010.0, 0.75]],
            },
        },
    }


def _unsafe_event(base: PublicMarketDataEvent, **overrides: object) -> PublicMarketDataEvent:
    event = object.__new__(PublicMarketDataEvent)
    values = {
        "venue_id": base.venue_id,
        "symbol": base.symbol,
        "canonical_symbol": base.canonical_symbol,
        "feed_type": base.feed_type,
        "event_time_ns": base.event_time_ns,
        "receive_time_ns": base.receive_time_ns,
        "sequence_id": base.sequence_id,
        "payload_hash": base.payload_hash,
        "raw_payload_ref": base.raw_payload_ref,
        "normalized": base.normalized,
    }
    values.update(overrides)
    for key, value in values.items():
        object.__setattr__(event, key, value)
    return event


def _unsafe_snapshot(base: OrderBookSnapshot, **overrides: object) -> OrderBookSnapshot:
    snapshot = object.__new__(OrderBookSnapshot)
    values = {
        "venue_id": base.venue_id,
        "symbol": base.symbol,
        "canonical_symbol": base.canonical_symbol,
        "event_time_ns": base.event_time_ns,
        "receive_time_ns": base.receive_time_ns,
        "sequence_id": base.sequence_id,
        "bids": base.bids,
        "asks": base.asks,
        "checksum": base.checksum,
        "depth": base.depth,
        "source": base.source,
    }
    values.update(overrides)
    for key, value in values.items():
        object.__setattr__(snapshot, key, value)
    return snapshot


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
