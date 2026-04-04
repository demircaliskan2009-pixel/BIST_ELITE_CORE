"""Regime detection — market regime awareness for decision pipeline."""

from .regime_engine import (
    RegimeEngine,
    TRENDING_UP,
    TRENDING_DOWN,
    RANGE,
    HIGH_VOLATILITY,
    UNKNOWN,
)

__all__ = [
    "RegimeEngine",
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGE",
    "HIGH_VOLATILITY",
    "UNKNOWN",
]
