"""Deterministic event-risk flag per symbol (placeholder set)."""

from __future__ import annotations


class EventRisk:
    def is_risky(self, symbol: str) -> bool:
        risky_symbols = {"THYAO", "GARAN"}
        return symbol in risky_symbols


__all__ = ["EventRisk"]
