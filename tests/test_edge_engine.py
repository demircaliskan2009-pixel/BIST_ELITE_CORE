"""Tests for institutional edge scoring via ``compute_edge`` + feature bundle."""

from __future__ import annotations

import math

from bist_core.decision.edge_engine import compute_edge
from bist_core.decision.institutional_brain import (
    build_compute_edge_features,
    compute_features,
)


def _f_from_close_dicts(bars: list[dict[str, float]], *, vol_norm: float, rp: float):
    closes = [float(b["close"]) for b in bars]
    lc = closes[-1]
    st = (
        (closes[-1] - closes[-10]) / max(abs(closes[-10]), 1e-9)
        if len(closes) >= 10
        else 0.0
    )
    mom = closes[-1] - closes[-5] if len(closes) >= 5 else 0.0
    return {
        "short_trend": float(st),
        "mid_trend": 0.0,
        "momentum": float(mom),
        "volatility": 0.01,
        "vol_norm": float(vol_norm),
        "range_position": float(rp),
        "last_close": float(lc),
        "sma10": float(lc),
        "sma30": float(lc),
    }


def _edge_scalar_dict_bars(
    bars: list[dict[str, float]],
    state: str,
    *,
    vol_norm: float = 0.002,
    rp: float = 0.5,
) -> float:
    f = _f_from_close_dicts(bars, vol_norm=vol_norm, rp=rp)
    feats = build_compute_edge_features(bars, f, float(rp))
    return float(compute_edge(feats, state))


def _bars_dict(n: int = 55, *, slope: float = 0.05) -> list[dict[str, float]]:
    return [{"close": 100.0 + float(i) * slope} for i in range(n)]


def test_edge_score_basic() -> None:
    es = _edge_scalar_dict_bars(_bars_dict(), "RANGE")
    assert 0.0 <= es <= 1.0


def _bars_rally_no_pullback() -> list[dict[str, float]]:
    return [{"close": 100.0 + float(i) * 0.2} for i in range(55)]


def _bars_rally_with_pullback() -> list[dict[str, float]]:
    base = [100.0 + float(i) * 0.2 for i in range(48)]
    mx = max(base[-20:])
    tail = [
        mx * 0.995,
        mx * 0.99,
        mx * 0.985,
        mx * 0.982,
        mx * 0.979,
        mx * 0.977,
        mx * 0.975,
    ]
    return [{"close": float(x)} for x in (base + tail)]


def test_edge_score_support_bonus() -> None:
    with_pb = _edge_scalar_dict_bars(_bars_rally_with_pullback(), "RANGE")
    no_pb = _edge_scalar_dict_bars(_bars_rally_no_pullback(), "RANGE")
    assert with_pb != no_pb


def _bars_choppy_high_vol() -> list[dict[str, float]]:
    c = [100.0]
    for i in range(1, 55):
        step = 0.15 * (1.0 if i % 2 == 0 else -0.95)
        c.append(max(40.0, min(200.0, c[-1] + step)))
    return [{"close": float(x)} for x in c]


def test_edge_score_vol_penalty() -> None:
    low_vol = _edge_scalar_dict_bars(_bars_dict(), "RANGE")
    high_vol = _edge_scalar_dict_bars(_bars_choppy_high_vol(), "RANGE")
    assert low_vol != high_vol


def test_edge_score_accepts_ohlcv_bar_like() -> None:
    from bist_core.models.ohlcv import OHLCVBar

    bars = [
        OHLCVBar(
            timestamp=i,
            symbol="X",
            open=100.0 + i * 0.05,
            high=101.0 + i * 0.05,
            low=99.0 + i * 0.05,
            close=100.0 + i * 0.05,
            volume=1.0,
        )
        for i in range(55)
    ]
    f0 = compute_features(bars)
    assert f0 is not None
    f = dict(f0)
    rp = float(f["range_position"])
    feats = build_compute_edge_features(bars, f, rp)
    es = float(compute_edge(feats, "TRENDING_UP"))
    assert 0.0 <= es <= 1.0


def test_edge_score_alpha_features_with_full_ohlcv_51_bars() -> None:
    from bist_core.models.ohlcv import OHLCVBar

    bars = [
        OHLCVBar(
            timestamp=i,
            symbol="X",
            open=100.0 + i * 0.04,
            high=101.0 + i * 0.04 + 0.15 * (i % 3),
            low=99.0 + i * 0.04 - 0.1 * (i % 2),
            close=100.0 + i * 0.04,
            volume=500_000.0 + float(i) * 2_000.0,
        )
        for i in range(60)
    ]
    f0 = compute_features(bars)
    assert f0 is not None
    f = dict(f0)
    rp = float(f["range_position"])
    feats = build_compute_edge_features(bars, f, rp)
    es = float(compute_edge(feats, "TRENDING_UP"))
    assert 0.0 <= es <= 1.0


def _population_std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / float(len(vals))
    v = sum((x - m) ** 2 for x in vals) / float(len(vals))
    return float(math.sqrt(max(0.0, v)))


def _ohlcv_series(
    *,
    n: int,
    close_slope: float,
    vol_base: float,
    vol_trend: float,
    wiggle: float,
) -> list:
    from bist_core.models.ohlcv import OHLCVBar

    out = []
    c = 100.0
    for i in range(n):
        c = max(10.0, c + close_slope + wiggle * (1.0 if i % 2 == 0 else -0.9))
        spread = 0.2 + 0.01 * (i % 5)
        v = max(1.0, vol_base + vol_trend * float(i))
        out.append(
            OHLCVBar(
                timestamp=i,
                symbol="X",
                open=c - spread * 0.3,
                high=c + spread,
                low=c - spread,
                close=c,
                volume=v,
            )
        )
    return out


def test_cross_symbol_edge_std_separation() -> None:
    """Distinct BIST-style paths → edge scores spread (population std > 0.08)."""
    a = _ohlcv_series(
        n=60, close_slope=-0.08, vol_base=800_000.0, vol_trend=500.0, wiggle=0.35
    )
    b = _ohlcv_series(
        n=60, close_slope=0.22, vol_base=200_000.0, vol_trend=100.0, wiggle=0.02
    )
    c = _ohlcv_series(
        n=60, close_slope=0.01, vol_base=2_000_000.0, vol_trend=-200.0, wiggle=0.5
    )
    edges: list[float] = []
    for bars in (a, b, c):
        f0 = compute_features(bars)
        assert f0 is not None
        f = dict(f0)
        rp = float(f["range_position"])
        feats = build_compute_edge_features(bars, f, rp)
        edges.append(float(compute_edge(feats, "RANGE")))
    estd = _population_std(edges)
    assert estd > 0.08, f"edge_std={estd} edges={edges}"
    assert max(edges) - min(edges) > 0.12
