"""Deterministic latency / queue price impact (no randomness)."""

from __future__ import annotations


class LatencyModel:
    def apply(self, price: float) -> float:
        return float(float(price) * 1.0002)


__all__ = ["LatencyModel"]
