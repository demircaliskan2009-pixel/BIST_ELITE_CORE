"""Regime-selected multi-model edge score (deterministic, no RNG)."""

from __future__ import annotations

import math
from typing import Any


def clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


def calibrate_edge(edge: float) -> float:
    """Shift + stretch around 0.5, then clip — wider separation for gating."""
    edge = (float(edge) - 0.5) * 1.4 + 0.5
    return max(0.0, min(1.0, edge))


def select_edge_model(regime: str) -> str:
    r = str(regime).upper()
    if "TREND" in r:
        return "trend"
    if "RANGE" in r:
        return "mean_reversion"
    if "BREAKOUT" in r:
        return "breakout"
    if "VOLATILE" in r:
        return "breakout"
    if "NEUTRAL" in r:
        return "mean_reversion"
    return "none"


def trend_edge(f: dict[str, Any]) -> float:
    return clamp(
        0.30 * float(f.get("trend_strength", 0) or 0)
        + 0.20 * float(f.get("ema_slope", 0) or 0)
        + 0.15 * float(f.get("pullback_quality", 0) or 0)
        + 0.15 * float(f.get("volume_support", 0) or 0)
        + 0.20 * float(f.get("higher_highs", 0) or 0),
        0.0,
        1.0,
    )


def mean_reversion_edge(f: dict[str, Any]) -> float:
    return clamp(
        0.30 * (1.0 - float(f.get("range_position", 0.5) or 0))
        + 0.25 * float(f.get("mean_reversion", 0) or 0)
        + 0.20 * float(f.get("volatility_compression", 0) or 0)
        + 0.15 * float(f.get("rsi_zscore", 0) or 0)
        + 0.10 * float(f.get("bollinger_distance", 0) or 0),
        0.0,
        1.0,
    )


def breakout_edge(f: dict[str, Any]) -> float:
    return clamp(
        0.30 * float(f.get("volatility_compression", 0) or 0)
        + 0.20 * float(f.get("range_expansion", 0) or 0)
        + 0.20 * float(f.get("momentum_burst", 0) or 0)
        + 0.15 * float(f.get("volume_spike", 0) or 0)
        + 0.15 * float(f.get("trend_alignment", 0) or 0),
        0.0,
        1.0,
    )


def compute_edge(features: dict[str, Any], regime: str) -> float:
    feats = features if isinstance(features, dict) else {}
    model = select_edge_model(regime)

    if model == "trend":
        edge = trend_edge(feats)
    elif model == "mean_reversion":
        edge = mean_reversion_edge(feats)
    elif model == "breakout":
        edge = breakout_edge(feats)
    else:
        edge = 0.0

    edge_raw_model = float(edge)
    edge = clamp(edge_raw_model, 0.0, 1.0)
    edge_base = float(edge)
    edge_nl = edge_base**1.2
    edge_sig = 1.0 / (1.0 + math.exp(-3.0 * (edge_nl - 0.5)))
    edge_linear = 0.6 * edge_base + 0.4 * edge_sig
    edge = calibrate_edge(float(edge_linear))

    print(
        {
            "EDGE_CALIBRATION": {
                "before": float(edge_linear),
                "after": float(edge),
            }
        },
        flush=True,
    )

    print(
        {
            "EDGE_MODEL_SELECTED": model,
            "EDGE_VALUE_LINEAR": float(edge_raw_model),
            "EDGE_VALUE_CLIPPED": float(edge_base),
            "EDGE_VALUE_NL": float(edge_nl),
            "EDGE_VALUE_SIG": float(edge_sig),
            "EDGE_VALUE": float(edge),
            "REGIME": regime,
        },
        flush=True,
    )

    return float(edge)


__all__ = [
    "calibrate_edge",
    "clamp",
    "select_edge_model",
    "trend_edge",
    "mean_reversion_edge",
    "breakout_edge",
    "compute_edge",
]
