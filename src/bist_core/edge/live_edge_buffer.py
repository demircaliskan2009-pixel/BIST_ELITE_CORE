"""Append-only buffer of rich learning rows for online edge refresh."""

from __future__ import annotations

from typing import Any


class LiveEdgeBuffer:
    """Each row: features (entry), return, exit context (deterministic)."""

    def __init__(self, max_rows: int = 50_000) -> None:
        # Minimum 1 so callers can cap buffer tightly (tests, low-memory runs).
        self.max_rows = max(1, int(max_rows))
        self.data: list[dict[str, Any]] = []

    def add(self, record: dict[str, Any]) -> None:
        self.data.append(
            {
                "features": dict(record["features"]),
                "return": float(record["return"]),
                "holding_period": int(record["holding_period"]),
                "volatility": float(record["volatility"]),
                "regime": str(record["regime"]),
            }
        )
        if len(self.data) > self.max_rows:
            self.data = self.data[-self.max_rows :]


__all__ = ["LiveEdgeBuffer"]
