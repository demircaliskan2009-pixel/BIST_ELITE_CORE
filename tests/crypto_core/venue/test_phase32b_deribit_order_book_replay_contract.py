from __future__ import annotations

from crypto_core.data.order_book import order_book_state_ready
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_marketevent_normalizer import normalize_deribit_public_book_parse_result
from crypto_core.venue.deribit_order_book_replay import DeribitOrderBookReplayEvent, replay_deribit_order_book_events
from crypto_core.venue.deribit_public_data_quality import evaluate_deribit_normalized_book_quality
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload
from crypto_core.venue.deribit_public_feed_ingest import ingest_deribit_public_data_quality_result
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase32b_readiness_preconditions_hold_and_replay_preserves_dialect_policy() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    before = connector_ready_dialects()
    spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")

    snapshot_quality = _quality("snapshot")
    snapshot_ingest = ingest_deribit_public_data_quality_result(snapshot_quality)
    result = replay_deribit_order_book_events((_entry(snapshot_quality, snapshot_ingest),))
    after = connector_ready_dialects()

    assert readiness.accepted is True
    assert len(before) == 1
    assert len(after) == 1
    assert before == after
    assert result.accepted is True
    assert result.state is not None
    assert result.order_book_result is not None
    assert result.order_book_result.applied is True
    assert order_book_state_ready(result.state) is True
    assert result.state.last_sequence_id == 101
    assert result.applied_event_count == 1
    assert result.state.source == snapshot_quality.order_book_snapshot.source
    assert snapshot_ingest.ingest_plan is not None
    assert snapshot_ingest.ingest_plan.policy.max_staleness_ns == spec.max_staleness_ns
    assert snapshot_ingest.ingest_plan.policy.max_receive_lag_ns == spec.max_receive_lag_ns


def test_phase32b_valid_snapshot_then_delta_updates_state_deterministically() -> None:
    snapshot_quality = _quality("snapshot", change_id=101, prev_change_id=100)
    snapshot_ingest = ingest_deribit_public_data_quality_result(snapshot_quality)
    delta_quality = _quality("change", change_id=102, prev_change_id=101, bid_price=50_001.0, bid_qty=2.25)
    delta_ingest = ingest_deribit_public_data_quality_result(delta_quality)

    result = replay_deribit_order_book_events(
        (
            _entry(snapshot_quality, snapshot_ingest),
            _entry(delta_quality, delta_ingest),
        )
    )

    assert result.accepted is True
    assert result.state is not None
    assert result.state.last_sequence_id == 102
    assert tuple((level.price, level.quantity) for level in result.state.bids) == (
        (50_001.0, 2.25),
        (50_000.0, 1.25),
    )
    assert tuple((level.price, level.quantity) for level in result.state.asks) == ((50_010.0, 0.75),)
    assert result.applied_event_count == 2
    assert result.rejection_reasons == ()


def _entry(quality_result, ingest_result) -> DeribitOrderBookReplayEvent:
    return DeribitOrderBookReplayEvent(quality_result=quality_result, ingest_result=ingest_result)


def _quality(
    event_type: str,
    *,
    change_id: int = 101,
    prev_change_id: int = 100,
    bid_price: float = 50_000.0,
    bid_qty: float = 1.25,
    ask_price: float = 50_010.0,
    ask_qty: float = 0.75,
):
    return evaluate_deribit_normalized_book_quality(
        normalize_deribit_public_book_parse_result(
            parse_deribit_public_book_payload(
                _payload(
                    event_type,
                    change_id=change_id,
                    prev_change_id=prev_change_id,
                    bid_price=bid_price,
                    bid_qty=bid_qty,
                    ask_price=ask_price,
                    ask_qty=ask_qty,
                ),
                received_at_ns=RECEIVED_AT_NS,
            )
        ),
        prior_sequence_id=prev_change_id if event_type == "change" else None,
    )


def _payload(
    event_type: str,
    *,
    change_id: int,
    prev_change_id: int,
    bid_price: float,
    bid_qty: float,
    ask_price: float,
    ask_qty: float,
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
                "bids": [["change", bid_price, bid_qty]],
                "asks": [["change", ask_price, ask_qty]],
            },
        },
    }
