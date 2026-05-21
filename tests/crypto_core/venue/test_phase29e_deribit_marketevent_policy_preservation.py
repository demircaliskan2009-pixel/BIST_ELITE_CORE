from __future__ import annotations

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect


def test_phase29e_public_feed_dialect_policy_values_are_preserved() -> None:
    ready = connector_ready_dialects()
    spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")

    assert len(ready) == 1
    assert ready[0] == spec
    assert spec.enabled_for_connector is True
    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000
