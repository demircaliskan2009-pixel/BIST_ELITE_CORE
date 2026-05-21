from __future__ import annotations

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_marketevent_normalizer import (
    normalize_deribit_public_book_observation,
    normalize_deribit_public_book_parse_result,
)
from crypto_core.venue.deribit_public_data_quality import (
    evaluate_deribit_normalized_book_quality,
    evaluate_deribit_public_data_quality,
)
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload
from crypto_core.venue.deribit_public_feed_ingest import ingest_deribit_public_data_quality_result
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase31b_snapshot_quality_result_wires_into_existing_public_feed_ingest() -> None:
    quality = evaluate_deribit_normalized_book_quality(
        normalize_deribit_public_book_parse_result(
            parse_deribit_public_book_payload(_payload("snapshot"), received_at_ns=RECEIVED_AT_NS)
        )
    )

    result = ingest_deribit_public_data_quality_result(quality)

    assert result.accepted is True
    assert result.ingest_plan is not None
    assert result.ingest_plan.require_public_data_ready is False
    assert result.ingest_plan.policy.require_order_book is True
    assert result.ingest_plan.subscription.depth == 10
    assert result.ingest_result is not None
    assert result.ingest_result.accepted is True
    assert result.ingest_result.journal_entry_count == 1
    assert result.ingest_result.replay_result.applied is True
    assert result.ingest_result.readiness_snapshot.feed_gate_ready is False
    assert result.ingest_result.readiness_snapshot.order_book_ready is False
    assert result.ingest_result.readiness_snapshot.accepted_for_paper is False


def test_phase31b_delta_quality_result_preserves_deribit_dialect_policy() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    before = connector_ready_dialects()
    spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")
    parsed = parse_deribit_public_book_payload(_payload("change"), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None
    normalized = normalize_deribit_public_book_observation(parsed.observation, prior_change_id=100)
    quality = evaluate_deribit_public_data_quality(
        normalized.market_event,
        order_book_delta=normalized.order_book_delta,
        prior_sequence_id=100,
    )

    result = ingest_deribit_public_data_quality_result(quality)
    after = connector_ready_dialects()

    assert readiness.accepted is True
    assert len(before) == 1
    assert len(after) == 1
    assert before == after
    assert result.accepted is True
    assert result.ingest_plan is not None
    assert result.ingest_plan.policy.max_staleness_ns == spec.max_staleness_ns
    assert result.ingest_plan.policy.max_receive_lag_ns == spec.max_receive_lag_ns
    assert result.ingest_plan.max_receive_lag_ns == spec.max_receive_lag_ns
    assert result.ingest_plan.subscription.depth == 10


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
