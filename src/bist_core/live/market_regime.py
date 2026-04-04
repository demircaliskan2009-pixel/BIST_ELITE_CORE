"""Deterministic market regime labels from aggregate volatility / trend (no randomness)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar


def detect_market_regime(avg_vol: float, avg_trend_abs: float) -> str:
    """
    Classify one of: CALM, TRENDING, CHOPPY, MIXED.

    - CALM: low aggregate volatility
    - TRENDING: strong trend, volatility not extreme
    - CHOPPY: elevated volatility with weak trend
    """
    v = float(avg_vol)
    t = float(avg_trend_abs)
    # Low vol first
    if v < 0.012:
        return "CALM"
    # Strong trend + controlled vol
    if t >= 0.018 and v <= 0.038:
        return "TRENDING"
    # High vol + weak trend
    if v >= 0.022 and t < 0.010:
        return "CHOPPY"
    return "MIXED"


def aggregate_vol_trend_from_snap(
    per_symbol: Dict[str, Dict[str, Any]],
    fe: FeatureEngineV2,
) -> Tuple[float, float]:
    """Mean vol and mean |trend| across symbols with valid bars (≥50)."""
    vols: List[float] = []
    trends: List[float] = []
    for _sym, pack in per_symbol.items():
        if not isinstance(pack, dict):
            continue
        bars = pack.get("bars")
        if not isinstance(bars, list) or len(bars) < 50:
            continue
        ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
        if len(ohlcv) < 50:
            continue
        feat = fe.extract(ohlcv)
        vols.append(float(feat.get("vol", 0.0) or 0.0))
        trends.append(abs(float(feat.get("trend", 0.0) or 0.0)))
    if not vols:
        return 0.02, 0.0
    mv = sum(vols) / len(vols)
    mt = sum(trends) / len(trends)
    return mv, mt


__all__ = [
    "aggregate_vol_trend_from_snap",
    "detect_market_regime",
]
