"""Decision schemas — final trade decision object."""

from __future__ import annotations

from typing import Any


def build_decision(
    symbol: str,
    action: str,
    entry: float,
    stop: float,
    target: float,
    confidence: float,
    score: float,
    reasons: dict[str, Any],
) -> dict[str, Any]:
    """Build decision dict with full schema."""
    return {
        "symbol": symbol,
        "action": action,
        "entry": entry,
        "stop": stop,
        "target": target,
        "confidence": confidence,
        "score": score,
        "reasons": dict(reasons),
    }


__all__ = ["build_decision"]
