from __future__ import annotations

import numpy as np


def compute_realized_vol(bars):
    closes = np.array([b["close"] for b in bars], dtype=float)
    returns = np.diff(closes) / closes[:-1]
    return np.std(returns) * np.sqrt(len(returns))


def classify_vol_regime(vol, history):
    p30 = np.percentile(history, 30)
    p70 = np.percentile(history, 70)

    if vol < p30:
        return "LOW"
    elif vol > p70:
        return "HIGH"
    return "MID"


def volatility_edge_adjust(edge, regime):
    weights = {
        "LOW": 0.85,
        "MID": 1.0,
        "HIGH": 1.15
    }
    return max(0.0, min(1.0, edge * weights.get(regime, 1.0)))


__all__ = [
    "compute_realized_vol",
    "classify_vol_regime",
    "volatility_edge_adjust",
]
