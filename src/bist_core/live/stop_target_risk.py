"""ATR-based stop/target sizing for paper execution (deterministic, no RNG)."""

from __future__ import annotations

import math
import os
from typing import Any

from bist_core.execution.tick_size import get_tick_size
from bist_core.models.ohlcv import OHLCVBar


def _tick_floor(price: float) -> float:
    t = get_tick_size(float(price))
    if t <= 0:
        return float(price)
    return math.floor(float(price) / t + 1e-12) * t


def _tick_ceil(price: float) -> float:
    t = get_tick_size(float(price))
    if t <= 0:
        return float(price)
    return math.ceil(float(price) / t - 1e-12) * t


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _mean_abs_return_vol(closes: list[float]) -> float:
    if len(closes) < 2:
        return 0.0
    r = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]
    if not r:
        return 0.0
    return sum(abs(x) for x in r) / float(len(r))


def _true_range(bars: list[OHLCVBar], i: int) -> float:
    b = bars[i]
    prev = bars[i - 1]
    h = float(b.high)
    l = float(b.low)
    c_prev = float(prev.close)
    return max(h - l, abs(h - c_prev), abs(l - c_prev))


def atr14_sma(bars: list[OHLCVBar]) -> float:
    """Classic 14-period ATR as simple moving average of last 14 true ranges."""
    n = len(bars)
    if n < 15:
        return 0.0
    trs: list[float] = []
    for i in range(1, n):
        trs.append(_true_range(bars, i))
    if len(trs) < 14:
        return 0.0
    last14 = trs[-14:]
    return sum(last14) / 14.0


def vol_stop_scale(vol_norm: float) -> float:
    """Low vol_norm → widen stop; high vol_norm → tighten (vs reference)."""
    ref = _env_float("BIST_STOP_VOL_REF", 0.02)
    v = max(float(vol_norm), 1e-8)
    scale = ref / v
    lo = _env_float("BIST_STOP_VOL_SCALE_MIN", 0.6)
    hi = _env_float("BIST_STOP_VOL_SCALE_MAX", 2.2)
    return max(lo, min(hi, scale))


def compute_atr_stop_target(
    entry: float,
    *,
    is_short: bool,
    bars: list[OHLCVBar],
    vol_norm: float | None,
) -> dict[str, Any] | None:
    """
    stop = entry ± (ATR * k * vol_scale), target at RR >= 1.5 vs that risk.

    Returns STOP_DEBUG-shaped dict including stop/target, or None if not applicable.
    """
    e = float(entry)
    if e <= 0 or not bars or len(bars) < 15:
        return None

    atr = atr14_sma(bars)
    if atr <= 0 or atr != atr:
        return None

    k = _env_float("BIST_STOP_ATR_K", 2.0)
    if k <= 0:
        return None

    rr_min = _env_float("BIST_STOP_RR_MIN", 1.5)
    if rr_min < 1.5:
        rr_min = 1.5

    vn = float(vol_norm) if vol_norm is not None else _mean_abs_return_vol(
        [float(b.close) for b in bars]
    )
    if vn != vn:
        return None

    scale = vol_stop_scale(vn)
    raw_dist = float(atr) * float(k) * float(scale)
    if raw_dist <= 0:
        return None

    if is_short:
        sl = _tick_ceil(e + raw_dist)
        risk = sl - e
        if risk <= 0:
            return None
        tg = _tick_floor(e - risk * float(rr_min))
    else:
        sl = _tick_floor(e - raw_dist)
        risk = e - sl
        if risk <= 0:
            return None
        tg = _tick_ceil(e + risk * float(rr_min))

    if sl <= 0 or tg <= 0:
        return None

    if is_short:
        if not (tg < e < sl):
            return None
        reward = e - tg
    else:
        if not (sl < e < tg):
            return None
        reward = tg - e

    if reward <= 0:
        return None

    rr = reward / risk
    if rr + 1e-12 < rr_min:
        return None

    return {
        "entry": float(e),
        "stop": float(sl),
        "target": float(tg),
        "atr": float(atr),
        "rr": float(rr),
    }


__all__ = [
    "atr14_sma",
    "compute_atr_stop_target",
    "vol_stop_scale",
]
