"""Scalar FeatureEngine — deterministic extract()."""

from __future__ import annotations

import pytest

from bist_core.features.feature_engine import FeatureEngine
from bist_core.models.ohlcv import OHLCVBar


def _bar(close: float, ts: int = 0) -> OHLCVBar:
    return OHLCVBar(
        symbol="X",
        open=close,
        high=close + 0.5,
        low=max(close - 0.5, 0.01),
        close=close,
        volume=1000.0,
        timestamp=ts,
    )


def test_returns_computed_correctly() -> None:
    fe = FeatureEngine()
    closes = [100.0, 100.0, 110.0]
    bars = [_bar(c, ts=i) for i, c in enumerate(closes)]
    out = fe.extract(bars, lookback=20)
    assert out["returns"] == pytest.approx(110.0 / 100.0 - 1.0)


def test_volatility_positive_on_varying_series() -> None:
    fe = FeatureEngine()
    closes = [10.0, 12.0, 9.0, 11.0, 10.5]
    bars = [_bar(c, ts=i) for i, c in enumerate(closes)]
    out = fe.extract(bars, lookback=20)
    assert out["volatility"] > 0.0


def test_slope_direction_up_vs_down() -> None:
    fe = FeatureEngine()
    up = [_bar(50.0 + i * 2.0, ts=i) for i in range(15)]
    down = [_bar(200.0 - i * 3.0, ts=i) for i in range(15)]
    su = fe.extract(up, lookback=10)["slope"]
    sd = fe.extract(down, lookback=10)["slope"]
    assert su > 0.0
    assert sd < 0.0
