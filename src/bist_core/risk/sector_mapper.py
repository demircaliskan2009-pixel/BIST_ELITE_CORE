"""BIST symbol → coarse sector bucket (deterministic lookup)."""

from __future__ import annotations

SECTOR_MAP = {
    "GARAN": "bank",
    "AKBNK": "bank",
    "ISCTR": "bank",
    "THYAO": "transport",
    "SISE": "industry",
}


def get_sector(symbol: str) -> str:
    return SECTOR_MAP.get(symbol, "other")


__all__ = ["SECTOR_MAP", "get_sector"]
