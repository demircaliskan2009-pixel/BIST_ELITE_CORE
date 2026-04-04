"""Scanner engine — scans a symbol universe and produces ranked signals.

Combines StrategyEngine (decision generation) and RankingEngine (scoring)
into a single deterministic scan pipeline.  No network, no numpy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.ranking_engine import RankedSignal, RankingEngine
from bist_core.brain.strategy_engine import Decision, StrategyEngine


@dataclass
class ScanResult:
    timestamp: int
    signals: list[RankedSignal] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "signals": [s.to_dict() for s in self.signals],
            "count": len(self.signals),
        }


class ScannerEngine:
    """Scan a symbol universe, generate decisions, and rank them."""

    def __init__(
        self,
        strategy_engine: StrategyEngine | None = None,
        ranking_engine: RankingEngine | None = None,
    ) -> None:
        self._strategy = strategy_engine or StrategyEngine()
        self._ranking = ranking_engine or RankingEngine()

    def scan(
        self,
        symbol_bars: Dict[str, Sequence[OHLCVBar]],
    ) -> ScanResult:
        decisions: list[Decision] = []
        latest_ts = 0

        for symbol in sorted(symbol_bars.keys()):
            bars = symbol_bars[symbol]
            if not bars:
                continue
            decision = self._strategy.generate_decision(symbol, bars)
            if decision is not None:
                decisions.append(decision)
                if decision.timestamp > latest_ts:
                    latest_ts = decision.timestamp

        ranked = self._ranking.rank_decisions(decisions)
        return ScanResult(timestamp=latest_ts, signals=ranked)

    def scan_top(
        self,
        symbol_bars: Dict[str, Sequence[OHLCVBar]],
        n: int,
    ) -> List[RankedSignal]:
        result = self.scan(symbol_bars)
        return result.signals[:max(n, 0)]

    def scan_universe(
        self,
        symbol_dataset: Dict[str, Sequence[OHLCVBar]],
    ) -> List[RankedSignal]:
        result = self.scan(symbol_dataset)
        return result.signals
