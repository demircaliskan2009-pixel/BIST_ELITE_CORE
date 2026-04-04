"""Regime engine — detects market regime from price structure.

Uses SMA fast/slow crossover to classify bull/bear/sideways with
strength measurement.  Pure stdlib, deterministic, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.features.indicator_library import sma as compute_sma


@dataclass
class MarketRegime:
    regime: str
    strength: float
    sma_fast: float
    sma_slow: float
    timestamp: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime,
            "strength": self.strength,
            "sma_fast": self.sma_fast,
            "sma_slow": self.sma_slow,
            "timestamp": self.timestamp,
        }


class RegimeEngine:
    """Detect bull/bear/sideways regime from SMA crossover structure."""

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
    ) -> None:
        self._fast = fast_period
        self._slow = slow_period

    @property
    def fast_period(self) -> int:
        return self._fast

    @property
    def slow_period(self) -> int:
        return self._slow

    def detect_regime(self, bars: Sequence[OHLCVBar]) -> MarketRegime | None:
        if len(bars) < self._slow:
            return None

        sma_fast_vals = compute_sma(bars, self._fast)
        sma_slow_vals = compute_sma(bars, self._slow)

        fast = sma_fast_vals[-1]
        slow = sma_slow_vals[-1]

        if fast is None or slow is None or slow <= 0:
            return None

        diff = fast - slow
        abs_diff = abs(diff)
        threshold = 0.002 * slow

        if abs_diff < threshold:
            regime = "sideways"
            strength = round(abs_diff / slow, 6)
        elif diff > 0:
            regime = "bull"
            strength = round(diff / slow, 6)
        else:
            regime = "bear"
            strength = round(abs_diff / slow, 6)

        return MarketRegime(
            regime=regime,
            strength=strength,
            sma_fast=round(fast, 6),
            sma_slow=round(slow, 6),
            timestamp=bars[-1].timestamp,
        )
