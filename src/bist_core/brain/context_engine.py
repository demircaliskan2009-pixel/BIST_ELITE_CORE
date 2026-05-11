"""Context engine — evaluates trading context around a decision.

Checks entry validity, missed-entry detection, pullback opportunity,
and trend strength relative to detected regime.
Pure stdlib, deterministic, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.regime_engine import (NO_REGIME, TREND_DOWN, TREND_UP,
                                           RegimeEngine)
from bist_core.brain.strategy_engine import Decision


@dataclass
class DecisionContext:
    symbol: str
    entry_valid: bool
    missed_entry: bool
    pullback_possible: bool
    trend_strength: float
    regime: str
    timestamp: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_valid": self.entry_valid,
            "missed_entry": self.missed_entry,
            "pullback_possible": self.pullback_possible,
            "trend_strength": self.trend_strength,
            "regime": self.regime,
            "timestamp": self.timestamp,
        }


class ContextEngine:
    """Evaluate trading context for a Decision given market bars."""

    def __init__(self, regime_engine: RegimeEngine | None = None) -> None:
        self._regime = regime_engine or RegimeEngine()

    def evaluate_context(
        self,
        decision: Decision,
        bars: Sequence[OHLCVBar],
    ) -> DecisionContext | None:
        if not bars:
            return None

        market_regime = self._regime.detect_regime(bars)
        if market_regime.regime == NO_REGIME:
            return None

        close = bars[-1].close
        entry = decision.entry
        side = decision.side

        if side == "long":
            entry_valid = close <= entry * 1.01
            missed_entry = close > entry * 1.03
            pullback_possible = close < entry and market_regime.regime == TREND_UP
        else:
            entry_valid = close >= entry * 0.99
            missed_entry = close < entry * 0.97
            pullback_possible = close > entry and market_regime.regime == TREND_DOWN

        return DecisionContext(
            symbol=decision.symbol,
            entry_valid=entry_valid,
            missed_entry=missed_entry,
            pullback_possible=pullback_possible,
            trend_strength=market_regime.strength,
            regime=market_regime.regime,
            timestamp=bars[-1].timestamp,
        )
