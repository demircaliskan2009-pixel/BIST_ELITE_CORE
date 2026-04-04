"""
FAZ62: Deterministic dummy baseline model. predict(features) -> scores (stable).
"""

from __future__ import annotations

from typing import Any, Dict, List


def _deterministic_score(symbol: str, close: float) -> float:
    """Stable score from symbol and close; no randomness."""
    h = hash(symbol) % 10000
    return round(float(close) * 0.01 + (h % 100) * 0.0001, 6)


class BaselineModel:
    """Dummy baseline: score = f(symbol, close); deterministic."""

    def predict(self, features: List[Dict[str, Any]]) -> List[float]:
        """One score per row; order matches features."""
        scores: List[float] = []
        for row in features:
            sym = (row.get("symbol") or "").strip() or "UNKNOWN"
            try:
                close = float(row.get("close") or 0)
            except (TypeError, ValueError):
                close = 0.0
            scores.append(_deterministic_score(sym, close))
        return scores
