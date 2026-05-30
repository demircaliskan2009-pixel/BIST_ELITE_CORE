from __future__ import annotations

from crypto_core.venue.contracts import PublicFeedHealth
from crypto_core.venue.deribit_marketevent_normalizer import (
    normalize_deribit_public_book_observation,
    normalize_deribit_public_book_parse_result,
)
from crypto_core.venue.deribit_public_data_quality import (
    evaluate_deribit_normalized_book_quality,
    evaluate_deribit_public_data_quality,
)
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase30b_snapshot_event_passes_data_quality_gate() -> None:
    normalized = normalize_deribit_public_book_parse_result(
        parse_deribit_public_book_payload(_payload("snapshot"), received_at_ns=RECEIVED_AT_NS)
    )

    result = evaluate_deribit_normalized_book_quality(normalized)

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert isinstance(result.public_feed_health, PublicFeedHealth)
    assert result.public_feed_health.healthy is True
    assert result.public_feed_health.stale is False
    assert result.public_feed_health.gap_detected is False
    assert result.public_feed_health.resync_required is False
    assert result.market_event == normalized.market_event
    assert result.order_book_snapshot == normalized.order_book_snapshot
    assert result.order_book_delta is None


def test_phase30b_delta_event_passes_data_quality_gate() -> None:
    parsed = parse_deribit_public_book_payload(_payload("change"), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None
    normalized = normalize_deribit_public_book_observation(parsed.observation, prior_change_id=100)

    result = evaluate_deribit_public_data_quality(
        normalized.market_event,
        order_book_delta=normalized.order_book_delta,
        prior_sequence_id=100,
    )

    assert result.accepted is True
    assert result.public_feed_health is not None
    assert result.public_feed_health.healthy is True
    assert result.public_feed_health.symbol == "BTC-PERPETUAL"
    assert result.order_book_delta == normalized.order_book_delta
    assert result.order_book_snapshot is None


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
