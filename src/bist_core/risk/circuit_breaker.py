"""Single-bar circuit breaker from prior close (deterministic)."""

from __future__ import annotations

from typing import Any


class CircuitBreaker:
    def triggered(self, bars: list[Any]) -> bool:
        if len(bars) < 2:
            return False

        prev = getattr(bars[-2], "close", 0)
        curr = getattr(bars[-1], "close", 0)

        try:
            pf = float(prev)
            cf = float(curr)
        except (TypeError, ValueError):
            return False

        if pf <= 0:
            return False

        change = (cf - pf) / pf

        return abs(change) > 0.1


__all__ = ["CircuitBreaker"]
