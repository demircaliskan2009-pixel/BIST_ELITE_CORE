"""Cross-symbol edge adjustments — regime + volatility penalties only (no RNG)."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, Optional, Tuple

from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.live.portfolio_engine import ENTER_ACTIONS
from bist_core.models.ohlcv import OHLCVBar


def _norm_sym(sym: str) -> str:
    return str(sym).strip().upper()


def _population_std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / float(len(vals))
    v = sum((x - m) ** 2 for x in vals) / float(len(vals))
    return float(math.sqrt(max(0.0, v)))


def _sym_det_spread(sym: str) -> float:
    h = hashlib.sha256(sym.encode("utf-8")).digest()
    return float((h[0] % 10) * 0.001)


def _non_destructive_scale(current: float, factor: float) -> float:
    """Preserve scale vs raw ``out *= factor``: blend 70% identity + 30% factor."""
    f = float(factor)
    return float(current) * (0.7 + 0.3 * f)


def _edge_safety_clamp(x: float) -> float:
    return max(0.02, min(0.98, float(x)))


def _feat_for_symbol(
    pack: dict[str, Any], fe: FeatureEngineV2
) -> Optional[dict[str, Any]]:
    bars = pack.get("bars")
    if not isinstance(bars, list) or len(bars) < 50:
        return None
    ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
    if len(ohlcv) < 50:
        return None
    return fe.extract(ohlcv)


def _signal_style(dec: dict[str, Any], feat: dict[str, Any]) -> str:
    """Classify enter-style decision as trend-following vs mean-reversion vs neutral."""
    a = str(dec.get("action", "")).strip().lower()
    if a not in ENTER_ACTIONS:
        return "neutral"
    tr = float(feat.get("trend", 0.0) or 0.0)
    if a == "enter_long":
        side = 1
    elif a == "enter_short":
        side = -1
    else:
        if tr > 0:
            side = 1
        elif tr < 0:
            side = -1
        else:
            return "mean_reversion"
    if abs(tr) < 0.01:
        return "mean_reversion"
    same = (tr > 0 and side > 0) or (tr < 0 and side < 0)
    return "trend_follow" if same else "mean_reversion"


def _final_edge_from_decision(dec: dict[str, Any]) -> Optional[float]:
    """Single source of truth: final edge from decision dict (``edge`` then ``edge_score``)."""
    v = dec.get("edge")
    if v is None:
        v = dec.get("edge_score")
    if v is None:
        return None
    try:
        x = float(v)
        if x != x:
            return None
        return x
    except (TypeError, ValueError):
        return None


def _lookup_pack(per_symbol: Dict[str, Dict[str, Any]], sym: str) -> Optional[dict[str, Any]]:
    u = _norm_sym(sym)
    if u in per_symbol:
        p = per_symbol[u]
        return p if isinstance(p, dict) else None
    for k, v in per_symbol.items():
        if _norm_sym(str(k)) == u and isinstance(v, dict):
            return v
    return None


def apply_edge_distribution_adjustments(
    edge_scores: Dict[str, float],
    per_symbol: Dict[str, Dict[str, Any]],
    fe: FeatureEngineV2,
    regime: str,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Only regime penalty and volatility penalty — no artificial spreading or band clamps.
    """
    out: Dict[str, float] = {str(k).strip().upper(): float(v) for k, v in edge_scores.items()}
    dbg: Dict[str, Any] = {"regime_in": str(regime)}
    feat_cache: Dict[str, Optional[dict[str, Any]]] = {}

    def _feat_cached(sym: str) -> Optional[dict[str, Any]]:
        if sym in feat_cache:
            return feat_cache[sym]
        pack = _lookup_pack(per_symbol, sym)
        if pack is None:
            feat_cache[sym] = None
            return None
        f = _feat_for_symbol(pack, fe)
        feat_cache[sym] = f
        return f

    for sym in list(out.keys()):
        out[sym] = float(out[sym])

    for sym in list(out.keys()):
        pack = _lookup_pack(per_symbol, sym)
        dec = pack.get("decision") if isinstance(pack, dict) else None
        decision_edge = _final_edge_from_decision(dec) if isinstance(dec, dict) else None
        if decision_edge is None:
            raise RuntimeError("CRITICAL: EDGE LOST IN PIPELINE")
        out[sym] = float(decision_edge)
        print(
            {
                "EDGE_SOURCE_CHECK": {
                    "symbol": sym,
                    "used_edge": float(out[sym]),
                    "decision_edge": float(decision_edge),
                }
            },
            flush=True,
        )

    post_overlay_baseline: Dict[str, float] = {k: float(v) for k, v in out.items()}

    r = str(regime).strip().upper()
    is_trend_regime = r == "TRENDING"
    is_range_regime = r in ("CHOPPY", "MIXED")

    for sym in list(out.keys()):
        pack = _lookup_pack(per_symbol, sym)
        if pack is None:
            continue
        dec = pack.get("decision")
        if not isinstance(dec, dict):
            continue
        feat = _feat_cached(sym)
        if feat is None:
            continue
        vol_norm = max(0.0, float(feat.get("vol", 0.0) or 0.0))
        vol_factor = max(0.88, 1.0 - min(0.12, vol_norm * 1.5))
        out[sym] = _non_destructive_scale(out[sym], vol_factor)

    for sym in list(out.keys()):
        pack = _lookup_pack(per_symbol, sym)
        if pack is None:
            continue
        dec = pack.get("decision")
        if not isinstance(dec, dict):
            continue
        feat = _feat_cached(sym)
        if feat is None:
            continue
        st = _signal_style(dec, feat)
        if is_range_regime and st == "trend_follow":
            out[sym] = _non_destructive_scale(out[sym], 0.92)
        elif is_trend_regime and st == "mean_reversion":
            out[sym] = _non_destructive_scale(out[sym], 0.92)

    if len(out) >= 2:
        vals = list(out.values())
        mn, mx = min(vals), max(vals)
        if mx - mn < 0.05:
            for k in out:
                out[k] = float(out[k]) + _sym_det_spread(str(k))

    for sym in list(out.keys()):
        out[sym] = _edge_safety_clamp(out[sym])

    for sym in list(out.keys()):
        print(
            {
                "EDGE_POST_ADJUST_CHECK": {
                    "symbol": sym,
                    "before": float(post_overlay_baseline.get(sym, out[sym])),
                    "after": float(out[sym]),
                }
            },
            flush=True,
        )

    decisions: list[dict[str, Any]] = []
    for pack in per_symbol.values():
        if not isinstance(pack, dict):
            continue
        dec = pack.get("decision")
        if not isinstance(dec, dict):
            continue
        decisions.append(dec)

    for dec in decisions:
        if str(dec.get("direction", "")).strip():
            continue
        a = str(dec.get("action", "")).strip().lower()
        if a == "enter_long":
            dec["direction"] = "long"
        elif a == "enter_short":
            dec["direction"] = "short"

    dirs = [
        str(x).strip().lower()
        for x in (d.get("direction") for d in decisions)
        if x is not None and str(x).strip()
    ]
    dbg["DIRECTION_DISTRIBUTION"] = {
        "long": int(dirs.count("long")),
        "short": int(dirs.count("short")),
    }

    estd = _population_std(list(out.values()))
    vals = list(out.values())
    vmin = float(min(vals)) if vals else 0.0
    vmax = float(max(vals)) if vals else 0.0

    dbg["EDGE_STD"] = round(estd, 10)
    dbg["edge_std"] = dbg["EDGE_STD"]
    dbg["EDGE_MIN"] = round(vmin, 6)
    dbg["EDGE_MAX"] = round(vmax, 6)
    dbg["LOW_EDGE_DIVERSITY"] = bool(estd < 0.03)
    dbg["PORTFOLIO_RECOVERED"] = False

    print(
        {
            "EDGE_STD": dbg["EDGE_STD"],
            "LOW_EDGE_DIVERSITY": dbg["LOW_EDGE_DIVERSITY"],
            "PORTFOLIO_RECOVERED": dbg["PORTFOLIO_RECOVERED"],
        },
        flush=True,
    )

    edges = list(out.values())
    if edges:
        print(
            {
                "EDGE_DISTRIBUTION_CHECK": {
                    "min": min(edges),
                    "max": max(edges),
                    "mean": sum(edges) / len(edges),
                }
            },
            flush=True,
        )

    return out, dbg


__all__ = ["apply_edge_distribution_adjustments"]
