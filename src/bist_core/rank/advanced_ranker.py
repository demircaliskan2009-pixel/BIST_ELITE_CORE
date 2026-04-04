"""Advanced ranking: decision score + returns/volatility (min–max normalized)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from bist_core.decision.decision_engine_v2 import DecisionEngineV2
from bist_core.features.feature_engine import FeatureEngine


def _norm_min_max(values: list[float], x: float) -> float:
    if not values:
        return 0.5
    lo = min(values)
    hi = max(values)
    if hi <= lo or abs(hi - lo) < 1e-15:
        return 0.5
    return float((x - lo) / (hi - lo))


class AdvancedRanker:
    """Rank symbols by composite ``rank_score``; keeps ``ScoreRanker`` unchanged elsewhere."""

    def __init__(
        self,
        engine: Optional[DecisionEngineV2] = None,
        *,
        lookback: int | None = None,
    ) -> None:
        self._engine = engine if engine is not None else DecisionEngineV2()
        lb = lookback
        if lb is None:
            lb = int(getattr(self._engine, "_lookback", 20))
        self._lookback = int(lb) if lb and lb > 5 else 20
        self._feature_engine = FeatureEngine()

    def rank(self, symbol_contexts: Mapping[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not symbol_contexts:
            return []

        raw_rows: list[dict[str, Any]] = []

        for symbol in sorted(symbol_contexts.keys()):
            ctx = symbol_contexts.get(symbol)
            if not isinstance(ctx, dict):
                continue
            try:
                decision = self._engine.evaluate_symbol(ctx)
            except Exception:
                continue
            if not isinstance(decision, dict):
                continue

            sc_raw = decision.get("score")
            score = float(sc_raw) if isinstance(sc_raw, (int, float)) else 0.0

            bars = ctx.get("bars")
            if not isinstance(bars, list):
                volatility = 0.0
                returns = 0.0
            else:
                try:
                    feats = self._feature_engine.extract(bars, lookback=self._lookback)
                    volatility = float(feats.get("volatility", 0.0))
                    returns = float(feats.get("returns", 0.0))
                except Exception:
                    volatility = 0.0
                    returns = 0.0

            raw_rows.append(
                {
                    "symbol": str(symbol),
                    "score": score,
                    "volatility": volatility,
                    "returns": returns,
                    "decision": decision,
                }
            )

        if not raw_rows:
            return []

        rets = [float(r["returns"]) for r in raw_rows]
        vols = [float(r["volatility"]) for r in raw_rows]

        ranked: list[dict[str, Any]] = []
        for r in raw_rows:
            nr = _norm_min_max(rets, float(r["returns"]))
            nv = _norm_min_max(vols, float(r["volatility"]))
            rank_score = 0.5 * float(r["score"]) + 0.3 * nr - 0.2 * nv
            ranked.append(
                {
                    "symbol": r["symbol"],
                    "rank_score": float(rank_score),
                    "score": float(r["score"]),
                    "volatility": float(r["volatility"]),
                    "returns": float(r["returns"]),
                    "decision": r["decision"],
                }
            )

        ranked.sort(key=lambda x: (-x["rank_score"], x["symbol"]))
        return ranked


__all__ = ["AdvancedRanker"]
