"""Mean-reversion strategy from routed feature context."""

from __future__ import annotations

from typing import Any

from bist_core.strategy.base_strategy import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        mr = context.get("mean_reversion", 0)
        if not isinstance(mr, (int, float)):
            mr = 0.0
        mr = float(mr)
        if mr < -0.02:
            return {"signal": "long"}
        if mr > 0.02:
            return {"signal": "exit"}
        return {"signal": "hold"}


__all__ = ["MeanReversionStrategy"]
