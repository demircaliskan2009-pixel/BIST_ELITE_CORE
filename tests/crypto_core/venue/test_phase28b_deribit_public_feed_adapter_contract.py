from __future__ import annotations

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.deribit_public_feed_adapter import (
    DERIBIT_PUBLIC_BOOK_CHANNEL,
    DERIBIT_PUBLIC_BOOK_DIALECT_ID,
    deribit_public_book_dialect,
    deribit_public_book_observation_to_dict,
    parse_deribit_public_book_payload,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects


def _payload(*, timestamp: int = 1_700_000_000_000, event_type: str = "snapshot") -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "method": "subscription",
        "params": {
            "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
            "data": {
                "type": event_type,
                "timestamp": timestamp,
                "instrument_name": "BTC-PERPETUAL",
                "change_id": 101,
                "prev_change_id": None,
                "bids": [["new", 50_000.0, 1.25]],
                "asks": [["new", 50_010.0, 0.75]],
            },
        },
    }


def test_phase28b_adapter_uses_only_enabled_deribit_public_book_dialect() -> None:
    spec = deribit_public_book_dialect()
    ready = connector_ready_dialects()

    assert spec is not None
    assert len(ready) == 1
    assert ready[0] == spec
    assert spec.dialect_id == DERIBIT_PUBLIC_BOOK_DIALECT_ID
    assert spec.venue_id is VenueId.DERIBIT
    assert spec.feed_type is PublicFeedType.L2_ORDERBOOK
    assert spec.enabled_for_connector is True


def test_phase28b_registry_policy_values_are_preserved() -> None:
    spec = deribit_public_book_dialect()
    assert spec is not None

    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


def test_phase28b_valid_sample_public_book_payload_parses_deterministically() -> None:
    event_time_ns = 1_700_000_000_000_000_000
    result = parse_deribit_public_book_payload(_payload(), received_at_ns=event_time_ns + 500_000_000)

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.observation is not None
    assert result.observation.normalized is False
    assert result.observation.change_id == 101
    assert result.observation.receive_lag_ns == 500_000_000
    assert result.observation.bids[0].price == 50_000.0
    assert result.observation.asks[0].amount == 0.75
    assert deribit_public_book_observation_to_dict(result.observation)["dialect_id"] == DERIBIT_PUBLIC_BOOK_DIALECT_ID
