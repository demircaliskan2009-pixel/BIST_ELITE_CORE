"""Deterministic portfolio exposure cap in weight space."""

from __future__ import annotations


class ExposureController:
    def __init__(self) -> None:
        self.max_exposure = 1.0

    def adjust(self, current_exposure: float, new_weight: float) -> float:
        ce = float(current_exposure)
        nw = float(new_weight)
        if ce + nw > self.max_exposure:
            return 0.0
        return nw


__all__ = ["ExposureController"]
