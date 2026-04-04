"""Canonical edge bucket key — context-aware, deterministic."""

from __future__ import annotations

import math
from typing import Any


def _vol_bucket(vol: float) -> int:
    """Quantize volatility to ~11 buckets in [0, 0.5]."""
    v = max(0.0, min(0.5, float(vol)))
    return int(v / 0.05)


def _trend_bucket(trend: float) -> int:
    """Quantize trend to ~21 buckets in [-0.5, 0.5]."""
    t = max(-0.5, min(0.5, float(trend)))
    return int((t + 0.5) / 0.05)


def _holding_bucket(bars: int) -> int:
    b = max(0, int(bars))
    if b <= 5:
        return 0
    if b <= 20:
        return 1
    if b <= 50:
        return 2
    return 3


def regime_from_feat(feat: dict[str, Any]) -> str:
    """Deterministic regime label from edge features (no randomness)."""
    vol = float(feat["vol"])
    tr = float(feat["trend"])
    if vol >= 0.05:
        vc = "hv"
    elif vol <= 0.01:
        vc = "lv"
    else:
        vc = "mv"
    if tr > 0.02:
        tc = "up"
    elif tr < -0.02:
        tc = "dn"
    else:
        tc = "flat"
    return f"{vc}_{tc}"


def edge_bucket_key(feat: dict[str, Any], context: dict[str, Any] | None = None) -> tuple[Any, ...]:
    """
    Bucket key: (volatility_bucket, trend_bucket, breakout, volume_spike, regime, holding_period_bucket).

    When ``context`` is omitted, uses entry-style defaults: holding=0, vol/regime from ``feat``.
    """
    ctx = dict(context) if context else {}
    vol_src = float(ctx.get("volatility", feat["vol"]))
    regime = str(ctx.get("regime", regime_from_feat(feat)))
    hold = int(ctx.get("holding_period_bars", 0))
    return (
        _vol_bucket(vol_src),
        _trend_bucket(float(feat["trend"])),
        int(feat["breakout"]),
        int(float(feat["vol_ratio"]) > 1.5),
        regime,
        _holding_bucket(hold),
    )


def weighted_std(samples: list[tuple[float, float]]) -> float:
    """Population std of returns with non-negative weights (deterministic)."""
    if not samples:
        return 0.0
    tw = sum(w for _, w in samples)
    if tw <= 0.0:
        return 0.0
    mean = sum(r * w for r, w in samples) / tw
    var = sum(w * (r - mean) ** 2 for r, w in samples) / tw
    return float(math.sqrt(max(0.0, var)))


__all__ = ["edge_bucket_key", "regime_from_feat", "weighted_std"]
