"""Decision engine — converts ranked candidates + context into trade decisions."""

from __future__ import annotations

from typing import Any

from bist_core.regime import HIGH_VOLATILITY, RANGE, TRENDING_DOWN, TRENDING_UP, UNKNOWN

from .schemas import build_decision


def _safe_float(d: dict, key: str) -> float | None:
    """Extract float from dict; return None if invalid."""
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


MIN_RANGE_PCT = 0.005


class DecisionEngine:
    """Converts ranked candidate + context into trade decision.

    BUY when: score > threshold AND score_modifier >= 1.0 AND avg_range >= MIN_RANGE
    Else: NO_TRADE

    Fail-closed: missing fields or invalid numbers → NO_TRADE.
    """

    def __init__(self, threshold: float) -> None:
        self._threshold = float(threshold)

    def decide(self, candidate: dict, context: dict) -> dict:
        """Produce decision from candidate and context.

        candidate: from Ranker.rank() — symbol, score, momentum, volatility, score_modifier, reasons
        context: from ContextBuilder.build() — current_price, trend, avg_range
        """
        score = _safe_float(candidate, "score")
        score_modifier = _safe_float(candidate, "score_modifier")
        current_price = _safe_float(context, "current_price")
        avg_range = _safe_float(context, "avg_range")
        symbol = candidate.get("symbol")
        reasons = candidate.get("reasons", {})

        if symbol is None or not isinstance(symbol, str):
            return build_decision(
                symbol="",
                action="NO_TRADE",
                entry=0.0,
                stop=0.0,
                target=0.0,
                confidence=0.0,
                score=0.0,
                reasons={"error": "missing symbol"},
            )
        if score is None or current_price is None or avg_range is None:
            return build_decision(
                symbol=str(symbol),
                action="NO_TRADE",
                entry=0.0,
                stop=0.0,
                target=0.0,
                confidence=0.0,
                score=score or 0.0,
                reasons={"error": "missing or invalid numeric fields"},
            )

        min_range = current_price * MIN_RANGE_PCT
        if avg_range < min_range:
            return build_decision(
                symbol=str(symbol),
                action="NO_TRADE",
                entry=0.0,
                stop=0.0,
                target=0.0,
                confidence=0.0,
                score=score,
                reasons={"error": "avg_range below minimum", "avg_range": avg_range, "min_range": min_range},
            )

        regime = context.get("regime", UNKNOWN)
        if regime in (TRENDING_DOWN, UNKNOWN):
            return build_decision(
                symbol=str(symbol),
                action="NO_TRADE",
                entry=0.0,
                stop=0.0,
                target=0.0,
                confidence=0.0,
                score=score,
                reasons={"error": "regime not favorable", "regime": regime},
            )

        if regime == RANGE:
            min_score = max(self._threshold * 1.5, self._threshold * 1.2)
        else:
            min_score = max(self._threshold, self._threshold * 1.2)

        if regime != TRENDING_UP and regime != RANGE and regime != HIGH_VOLATILITY:
            return build_decision(
                symbol=str(symbol),
                action="NO_TRADE",
                entry=0.0,
                stop=0.0,
                target=0.0,
                confidence=0.0,
                score=score,
                reasons={"error": "regime not favorable", "regime": regime},
            )

        if score >= min_score and score_modifier is not None and score_modifier >= 1.0:
            entry = current_price
            stop = entry - avg_range
            target = entry + (avg_range * 1.5)
            confidence = min(score / 10.0, 1.0)
            decision = build_decision(
                symbol=str(symbol),
                action="BUY",
                entry=entry,
                stop=stop,
                target=target,
                confidence=confidence,
                score=score,
                reasons=dict(reasons) if isinstance(reasons, dict) else {},
            )
            if regime == HIGH_VOLATILITY:
                decision["size_modifier"] = 0.5
            return decision
        return build_decision(
            symbol=str(symbol),
            action="NO_TRADE",
            entry=0.0,
            stop=0.0,
            target=0.0,
            confidence=0.0,
            score=score,
            reasons=dict(reasons) if isinstance(reasons, dict) else {},
        )


__all__ = ["DecisionEngine"]
