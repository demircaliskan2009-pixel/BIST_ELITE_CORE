"""Ranking engine — converts candidates into ranked decisions."""

from __future__ import annotations

from .weights import InvalidWeightsError, normalize_weights

REQUIRED_FIELDS = ("symbol", "momentum", "volatility", "score_modifier", "reasons")


def _has_required_fields(candidate: dict) -> bool:
    """Check candidate has all required fields."""
    for k in REQUIRED_FIELDS:
        if k not in candidate:
            return False
    return True


def _safe_float(candidate: dict, key: str) -> float | None:
    """Extract float from candidate; return None if invalid."""
    v = candidate.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Ranker:
    """Converts scan candidates into ranked decisions.

    score = (momentum * w_momentum + volatility * w_volatility) * score_modifier
    Sort by score DESC, tie-breaker symbol alphabetical.
    """

    def __init__(self, weights: dict) -> None:
        self._weights = normalize_weights(dict(weights))
        if "momentum" not in self._weights or "volatility" not in self._weights:
            raise InvalidWeightsError("weights must contain 'momentum' and 'volatility'")

    def score(self, candidate: dict) -> dict:
        """Compute score and return dict with symbol, score, momentum, volatility, score_modifier, reasons."""
        if not _has_required_fields(candidate):
            raise ValueError("candidate missing required fields")
        momentum = _safe_float(candidate, "momentum")
        volatility = _safe_float(candidate, "volatility")
        score_modifier = _safe_float(candidate, "score_modifier")
        if momentum is None or volatility is None or score_modifier is None:
            raise ValueError("invalid numeric fields in candidate")
        raw = (
            momentum * self._weights["momentum"]
            + volatility * self._weights["volatility"]
        )
        score = raw * score_modifier
        return {
            "symbol": str(candidate["symbol"]),
            "score": score,
            "momentum": momentum,
            "volatility": volatility,
            "score_modifier": score_modifier,
            "reasons": dict(candidate.get("reasons", {})),
        }

    def rank(self, candidates: list[dict], top_n: int = 5) -> list[dict]:
        """Rank candidates by score DESC, tie-breaker symbol alphabetical.

        Skip invalid candidates. Empty input → return [].
        """
        if not candidates:
            return []
        scored: list[dict] = []
        for c in candidates:
            try:
                s = self.score(c)
                scored.append(s)
            except (ValueError, KeyError, TypeError):
                continue
        scored.sort(key=lambda x: (-x["score"], x["symbol"]))
        return scored[:top_n]


__all__ = ["Ranker"]
