"""Rolling close volatility vs mean — shock detector (deterministic)."""

from __future__ import annotations

from typing import Any


class VolatilityShock:
    def detect(self, bars: list[Any]) -> bool:
        if len(bars) < 10:
            return False

        closes = [float(getattr(b, "close", 0) or 0) for b in bars[-10:]]

        mean = sum(closes) / len(closes)

        var = sum((c - mean) ** 2 for c in closes) / len(closes)

        vol = var**0.5

        return vol / (mean + 1e-6) > 0.05


__all__ = ["VolatilityShock"]
