from __future__ import annotations

from crypto_core.venue.contracts import (
    OrderBookDelta,
    OrderBookSnapshot,
    PublicFeedType,
    PublicMarketDataEvent,
    VenueId,
)
from crypto_core.venue.deribit_marketevent_normalizer import (
    normalize_deribit_public_book_observation,
    normalize_deribit_public_book_parse_result,
)
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase29b_snapshot_observation_normalizes_to_public_event_and_snapshot() -> None:
    parsed = parse_deribit_public_book_payload(_payload(event_type="snapshot"), received_at_ns=RECEIVED_AT_NS)
    result = normalize_deribit_public_book_parse_result(parsed)

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert isinstance(result.market_event, PublicMarketDataEvent)
    assert isinstance(result.order_book_snapshot, OrderBookSnapshot)
    assert result.order_book_delta is None
    assert result.market_event.venue_id is VenueId.DERIBIT
    assert result.market_event.symbol == "BTC-PERPETUAL"
    assert result.market_event.canonical_symbol == "BTC-PERP"
    assert result.market_event.feed_type is PublicFeedType.L2_ORDERBOOK
    assert result.market_event.event_time_ns == EVENT_TIME_NS
    assert result.market_event.receive_time_ns == RECEIVED_AT_NS
    assert result.market_event.sequence_id == 101
    assert result.market_event.normalized is True
    assert result.order_book_snapshot.bids[0].price == 50_000.0
    assert result.order_book_snapshot.asks[0].quantity == 0.75


def test_phase29b_delta_observation_normalizes_to_public_event_and_delta() -> None:
    parsed = parse_deribit_public_book_payload(_payload(event_type="change"), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None

    result = normalize_deribit_public_book_observation(parsed.observation, prior_change_id=100)

    assert result.accepted is True
    assert isinstance(result.market_event, PublicMarketDataEvent)
    assert result.order_book_snapshot is None
    assert isinstance(result.order_book_delta, OrderBookDelta)
    assert result.order_book_delta.prev_update_id == 100
    assert result.order_book_delta.first_update_id == 101
    assert result.order_book_delta.final_update_id == 101
    assert result.order_book_delta.bid_updates[0].quantity == 1.25


def test_phase29b_typeless_aggregated_observation_normalizes_event_only() -> None:
    parsed = parse_deribit_public_book_payload(_payload(event_type=None), received_at_ns=RECEIVED_AT_NS)
    result = normalize_deribit_public_book_parse_result(parsed)

    assert result.accepted is True
    assert isinstance(result.market_event, PublicMarketDataEvent)
    assert result.order_book_snapshot is None
    assert result.order_book_delta is None
    assert result.market_event.raw_payload_ref is not None
    assert result.market_event.raw_payload_ref.endswith(":unspecified")


def test_phase29b_change_without_prev_change_id_degrades_to_event_only() -> None:
    payload = _payload(event_type="change")
    data = payload["params"]["data"]  # type: ignore[index]
    assert isinstance(data, dict)
    data["prev_change_id"] = None
    parsed = parse_deribit_public_book_payload(payload, received_at_ns=RECEIVED_AT_NS)

    result = normalize_deribit_public_book_parse_result(parsed)

    assert result.accepted is True
    assert isinstance(result.market_event, PublicMarketDataEvent)
    assert result.order_book_snapshot is None
    assert result.order_book_delta is None
    assert result.market_event.sequence_id == 101


def _payload(event_type: str | None) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
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
