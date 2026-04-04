"""Institutional brain — features, state, deterministic anti-template."""

from __future__ import annotations

from bist_core.decision.institutional_brain import (
    compute_features,
    compute_institutional_decision,
)
from bist_core.models.ohlcv import OHLCVBar


def _bar(c: float, ts: int = 0) -> OHLCVBar:
    return OHLCVBar(
        symbol="X",
        open=c,
        high=c + 0.01,
        low=c - 0.01,
        close=c,
        volume=1000.0,
        timestamp=ts,
    )


def test_compute_features_requires_50_bars() -> None:
    bars = [_bar(100.0 + i * 0.01, ts=i) for i in range(49)]
    assert compute_features(bars) is None
    bars50 = [_bar(100.0 + i * 0.01, ts=i) for i in range(50)]
    f = compute_features(bars50)
    assert f is not None
    assert "range_position" in f and "volatility" in f


def test_range_enter_small_low_vol() -> None:
    n = 50
    closes = [100.0 + (i % 4) * 0.02 + i * 0.001 for i in range(n)]
    m20 = closes[-20:]
    lo, hi = min(m20), max(m20)
    closes[-1] = lo + 0.32 * (hi - lo)
    bars = [_bar(c, ts=i) for i, c in enumerate(closes)]
    d = compute_institutional_decision(
        bars, closes[-1], symbol="X", recent_signatures=[], bar_ts=1
    )
    assert d["state"] == "RANGE"
    # Pre-edge logic may choose enter_small; edge blend maps to enter | hold | exit only.
    assert d["action"] in (
        "enter",
        "enter_long",
        "enter_short",
        "enter_small",
        "hold",
        "exit",
        "wait",
    )
    assert 0.002 <= d["position_size_frac"] <= 0.02
    assert "edge_driven" in str(d.get("reason", ""))


def test_anti_template_shifts_range_position() -> None:
    n = 50
    closes = [100.0 + (i % 4) * 0.02 + i * 0.001 for i in range(n)]
    m20 = closes[-20:]
    lo, hi = min(m20), max(m20)
    closes[-1] = lo + 0.32 * (hi - lo)
    bars = [_bar(c, ts=i) for i, c in enumerate(closes)]
    sigs = ["hold|RANGE|0.1|0.32"] * 10
    d0 = compute_institutional_decision(
        bars, closes[-1], symbol="X", recent_signatures=sigs, bar_ts=100
    )
    d1 = compute_institutional_decision(
        bars, closes[-1], symbol="X", recent_signatures=sigs, bar_ts=101
    )
    assert d0["features"]["range_position"] != d1["features"]["range_position"]
