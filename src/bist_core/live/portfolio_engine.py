"""Multi-symbol ranking and risk-budget allocation — deterministic, no randomness."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from bist_core.brain.ranking_engine import rank_symbols
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar

DEFAULT_BIST_SYMBOLS: tuple[str, ...] = (
    "ASELS",
    "THYAO",
    "AKBNK",
    "SISE",
    "KCHOL",
    "EREGL",
    "BIMAS",
    "TUPRS",
    "GARAN",
    "ISCTR",
)

ENTER_ACTIONS = frozenset(
    {
        "enter",
        "enter_small",
        "aggressive_enter",
        "enter_long",
        "enter_short",
    }
)

# Aligned with decision_engine_v2 hard gate — portfolio must not admit weaker names.
_PORT_HARD_EDGE_MIN = 0.60
_PORT_HARD_CONF_MIN = 0.55


def _portfolio_hard_edge_confidence_ok(edge: float, confidence: float) -> tuple[bool, str]:
    """No exceptions: entries require edge ≥ 0.60 and confidence ≥ 0.55."""
    try:
        e = float(edge)
    except (TypeError, ValueError):
        e = 0.0
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        c = 0.0
    if e < _PORT_HARD_EDGE_MIN:
        return False, "edge_below_0_60"
    if c < _PORT_HARD_CONF_MIN:
        return False, "confidence_below_0_55"
    return True, ""


def _log_portfolio_hard_reject(
    symbol: str,
    *,
    phase: str,
    detail: str,
    edge: float,
    confidence: float,
) -> None:
    print(
        {
            "PORTFOLIO_HARD_GATE_REJECT": {
                "symbol": str(symbol).strip().upper(),
                "phase": str(phase),
                "reason": str(detail),
                "edge": float(edge),
                "confidence": float(confidence),
                "edge_floor": _PORT_HARD_EDGE_MIN,
                "confidence_floor": _PORT_HARD_CONF_MIN,
            }
        },
        flush=True,
    )


def _normalize_decision_action_for_portfolio(decision: dict[str, Any]) -> None:
    """Map BUY/SELL-style labels to enter-class actions portfolio gates understand."""
    if not isinstance(decision, dict):
        return
    raw = decision.get("action")
    if not isinstance(raw, str):
        return
    original_action = raw
    a = raw.strip().upper()
    if a in ("BUY", "STRONG_BUY"):
        decision["action"] = "enter_long"
        print(
            {
                "ACTION_NORMALIZED": {
                    "original": original_action,
                    "normalized": decision["action"],
                }
            }
        )
    elif a in ("SELL", "STRONG_SELL"):
        decision["action"] = "enter_short"
        print(
            {
                "ACTION_NORMALIZED": {
                    "original": original_action,
                    "normalized": decision["action"],
                }
            }
        )


def load_symbol_universe_from_env() -> list[str]:
    """BIST_SYMBOLS overrides BIST_LIVE_SYMBOLS; else default 10-name universe."""
    raw = os.environ.get("BIST_SYMBOLS", "").strip()
    if not raw:
        raw = os.environ.get("BIST_LIVE_SYMBOLS", "").strip()
    if raw:
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return list(DEFAULT_BIST_SYMBOLS)


def _tie_break_delta(symbol: str) -> float:
    h = hashlib.sha256(symbol.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 16**8 * 1e-12


def _volatility_penalty(vol: float, price: float) -> float:
    """vol: mean abs return (dimensionless); user spec also allows vol/price — cap at 0.5."""
    if price > 0 and vol > 1.0:
        return min(float(vol) / float(price), 0.5)
    return min(float(vol), 0.5)


def _momentum(decision: dict[str, Any], feat: dict[str, Any]) -> float:
    bm = decision.get("brain_momentum")
    try:
        if bm is not None and float(bm) == float(bm):
            return float(bm)
    except (TypeError, ValueError):
        pass
    try:
        return float(feat.get("trend", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _position_fraction(decision: dict[str, Any], capital: float) -> float:
    ps = decision.get("position_size")
    try:
        p = float(ps) if ps is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if capital <= 0 or p <= 0:
        return 0.0
    return min(1.0, p / capital)


def raw_ranking_score(
    *,
    confidence: float,
    position_frac: float,
    momentum: float,
    vol: float,
    price: float,
) -> float:
    """Unnormalized edge score; batch-normalize with normalize_scores_to_unit_interval."""
    vol_pen = _volatility_penalty(vol, price)
    trend_strength = abs(float(momentum))
    pf = max(float(position_frac), 1e-9)
    return (
        float(confidence)
        * pf
        * max(trend_strength, 1e-9)
        * (1.0 - vol_pen)
    )


def _population_std_edge(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / float(len(vals))
    v = sum((x - m) ** 2 for x in vals) / float(len(vals))
    return float(math.sqrt(max(0.0, v)))


def normalize_scores_to_unit_interval(scores: list[float]) -> list[float]:
    if not scores:
        return []
    mx = max(scores)
    if mx <= 0.0:
        return [0.0 for _ in scores]
    return [float(s) / mx for s in scores]


def _profile_key(trend: float, vol: float) -> Tuple[float, float]:
    return (round(trend, 3), round(vol, 4))


def _diversity_mult(keys: List[Tuple[float, float]], idx: int) -> float:
    """×1.1 if this candidate's (trend, vol) profile appears exactly once in the batch."""
    k = keys[idx]
    cnt = sum(1 for x in keys if x == k)
    return 1.1 if cnt == 1 else 1.0


def _symbol_decisions_for_ranking(
    per_symbol: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten per-symbol packs into decision dicts with uppercase ``symbol`` (deterministic)."""
    out: list[dict[str, Any]] = []
    for sym, pack in per_symbol.items():
        dec = pack.get("decision")
        if not isinstance(dec, dict):
            continue
        u = str(sym).strip().upper()
        out.append({**dec, "symbol": u})
    return out


def _apply_confidence_spread(confidences: list[float], ranking_order: list[int]) -> list[float]:
    """If all confidences within 0.05, spread by ranking_score order (best = larger bump)."""
    if len(confidences) < 2:
        return confidences
    lo, hi = min(confidences), max(confidences)
    if hi - lo >= 0.05:
        return confidences
    out = list(confidences)
    n = len(ranking_order)
    for rank, idx in enumerate(ranking_order):
        bump = 0.01 * float(n - 1 - rank) / max(1, n - 1)
        out[idx] = min(0.99, float(out[idx]) + bump)
    return out


@dataclass
class _Work:
    symbol: str
    action: str
    reason: str
    confidence: float
    entry: float
    stop_loss: float
    target: float
    position_frac: float
    raw_score: float
    trend: float
    vol: float


def _lookup_incoming_decision_action(
    per_symbol: dict[str, dict[str, Any]], sym_upper: str
) -> str:
    """Action from the snapshot decision dict (after normalize pass), upper symbol key."""
    u = str(sym_upper).strip().upper()
    for k, pack in per_symbol.items():
        if str(k).strip().upper() != u:
            continue
        if not isinstance(pack, dict):
            return ""
        dec = pack.get("decision")
        if not isinstance(dec, dict):
            return ""
        return str(dec.get("action", "") or "").strip().lower()
    return ""


def _pack_for_symbol(
    per_symbol: dict[str, dict[str, Any]], sym_upper: str
) -> dict[str, Any] | None:
    u = str(sym_upper).strip().upper()
    for k, pack in per_symbol.items():
        if str(k).strip().upper() != u:
            continue
        return pack if isinstance(pack, dict) else None
    return None


def _incoming_decision_size_notional(dec: dict[str, Any]) -> float | None:
    """Notional from decision ``size`` or ``position_size`` when present (deterministic)."""
    for key in ("size", "position_size"):
        if key not in dec:
            continue
        v = dec.get(key)
        if v is None:
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if x == x:
            return x
    return None


def _parse_float(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    v = d.get(key)
    try:
        if v is None:
            return default
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _apply_edge_multiplier(raw_adj: float, sym: str, edge_scores: Optional[dict[str, float]]) -> float:
    if not edge_scores:
        return raw_adj
    es = float(edge_scores.get(str(sym).strip().upper(), 0.0))
    return float(raw_adj) * max(0.12, 1.0 + es)


def _pack_to_work(
    sym: str,
    pack: dict[str, Any],
    fe: FeatureEngineV2,
    *,
    min_conf: float,
    min_pf: float,
    allow_enter_small_reason: bool,
    edge_scores: Optional[dict[str, float]] = None,
) -> _Work | None:
    dec = pack.get("decision")
    if not isinstance(dec, dict):
        return None
    act = str(dec.get("action", "")).strip().lower()
    conf = _parse_float(dec, "confidence", 0.0)
    edge_pf = _parse_float(dec, "edge_score", 0.0)
    if act == "hold" or act not in ENTER_ACTIONS:
        return None
    _hg_ok, _hg_det = _portfolio_hard_edge_confidence_ok(edge_pf, conf)
    if not _hg_ok:
        _log_portfolio_hard_reject(
            sym,
            phase="pack_to_work",
            detail=_hg_det,
            edge=edge_pf,
            confidence=conf,
        )
        return None
    reason = str(dec.get("reason", "")).lower()
    is_small = act == "enter_small" or "enter_small" in reason
    small_bypass = allow_enter_small_reason and is_small and conf >= 0.08
    cap = float(pack.get("capital", 0.0) or 0.0)
    pf_cap = _position_fraction(dec, cap)
    pf_explicit = _parse_float(dec, "position_frac", 0.0)
    pf_base = max(pf_cap, pf_explicit)
    pf_floor = max(float(min_pf), float(edge_pf) * float(conf) * 0.5)
    pf = min(1.0, max(pf_base, pf_floor))
    print(
        {
            "PF_DEBUG": {
                "symbol": sym.upper(),
                "pf": round(float(pf), 6),
                "conf": round(float(conf), 6),
                "edge": round(float(edge_pf), 6),
            }
        }
    )
    if not small_bypass:
        # Reject only if confidence, position fraction, AND edge are all below bar.
        if conf < min_conf and pf < min_pf and edge_pf < min_conf:
            return None

    bars = pack.get("bars")
    if not isinstance(bars, list) or not bars:
        return None
    ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
    if len(ohlcv) < 50:
        return None
    feat = fe.extract(ohlcv)
    price = float(pack.get("current_price", 0.0) or 0.0)
    if price <= 0:
        return None
    vol = float(feat.get("vol", 0.0) or 0.0)
    trend = float(feat.get("trend", 0.0) or 0.0)
    mom = _momentum(dec, feat)
    raw = raw_ranking_score(
        confidence=max(conf, 0.05),
        position_frac=max(pf, 1e-6),
        momentum=mom,
        vol=vol,
        price=price,
    )
    raw_adj = raw + _tie_break_delta(sym)
    raw_adj = _apply_edge_multiplier(raw_adj, sym, edge_scores)
    print(
        {
            "PORTFOLIO_DECISION": {
                "symbol": sym.upper(),
                "edge": round(float(edge_pf), 6),
                "conf": round(float(conf), 6),
                "accepted": True,
            }
        }
    )
    return _Work(
        symbol=sym.upper(),
        action=act,
        reason=str(dec.get("reason", ""))[:200],
        confidence=conf,
        entry=_parse_float(dec, "entry", price),
        stop_loss=_parse_float(dec, "stop_loss", 0.0),
        target=_parse_float(dec, "target", 0.0),
        position_frac=pf,
        raw_score=raw_adj,
        trend=trend,
        vol=vol,
    )


def _hold_work(
    sym: str,
    pack: dict[str, Any],
    fe: FeatureEngineV2,
    *,
    edge_scores: Optional[dict[str, float]] = None,
) -> _Work | None:
    """Synthetic portfolio row for force-fill (display-only sizing) when <2 enters."""
    dec = pack.get("decision")
    if not isinstance(dec, dict):
        return None
    act = str(dec.get("action", "")).strip().lower()
    if act != "hold":
        return None
    conf = max(0.05, _parse_float(dec, "confidence", 0.05))
    bars = pack.get("bars")
    if not isinstance(bars, list) or not bars:
        return None
    ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
    if len(ohlcv) < 50:
        return None
    feat = fe.extract(ohlcv)
    price = float(pack.get("current_price", 0.0) or 0.0)
    if price <= 0:
        return None
    vol = float(feat.get("vol", 0.0) or 0.0)
    trend = float(feat.get("trend", 0.0) or 0.0)
    mom = _momentum(dec, feat)
    pf = 0.002
    raw = raw_ranking_score(
        confidence=conf,
        position_frac=pf,
        momentum=mom,
        vol=vol,
        price=price,
    )
    raw_adj = raw * 0.35 + _tie_break_delta(sym)
    return _Work(
        symbol=sym.upper(),
        action="hold",
        reason=str(dec.get("reason", ""))[:200],
        confidence=conf,
        entry=_parse_float(dec, "entry", price),
        stop_loss=_parse_float(dec, "stop_loss", 0.0),
        target=_parse_float(dec, "target", 0.0),
        position_frac=pf,
        raw_score=raw_adj,
        trend=trend,
        vol=vol,
    )


def _force_pool_enters(
    per_symbol: dict[str, dict[str, Any]],
    fe: FeatureEngineV2,
    *,
    edge_scores: Optional[dict[str, float]] = None,
) -> list[_Work]:
    """All enter/aggressive_enter with bars; ignore conf/pf thresholds (score only)."""
    out: list[_Work] = []
    for sym, pack in per_symbol.items():
        if not isinstance(pack, dict):
            continue
        dec = pack.get("decision")
        if not isinstance(dec, dict):
            continue
        act = str(dec.get("action", "")).strip().lower()
        if act not in ENTER_ACTIONS:
            continue
        _fe = _parse_float(dec, "edge_score", 0.0)
        _fc = _parse_float(dec, "confidence", 0.0)
        _fp_ok, _fp_det = _portfolio_hard_edge_confidence_ok(_fe, _fc)
        if not _fp_ok:
            _log_portfolio_hard_reject(
                str(sym),
                phase="force_pool_enters",
                detail=_fp_det,
                edge=_fe,
                confidence=_fc,
            )
            continue
        cap = float(pack.get("capital", 0.0) or 0.0)
        pf = max(_position_fraction(dec, cap), 0.002)
        conf = max(0.05, _parse_float(dec, "confidence", 0.05))
        bars = pack.get("bars")
        if not isinstance(bars, list) or not bars:
            continue
        ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
        if len(ohlcv) < 50:
            continue
        feat = fe.extract(ohlcv)
        price = float(pack.get("current_price", 0.0) or 0.0)
        if price <= 0:
            continue
        vol = float(feat.get("vol", 0.0) or 0.0)
        trend = float(feat.get("trend", 0.0) or 0.0)
        mom = _momentum(dec, feat)
        raw = raw_ranking_score(
            confidence=conf,
            position_frac=pf,
            momentum=mom,
            vol=vol,
            price=price,
        )
        raw_adj = raw + _tie_break_delta(sym)
        raw_adj = _apply_edge_multiplier(raw_adj, sym, edge_scores)
        out.append(
            _Work(
                symbol=sym.upper(),
                action=act,
                reason=str(dec.get("reason", ""))[:200],
                confidence=_parse_float(dec, "confidence", 0.0),
                entry=_parse_float(dec, "entry", price),
                stop_loss=_parse_float(dec, "stop_loss", 0.0),
                target=_parse_float(dec, "target", 0.0),
                position_frac=pf,
                raw_score=raw_adj,
                trend=trend,
                vol=vol,
            )
        )
    out.sort(key=lambda w: (-w.raw_score, w.symbol))
    return out


def _thr_get(
    key: str,
    default_env: str,
    default_val: str,
    threshold_overrides: Optional[dict[str, float]],
) -> float:
    if threshold_overrides and key in threshold_overrides:
        return float(threshold_overrides[key])
    return float(os.environ.get(default_env, default_val))


def build_portfolio_payload(
    per_symbol: dict[str, dict[str, Any]],
    *,
    symbols_scanned: list[str],
    fe: Optional[FeatureEngineV2] = None,
    threshold_overrides: Optional[dict[str, float]] = None,
    edge_scores: Optional[dict[str, float]] = None,
    risk_snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build PORTFOLIO terminal structure from last-per-cycle symbol snapshots.

    Each ``per_symbol[sym]`` must contain:
    ``decision`` (dict), ``bars`` (list[OHLCVBar]), ``capital`` (float), ``current_price`` (float).

    Optional ``risk_snapshot`` (from :class:`~bist_core.live.risk_engine.RiskEngine`):
    applies ``combined_position_factor``, enforces max 3 names and 30% per-symbol cap.
    """
    fe = fe or FeatureEngineV2()
    try:
        max_sym_frac = float(os.environ.get("BIST_RISK_MAX_SYMBOL_FRACTION", "0.30"))
    except ValueError:
        max_sym_frac = 0.30
    max_sym_frac = max(0.01, min(1.0, max_sym_frac))
    risk_combined = 1.0
    risk_kill = False
    if isinstance(risk_snapshot, dict):
        if risk_snapshot.get("kill_switch"):
            risk_kill = True
        try:
            risk_combined = float(
                risk_snapshot.get("combined_position_factor", 1.0) or 1.0
            )
        except (TypeError, ValueError):
            risk_combined = 1.0
        risk_combined = max(0.0, min(1.5, risk_combined))
    min_conf = _thr_get(
        "min_conf", "BIST_PORTFOLIO_MIN_CONF", "0.1", threshold_overrides
    )
    min_pf = _thr_get(
        "min_pf",
        "BIST_PORTFOLIO_MIN_POSITION_FRAC",
        "0.002",
        threshold_overrides,
    )
    min_conf_fb = _thr_get(
        "min_conf_fb",
        "BIST_PORTFOLIO_MIN_CONF_FALLBACK",
        "0.08",
        threshold_overrides,
    )
    min_pf_fb = _thr_get(
        "min_pf_fb",
        "BIST_PORTFOLIO_MIN_POSITION_FRAC_FALLBACK",
        "0.001",
        threshold_overrides,
    )
    try:
        pcm = float(os.environ.get("BIST_PORTFOLIO_MIN_CONF_MULT", "1.0"))
    except ValueError:
        pcm = 1.0
    pcm = max(0.80, min(1.20, pcm))
    min_conf = max(0.05, min(0.35, min_conf * pcm))
    min_conf_fb = max(0.05, min(0.30, min_conf_fb * pcm))
    try:
        top_k = int(os.environ.get("BIST_PORTFOLIO_TOP_K", "5"))
    except ValueError:
        top_k = 5
    top_k = max(2, min(5, top_k))
    if risk_snapshot is None:
        max_names = top_k
    else:
        try:
            max_names = int(os.environ.get("BIST_RISK_MAX_POSITIONS", "3"))
        except ValueError:
            max_names = 3
        max_names = max(1, min(20, max_names))
    total_risk = float(os.environ.get("BIST_PORTFOLIO_RISK_BUDGET", "0.05"))
    lo = float(os.environ.get("BIST_PORTFOLIO_WEIGHT_MIN", "0.002"))
    hi = float(os.environ.get("BIST_PORTFOLIO_WEIGHT_MAX", "0.03"))

    n_scanned = len(symbols_scanned)
    portfolio_recovered = False

    for _pack in per_symbol.values():
        if not isinstance(_pack, dict):
            continue
        _dec = _pack.get("decision")
        if isinstance(_dec, dict):
            _normalize_decision_action_for_portfolio(_dec)

    # --- Phase 1: primary filters
    cands: list[_Work] = []
    for sym, pack in per_symbol.items():
        w = _pack_to_work(
            sym,
            pack,
            fe,
            min_conf=min_conf,
            min_pf=min_pf,
            allow_enter_small_reason=False,
            edge_scores=edge_scores,
        )
        if w is not None:
            cands.append(w)

    # --- Phase 2: fallback (no primary hits)
    if not cands:
        for sym, pack in per_symbol.items():
            w = _pack_to_work(
                sym,
                pack,
                fe,
                min_conf=min_conf_fb,
                min_pf=min_pf_fb,
                allow_enter_small_reason=True,
                edge_scores=edge_scores,
            )
            if w is not None:
                cands.append(w)

    # Diversity bonus on raw scores
    keys = [_profile_key(c.trend, c.vol) for c in cands]
    for i, c in enumerate(cands):
        c.raw_score *= _diversity_mult(keys, i)

    if not cands:
        # Force pool: unfiltered enters
        cands = _force_pool_enters(per_symbol, fe, edge_scores=edge_scores)
        keys = [_profile_key(c.trend, c.vol) for c in cands]
        for i, c in enumerate(cands):
            c.raw_score *= _diversity_mult(keys, i)

    if not cands:
        hold_list: list[_Work] = []
        for sym, pack in per_symbol.items():
            hw = _hold_work(sym, pack, fe, edge_scores=edge_scores)
            if hw is not None:
                hold_list.append(hw)
        hold_list.sort(key=lambda x: (-x.raw_score, x.symbol))
        if hold_list:
            cands = hold_list[:top_k]
            keys = [_profile_key(c.trend, c.vol) for c in cands]
            for i, c in enumerate(cands):
                c.raw_score *= _diversity_mult(keys, i)

    if not cands and edge_scores:
        ranked_edges: list[tuple[str, float]] = []
        for sym, es in edge_scores.items():
            try:
                e = float(es)
            except (TypeError, ValueError):
                continue
            if e > 0.25:
                ranked_edges.append((str(sym).strip().upper(), e))
        ranked_edges.sort(key=lambda x: (-x[1], x[0]))
        for sym_u, _es in ranked_edges:
            pack = _pack_for_symbol(per_symbol, sym_u)
            if pack is None:
                continue
            w = _pack_to_work(
                sym_u,
                pack,
                fe,
                min_conf=min_conf_fb,
                min_pf=min_pf_fb,
                allow_enter_small_reason=True,
                edge_scores=edge_scores,
            )
            if w is not None:
                cands = [w]
                portfolio_recovered = True
                break
        if not cands and ranked_edges:
            for sym_u, _es in ranked_edges:
                pack = _pack_for_symbol(per_symbol, sym_u)
                if pack is None:
                    continue
                fp = _force_pool_enters({sym_u: pack}, fe, edge_scores=edge_scores)
                if fp:
                    cands = fp[:1]
                    portfolio_recovered = True
                    break

    if portfolio_recovered and edge_scores:
        _evs: list[float] = []
        for _v in edge_scores.values():
            try:
                _evs.append(float(_v))
            except (TypeError, ValueError):
                continue
        _estd_r = round(_population_std_edge(_evs), 10)
        print(
            {
                "EDGE_STD": _estd_r,
                "LOW_EDGE_DIVERSITY": False,
                "PORTFOLIO_RECOVERED": True,
            },
            flush=True,
        )

    if not cands:
        print(
            {
                "EDGE_FULL_DISTRIBUTION": [],
            },
            flush=True,
        )
        return {
            "PORTFOLIO": [],
            "TOTAL_SYMBOLS_SCANNED": n_scanned,
            "SELECTED": 0,
            "PORTFOLIO_RECOVERED": portfolio_recovered,
        }

    all_decisions = _symbol_decisions_for_ranking(per_symbol)
    ranked = rank_symbols(all_decisions)
    print(
        json.dumps(
            {
                "ranking": [
                    {"symbol": d["symbol"], "edge": d["edge_score"]}
                    for d in ranked[:5]
                ]
            },
            ensure_ascii=False,
        )
    )

    if risk_kill:
        print(
            {
                "EDGE_FULL_DISTRIBUTION": [],
            },
            flush=True,
        )
        return {
            "PORTFOLIO": [],
            "TOTAL_SYMBOLS_SCANNED": n_scanned,
            "SELECTED": 0,
            "RISK_KILL_SWITCH": True,
            "PORTFOLIO_RECOVERED": portfolio_recovered,
        }

    work_by_sym = {c.symbol: c for c in cands}
    selected: list[_Work] = []
    for d in ranked:
        if len(selected) >= top_k:
            break
        sym_u = str(d.get("symbol", "")).strip().upper()
        _pk = _pack_for_symbol(per_symbol, sym_u)
        if isinstance(_pk, dict):
            _pdec = _pk.get("decision")
            if isinstance(_pdec, dict):
                _re = _parse_float(_pdec, "edge_score", 0.0)
                _rc = _parse_float(_pdec, "confidence", 0.0)
                _ra = str(_pdec.get("action", "") or "").strip().lower()
                if _ra in ENTER_ACTIONS:
                    _rk_ok, _rk_det = _portfolio_hard_edge_confidence_ok(_re, _rc)
                    if not _rk_ok:
                        _log_portfolio_hard_reject(
                            sym_u,
                            phase="ranking_acceptance",
                            detail=_rk_det,
                            edge=_re,
                            confidence=_rc,
                        )
                        continue
        w = work_by_sym.get(sym_u)
        if w is not None:
            selected.append(w)

    edge_rank_used = bool(selected)

    if not selected:
        raws = [c.raw_score for c in cands]
        norms = normalize_scores_to_unit_interval(raws)
        scored: list[tuple[_Work, float]] = [(c, float(n)) for c, n in zip(cands, norms)]
        scored.sort(key=lambda x: (-x[1], x[0].symbol))

        # Select top_k, minimum 2 rows when possible
        k = min(top_k, len(scored))
        selected = [t[0] for t in scored[:k]]

    # Force at least 2 if possible (unfiltered enters, then holds)
    if len(selected) < 2:
        forced = _force_pool_enters(per_symbol, fe, edge_scores=edge_scores)
        seen = {x.symbol for x in selected}
        for w in forced:
            if w.symbol not in seen:
                selected.append(w)
                seen.add(w.symbol)
            if len(selected) >= 2:
                break
    if len(selected) < 2:
        holds: list[_Work] = []
        for sym, pack in per_symbol.items():
            hw = _hold_work(sym, pack, fe, edge_scores=edge_scores)
            if hw is not None:
                holds.append(hw)
        holds.sort(key=lambda x: (-x.raw_score, x.symbol))
        seen = {x.symbol for x in selected}
        for h in holds:
            if h.symbol not in seen:
                selected.append(h)
                seen.add(h.symbol)
            if len(selected) >= 2:
                break

    # Re-sort selected by raw_score for allocation (unless edge-ranked order applies)
    if not edge_rank_used:
        selected.sort(key=lambda x: (-x.raw_score, x.symbol))
    if len(selected) > 2:
        sigs = {(x.action, x.reason[:48]) for x in selected}
        if len(sigs) == 1:
            selected = selected[:-1]

    selected = selected[:top_k]

    enter_like = [w for w in selected if w.action in ENTER_ACTIONS]
    if len(enter_like) > max_names:
        enter_like.sort(key=lambda x: (-x.raw_score, x.symbol))
        keep_enter = {w.symbol for w in enter_like[:max_names]}
        selected = [
            w
            for w in selected
            if w.action not in ENTER_ACTIONS or w.symbol in keep_enter
        ]

    sum_raw = sum(max(w.raw_score, 1e-12) for w in selected)
    score_norms = normalize_scores_to_unit_interval([w.raw_score for w in selected])
    confidences = [w.confidence for w in selected]
    order = sorted(range(len(selected)), key=lambda i: (-selected[i].raw_score, selected[i].symbol))
    confidences = _apply_confidence_spread(confidences, order)

    _preserve_enter = frozenset(
        {"enter", "enter_small", "enter_long", "enter_short"}
    )

    out_list: list[dict[str, Any]] = []
    for i, w in enumerate(selected):
        w_share = max(w.raw_score, 1e-12) / sum_raw
        w_alloc = w_share * total_risk
        w_clamped = max(lo, min(hi, w_alloc))
        w_adj = w_clamped * risk_combined
        if risk_snapshot is not None:
            w_adj = min(max_sym_frac, w_adj)
        sn = score_norms[i] if i < len(score_norms) else 0.0
        incoming_action = _lookup_incoming_decision_action(per_symbol, w.symbol)
        final_action = str(w.action).strip().lower()
        if incoming_action in _preserve_enter:
            final_action = incoming_action
        print(
            {
                "PORTFOLIO_ACTION_CHECK": {
                    "symbol": w.symbol,
                    "incoming": incoming_action,
                    "final": final_action,
                }
            },
            flush=True,
        )
        if incoming_action.startswith("enter") and final_action == "hold":
            raise RuntimeError("PORTFOLIO_KILLED_VALID_TRADE")
        pack_i = _pack_for_symbol(per_symbol, w.symbol)
        dec_i_edge: dict[str, Any] | None = None
        if pack_i is not None:
            _di = pack_i.get("decision")
            if isinstance(_di, dict):
                dec_i_edge = _di
        if (
            dec_i_edge is None
            or dec_i_edge.get("edge_score") is None
            or dec_i_edge.get("edge") is None
        ):
            raise RuntimeError("EDGE_SSOT_VIOLATION")
        try:
            _ev_chk = float(dec_i_edge["edge_score"])
            if _ev_chk != _ev_chk:
                raise RuntimeError("EDGE_SSOT_VIOLATION")
        except (TypeError, ValueError):
            raise RuntimeError("EDGE_SSOT_VIOLATION") from None
        try:
            _e_ssot = float(dec_i_edge["edge"])
            if _e_ssot != _e_ssot:
                raise RuntimeError("EDGE_SSOT_VIOLATION")
        except (TypeError, ValueError):
            raise RuntimeError("EDGE_SSOT_VIOLATION") from None
        final_size = w_adj
        out_ps = round(final_size, 6)
        out_list.append(
            {
                "symbol": w.symbol,
                "action": final_action,
                "confidence": round(confidences[i], 6),
                "position_size": out_ps,
                "entry": round(w.entry, 6),
                "stop_loss": round(w.stop_loss, 6),
                "target": round(w.target, 6),
                "score": round(float(sn), 6),
                "decision": dict(dec_i_edge),
            }
        )

    print(
        {
            "EDGE_FULL_DISTRIBUTION": [
                {
                    "symbol": p.get("symbol"),
                    "edge": p.get("decision", {}).get("edge"),
                }
                for p in out_list
            ]
        },
        flush=True,
    )

    if out_list and any(
        not isinstance(p.get("decision"), dict)
        or p["decision"].get("edge_score") is None
        or p["decision"].get("edge") is None
        for p in out_list
    ):
        raise RuntimeError("PORTFOLIO_EDGE_MISSING")

    return {
        "PORTFOLIO": out_list,
        "TOTAL_SYMBOLS_SCANNED": n_scanned,
        "SELECTED": len(out_list),
        "risk_combined_factor": round(float(risk_combined), 8),
        "PORTFOLIO_RECOVERED": portfolio_recovered,
    }


__all__ = [
    "DEFAULT_BIST_SYMBOLS",
    "ENTER_ACTIONS",
    "build_portfolio_payload",
    "load_symbol_universe_from_env",
    "normalize_scores_to_unit_interval",
    "raw_ranking_score",
]
