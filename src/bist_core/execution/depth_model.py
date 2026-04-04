"""Simplified market depth / impact (deterministic, volume-scaled)."""

from __future__ import annotations


class DepthModel:
    def impact(self, size: int, avg_volume: float) -> float:
        av = float(avg_volume)
        if av <= 0:
            return 0.0
        ratio = float(size) / av
        return float(min(0.02, ratio * 0.1))


__all__ = ["DepthModel"]
