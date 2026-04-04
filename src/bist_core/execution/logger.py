"""Trade logger — records trade history."""

from __future__ import annotations

from typing import Any


class TradeLogger:
    """In-memory trade log. Deterministic, fail-closed."""

    def __init__(self) -> None:
        self._history: list[dict[str, Any]] = []

    def log_trade(self, trade: dict) -> None:
        """Append trade to history."""
        self._history.append(dict(trade))

    def history(self) -> list[dict]:
        """Return copy of trade history."""
        return [dict(t) for t in self._history]


__all__ = ["TradeLogger"]
