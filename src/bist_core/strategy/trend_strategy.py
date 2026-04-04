"""Trend-following strategy from routed score context."""

from __future__ import annotations

from typing import Any

from bist_core.strategy.base_strategy import BaseStrategy


class TrendStrategy(BaseStrategy):
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        score = context.get("score", 0)
        if not isinstance(score, (int, float)):
            score = 0.0
        score = float(score)
        if score > 0.45:
            return {"signal": "long"}
        if score < 0.4:
            return {"signal": "exit"}
        return {"signal": "hold"}


__all__ = ["TrendStrategy"]
