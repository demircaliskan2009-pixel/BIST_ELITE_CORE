"""Deterministic bid–ask spread proxy (no randomness)."""

from __future__ import annotations


class SpreadModel:
    def compute(self, price: float) -> float:
        return float(float(price) * 0.001)


__all__ = ["SpreadModel"]
