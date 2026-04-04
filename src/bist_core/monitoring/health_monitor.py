"""Lightweight in-process health metrics (deterministic counters)."""

from __future__ import annotations

from typing import Any, Dict


class HealthMonitor:
    def __init__(self) -> None:
        self.metrics: Dict[str, Any] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "last_error": None,
        }

    def record_trade(self, pnl: float) -> None:
        self.metrics["total_trades"] = int(self.metrics.get("total_trades", 0)) + 1
        try:
            p = float(pnl)
        except (TypeError, ValueError):
            return
        if p > 0:
            self.metrics["wins"] = int(self.metrics.get("wins", 0)) + 1
        elif p < 0:
            self.metrics["losses"] = int(self.metrics.get("losses", 0)) + 1

    def record_error(self, err: str) -> None:
        self.metrics["last_error"] = str(err)[:2000]

    def snapshot(self) -> Dict[str, Any]:
        return dict(self.metrics)


__all__ = ["HealthMonitor"]
