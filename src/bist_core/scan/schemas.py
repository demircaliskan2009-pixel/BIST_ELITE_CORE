"""Scan schemas — candidate structure and types."""

from __future__ import annotations

from typing import Any


def build_candidate(
    symbol: str,
    momentum: float,
    volatility: float,
    passed_filters: bool,
    score_modifier: float,
    reasons: dict[str, Any],
) -> dict[str, Any]:
    """Build candidate dict with full schema."""
    return {
        "symbol": symbol,
        "momentum": momentum,
        "volatility": volatility,
        "passed_filters": passed_filters,
        "score_modifier": score_modifier,
        "reasons": dict(reasons),
    }


__all__ = ["build_candidate"]
