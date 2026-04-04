"""Edge discovery + FeatureEngineV2 — deterministic, fail-closed."""

from __future__ import annotations

from bist_core.backtest.edge_discovery_v2 import discover_edges
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar


def test_discover_edges_fail_closed_short_series() -> None:
    bars = [
        OHLCVBar(
            timestamp=1_700_000_000 + i,
            symbol="X",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 + i * 0.01,
            volume=1000.0,
        )
        for i in range(40)
    ]
    assert discover_edges(bars) == {}


def test_discover_edges_nonempty_constant_regime() -> None:
    """Repeated feature keys → one bucket with ≥30 samples."""
    base = 1_700_000_000
    bars = [
        OHLCVBar(
            timestamp=base + i * 60,
            symbol="X",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000.0,
        )
        for i in range(130)
    ]
    out = discover_edges(bars)
    assert isinstance(out, dict)
    assert len(out) >= 1
    first = next(iter(out.values()))
    assert "exp" in first and "count" in first
    assert "confidence" in first
    assert first["count"] >= 30


def test_feature_engine_v2_extract_hour() -> None:
    ts = 1_704_067_200  # aligned with bucket hour
    bars = [
        OHLCVBar(
            timestamp=ts + i * 60,
            symbol="X",
            open=10.0,
            high=11.0,
            low=9.0,
            close=10.0 + i * 0.01,
            volume=1000.0,
        )
        for i in range(30)
    ]
    fe = FeatureEngineV2()
    f = fe.extract(bars)
    assert f["hour"] == int((ts // 3600) % 24)
    assert "vol" in f and "trend" in f and "breakout" in f and "vol_ratio" in f
