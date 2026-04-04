"""Pearson correlation on aligned trailing series (deterministic)."""

from __future__ import annotations


class CorrelationEngine:
    def correlation(self, a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n < 2:
            return 0.0

        a = a[-n:]
        b = b[-n:]

        ma = sum(a) / n
        mb = sum(b) / n

        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        va = sum((x - ma) ** 2 for x in a)
        vb = sum((y - mb) ** 2 for y in b)

        if va == 0 or vb == 0:
            return 0.0

        return cov / ((va**0.5) * (vb**0.5))


__all__ = ["CorrelationEngine"]
