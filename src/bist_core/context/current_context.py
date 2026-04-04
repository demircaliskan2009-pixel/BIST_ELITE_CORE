"""Current Context Analyzer — entry status relative to current price."""

from __future__ import annotations

import math
from typing import Any


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _classify_delta(delta: float) -> str:
    if delta > 0.03:
        return "missed_entry"
    if delta > 0:
        return "late_entry"
    if delta >= -0.02:
        return "ideal_entry"
    return "pullback"


class CurrentContextAnalyzer:
    """Analyze decisions against current prices. Fail-closed, deterministic."""

    def analyze(
        self,
        decisions: list[dict],
        current_prices: dict[str, float],
    ) -> list[dict]:
        """Add current_price, entry_delta, entry_status to each decision.

        Skip symbol if price missing.
        """
        result: list[dict] = []
        for d in decisions:
            symbol = d.get("symbol")
            if not isinstance(symbol, str):
                continue
            price = current_prices.get(symbol)
            if price is None:
                continue
            p = _safe_float(price)
            if p is None or p <= 0:
                continue

            entry = _safe_float(d.get("entry"))
            if entry is None or entry <= 0:
                continue

            delta = (p - entry) / entry
            status = _classify_delta(delta)

            out = dict(d)
            out["current_price"] = round(p, 4)
            out["entry_delta"] = round(delta, 6)
            out["entry_status"] = status
            result.append(out)
        return result
