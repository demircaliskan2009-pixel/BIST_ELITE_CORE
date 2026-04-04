"""Trade-level win/loss statistics (deterministic)."""

from __future__ import annotations

from typing import Any


def compute_expectancy(trades: list[dict[str, Any]]) -> float:
    """Mean realized return per trade (deterministic, no win/loss weighting)."""
    if not trades:
        return 0.0

    pnls = [
        float(t.get("pnl", 0.0))
        for t in trades
        if isinstance(t, dict)
    ]

    if not pnls:
        return 0.0

    return float(sum(pnls) / len(pnls))


class TradeAnalytics:
    def compute(self, trades: list[dict[str, Any]]) -> dict[str, float]:
        wins: list[float] = []
        losses: list[float] = []

        for t in trades:
            if not isinstance(t, dict):
                continue
            try:
                pnl = float(t.get("pnl", 0.0))
            except (TypeError, ValueError):
                pnl = 0.0
            if pnl > 0:
                wins.append(pnl)
            elif pnl < 0:
                losses.append(pnl)

        n = max(len(trades), 1)
        win_rate = len(wins) / n

        avg_win = sum(wins) / max(len(wins), 1)
        avg_loss = sum(losses) / max(len(losses), 1)

        total_pnl = 0.0
        for t in trades:
            if not isinstance(t, dict):
                continue
            try:
                total_pnl += float(t.get("pnl", 0.0))
            except (TypeError, ValueError):
                pass

        # STAGE 84 — EXPECTANCY FIX
        if len(trades) > 3:
            expectancy = total_pnl / len(trades)
        else:
            expectancy = 0.0

        return {
            "win_rate": float(win_rate),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "expectancy": float(expectancy),
        }


__all__ = ["TradeAnalytics", "compute_expectancy"]
