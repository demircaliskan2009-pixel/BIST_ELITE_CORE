"""Simple order record for realistic fill simulation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Order:
    id: str
    symbol: str
    side: str  # "buy" | "sell"
    price: float
    size: int
    filled: int = 0
    status: str = "pending"


__all__ = ["Order"]
