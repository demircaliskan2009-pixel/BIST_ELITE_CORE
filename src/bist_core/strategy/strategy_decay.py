"""Deterministic decay/boost from rolling performance (no randomness)."""

from __future__ import annotations


class StrategyDecay:
    def compute_weight(self, performance: float) -> float:
        p = float(performance)
        if p > 0:
            return float(min(1.5, 1.0 + p))
        return float(max(0.1, 1.0 + p))


__all__ = ["StrategyDecay"]
