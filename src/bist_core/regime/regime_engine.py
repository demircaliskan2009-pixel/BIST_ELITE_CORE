"""Regime engine — deterministic market regime detection from OHLCV bars."""

from __future__ import annotations

import statistics

from bist_core.models.ohlcv import OHLCVBar


TRENDING_UP = "TRENDING_UP"
TRENDING_DOWN = "TRENDING_DOWN"
RANGE = "RANGE"
HIGH_VOLATILITY = "HIGH_VOLATILITY"
UNKNOWN = "UNKNOWN"

TREND_THRESHOLD_PCT = 0.02
VOLATILITY_HIGH_PCT = 0.03
VOLATILITY_LOW_PCT = 0.005
STD_DEV_LOW_PCT = 0.01


def _avg_price(bars: list[OHLCVBar]) -> float:
    if not bars:
        return 0.0
    return sum(b.close for b in bars) / len(bars)


def _volatility(bars: list[OHLCVBar]) -> float:
    if not bars:
        return 0.0
    return sum(b.high - b.low for b in bars) / len(bars)


def _std_dev(bars: list[OHLCVBar]) -> float:
    if len(bars) < 2:
        return 0.0
    closes = [b.close for b in bars]
    return statistics.stdev(closes)


class RegimeEngine:
    """Detect market regime from price structure. Deterministic, fail-closed."""

    def __init__(
        self,
        trend_threshold_pct: float = TREND_THRESHOLD_PCT,
        volatility_high_pct: float = VOLATILITY_HIGH_PCT,
        volatility_low_pct: float = VOLATILITY_LOW_PCT,
        std_dev_low_pct: float = STD_DEV_LOW_PCT,
    ) -> None:
        self._trend_threshold_pct = trend_threshold_pct
        self._volatility_high_pct = volatility_high_pct
        self._volatility_low_pct = volatility_low_pct
        self._std_dev_low_pct = std_dev_low_pct

    def detect(self, bars: list[OHLCVBar]) -> str:
        """Detect regime from bars. Returns TRENDING_UP, TRENDING_DOWN, RANGE, HIGH_VOLATILITY, or UNKNOWN.

        Fail-closed: invalid/insufficient data → UNKNOWN.
        """
        if not bars or len(bars) < 2:
            return UNKNOWN

        avg_price = _avg_price(bars)
        if avg_price <= 0:
            return UNKNOWN

        trend = bars[-1].close - bars[0].close
        volatility = _volatility(bars)
        std_dev = _std_dev(bars)

        trend_threshold = avg_price * self._trend_threshold_pct
        vol_high = avg_price * self._volatility_high_pct
        vol_low = avg_price * self._volatility_low_pct
        std_low = avg_price * self._std_dev_low_pct

        if volatility > vol_high:
            return HIGH_VOLATILITY
        if trend < -trend_threshold:
            return TRENDING_DOWN
        if trend > trend_threshold and volatility >= vol_low:
            return TRENDING_UP
        if abs(trend) < trend_threshold and std_dev < std_low:
            return RANGE

        return UNKNOWN


__all__ = [
    "RegimeEngine",
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGE",
    "HIGH_VOLATILITY",
    "UNKNOWN",
]
