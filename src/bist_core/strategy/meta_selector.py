"""Normalize non-negative rolling performance into strategy weights (deterministic)."""

from __future__ import annotations


class MetaSelector:
    def select(self, perf: dict[str, float]) -> dict[str, float]:
        if not perf:
            return {}
        total = sum(max(v, 0.0) for v in perf.values())
        if total <= 0:
            n = len(perf)
            return {k: 1.0 / n for k in perf}
        return {k: max(v, 0.0) / total for k, v in perf.items()}


__all__ = ["MetaSelector"]
