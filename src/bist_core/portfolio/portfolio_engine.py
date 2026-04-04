"""Inverse-volatility portfolio weights from ranked symbols (deterministic)."""

from __future__ import annotations

from typing import Any, List


def _regime_weight_adjustment(regime: str) -> float:
    if regime == "trend":
        return 1.2
    if regime == "range":
        return 0.8
    return 1.0


def _regime_from_rank_row(row: dict[str, Any]) -> str:
    dec = row.get("decision")
    if isinstance(dec, dict):
        r = dec.get("regime", "unknown")
        return str(r) if r is not None else "unknown"
    return "unknown"


def _apply_regime_weights_and_normalize(
    rows: list[dict[str, Any]],
    top: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Multiply weights by regime factor, renormalize to sum 1; attach ``regime`` per row."""
    if not rows:
        return []
    adjusted: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        regime = _regime_from_rank_row(top[i]) if i < len(top) else "unknown"
        w = float(row["weight"]) * _regime_weight_adjustment(regime)
        adjusted.append(
            {
                "symbol": str(row["symbol"]),
                "weight": w,
                "regime": regime,
            }
        )
    s = sum(float(r["weight"]) for r in adjusted)
    if s <= 0:
        return [
            {
                "symbol": str(row["symbol"]),
                "weight": float(row["weight"]),
                "regime": _regime_from_rank_row(top[i]) if i < len(top) else "unknown",
            }
            for i, row in enumerate(rows)
        ]
    return [
        {
            "symbol": r["symbol"],
            "weight": float(r["weight"]) / s,
            "regime": r["regime"],
        }
        for r in adjusted
    ]


class PortfolioEngine:
    """Top-N selection + inverse-volatility weights (sum to 1)."""

    def __init__(self, top_n: int = 5) -> None:
        self._top_n = int(top_n) if top_n and top_n > 0 else 5

    def allocate(
        self,
        ranked: List[dict[str, Any]],
        *,
        top_n: int | None = None,
    ) -> List[dict[str, Any]]:
        """``ranked`` must be sorted best-first (e.g. AdvancedRanker output)."""
        n = int(top_n) if isinstance(top_n, int) and top_n > 0 else self._top_n
        if not ranked:
            return []
        top = ranked[:n]
        if len(top) == 1:
            out = [{"symbol": str(top[0]["symbol"]), "weight": 0.25}]
            return _apply_regime_weights_and_normalize(out, top)

        vols = [float(r.get("volatility", 0) or 0.0) for r in top]
        if all(abs(v) < 1e-15 for v in vols):
            w = 1.0 / len(top)
            out = [{"symbol": str(r["symbol"]), "weight": w} for r in top]
            return _apply_regime_weights_and_normalize(out, top)

        eps = 1e-12
        inv: list[float] = []
        for v in vols:
            inv.append(1.0 / max(float(v), eps))
        s = sum(inv)
        if s <= 0 or not (s == s):  # NaN guard
            w = 1.0 / len(top)
            out = [{"symbol": str(r["symbol"]), "weight": w} for r in top]
            return _apply_regime_weights_and_normalize(out, top)

        raw: list[float] = [float(inv[i] / s) for i in range(len(top))]
        cap = 0.25
        capped = [min(w, cap) for w in raw]
        sm = sum(capped)
        if sm <= 0:
            w = 1.0 / len(top)
            out = [{"symbol": str(r["symbol"]), "weight": w} for r in top]
            return _apply_regime_weights_and_normalize(out, top)
        out = []
        for i, r in enumerate(top):
            out.append({"symbol": str(r["symbol"]), "weight": float(capped[i] / sm)})
        return _apply_regime_weights_and_normalize(out, top)


__all__ = ["PortfolioEngine", "_regime_weight_adjustment"]
