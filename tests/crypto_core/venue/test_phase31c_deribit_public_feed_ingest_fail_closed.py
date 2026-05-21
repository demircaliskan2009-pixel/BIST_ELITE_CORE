from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_marketevent_normalizer import normalize_deribit_public_book_parse_result
from crypto_core.venue.deribit_public_data_quality import (
    evaluate_deribit_normalized_book_quality,
    evaluate_deribit_public_data_quality,
)
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload
from crypto_core.venue.deribit_public_feed_ingest import ingest_deribit_public_data_quality_result

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase31c_rejected_quality_gate_result_never_enters_ingest() -> None:
    normalized = normalize_deribit_public_book_parse_result(
        parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
    )
    assert normalized.market_event is not None
    assert normalized.order_book_snapshot is not None
    contaminated_event = replace(normalized.market_event, raw_payload_ref="private/order:BTC-PERPETUAL")
    quality = evaluate_deribit_public_data_quality(
        contaminated_event, order_book_snapshot=normalized.order_book_snapshot
    )

    result = ingest_deribit_public_data_quality_result(quality)

    assert result.accepted is False
    assert result.ingest_result is None
    assert "deribit_public_feed_ingest:quality_gate_rejected" in result.rejection_reasons
    assert "deribit_public_data_quality:private_or_execution_contamination" in result.rejection_reasons


def test_phase31c_post_gate_receive_lag_breach_fails_closed() -> None:
    quality = evaluate_deribit_normalized_book_quality(
        normalize_deribit_public_book_parse_result(
            parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
        )
    )

    result = ingest_deribit_public_data_quality_result(quality, now_ns=RECEIVED_AT_NS + 1_000_000_001)

    assert result.accepted is False
    assert result.ingest_result is not None
    assert "deribit_public_feed_ingest:ingest_rejected" in result.rejection_reasons
    assert "public_feed_source:receive_lag_exceeded" in result.rejection_reasons


def _payload() -> dict[str, object]:
    return {
        "method": "subscription",
        "params": {
            "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
            "data": {
                "type": "snapshot",
                "timestamp": 1_700_000_000_000,
                "instrument_name": "BTC-PERPETUAL",
                "change_id": 101,
                "prev_change_id": 100,
                "bids": [["change", 50_000.0, 1.25]],
                "asks": [["change", 50_010.0, 0.75]],
            },
        },
    }
