from __future__ import annotations
from typing import Any

# Explicit weights — no randomness
W_MOMENTUM = 0.35
W_TREND = 0.30
W_RSI = 0.20
W_VOL_PENALTY = 0.15

# No-trade threshold
SCORE_THRESHOLD = 0.10

# Top-N default
TOP_N = 3


def _safe(val: float | None, default: float = 0.0) -> float:
    if val is None or val != val:  # None or NaN
        return default
    return float(val)


def _momentum_signal(returns: float) -> float:
    """Normalize 20-bar return to [-1, 1]. Cap at ±10%."""
    capped = max(-0.10, min(0.10, returns))
    return capped / 0.10


def _trend_signal(ema_20: float, sma_50: float) -> float:
    """EMA20 vs SMA50 crossover signal. Normalized to [-1, 1]."""
    if sma_50 <= 0:
        return 0.0
    diff_pct = (ema_20 - sma_50) / sma_50
    return max(-1.0, min(1.0, diff_pct / 0.05))


def _rsi_signal(rsi: float) -> float:
    """RSI mean-reversion signal. Oversold=+1, overbought=-1."""
    rsi = max(0.0, min(100.0, rsi))
    if rsi < 30:
        return 1.0
    if rsi > 70:
        return -1.0
    return (50.0 - rsi) / 50.0


def _vol_penalty(atr: float, price: float) -> float:
    """ATR as % of price. Higher vol → higher penalty [0, 1]."""
    if price <= 0:
        return 0.0
    atr_pct = atr / price
    return min(1.0, atr_pct / 0.10)


def score_symbol(
    symbol: str,
    features: dict[str, list[float | None]],
    last_price: float,
) -> dict[str, Any] | None:
    """Score symbol from pre-computed features only.
    Strict fail-closed: any missing/None/NaN value returns None immediately.
    No default substitution. No silent correction. No bar access.
    """
    def _last(key: str) -> float | None:
        vals = features.get(key)
        if not vals:
            return None
        v = vals[-1]
        if v is None:
            return None
        v = float(v)
        if v != v:  # NaN check
            return None
        return v

    if last_price is None or float(last_price) <= 0:
        return None

    required = ["momentum_20", "ema_20", "sma_50", "rsi_14", "atr_14"]
    for k in required:
        if k not in features or not features[k]:
            return None

    ret = _last("momentum_20")
    if ret is None:
        return None

    ema = _last("ema_20")
    if ema is None:
        return None

    sma = _last("sma_50")
    if sma is None:
        return None

    rsi = _last("rsi_14")
    if rsi is None:
        return None

    atr = _last("atr_14")
    if atr is None:
        return None

    if ema == 0.0 and sma == 0.0:
        return None

    m = _momentum_signal(ret)
    t = _trend_signal(ema, sma)
    r = _rsi_signal(rsi)
    v = _vol_penalty(atr, float(last_price))

    conflict = (m > 0 and t < 0) or (m < 0 and t > 0)
    if conflict:
        score_penalty = 0.30
    else:
        score_penalty = 0.0

    score = W_MOMENTUM * m + W_TREND * t + W_RSI * r - W_VOL_PENALTY * v - score_penalty
    score = round(max(-1.0, min(1.0, score)), 6)

    return {
        "symbol": symbol,
        "score": score,
        "features": {
            "momentum": round(m, 4),
            "trend": round(t, 4),
            "rsi_signal": round(r, 4),
            "vol_penalty": round(v, 4),
        },
        "reason": f"m={m:.2f} t={t:.2f} r={r:.2f} v={v:.2f}",
    }


def rank_symbols(
    scored: list[dict[str, Any]],
    top_n: int = TOP_N,
    threshold: float = SCORE_THRESHOLD,
    force_top: bool = True,
) -> list[dict[str, Any]]:
    """Sort by score descending. Filter below threshold.
    If force_top=True and all filtered: return positive scores; else top_n by score.
    """
    above = [s for s in scored if s["score"] >= threshold]
    above.sort(key=lambda x: x["score"], reverse=True)
    if above:
        return above[:top_n]
    if force_top:
        positive = [s for s in scored if s["score"] > 0]
        positive.sort(key=lambda x: x["score"], reverse=True)
        if positive:
            return positive[:top_n]
        all_sorted = sorted(scored, key=lambda x: x["score"], reverse=True)
        return all_sorted[:top_n]
    return []
