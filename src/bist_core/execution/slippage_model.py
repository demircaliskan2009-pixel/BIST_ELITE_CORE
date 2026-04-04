"""Deterministic slippage (no randomness)."""

from __future__ import annotations


class SlippageModel:
    def compute(self, price: float, volatility: float) -> float:
        slippage = float(price) * 0.0005 + float(volatility) * 0.1
        return float(slippage)


__all__ = ["SlippageModel"]
