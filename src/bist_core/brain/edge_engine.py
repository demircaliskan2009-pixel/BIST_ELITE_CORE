"""Deterministic edge scoring (no RNG, no external data)."""

from __future__ import annotations

import math
from typing import Any

def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _clip_m11(x: float) -> float:
    return max(-1.0, min(1.0, float(x)))


def _pstdev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / float(len(vals))
    v = sum((x - m) ** 2 for x in vals) / float(len(vals))
    return float(v**0.5)


def _returns_from_closes(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        try:
            out.append(
                (closes[i] - closes[i - 1]) / max(closes[i - 1], 1e-12)
            )
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return out


def _volumes_aligned(bars: Any, n: int) -> list[float] | None:
    """Last ``n`` volumes aligned with closes, or None if missing/not parseable."""
    if not bars or len(bars) < n:
        return None
    seg = bars[-n:]
    out: list[float] = []
    for x in seg:
        try:
            if isinstance(x, dict) and "volume" in x:
                out.append(float(x["volume"]))
            elif hasattr(x, "volume"):
                out.append(float(getattr(x, "volume")))
            else:
                return None
        except (TypeError, ValueError, AttributeError):
            return None
    return out


def _hi_lo_last_n(bars: Any, closes: list[float], n: int) -> tuple[float, float]:
    """Last ``n`` bars high/low; use bar high/low when present else close."""
    if len(closes) < n:
        return max(closes), min(closes)
    off = len(closes) - n
    hi_v: list[float] = []
    lo_v: list[float] = []
    for j in range(n):
        cl = float(closes[off + j])
        h = l = cl
        if bars is not None and len(bars) > off + j:
            x = bars[off + j]
            try:
                if isinstance(x, dict):
                    if "high" in x:
                        h = float(x["high"])
                    if "low" in x:
                        l = float(x["low"])
                elif hasattr(x, "high") and hasattr(x, "low"):
                    h = float(getattr(x, "high"))
                    l = float(getattr(x, "low"))
            except (TypeError, ValueError, AttributeError):
                h = l = cl
        hi_v.append(h)
        lo_v.append(l)
    return max(hi_v), min(lo_v)


def _feat_mean_reversion_short_term(closes: list[float]) -> float:
    """Z-score of last close vs 20-period mean; negative z → long bias → positive feature."""
    if len(closes) < 20:
        return 0.0
    w = closes[-20:]
    mu = sum(w) / 20.0
    sd = _pstdev(w)
    if sd < 1e-12:
        return 0.0
    z = (closes[-1] - mu) / sd
    return _clip_m11(-z / 3.0)


def _feat_momentum_burst_norm(closes: list[float]) -> float:
    """Short-horizon return vs recent vol scale; nonlinear |mb|^1.5, clipped [-1, 1]."""
    if len(closes) < 20:
        return 0.0
    rets = _returns_from_closes(closes)
    if len(rets) < 20:
        return 0.0
    sig = _pstdev(rets[-20:])
    raw = (closes[-1] - closes[-5]) / max(closes[-1], 1e-12)
    if sig < 1e-12:
        mb = raw / 0.01
    else:
        mb = raw / max(sig * 5.0, 1e-12)
    mb = float(mb)
    if mb == 0.0:
        return 0.0
    burst = math.copysign(abs(mb) ** 1.5, mb)
    return _clip_m11(burst)


def _feat_vol_clustering(closes: list[float]) -> float:
    """std(returns,20) / std(returns,50); expansion → positive."""
    rets = _returns_from_closes(closes)
    if len(rets) < 50:
        return 0.0
    s20 = _pstdev(rets[-20:])
    s50 = _pstdev(rets[-50:])
    if s50 < 1e-12:
        return 0.0
    ratio = s20 / s50
    return _clip_m11(math.tanh((ratio - 1.0) * 2.0))


def _feat_liquidity_proxy(volumes: list[float] | None) -> float:
    """volume / mean(vol,20); low relative volume → negative."""
    if volumes is None or len(volumes) < 20:
        return 0.0
    vm = sum(volumes[-20:]) / 20.0
    if vm < 1e-12:
        return -1.0
    rel = volumes[-1] / vm
    return _clip_m11(math.tanh((rel - 1.0) * 3.0))


def _feat_range_position_asymmetry(bars: Any, closes: list[float]) -> float:
    """50-bar range; nearer to low → long bias (positive)."""
    if len(closes) < 50:
        return 0.0
    hi, lo = _hi_lo_last_n(bars, closes, 50)
    span = hi - lo
    if span < 1e-12:
        return 0.0
    pos = (closes[-1] - lo) / span
    return _clip_m11(math.tanh(3.0 * (0.5 - pos)))


def _feat_micro_trend_acceleration(closes: list[float]) -> float:
    """slope(last 5 closes) - slope(last 20 closes), price-normalized."""
    if len(closes) < 20:
        return 0.0
    s5 = (closes[-1] - closes[-5]) / 4.0
    s20 = (closes[-1] - closes[-20]) / 19.0
    acc = s5 - s20
    denom = max(abs(closes[-1]), 1e-12)
    acc = acc / denom
    return _clip_m11(math.tanh(acc * 5.0))


def _vol_regime_ratio(closes: list[float]) -> float:
    """std(returns,20)/std(returns,50) for edge scaling (unclipped, >=0)."""
    rets = _returns_from_closes(closes)
    if len(rets) < 50:
        return 1.0
    s20 = _pstdev(rets[-20:])
    s50 = _pstdev(rets[-50:])
    if s50 < 1e-12:
        return 1.0
    return float(s20 / s50)


def _require_closes(bars, min_bars: int = 30):
    if not bars or len(bars) < min_bars:
        return None
    closes: list[float] = []
    for x in bars:
        try:
            if isinstance(x, dict) and "close" in x:
                closes.append(float(x["close"]))
            elif isinstance(x, (list, tuple)) and len(x) > 4:
                closes.append(float(x[4]))
            elif hasattr(x, "close"):
                closes.append(float(getattr(x, "close")))
        except (TypeError, ValueError, IndexError):
            continue
    return closes if len(closes) >= min_bars else None


def _bars_for_liquidity_sweep(bars: Any) -> list[dict[str, float]] | None:
    """Full OHLCV per bar (dict or bar-like); else None so sweep does not run."""
    if not bars:
        return None
    out: list[dict[str, float]] = []
    for x in bars:
        try:
            if isinstance(x, dict):
                req = ("open", "high", "low", "close", "volume")
                if not all(k in x for k in req):
                    return None
                out.append({k: float(x[k]) for k in req})
            elif all(hasattr(x, a) for a in ("open", "high", "low", "close", "volume")):
                out.append(
                    {
                        "open": float(x.open),
                        "high": float(x.high),
                        "low": float(x.low),
                        "close": float(x.close),
                        "volume": float(x.volume),
                    }
                )
            else:
                return None
        except (TypeError, ValueError, AttributeError):
            return None
    return out


def _compute_alpha_microstructure_features(bars: list[dict[str, float]]) -> dict[str, float] | None:
    """Microstructure features (needs >= 51 full OHLCV bars)."""
    n = len(bars)
    if n < 51:
        return None

    h = [float(b["high"]) for b in bars]
    low = [float(b["low"]) for b in bars]
    c = [float(b["close"]) for b in bars]
    v = [float(b["volume"]) for b in bars]

    tr: list[float] = []
    tr.append(max(h[0] - low[0], 0.0))
    for i in range(1, n):
        tr.append(
            max(
                h[i] - low[i],
                abs(h[i] - c[i - 1]),
                abs(low[i] - c[i - 1]),
            )
        )

    avg_vol_20 = sum(v[-20:]) / 20.0
    rngs = [h[j] - low[j] for j in range(n)]
    avg_range_20 = sum(rngs[-20:]) / 20.0

    atr_14 = sum(tr[-14:]) / 14.0
    rolling_atr_50 = sum(tr[-50:]) / 50.0

    last_vol = v[-1]
    last_rng = h[-1] - low[-1]
    eps = 1e-12
    relative_volume = last_vol / max(avg_vol_20, eps)
    range_expansion = last_rng / max(avg_range_20, eps)
    momentum_burst = abs(c[-1] - c[-5]) / max(atr_14, eps)
    signed_momentum_burst = (c[-1] - c[-5]) / max(atr_14, eps)

    vol_regime = atr_14 / max(rolling_atr_50, eps)

    return {
        "relative_volume": float(relative_volume),
        "range_expansion": float(range_expansion),
        "momentum_burst": float(momentum_burst),
        "signed_momentum_burst": float(signed_momentum_burst),
        "vol_regime": float(vol_regime),
    }


def _trend_strength_from_prices(closes):
    if len(closes) < 30:
        return 0.0

    ema20 = sum(closes[-20:]) / 20.0
    ema50 = sum(closes[-50:]) / 50.0

    slope = (ema20 - ema50) / max(ema50, 1e-6)

    norm = (slope + 0.05) / 0.10
    return _clip01(norm)


def _pullback_from_prices(closes):
    if len(closes) < 20:
        return 0.0

    recent_high = max(closes[-20:])
    last = closes[-1]

    if recent_high <= 0:
        return 0.0

    dist = (recent_high - last) / max(recent_high, 1e-6)

    score = 1.0 - abs(dist - 0.02) / 0.05

    if dist < 0.005:
        score *= 0.3
    if dist > 0.08:
        score *= 0.4

    return _clip01(score)


def _volatility_from_prices(closes):
    if len(closes) < 20:
        return 0.0

    rets = []
    for i in range(1, len(closes)):
        r = (closes[i] - closes[i - 1]) / max(closes[i - 1], 1e-6)
        rets.append(r)

    if len(rets) < 20:
        return 0.0
    mean = sum(rets[-20:]) / 20.0
    var = sum((x - mean) ** 2 for x in rets[-20:]) / 20.0
    std = var**0.5

    norm = 1.0 - min(std / 0.03, 1.0)
    return _clip01(norm)


def signed_momentum_burst_ratio_from_bars(bars: Any) -> float | None:
    """Signed (close - close[-5]) / ATR_14 when ≥51 full OHLCV bars; else None."""
    sb = _bars_for_liquidity_sweep(bars)
    if sb is None or len(sb) < 51:
        return None
    a = _compute_alpha_microstructure_features(sb)
    if a is None:
        return None
    return float(a["signed_momentum_burst"])


__all__ = ["signed_momentum_burst_ratio_from_bars"]
