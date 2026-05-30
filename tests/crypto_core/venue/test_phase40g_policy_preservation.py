from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase40g_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT
    assert ready[0].enabled_for_connector is True


def test_phase40g_deribit_public_feed_policy_values_are_preserved() -> None:
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000


def test_phase40g_public_feed_registry_was_not_used_as_phase40_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")

    assert "phase40" not in text.lower()
    assert "paper_run_harness" not in text
