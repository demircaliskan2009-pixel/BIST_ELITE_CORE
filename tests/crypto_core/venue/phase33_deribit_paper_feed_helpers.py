from __future__ import annotations

from crypto_core.venue.deribit_marketevent_normalizer import normalize_deribit_public_book_parse_result
from crypto_core.venue.deribit_order_book_replay import DeribitOrderBookReplayEvent, replay_deribit_order_book_events
from crypto_core.venue.deribit_public_data_quality import evaluate_deribit_normalized_book_quality
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload
from crypto_core.venue.deribit_public_feed_ingest import ingest_deribit_public_data_quality_result

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def accepted_replay_result():
    snapshot_quality = quality("snapshot", change_id=101, prev_change_id=100)
    delta_quality = quality("change", change_id=102, prev_change_id=101, bid_price=50_001.0, bid_qty=2.25)
    return replay_deribit_order_book_events((entry(snapshot_quality), entry(delta_quality)))


def rejected_replay_result():
    delta_quality = quality("change", change_id=102, prev_change_id=101)
    return replay_deribit_order_book_events((entry(delta_quality),))


def entry(quality_result) -> DeribitOrderBookReplayEvent:
    return DeribitOrderBookReplayEvent(
        quality_result=quality_result,
        ingest_result=ingest_deribit_public_data_quality_result(quality_result),
    )


def quality(
    event_type: str,
    *,
    change_id: int,
    prev_change_id: int,
    bid_price: float = 50_000.0,
    bid_qty: float = 1.25,
    ask_price: float = 50_010.0,
    ask_qty: float = 0.75,
):
    return evaluate_deribit_normalized_book_quality(
        normalize_deribit_public_book_parse_result(
            parse_deribit_public_book_payload(
                {
                    "method": "subscription",
                    "params": {
                        "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
                        "data": {
                            "type": event_type,
                            "timestamp": 1_700_000_000_000,
                            "instrument_name": "BTC-PERPETUAL",
                            "change_id": change_id,
                            "prev_change_id": prev_change_id,
                            "bids": [["change", bid_price, bid_qty]],
                            "asks": [["change", ask_price, ask_qty]],
                        },
                    },
                },
                received_at_ns=RECEIVED_AT_NS,
            )
        ),
        prior_sequence_id=prev_change_id if event_type == "change" else None,
    )
