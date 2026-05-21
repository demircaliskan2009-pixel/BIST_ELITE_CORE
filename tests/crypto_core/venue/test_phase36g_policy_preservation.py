from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase36g_connector_ready_dialects_and_validator_state_remain_preserved() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    dialects = connector_ready_dialects()
    spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(dialects) == 1
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


def test_phase36g_public_feed_dialects_source_is_unchanged_for_deribit_connector_policy() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")

    assert "deribit:l2_orderbook:book_instrument_interval" in text
    assert "supports_checksum=False" in text
    assert "max_gap_tolerance=0" in text
    assert "enabled_for_connector=True" in text
