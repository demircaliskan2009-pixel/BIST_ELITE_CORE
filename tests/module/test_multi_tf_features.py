"""MultiTFFeatures — skips short series."""

from __future__ import annotations

from bist_core.features.multi_tf_features import MultiTFFeatures
from bist_core.models.ohlcv import OHLCVBar


def _bar(i: int) -> OHLCVBar:
    c = 100.0 + i * 0.1
    return OHLCVBar(
        timestamp=1_700_000_000 + i * 60,
        symbol="X",
        open=c,
        high=c + 0.5,
        low=c - 0.5,
        close=c,
        volume=1000.0,
    )


def test_extract_only_long_enough() -> None:
    long_b = [_bar(i) for i in range(50)]
    short_b = [_bar(i) for i in range(10)]
    m = MultiTFFeatures().extract({"1m": short_b, "5m": long_b})
    assert "1m" not in m
    assert "5m" in m and "vol" in m["5m"]
