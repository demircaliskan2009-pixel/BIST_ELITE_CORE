"""Per-strategy PnL lists (deterministic aggregation input)."""

from __future__ import annotations


class StrategyMetrics:
    def __init__(self) -> None:
        self._data: dict[str, list[float]] = {}

    def record(self, strategy: str, pnl: float) -> None:
        if strategy not in self._data:
            self._data[strategy] = []
        self._data[strategy].append(float(pnl))

    def get(self) -> dict[str, list[float]]:
        return self._data

    def rolling_performance(self, window: int = 20) -> dict[str, float]:
        out: dict[str, float] = {}
        w = int(window) if window > 0 else 20
        for strat, pnls in self._data.items():
            recent = pnls[-w:]
            if not recent:
                out[strat] = 0.0
            else:
                out[strat] = sum(recent) / len(recent)
        return out

    def summary(self) -> dict[str, dict[str, float | int]]:
        out: dict[str, dict[str, float | int]] = {}
        for k, v in self._data.items():
            if not v:
                continue
            out[k] = {
                "count": len(v),
                "mean": sum(v) / len(v),
                "last": v[-1],
            }
        return out


__all__ = ["StrategyMetrics"]
