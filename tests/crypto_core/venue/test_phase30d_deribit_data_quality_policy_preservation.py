from __future__ import annotations

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_marketevent_normalizer import normalize_deribit_public_book_parse_result
from crypto_core.venue.deribit_public_data_quality import evaluate_deribit_normalized_book_quality
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase30d_readiness_preconditions_and_gate_do_not_change_policy() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    before = connector_ready_dialects()
    spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")

    normalized = normalize_deribit_public_book_parse_result(
        parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
    )
    result = evaluate_deribit_normalized_book_quality(normalized)
    after = connector_ready_dialects()

    assert readiness.accepted is True
    assert len(before) == 1
    assert len(after) == 1
    assert before == after
    assert result.accepted is True
    assert spec.enabled_for_connector is True
    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


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
