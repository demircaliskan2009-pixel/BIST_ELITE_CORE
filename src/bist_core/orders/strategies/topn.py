from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _extract_score(rec: Dict[str, Any]) -> float:
    for k in ("score", "rank_score", "signal_score", "alpha", "edge", "value"):
        if k in rec:
            return _safe_float(rec.get(k), 0.0)
    side = str(rec.get("side") or rec.get("action") or "").upper().strip()
    if side == "BUY":
        return 1.0
    if side == "SELL":
        return -1.0
    return 0.0


def _rank(universe: List[str], advice_records: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    score_by: Dict[str, float] = {}
    for rec in advice_records or []:
        if not isinstance(rec, dict):
            continue
        sym = (rec.get("symbol") or "").strip().upper()
        if not sym:
            continue
        s = _extract_score(rec)
        prev = score_by.get(sym)
        score_by[sym] = s if prev is None else max(prev, s)

    ranked: List[Tuple[str, float]] = []
    for sym in universe or []:
        ss = str(sym).strip().upper()
        if not ss:
            continue
        ranked.append((ss, float(score_by.get(ss, 0.0))))

    ranked.sort(key=lambda x: (-x[1], x[0]))
    return ranked


@dataclass(frozen=True)
class TopNStrategy:
    name: str = "topn"

    def build_intent(
        self,
        *,
        day: str,
        universe: List[str],
        advice_records: List[Dict[str, Any]],
        params: Dict[str, Any],
        **_: Any,
    ) -> Dict[str, Any]:
        top_n = int(params.get("top_n", 5) or 0)
        min_score = _safe_float(params.get("min_score", -1e18), -1e18)

        ranked = _rank(universe, advice_records)
        actions: List[Dict[str, Any]] = []
        for sym, score in ranked[: max(top_n, 0)]:
            if score < min_score:
                continue
            actions.append({"symbol": sym, "side": "BUY", "qty": 1})

        notes: List[str] = ["topn"]
        if not actions:
            notes.append("no_actions")

        return {
            "schema_version": 1,
            "strategy": {"name": "topn", "params": {"top_n": top_n, "min_score": min_score}},
            "day": str(day),
            "universe_size": int(len(universe or [])),
            "actions": actions,
            "notes": sorted(set(notes)),
        }
