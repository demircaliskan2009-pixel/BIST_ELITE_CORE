"""BIST symbol → coarse sector bucket (deterministic lookup)."""

from __future__ import annotations

SECTOR_MAP = {
    # Banks
    "GARAN": "bank",
    "AKBNK": "bank",
    "ISCTR": "bank",
    "YKBNK": "bank",
    "HALKB": "bank",
    "VAKBN": "bank",
    # Industry / Materials
    "EREGL": "materials",
    "SISE": "materials",
    "SASA": "materials",
    "KRDMD": "materials",
    # Energy / Chemicals
    "PETKM": "energy",
    "TUPRS": "energy",
    # Transport / Aviation
    "THYAO": "transport",
    "PGSUS": "transport",
    "TSPOR": "sport",
    # Holdings / Conglomerates
    "KCHOL": "holding",
    "SAHOL": "holding",
    "DOHOL": "holding",
    "TAVHL": "holding",
    # Consumer / Retail
    "BIMAS": "consumer",
    "ARCLK": "consumer",
    "ADESE": "consumer",
    "CANTE": "consumer",
    # Automotive / Industrial
    "TOASO": "industrial",
    "FROTO": "industrial",
    "ASELS": "defense",
    "ENKAI": "industrial",
    "KATMR": "industrial",
    "PEKGY": "industrial",
    # Telecom
    "TCELL": "telecom",
    # REITs / Real Estate
    "EKGYO": "reit",
    "PSGYO": "reit",
    # Pharma / Healthcare
    "HEKTS": "pharma",
    # Sports
    "GSRAY": "sport",
}


def get_sector(symbol: str) -> str:
    return SECTOR_MAP.get(symbol, "other")


__all__ = ["SECTOR_MAP", "get_sector"]
