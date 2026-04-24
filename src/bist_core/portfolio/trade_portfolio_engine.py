"""Trade decision → risk-sized positions (legacy pipeline)."""

from __future__ import annotations

import math

from bist_core.risk.risk_engine import TradeRiskEngine

RISK_PER_TRADE = 0.015
MAX_POSITIONS = 10


def _safe_float(d: dict, key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return f if not math.isnan(f) and math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _is_valid_decision(d: dict) -> bool:
    """Fail-closed: skip if any required field missing or invalid."""
    if not isinstance(d.get("symbol"), str):
        return False
    entry = _safe_float(d, "entry")
    stop = _safe_float(d, "stop")
    return entry is not None and stop is not None and entry > stop


class TradePortfolioEngine:
    """Convert trade decisions into capital-allocated, risk-controlled positions.

    Deterministic, fail-closed, no randomness.
    """

    def __init__(
        self,
        risk_per_trade: float = RISK_PER_TRADE,
        max_positions: int = MAX_POSITIONS,
        risk_engine: TradeRiskEngine | None = None,
    ) -> None:
        self._risk_per_trade = risk_per_trade
        self._max_positions = max_positions
        self._risk = risk_engine or TradeRiskEngine()

    def allocate(
        self,
        decisions: list[dict],
        capital: float,
    ) -> list[dict]:
        """Produce positions from decisions, sorted by confidence, capped at max_positions.

        Skips invalid decisions. Rejects positions that fail risk checks.
        """
        if capital <= 0:
            return []

        valid = [d for d in decisions if _is_valid_decision(d)]
        sorted_decisions = sorted(
            valid,
            key=lambda d: _safe_float(d, "confidence") or 0.0,
            reverse=True,
        )

        positions: list[dict] = []
        cumulative_risk = 0.0

        for d in sorted_decisions:
            if len(positions) >= self._max_positions:
                break

            symbol = str(d["symbol"])
            entry = float(d["entry"])
            stop = float(d["stop"])
            target = float(d.get("target") or entry * 1.04)

            risk_amount = capital * self._risk_per_trade
            stop_distance = entry - stop
            if stop_distance <= 0:
                continue

            size = risk_amount / stop_distance
            risk_pct = risk_amount / capital

            position = {
                "symbol": symbol,
                "size": round(size, 4),
                "entry": round(entry, 4),
                "stop": round(stop, 4),
                "target": round(target, 4),
                "risk_pct": round(risk_pct, 6),
            }

            if not self._risk.accept(position, capital, cumulative_risk):
                continue

            positions.append(position)
            cumulative_risk += risk_amount

        return positions


__all__ = ["TradePortfolioEngine"]
