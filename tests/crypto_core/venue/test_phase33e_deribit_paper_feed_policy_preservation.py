from __future__ import annotations

from pathlib import Path

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result

REGISTRY = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase33e_connector_ready_dialect_and_registry_policy_are_preserved() -> None:
    ready = connector_ready_dialects()
    result = build_deribit_paper_feed_input(accepted_replay_result())

    assert result.accepted is True
    assert len(ready) == 1
    spec = ready[0]
    assert spec.dialect_id == "deribit:l2_orderbook:book_instrument_interval"
    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


def test_phase33e_public_feed_registry_was_not_extended_for_phase33() -> None:
    registry_text = REGISTRY.read_text(encoding="utf-8")

    assert "DERIBIT_PAPER_FEED_INPUT_ID" not in registry_text
    assert "phase33" not in registry_text.lower()
