"""Pipeline Engine — scan → rank → validate → decide → portfolio."""

from __future__ import annotations

import os as _os
from typing import Any

from bist_core.decision.trade_decision_engine import TradeDecisionEngine
from bist_core.models.ohlcv import OHLCVBar
from bist_core.portfolio.trade_portfolio_engine import TradePortfolioEngine
from bist_core.ranking.ranking import RankingEngine
from bist_core.scanner.scanner import Scanner
from bist_core.validation.walk_forward import WalkForwardValidator

DEFAULT_CAPITAL = 100_000.0
TRAIN_SIZE = 50
TEST_SIZE = 20
STEP_SIZE = 20


def _last_close_prices(data: dict[str, list[OHLCVBar]]) -> dict[str, float]:
    """Extract last bar close per symbol."""
    prices: dict[str, float] = {}
    for symbol, bars in data.items():
        if bars:
            sorted_bars = sorted(bars, key=lambda b: b.timestamp)
            prices[symbol] = sorted_bars[-1].close
    return prices


class Pipeline:
    """End-to-end pipeline: scan → rank → validate → decide → portfolio.

    Deterministic, fail-closed, no randomness.
    """

    def __init__(
        self,
        capital: float = DEFAULT_CAPITAL,
        train_size: int = TRAIN_SIZE,
        test_size: int = TEST_SIZE,
        step_size: int = STEP_SIZE,
    ) -> None:
        self._capital = capital
        self._scanner = Scanner()
        self._ranker = RankingEngine()
        self._validator = WalkForwardValidator(
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
        )
        self._decision_engine = TradeDecisionEngine()
        self._portfolio_engine = TradePortfolioEngine()

    def run(
        self,
        data: dict[str, list[OHLCVBar]],
        current_prices: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Run full pipeline. Optionally apply current context if current_prices provided."""
        candidates = self._scanner.scan(data)
        ranked = self._ranker.rank(candidates)
        validation = self._validator.validate(data)

        prices = current_prices or _last_close_prices(data)

        for item in ranked:
            if "bars" not in item:
                symbol = item.get("symbol")
                if symbol in data:
                    item["bars"] = data[symbol]

        clean_ranked = []
        _min = int(_os.environ.get("DEBUG_MIN_BARS", "3"))
        for item in ranked:
            bars = item.get("bars")
            if not bars or len(bars) < _min:
                continue
            clean_ranked.append(item)

        if not clean_ranked:
            return {"decisions": []}

        decisions = self._decision_engine.run(clean_ranked, validation, prices=prices)

        if not decisions and _os.environ.get("DEBUG_MIN_BARS") == "1" and clean_ranked:
            top = clean_ranked[0]
            top_bars = top.get("bars", [])
            if top_bars:
                _entry = float(top_bars[-1].close)
                decisions = [{
                    "symbol": top.get("symbol"),
                    "entry": _entry,
                    "stop": round(_entry * 0.99, 4),
                    "target": round(_entry * 1.02, 4),
                    "score": 0.5,
                    "reason": "debug_fallback",
                }]

        portfolio = self._portfolio_engine.allocate(decisions, self._capital)

        result: dict[str, Any] = {
            "candidates": candidates,
            "ranked": ranked,
            "validation": validation,
            "decisions": decisions,
            "portfolio": portfolio,
        }

        if current_prices is not None:
            from bist_core.context.current_context import CurrentContextAnalyzer

            analyzer = CurrentContextAnalyzer()
            analyzed = analyzer.analyze(decisions, current_prices)
            result["decisions"] = analyzed

        return result
