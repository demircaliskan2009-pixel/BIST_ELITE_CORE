"""Track live edge store quality over time (deterministic snapshots)."""

from __future__ import annotations

from typing import Any


class EdgeMonitor:
    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []

    def log(self, edge_count: int, avg_exp: float) -> None:
        self.history.append(
            {
                "edges": int(edge_count),
                "avg_exp": float(avg_exp),
            }
        )

    def summary(self) -> dict[str, Any]:
        if not self.history:
            return {}

        last = self.history[-1]

        return {
            "edges": last["edges"],
            "avg_exp": last["avg_exp"],
            "trend": "up" if last["avg_exp"] > 0 else "flat",
        }


__all__ = ["EdgeMonitor"]
