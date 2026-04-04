"""Position manager — track entry, stop, target, size."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Position:
    """Single position with entry, stop, target, size."""

    symbol: str
    entry: float
    stop: float
    target: float
    size: float

    def is_stop_hit(self, price: float) -> bool:
        """True if price has hit or breached stop (LONG: price <= stop)."""
        return price <= self.stop

    def is_target_hit(self, price: float) -> bool:
        """True if price has hit or breached target (LONG: price >= target)."""
        return price >= self.target


__all__ = ["Position"]
