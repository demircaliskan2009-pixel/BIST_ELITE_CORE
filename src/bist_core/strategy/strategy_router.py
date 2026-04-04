"""Route evaluation to regime-specific strategy (deterministic)."""

from __future__ import annotations

from typing import Any

from bist_core.config.system_config import CONFIG
from bist_core.strategy.mean_reversion_strategy import MeanReversionStrategy
from bist_core.strategy.trend_strategy import TrendStrategy


class StrategyRouter:
    def __init__(self) -> None:
        self.trend = TrendStrategy()
        self.mean_rev = MeanReversionStrategy()

    def route(self, context: dict[str, Any]) -> dict[str, Any]:
        regime = context.get("regime")

        if regime == "trend":
            if not CONFIG.enable_trend:
                return {"signal": "hold", "strategy": "disabled"}
            out = self.trend.evaluate(context)
            return {**out, "strategy": "trend"}

        if regime == "range":
            if not CONFIG.enable_mean_reversion:
                return {"signal": "hold", "strategy": "disabled"}
            out = self.mean_rev.evaluate(context)
            return {**out, "strategy": "mean_reversion"}

        return {"signal": "hold", "strategy": "none"}


__all__ = ["StrategyRouter"]
