"""Context builder — compute market context from OHLCV bars."""

from __future__ import annotations

from bist_core.data.quality import InvalidDataError, basic_checks
from bist_core.models.ohlcv import OHLCVBar
from bist_core.regime import RegimeEngine


def _avg_range(bars: list[OHLCVBar]) -> float:
    """mean(high - low)"""
    if not bars:
        return 0.0
    return sum(b.high - b.low for b in bars) / len(bars)


class ContextBuilder:
    """Builds market context from OHLCV bars.

    Fail-closed: invalid bars → raise InvalidDataError.
    """

    def __init__(self, regime_engine: RegimeEngine | None = None) -> None:
        self._regime_engine = regime_engine or RegimeEngine()

    def build(self, bars: list[OHLCVBar]) -> dict:
        """Compute context from bars.

        Returns:
            {
                "current_price": float,
                "trend": float,
                "avg_range": float,
                "regime": str
            }
        """
        if not bars:
            raise InvalidDataError("bars must not be empty")
        basic_checks(bars)
        current_price = bars[-1].close
        trend = bars[-1].close - bars[0].close
        avg_range = _avg_range(bars)
        regime = self._regime_engine.detect(bars)
        return {
            "current_price": current_price,
            "trend": trend,
            "avg_range": avg_range,
            "regime": regime,
        }


__all__ = ["ContextBuilder"]
