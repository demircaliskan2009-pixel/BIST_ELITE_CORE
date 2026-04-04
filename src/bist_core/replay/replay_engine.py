"""Deterministic replay driver — feeds step data then runs one trader cycle."""

from __future__ import annotations

from typing import Any


class ReplayEngine:
    def replay(self, trader: Any, bars_sequence: list[Any]) -> list[Any]:
        results: list[Any] = []
        for step_data in bars_sequence:
            trader.feed_data(step_data)
            res = trader.run_once()
            results.append(res)
        return results


__all__ = ["ReplayEngine"]
