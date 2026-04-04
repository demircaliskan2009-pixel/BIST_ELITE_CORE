"""PnL attribution by symbol and strategy (deterministic aggregation)."""

from __future__ import annotations

from typing import Any


class PerformanceAttribution:
    def compute(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        by_symbol: dict[str, float] = {}
        by_strategy: dict[str, float] = {}

        for t in trades:
            if not isinstance(t, dict):
                continue
            sym = t.get("symbol")
            strat = t.get("strategy", "unknown")
            try:
                pnl = float(t.get("pnl", 0.0))
            except (TypeError, ValueError):
                pnl = 0.0
            sk = str(sym) if sym is not None else "unknown"
            ss = str(strat) if strat is not None else "unknown"
            by_symbol[sk] = by_symbol.get(sk, 0.0) + pnl
            by_strategy[ss] = by_strategy.get(ss, 0.0) + pnl

        return {
            "by_symbol": by_symbol,
            "by_strategy": by_strategy,
        }


__all__ = ["PerformanceAttribution"]
