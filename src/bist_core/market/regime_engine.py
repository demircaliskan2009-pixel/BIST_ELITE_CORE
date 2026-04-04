"""Deterministic regime detection from close series (no randomness)."""

from __future__ import annotations


class RegimeEngine:
    """Classify window as trend vs range from return drift vs volatility."""

    def detect(self, closes: list[float]) -> str:
        if len(closes) < 10:
            return "unknown"

        returns = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        avg = sum(returns) / len(returns)
        vol = (sum((r - avg) ** 2 for r in returns) / len(returns)) ** 0.5

        if abs(avg) > vol * 0.5:
            return "trend"
        return "range"

    def regime_confidence(self, closes: list[float]) -> float:
        if len(closes) < 10:
            return 0.0
        moves: list[int] = []
        for i in range(1, len(closes)):
            diff = float(closes[i]) - float(closes[i - 1])
            moves.append(1 if diff > 0 else -1)
        trend_bias = abs(sum(moves)) / len(moves)
        return float(trend_bias)


__all__ = ["RegimeEngine"]
