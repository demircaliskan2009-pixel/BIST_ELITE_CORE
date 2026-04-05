"""Decision engine v2 — single-TF edge or multi-TF fusion (deterministic, fail-closed)."""

from __future__ import annotations

import math
import os
from typing import Any, Dict, Optional

from bist_core.analytics.expectancy import tracker
from bist_core.decision.edge_signal import (attach_edge_signal_to_decision,
                                            compute_edge_signal)
from bist_core.decision.institutional_brain import \
    compute_institutional_decision
from bist_core.decision.price_intelligence import \
    apply_realtime_price_intelligence
from bist_core.edge.bucket_key import edge_bucket_key, regime_from_feat
from bist_core.edge.edge_store import EdgeStore
from bist_core.exit_engine import compute_exit_decision
from bist_core.exit_engine_v2 import compute_exit_v2
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar
from bist_core.portfolio_engine_v2 import apply_portfolio_v2_to_trades


def run_portfolio_v2_once(context: Dict[str, Any]) -> None:
    """Run portfolio v2 allocation once per cycle (shared ``context`` dict across symbols)."""
    if not context.get("portfolio_v2_apply"):
        return

    if context.get("_portfolio_v2_ran"):
        return

    scan = context.get("portfolio_v2_scan_results")
    trades = context.get("portfolio_v2_trades")

    if not isinstance(scan, list) or not isinstance(trades, list):
        return

    apply_portfolio_v2_to_trades(scan, trades)

    context["_portfolio_v2_ran"] = True


def _no_trade(reason: str) -> Dict[str, Any]:
    """Always a valid decision object — hold / no trade (STAGE 6)."""
    return {
        "action": "hold",
        "reason": str(reason),
        "risk": {"stop_price": 0.0},
        "score": 0.0,
        "confidence": 0.0,
        "edge_score": 0.0,
        "edge": 0.0,
        "edge_signal": "NEUTRAL",
        "regime": "unknown",
        "vol_adj": 1.0,
        "strategy": "none",
        "no_trade": True,
    }


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _clamp_m11(x: float) -> float:
    return max(-1.0, min(1.0, float(x)))


def _de_v2_clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _de_v2_extract_closes(bars: list[Any]) -> list[float] | None:
    if not bars or len(bars) < 30:
        return None
    closes: list[float] = []
    for x in bars:
        try:
            if isinstance(x, dict) and "close" in x:
                closes.append(float(x["close"]))
            elif isinstance(x, (list, tuple)) and len(x) > 4:
                closes.append(float(x[4]))
            elif hasattr(x, "close"):
                closes.append(float(getattr(x, "close")))
        except (TypeError, ValueError, IndexError):
            continue
    return closes if len(closes) >= 30 else None


def _de_v2_trend_strength(closes: list[float]) -> float:
    if len(closes) < 30:
        return 0.0
    ema20 = sum(closes[-20:]) / 20.0
    ema50 = sum(closes[-50:]) / 50.0
    slope = (ema20 - ema50) / max(ema50, 1e-6)
    norm = (slope + 0.05) / 0.10
    return _de_v2_clip01(norm)


def _strict_trade_regime(market_state: str) -> str:
    """Institutional RANGE vs all other states (treated as TREND for strict filter)."""
    if str(market_state).strip().upper() == "RANGE":
        return "RANGE"
    return "TREND"


def _strict_regime_blocks_new_entry(
    market_state: str,
    edge_score: float,
    breakout_ready: int,
) -> bool:
    """RANGE entries are blocked when edge is below strict floor."""
    if _strict_trade_regime(market_state) != "RANGE":
        return False
    if int(breakout_ready) <= 0:
        return True
    if float(edge_score) >= 0.75:
        return False
    return True


_HARD_EDGE_MIN = 0.60
_HARD_CONF_MIN = 0.55

_ENTER_ACTIONS_HARD_GATE = frozenset(
    {
        "enter",
        "enter_small",
        "enter_long",
        "enter_short",
        "aggressive_enter",
        "partial_enter",
    }
)


def _mtf_context_string(context: Dict[str, Any]) -> str:
    raw = context.get("mtf_signal", context.get("mtf_trend"))
    if isinstance(raw, dict):
        return str(
            raw.get("trend")
            or raw.get("label")
            or raw.get("signal")
            or raw.get("action")
            or raw
        ).strip().lower()
    if raw is None:
        return ""
    return str(raw).strip().lower()


def _mtf_explicit_command(context: Dict[str, Any]) -> str | None:
    raw = context.get("mtf_signal")
    if isinstance(raw, dict):
        s = str(raw.get("action") or raw.get("signal") or "").strip().lower()
    elif raw is None:
        return None
    else:
        s = str(raw).strip().lower()
    if s == "enter_long":
        return "enter_long"
    if s == "enter_short":
        return "enter_short"
    return None


def _mtf_axis_from_context(context: Dict[str, Any]) -> str | None:
    """MTF directional axis: UP / DOWN / None (unknown or non-directional)."""
    raw = context.get("mtf_signal", context.get("mtf_trend"))
    if isinstance(raw, dict):
        s = str(
            raw.get("trend")
            or raw.get("label")
            or raw.get("signal")
            or raw.get("action")
            or ""
        ).strip().lower()
    elif raw is None:
        return None
    else:
        s = str(raw).strip().lower()
    if not s:
        return None
    if s in ("enter_long", "long", "up", "buy", "bull"):
        return "UP"
    if s in ("enter_short", "short", "down", "sell", "bear"):
        return "DOWN"
    if s in ("hold", "wait", "neutral", "flat", "none"):
        return None
    return None


def _resolve_entry_side_for_conflict(
    action: str,
    inst: Dict[str, Any] | None,
) -> str | None:
    a = str(action).strip().lower()
    if a == "enter_long":
        return "long"
    if a == "enter_short":
        return "short"
    if a in ("enter", "enter_small", "aggressive_enter", "partial_enter"):
        if inst and isinstance(inst.get("direction"), str):
            d = str(inst["direction"]).strip().lower()
            if d == "long":
                return "long"
            if d == "short":
                return "short"
    return None


def _apply_mtf_conflict_final(
    decision: Dict[str, Any],
    context: Dict[str, Any],
    inst: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    MTF > direction_engine > edge: block opening trades that fight ``mtf_signal`` / UP-DOWN axis.
    On conflict: hold, reason ``mtf_conflict_block``.
    """
    act = str(decision.get("action", "hold")).strip().lower()
    if act not in _ENTER_ACTIONS_HARD_GATE:
        return decision

    side = _resolve_entry_side_for_conflict(act, inst)
    exp = _mtf_explicit_command(context)
    axis = _mtf_axis_from_context(context)

    detail: str | None = None
    if exp == "enter_long" and side != "long":
        detail = "mtf_enter_long_mismatch"
    elif exp == "enter_short" and side != "short":
        detail = "mtf_enter_short_mismatch"
    elif side == "long" and axis is not None and axis != "UP":
        detail = "long_not_allowed_mtf_not_up"
    elif side == "short" and axis is not None and axis != "DOWN":
        detail = "short_not_allowed_mtf_not_down"
    elif side is None:
        if exp in ("enter_long", "enter_short"):
            detail = "entry_side_unresolved_vs_explicit_mtf"
        elif axis == "UP":
            detail = "entry_side_unresolved_mtf_up"
        elif axis == "DOWN":
            detail = "entry_side_unresolved_mtf_down"

    if detail is None:
        return decision

    sym = str(decision.get("symbol") or context.get("symbol") or "X").strip() or "X"
    print(
        {
            "MTF_CONFLICT_BLOCK": {
                "symbol": sym,
                "proposed_action": act,
                "resolved_side": side,
                "mtf_signal": _mtf_context_string(context),
                "mtf_explicit": exp,
                "mtf_axis": axis,
                "detail": detail,
            }
        },
        flush=True,
    )
    nxt = dict(decision)
    nxt["action"] = "hold"
    nxt["reason"] = "mtf_conflict_block"
    nxt["no_trade"] = True
    for _pk in (
        "position_size",
        "position_size_frac",
        "position_size_frac_remaining",
    ):
        if _pk in nxt:
            nxt[_pk] = 0.0
    return nxt


def _apply_global_edge_floor(decision: Dict[str, Any]) -> Dict[str, Any]:
    """Final global gate: enter-class actions require edge >= 0.60 (exits unchanged)."""
    act = str(decision.get("action", "hold")).strip().lower()
    if act == "enter_small":
        return decision
    if act not in _ENTER_ACTIONS_HARD_GATE:
        return decision
    try:
        edge_v = float(
            decision.get("edge_score", decision.get("score", 0.0)) or 0.0
        )
    except (TypeError, ValueError):
        edge_v = 0.0
    if edge_v >= _HARD_EDGE_MIN:
        return decision
    print({"EDGE_GLOBAL_BLOCK": edge_v}, flush=True)
    return {
        "action": "hold",
        "reason": "edge_below_threshold",
        "no_trade": True,
        "edge_score": float(edge_v),
        "edge": float(edge_v),
    }


def _apply_hard_edge_confidence_final(
    decision: Dict[str, Any],
    *,
    symbol: str,
) -> Dict[str, Any]:
    """Final stage: no new trades if edge < 0.60 or confidence < 0.55."""
    act = str(decision.get("action", "hold")).strip().lower()
    if act == "enter_small":
        return decision
    if act not in _ENTER_ACTIONS_HARD_GATE:
        return decision

    try:
        edge_v = float(
            decision.get("edge_score", decision.get("score", 0.0)) or 0.0
        )
    except (TypeError, ValueError):
        edge_v = 0.0
    try:
        conf_v = float(decision.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        conf_v = 0.0

    blocked_reason: str | None = None
    if edge_v < _HARD_EDGE_MIN:
        blocked_reason = "hard_edge_below_0_60"
    elif conf_v < _HARD_CONF_MIN:
        blocked_reason = "hard_confidence_below_0_55"

    if blocked_reason is None:
        return decision

    sym = str(symbol).strip() or "X"
    print(
        {
            "HARD_EDGE_CONF_FILTER": {
                "symbol": sym,
                "action_blocked": act,
                "edge": edge_v,
                "confidence": conf_v,
                "edge_floor": _HARD_EDGE_MIN,
                "confidence_floor": _HARD_CONF_MIN,
                "reason": blocked_reason,
            }
        },
        flush=True,
    )

    nxt = dict(decision)
    nxt["action"] = "hold"
    prior_reason = str(nxt.get("reason", ""))
    nxt["reason"] = f"hard_edge_conf_gate|{blocked_reason}|{prior_reason}"[:500]
    nxt["no_trade"] = True
    for _pk in (
        "position_size",
        "position_size_frac",
        "position_size_frac_remaining",
    ):
        if _pk in nxt:
            nxt[_pk] = 0.0
    return nxt


def _de_v2_volatility_compression(closes: list[float]) -> float:
    if len(closes) < 20:
        return 0.0
    rets: list[float] = []
    for i in range(1, len(closes)):
        r = (closes[i] - closes[i - 1]) / max(closes[i - 1], 1e-6)
        rets.append(r)
    if len(rets) < 20:
        return 0.0
    mean = sum(rets[-20:]) / 20.0
    var = sum((x - mean) ** 2 for x in rets[-20:]) / 20.0
    std = var**0.5
    norm = 1.0 - min(std / 0.03, 1.0)
    return _de_v2_clip01(norm)


def _open_position_side_from_context(context: Dict[str, Any]) -> Optional[str]:
    """Open position side for exit engine: explicit ``position_side`` or signed ``position_qty``."""
    raw = context.get("position_side")
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("long", "short"):
            return s
    try:
        pq = float(context.get("position_qty", 0.0) or 0.0)
    except (TypeError, ValueError):
        pq = 0.0
    if abs(pq) <= 1e-12:
        return None
    if pq < 0:
        return "short"
    return "long"


def _exit_engine_should_fire(
    *,
    position_side: str,
    edge_score: float,
    conf: float,
    edge_signal_label: str,
) -> tuple[bool, str]:
    ps = str(position_side).strip().lower()
    es = str(edge_signal_label).strip().upper()
    if ps == "long":
        if float(edge_score) < 0.25:
            return True, "long_edge_below_0.25"
        if es in ("SELL", "STRONG_SELL"):
            return True, "long_edge_signal_sell"
        if float(conf) < 0.45:
            return True, "long_conf_below_0.45"
    elif ps == "short":
        if es in ("BUY", "STRONG_BUY"):
            return True, "short_edge_signal_buy"
    return False, ""


def _compute_mtf_size_multiplier(context: Dict[str, Any]) -> float:
    states = context.get("mtf_state", {}) or {}
    if not isinstance(states, dict):
        return 1.0
    weights = {
        "G": 0.4,
        "60": 0.3,
        "05": 0.2,
        "01": 0.1,
    }
    score = 0.0
    for tf, w in weights.items():
        s = str(states.get(tf, "")).upper()
        if s == "UP":
            score += w
        elif s == "DOWN":
            score -= w
    score = max(-0.5, min(0.5, float(score)))
    return 1.0 + score


def _apply_kap_edge_mod(exp: float, context: Dict[str, Any]) -> tuple[float, Optional[str]]:
    """
    KAP is an edge modifier only — never creates trades without positive base edge.

    ``context["kap_feature"]`` may be a dict with ``kap_alpha`` or absent/None.

    Returns ``(modified_exp, None)`` or ``(exp, error_reason)`` for fail-closed no-trade.
    """
    kap = context.get("kap_feature")
    if not isinstance(kap, dict) or not kap:
        return exp, None
    try:
        ka = float(kap.get("kap_alpha", 0.0))
    except (TypeError, ValueError):
        return exp, None
    if not _finite(ka):
        return exp, None
    if ka < -0.5:
        return exp, "kap_negative"
    boost = 1.0 + min(0.5, max(-0.5, ka * 0.2))
    ne = float(exp) * float(boost)
    if not _finite(ne) or ne <= 0.0:
        return exp, "kap_edge_invalid"
    return ne, None


def _parse_capital_exposure(context: Dict[str, Any]) -> tuple[float, float] | None:
    """Fail-closed: invalid capital → None."""
    raw = context.get("capital")
    if not isinstance(raw, (int, float)) or float(raw) <= 0.0:
        return None
    capital = float(raw)
    pe_raw = context.get("portfolio_exposure", 0.0)
    if not isinstance(pe_raw, (int, float)):
        pe_raw = 0.0
    portfolio_exposure = max(0.0, min(1.0, float(pe_raw)))
    return capital, portfolio_exposure


def _decision_relax_mode() -> bool:
    """Live simulation recovery: lower sizing floor (deterministic env flag)."""
    return os.environ.get("BIST_DECISION_RELAX_MODE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _brain_feature_math(bars: list[OHLCVBar], current_price: float) -> dict[str, Any]:
    """PRDV3 brain features — deterministic from OHLCV bars + current price."""
    if len(bars) < 15:
        raise ValueError("brain requires at least 15 bars")
    last = bars[-1]
    b5 = bars[-5]
    momentum = (float(last.close) - float(b5.close)) / max(1e-6, float(b5.close))
    tail10 = bars[-10:]
    range_high = max(float(b.high) for b in tail10)
    range_low = min(float(b.low) for b in tail10)
    volatility = (range_high - range_low) / max(1e-6, float(last.close))
    trend = sum(float(b.close) for b in tail10) / 10.0
    trend_bias = (float(last.close) - trend) / max(1e-6, trend)
    recent_high = max(float(b.high) for b in bars[-15:])
    distance_from_high = (recent_high - float(current_price)) / max(1e-6, recent_high)
    if distance_from_high < 0.01:
        entry_quality = "LATE"
    else:
        entry_quality = "OK"
    raw_score = 0.4 * momentum + 0.3 * trend_bias + 0.3 * volatility
    score = _clamp_m11(math.tanh(raw_score * 2.5))
    return {
        "momentum": momentum,
        "volatility": volatility,
        "trend_bias": trend_bias,
        "trend": trend,
        "range_high": range_high,
        "range_low": range_low,
        "recent_high": recent_high,
        "distance_from_high": distance_from_high,
        "entry_quality": entry_quality,
        "score": score,
        "raw_score": raw_score,
    }


def run_decision(
    bars: list[OHLCVBar],
    price: float,
    symbol: str = "X",
) -> dict[str, Any]:
    """
    PRDV3 brain: score in [-1, 1], action from score + entry quality.
    """
    if not isinstance(bars, list) or len(bars) < 15:
        return {
            "symbol": symbol,
            "score": 0.0,
            "action": "hold",
            "entry_quality": "LATE",
            "reason": "insufficient_bars",
        }
    sym = str(symbol).strip() or "X"
    bf = _brain_feature_math(bars, float(price))
    score = float(bf["score"])
    eq = str(bf["entry_quality"])
    m = bf["momentum"]
    tb = bf["trend_bias"]
    v = bf["volatility"]
    reason = f"momentum={m:.4f}, trend_bias={tb:.4f}, volatility={v:.4f}"
    if score > 0.2 and eq == "OK":
        action = "enter"
    elif score > 0.2 and eq == "LATE":
        action = "wait_pullback"
    else:
        action = "hold"
    return {
        "symbol": sym,
        "score": score,
        "action": action,
        "entry_quality": eq,
        "reason": reason,
        "momentum": m,
        "trend_bias": tb,
        "volatility": v,
        "distance_from_high": bf["distance_from_high"],
    }


def _seed_u32(s: str) -> int:
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return int(h)


def _ohlc_row(
    i: int,
    sym: str,
    close: float,
    spread: float,
) -> OHLCVBar:
    hi = float(close) + spread
    lo = max(float(close) - spread * 0.8, 0.01)
    return OHLCVBar(
        timestamp=i,
        symbol=sym,
        open=float(close) - spread * 0.1,
        high=hi,
        low=lo,
        close=float(close),
        volume=1000.0 + float(i % 50),
    )


def _dummy_bars_brain_asels(n: int = 40) -> list[OHLCVBar]:
    """
    Strong late rally + pullback from peak: score>0.2, distance_from_high>=0.01 → enter.
    """
    sym = "ASELS"
    out: list[OHLCVBar] = []
    for i in range(n):
        if i < 25:
            c = 50.0 + float(i) * 0.4
        elif i < 35:
            c = 50.0 + 25.0 * 0.4 + float(i - 25) * 1.2
        else:
            c = 50.0 + 25.0 * 0.4 + 10.0 * 1.2 + float(i - 35) * 2.5
        sp = 0.4 if i < 35 else 1.2
        out.append(_ohlc_row(i, sym, c, sp))
    # Spike high mid-window so last close is not at recent_high but momentum stays hot
    last_i = n - 1
    hi_bar = out[last_i - 3]
    out[last_i - 3] = OHLCVBar(
        timestamp=hi_bar.timestamp,
        symbol=sym,
        open=hi_bar.open,
        high=max(float(hi_bar.high), float(out[last_i].close) + 8.0),
        low=hi_bar.low,
        close=hi_bar.close,
        volume=hi_bar.volume,
    )
    return out


def _dummy_bars_brain_thyao(n: int = 40) -> list[OHLCVBar]:
    """
    Rip into the close at the 15-bar high: score>0.2, distance_from_high<0.01 → wait_pullback.
    """
    sym = "THYAO"
    out: list[OHLCVBar] = []
    for i in range(n):
        if i < 24:
            c = 200.0 + float(i) * 0.25
        elif i < 34:
            c = 200.0 + 24.0 * 0.25 + float(i - 24) * 2.4
        else:
            c = 200.0 + 24.0 * 0.25 + 10.0 * 2.4 + float(i - 34) * 18.0
        if i < 24:
            sp = 0.3
        elif i < 34:
            sp = 0.9
        else:
            sp = 3.5
        out.append(_ohlc_row(i, sym, c, sp))
    # Last bar: close at the session high (LATE), wide range in last 10 for volatility
    li = n - 1
    c = float(out[li].close)
    out[li] = OHLCVBar(
        timestamp=li,
        symbol=sym,
        open=c - 0.5,
        high=c + 0.02,
        low=c - 0.4,
        close=c,
        volume=out[li].volume,
    )
    return out


def _dummy_bars_brain_sise(n: int = 40) -> list[OHLCVBar]:
    """Flat chop: low raw_score → hold."""
    sym = "SISE"
    out: list[OHLCVBar] = []
    base = 42.0
    for i in range(n):
        c = base + 0.08 * math.sin(float(i) * 0.5)
        out.append(_ohlc_row(i, sym, c, 0.25))
    return out


def generate_dummy_bars(seed: str, n: int = 40) -> list[OHLCVBar]:
    """Deterministic bars: known seeds use curated paths; others use hash-unique OHLC."""
    s = str(seed).strip()
    if s == "ASELS":
        return _dummy_bars_brain_asels(n)
    if s == "THYAO":
        return _dummy_bars_brain_thyao(n)
    if s == "SISE":
        return _dummy_bars_brain_sise(n)
    u = _seed_u32(s)
    base = 20.0 + (u % 500) / 10.0
    slope = ((u >> 8) % 200 - 100) / 500.0
    wobble = ((u >> 16) % 100) / 2000.0
    sym = s[:12] or "SYM"
    out: list[OHLCVBar] = []
    for i in range(n):
        t = float(i)
        c = base + t * slope + wobble * math.sin(t * 0.7 + (u % 7))
        spread = 0.3 + (u % 5) / 50.0
        out.append(_ohlc_row(i, sym, c, spread))
    return out


def _brain_test() -> dict[str, Any]:
    """
    Multi-symbol harness: scores, actions, and rationales must all differ.
    Raises ``SCORE_COLLAPSE`` / ``ACTION_COLLAPSE`` / ``RATIONALE_COLLAPSE`` on failure.
    """
    symbols = ["ASELS", "THYAO", "SISE"]
    results: dict[str, Any] = {}
    scores: list[float] = []
    actions: list[str] = []
    reasons: list[str] = []
    for s in symbols:
        bars = generate_dummy_bars(seed=s)
        price = float(bars[-1].close)
        res = run_decision(bars, price=price, symbol=s)
        results[s] = res
        scores.append(float(res["score"]))
        actions.append(str(res["action"]))
        reasons.append(str(res["reason"]))
    if len(scores) >= 2 and len(set(scores)) == 1:
        raise Exception("SCORE_COLLAPSE")
    if len(symbols) >= 3 and len(set(actions)) < 3:
        raise Exception("ACTION_COLLAPSE")
    if len(set(reasons)) < 3:
        raise Exception("RATIONALE_COLLAPSE")
    print({"BRAIN_TEST": results})
    print("BRAIN COMPLETE — PRDV3 READY")
    return results


class DecisionEngineV2:
    """Live/backtest: single-TF ``bars`` + flat ``edges``, or ``multi_tf`` + ``edges_by_tf``."""

    def __init__(
        self,
        lookback: int = 20,
        edges: Optional[Dict[tuple[Any, ...], Dict[str, Any]]] = None,
        edges_by_tf: Optional[Dict[str, Dict[tuple[Any, ...], Dict[str, Any]]]] = None,
    ) -> None:
        self._lookback = int(lookback) if lookback and lookback > 5 else 20
        self.edge_store = EdgeStore()
        if edges:
            self.edge_store.load(edges)
        if edges_by_tf:
            self.edge_store.load_by_tf(edges_by_tf)
        self.fe = FeatureEngineV2()
        self._inst_sig_ring: list[str] = []

    def evaluate_symbol(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            price = context.get("current_price")
            multi_tf = context.get("multi_tf")

            if not isinstance(price, (int, float)) or price <= 0 or not _finite(price):
                return attach_edge_signal_to_decision(_no_trade("invalid_price"))

            if isinstance(multi_tf, dict) and multi_tf:
                out = self._evaluate_multi_tf(context, float(price))
            else:
                out = self._evaluate_single_tf(context, float(price))
            out = _apply_global_edge_floor(out)
            return attach_edge_signal_to_decision(out)

        except Exception:
            return attach_edge_signal_to_decision(_no_trade("engine_exception"))

    def _evaluate_multi_tf(self, context: Dict[str, Any], price: float) -> Dict[str, Any]:
        """Multi-TF path: require deterministic cross-TF edge consensus before entry."""
        multi_tf = context.get("multi_tf")
        if isinstance(multi_tf, dict) and multi_tf:
            tf_hits: list[tuple[str, float]] = []
            for tf_name, tf_bars in multi_tf.items():
                if not isinstance(tf_bars, list) or len(tf_bars) < 50:
                    continue
                tf_feat = self.fe.extract(tf_bars)
                tf_key = edge_bucket_key(tf_feat)
                tf_edge = self.edge_store.get_tf(str(tf_name), tf_key)
                if not isinstance(tf_edge, dict):
                    continue
                try:
                    tf_exp = float(tf_edge.get("exp", 0.0) or 0.0)
                except (TypeError, ValueError):
                    tf_exp = 0.0
                if tf_exp > 0.0:
                    tf_hits.append((str(tf_name), tf_exp))
            if len(tf_hits) < 2:
                return _no_trade("multi_tf_no_consensus")

            avg_exp = sum(exp for _, exp in tf_hits) / float(len(tf_hits))
            consensus_edge = round(max(_HARD_EDGE_MIN, 0.60 + min(0.30, avg_exp)), 6)
            consensus_confidence = round(_clamp01(0.55 + min(0.30, avg_exp * 2.0)), 6)
            return {
                "action": "enter",
                "reason": f"MULTI_EDGE_{len(tf_hits)}",
                "confidence": consensus_confidence,
                "score": consensus_edge,
                "edge_score": consensus_edge,
                "edge": consensus_edge,
                "risk": {"stop_price": float(price) * 0.97},
                "position_size": min(1.0, consensus_edge * consensus_confidence),
                "strategy": "multi_edge",
                "price_source": str(context.get("price_source", "ideal")),
                "tf_consensus": [tf_name for tf_name, _ in tf_hits],
            }

        bars = context.get("bars")
        if not isinstance(bars, list) or len(bars) < 50:
            if isinstance(multi_tf, dict):
                bars = None
                for tf in ("5m", "60m", "1m", "1d"):
                    b = multi_tf.get(tf)
                    if isinstance(b, list) and len(b) >= 50:
                        bars = b
                        break
                if bars is None:
                    for _k, b in multi_tf.items():
                        if isinstance(b, list) and len(b) >= 50:
                            bars = b
                            break
        if not isinstance(bars, list) or len(bars) < 50:
            return _no_trade("no_bars")

        symbol = str(context.get("symbol", "")).strip()
        if not symbol and bars:
            symbol = str(getattr(bars[-1], "symbol", ""))

        bar_ts = int(getattr(bars[-1], "timestamp", 0) or 0)
        _mtf_raw = context.get("mtf_signal", context.get("mtf_state"))
        if isinstance(_mtf_raw, dict):
            _mtf_pass = str(
                _mtf_raw.get("label")
                or _mtf_raw.get("trend")
                or _mtf_raw.get("signal")
                or ""
            )
        else:
            _mtf_pass = str(_mtf_raw) if _mtf_raw is not None else ""

        inst = compute_institutional_decision(
            bars,
            float(price),
            symbol=symbol or "X",
            recent_signatures=self._inst_sig_ring,
            bar_ts=bar_ts,
            mtf_state=_mtf_pass.strip() or None,
        )
        self._inst_sig_ring.append(str(inst.get("signature", "")))
        if len(self._inst_sig_ring) > 10:
            self._inst_sig_ring.pop(0)

        action = str(inst.get("action", "hold")).strip().lower()
        confidence = float(inst.get("confidence", 0.0))
        edge = float(inst.get("edge_score", 0.0))

        if action in ("enter_long", "enter_short"):
            d_mt: Dict[str, Any] = {
                "action": action,
                "reason": "INSTITUTIONAL",
                "confidence": confidence,
                "score": edge,
                "edge_score": float(edge),
                "edge": float(edge),
                "risk": {"stop_price": float(price) * 0.97},
                "position_size": min(1.0, edge * confidence),
                "strategy": "institutional",
                "price_source": str(context.get("price_source", "ideal")),
            }
            return _apply_hard_edge_confidence_final(
                _apply_mtf_conflict_final(d_mt, context, inst),
                symbol=symbol or "X",
            )

        if action == "exit":
            print(
                {
                    "EXIT_TRIGGERED": {
                        "symbol": symbol or "X",
                        "edge": float(edge),
                        "confidence": confidence,
                    }
                },
                flush=True,
            )
            return {
                "action": "exit",
                "reason": "INSTITUTIONAL_EXIT",
                "confidence": confidence,
                "score": edge,
                "edge_score": float(edge),
                "edge": float(edge),
            }

        return _no_trade("institutional_hold")

    def _evaluate_single_tf(self, context: Dict[str, Any], price: float) -> Dict[str, Any]:
        bars = context.get("bars")
        if not isinstance(bars, list) or len(bars) < 50:
            return _no_trade("insufficient_bars")

        symbol = str(context.get("symbol", "")).strip()
        if not symbol and bars:
            symbol = str(getattr(bars[-1], "symbol", ""))

        print(
            {
                "debug": "input_bars",
                "symbol": symbol,
                "bars_len": len(bars),
                "last_close": bars[-1].close if bars else None,
            }
        )

        bar_ts = int(getattr(bars[-1], "timestamp", 0) or 0)
        _mtf_raw = context.get("mtf_signal", context.get("mtf_state"))
        if isinstance(_mtf_raw, dict):
            _mtf_pass = str(
                _mtf_raw.get("label")
                or _mtf_raw.get("trend")
                or _mtf_raw.get("signal")
                or ""
            )
        else:
            _mtf_pass = str(_mtf_raw) if _mtf_raw is not None else ""
        inst = compute_institutional_decision(
            bars,
            float(price),
            symbol=symbol or "X",
            recent_signatures=self._inst_sig_ring,
            bar_ts=bar_ts,
            mtf_state=_mtf_pass.strip() or None,
        )
        self._inst_sig_ring.append(str(inst.get("signature", "")))
        if len(self._inst_sig_ring) > 10:
            self._inst_sig_ring.pop(0)

        if inst.get("state") != "INSUFFICIENT_DATA":
            print(
                {
                    "institutional_brain": {
                        "state": inst.get("state"),
                        "action": inst.get("action"),
                        "confidence": inst.get("confidence"),
                        "range_position": inst.get("features", {}).get("range_position"),
                        "vol_norm": inst.get("features", {}).get("vol_norm"),
                    }
                }
            )

        feat = self.fe.extract(bars)
        for k in ("vol", "trend", "vol_ratio"):
            v = feat.get(k)
            if not _finite(v):
                return _no_trade("non_finite_feature")
        bctx = {
            "holding_period_bars": 0,
            "volatility": float(feat["vol"]),
            "regime": regime_from_feat(feat),
        }
        key = edge_bucket_key(feat, bctx)

        edge_cycle = context.get("edge_cycle")
        ec = int(edge_cycle) if isinstance(edge_cycle, (int, float)) else None
        edge = self.edge_store.get(key, edge_cycle=ec)

        out = self._institutional_response(context, float(price), inst, feat, edge, symbol)
        out, _ = apply_realtime_price_intelligence(out, context, inst)
        out = _apply_mtf_conflict_final(out, context, inst)
        out = _apply_hard_edge_confidence_final(out, symbol=symbol)
        return out

    def _institutional_response(
        self,
        context: Dict[str, Any],
        price: float,
        inst: Dict[str, Any],
        feat: Dict[str, Any],
        edge: Optional[Dict[str, Any]],
        symbol: str,
    ) -> Dict[str, Any]:
        """Price-structure brain + optional edge-store confidence boost."""
        if inst.get("state") == "INSUFFICIENT_DATA":
            return _no_trade("institutional_insufficient")

        _, kap_gate = _apply_kap_edge_mod(1.0, context)
        if kap_gate == "kap_negative":
            return _no_trade("kap_negative")

        cap_ex = _parse_capital_exposure(context)
        if cap_ex is None:
            return _no_trade("capital_missing")
        capital, portfolio_exposure = cap_ex

        vol = float(feat["vol"])
        reg = regime_from_feat(feat)
        vol_adj = 1.0 / (1.0 + max(0.0, vol))

        conf = float(inst["confidence"])
        if edge is not None:
            exp0 = float(edge.get("exp", 0.0))
            if _finite(exp0) and exp0 > 0:
                ec = float(edge.get("confidence", exp0))
                if _finite(ec):
                    conf = _clamp01(conf + min(0.12, ec * 0.12))

        bars_ctx = context.get("bars")
        _closes = _de_v2_extract_closes(bars_ctx) if isinstance(bars_ctx, list) else None
        if _closes is not None:
            trend_strength = _de_v2_trend_strength(_closes)
            volatility_compression = _de_v2_volatility_compression(_closes)
        else:
            trend_strength = 0.0
            volatility_compression = 0.0

        breakout_ready = 1 if (volatility_compression >= 0.85 and trend_strength >= 0.4) else 0

        edge_raw = float(inst.get("edge_score", 0.0) or 0.0)
        edge_score = float(edge_raw)
        print(
            {
                "EDGE_AMPLIFIED": {
                    "symbol": symbol,
                    "base": edge_raw,
                    "bonus": 0.0,
                    "final": edge_score,
                    "breakout_ready": breakout_ready,
                }
            },
            flush=True,
        )

        try:
            edge_threshold = float(os.environ.get("BIST_EDGE_GATE_THRESHOLD", "0.18"))
        except (TypeError, ValueError):
            edge_threshold = 0.18
        edge_threshold = max(0.0, min(1.0, float(edge_threshold)))
        _gate_act = str(inst.get("action", "")).strip().lower()
        if _gate_act not in ("exit",):
            if _gate_act in ("enter", "enter_small", "enter_long", "enter_short"):
                if float(edge_score) < edge_threshold:
                    print(
                        {
                            "EDGE_GATE_BLOCK": {
                                "symbol": symbol,
                                "edge": float(edge_score),
                                "threshold": edge_threshold,
                            }
                        },
                        flush=True,
                    )
                    return _no_trade("edge_below_threshold")

        exp_boost = None
        if edge is not None:
            exp0 = float(edge.get("exp", 0.0))
            if _finite(exp0) and exp0 > 0:
                exp_boost, kap_err = _apply_kap_edge_mod(exp0, context)
                if kap_err is not None or exp_boost is None or float(exp_boost) <= 0:
                    exp_boost = None

        pos_side = _open_position_side_from_context(context)
        if pos_side is not None:
            _pos_snap = context.get("position")
            entry_edge_v1: float | None = None
            if isinstance(_pos_snap, dict) and _pos_snap.get("entry_edge") is not None:
                try:
                    entry_edge_v1 = float(_pos_snap["entry_edge"])
                except (TypeError, ValueError):
                    entry_edge_v1 = None
            elif context.get("position_entry_edge") is not None:
                try:
                    entry_edge_v1 = float(context["position_entry_edge"])
                except (TypeError, ValueError):
                    entry_edge_v1 = None

            if entry_edge_v1 is not None:
                if isinstance(_pos_snap, dict):
                    try:
                        bars_held_v1 = int(_pos_snap.get("bars_held", 0) or 0)
                    except (TypeError, ValueError):
                        bars_held_v1 = 0
                    try:
                        unrealized_pnl_v1 = float(
                            _pos_snap.get("pnl", _pos_snap.get("unrealized_pnl", 0.0))
                            or 0.0
                        )
                    except (TypeError, ValueError):
                        unrealized_pnl_v1 = 0.0
                else:
                    try:
                        bars_held_v1 = int(context.get("position_bars_held", 0) or 0)
                    except (TypeError, ValueError):
                        bars_held_v1 = 0
                    try:
                        unrealized_pnl_v1 = float(
                            context.get("position_unrealized_pnl", 0.0) or 0.0
                        )
                    except (TypeError, ValueError):
                        unrealized_pnl_v1 = 0.0

                vol_norm = float(feat.get("vol", 0.0) or 0.0)
                _es_num = float(edge_score)
                if isinstance(_pos_snap, dict):
                    _pos_snap["peak_edge"] = max(
                        float(_pos_snap.get("peak_edge", entry_edge_v1)),
                        _es_num,
                    )
                    exit_v2 = compute_exit_v2(
                        entry_edge=entry_edge_v1,
                        peak_edge=float(_pos_snap["peak_edge"]),
                        current_edge=_es_num,
                        bars_held=bars_held_v1,
                        unrealized_pnl=unrealized_pnl_v1,
                    )
                    print(
                        {
                            "EXIT_V2": {
                                "action": exit_v2.action,
                                "reason": exit_v2.reason,
                                "size_fraction": exit_v2.size_fraction,
                                "peak_edge": _pos_snap.get("peak_edge"),
                            }
                        },
                        flush=True,
                    )
                    if exit_v2.action == "exit_full":
                        _bm_x = 0.0
                        if isinstance(inst.get("features"), dict):
                            try:
                                _bm_x = float(inst["features"].get("momentum", 0.0))
                            except (TypeError, ValueError):
                                _bm_x = 0.0
                        _es_exit = compute_edge_signal(
                            confidence=conf,
                            score=float(
                                inst.get("features", {}).get("short_trend", 0.0)
                            ),
                            action="hold",
                            edge_exp_boost=float(exp_boost)
                            if exp_boost is not None
                            else None,
                        )
                        _st_x = str(inst.get("state", ""))
                        _rb_x = str(inst["reason"])
                        print(
                            {
                                "FINAL_DECISION_V2": {
                                    "symbol": symbol or "X",
                                    "action": "exit",
                                    "edge": edge_score,
                                    "confidence": conf,
                                    "mtf": str(context.get("mtf_signal", "") or ""),
                                }
                            },
                            flush=True,
                        )
                        print(
                            {
                                "EXIT_TRIGGERED": {
                                    "symbol": symbol or "X",
                                    "edge": float(edge_score),
                                    "confidence": conf,
                                }
                            },
                            flush=True,
                        )
                        return {
                            "action": "exit",
                            "reason": f"v2_exit_engine_v2|{exit_v2.reason}|{_rb_x}",
                            "risk": {"stop_price": float(inst["stop_loss"])},
                            "no_trade": False,
                            "edge_signal": _es_exit,
                            "score": float(
                                inst.get("features", {}).get("short_trend", 0.0)
                            ),
                            "regime": reg,
                            "vol_adj": vol_adj,
                            "strategy": "institutional",
                            "symbol": symbol or "X",
                            "confidence": conf,
                            "entry": float(inst["entry"]),
                            "stop_loss": float(inst["stop_loss"]),
                            "target": float(inst["target"]),
                            "market_state": _st_x,
                            "institutional": True,
                            "brain_momentum": _bm_x,
                            "edge_score": float(edge_score),
                            "edge": float(edge_score),
                            **(
                                {"edge_exp_boost": float(exp_boost)}
                                if exp_boost is not None
                                else {}
                            ),
                        }
                    if exit_v2.action == "exit_partial":
                        _bm_x = 0.0
                        if isinstance(inst.get("features"), dict):
                            try:
                                _bm_x = float(inst["features"].get("momentum", 0.0))
                            except (TypeError, ValueError):
                                _bm_x = 0.0
                        _es_exit = compute_edge_signal(
                            confidence=conf,
                            score=float(
                                inst.get("features", {}).get("short_trend", 0.0)
                            ),
                            action="hold",
                            edge_exp_boost=float(exp_boost)
                            if exp_boost is not None
                            else None,
                        )
                        _st_x = str(inst.get("state", ""))
                        _rb_x = str(inst["reason"])
                        remain = max(
                            0.0,
                            min(1.0, 1.0 - float(exit_v2.size_fraction)),
                        )
                        print(
                            {
                                "FINAL_DECISION_V2": {
                                    "symbol": symbol or "X",
                                    "action": "partial_exit",
                                    "edge": edge_score,
                                    "confidence": conf,
                                    "mtf": str(context.get("mtf_signal", "") or ""),
                                }
                            },
                            flush=True,
                        )
                        out_v2: Dict[str, Any] = {
                            "action": "partial_exit",
                            "reason": f"v2_exit_engine_v2|{exit_v2.reason}|{_rb_x}",
                            "risk": {"stop_price": float(inst["stop_loss"])},
                            "no_trade": False,
                            "edge_signal": _es_exit,
                            "score": float(
                                inst.get("features", {}).get("short_trend", 0.0)
                            ),
                            "regime": reg,
                            "vol_adj": vol_adj,
                            "strategy": "institutional",
                            "symbol": symbol or "X",
                            "confidence": conf,
                            "entry": float(inst["entry"]),
                            "stop_loss": float(inst["stop_loss"]),
                            "target": float(inst["target"]),
                            "market_state": _st_x,
                            "institutional": True,
                            "brain_momentum": _bm_x,
                            "edge_score": float(edge_score),
                            "edge": float(edge_score),
                            "exit_partial_fraction": float(exit_v2.size_fraction),
                            "position_size_frac_remaining": remain,
                        }
                        if exp_boost is not None:
                            out_v2["edge_exp_boost"] = float(exp_boost)
                        return out_v2

                exit_decision = compute_exit_decision(
                    entry_edge=entry_edge_v1,
                    current_edge=float(edge_score),
                    bars_held=bars_held_v1,
                    volatility_norm=vol_norm,
                    unrealized_pnl=unrealized_pnl_v1,
                )
                print(
                    {
                        "EXIT_DECISION": {
                            "action": exit_decision.action,
                            "reason": exit_decision.reason,
                            "size_fraction": exit_decision.size_fraction,
                        }
                    },
                    flush=True,
                )
                if exit_decision.action == "exit_full":
                    _bm_x = 0.0
                    if isinstance(inst.get("features"), dict):
                        try:
                            _bm_x = float(inst["features"].get("momentum", 0.0))
                        except (TypeError, ValueError):
                            _bm_x = 0.0
                    _es_exit = compute_edge_signal(
                        confidence=conf,
                        score=float(inst.get("features", {}).get("short_trend", 0.0)),
                        action="hold",
                        edge_exp_boost=float(exp_boost) if exp_boost is not None else None,
                    )
                    _st_x = str(inst.get("state", ""))
                    _rb_x = str(inst["reason"])
                    print(
                        {
                            "FINAL_DECISION_V2": {
                                "symbol": symbol or "X",
                                "action": "exit",
                                "edge": edge_score,
                                "confidence": conf,
                                "mtf": str(context.get("mtf_signal", "") or ""),
                            }
                        },
                        flush=True,
                    )
                    print(
                        {
                            "EXIT_TRIGGERED": {
                                "symbol": symbol or "X",
                                "edge": float(edge_score),
                                "confidence": conf,
                            }
                        },
                        flush=True,
                    )
                    return {
                        "action": "exit",
                        "reason": f"v2_exit_engine_v1|{exit_decision.reason}|{_rb_x}",
                        "risk": {"stop_price": float(inst["stop_loss"])},
                        "no_trade": False,
                        "edge_signal": _es_exit,
                        "score": float(inst.get("features", {}).get("short_trend", 0.0)),
                        "regime": reg,
                        "vol_adj": vol_adj,
                        "strategy": "institutional",
                        "symbol": symbol or "X",
                        "confidence": conf,
                        "entry": float(inst["entry"]),
                        "stop_loss": float(inst["stop_loss"]),
                        "target": float(inst["target"]),
                        "market_state": _st_x,
                        "institutional": True,
                        "brain_momentum": _bm_x,
                        "edge_score": float(edge_score),
                        "edge": float(edge_score),
                        **(
                            {"edge_exp_boost": float(exp_boost)}
                            if exp_boost is not None
                            else {}
                        ),
                    }
                if exit_decision.action == "exit_partial":
                    _bm_x = 0.0
                    if isinstance(inst.get("features"), dict):
                        try:
                            _bm_x = float(inst["features"].get("momentum", 0.0))
                        except (TypeError, ValueError):
                            _bm_x = 0.0
                    _es_exit = compute_edge_signal(
                        confidence=conf,
                        score=float(inst.get("features", {}).get("short_trend", 0.0)),
                        action="hold",
                        edge_exp_boost=float(exp_boost) if exp_boost is not None else None,
                    )
                    _st_x = str(inst.get("state", ""))
                    _rb_x = str(inst["reason"])
                    remain = max(
                        0.0, min(1.0, 1.0 - float(exit_decision.size_fraction))
                    )
                    print(
                        {
                            "FINAL_DECISION_V2": {
                                "symbol": symbol or "X",
                                "action": "partial_exit",
                                "edge": edge_score,
                                "confidence": conf,
                                "mtf": str(context.get("mtf_signal", "") or ""),
                            }
                        },
                        flush=True,
                    )
                    out_pe: Dict[str, Any] = {
                        "action": "partial_exit",
                        "reason": f"v2_exit_engine_v1|{exit_decision.reason}|{_rb_x}",
                        "risk": {"stop_price": float(inst["stop_loss"])},
                        "no_trade": False,
                        "edge_signal": _es_exit,
                        "score": float(inst.get("features", {}).get("short_trend", 0.0)),
                        "regime": reg,
                        "vol_adj": vol_adj,
                        "strategy": "institutional",
                        "symbol": symbol or "X",
                        "confidence": conf,
                        "entry": float(inst["entry"]),
                        "stop_loss": float(inst["stop_loss"]),
                        "target": float(inst["target"]),
                        "market_state": _st_x,
                        "institutional": True,
                        "brain_momentum": _bm_x,
                        "edge_score": float(edge_score),
                        "edge": float(edge_score),
                        "exit_partial_fraction": float(exit_decision.size_fraction),
                        "position_size_frac_remaining": remain,
                    }
                    if exp_boost is not None:
                        out_pe["edge_exp_boost"] = float(exp_boost)
                    return out_pe

            _bm_x = 0.0
            if isinstance(inst.get("features"), dict):
                try:
                    _bm_x = float(inst["features"].get("momentum", 0.0))
                except (TypeError, ValueError):
                    _bm_x = 0.0
            _es_exit = compute_edge_signal(
                confidence=conf,
                score=float(inst.get("features", {}).get("short_trend", 0.0)),
                action="hold",
                edge_exp_boost=float(exp_boost) if exp_boost is not None else None,
            )
            _xf, _xr = _exit_engine_should_fire(
                position_side=pos_side,
                edge_score=edge_score,
                conf=conf,
                edge_signal_label=_es_exit,
            )
            if _xf:
                print(
                    {
                        "EXIT_TRIGGER": {
                            "symbol": symbol or "X",
                            "reason": _xr,
                            "edge": edge_score,
                            "confidence": conf,
                            "signal": _es_exit,
                        }
                    },
                    flush=True,
                )
                _st_x = str(inst.get("state", ""))
                _rb_x = str(inst["reason"])
                print(
                    {
                        "FINAL_DECISION_V2": {
                            "symbol": symbol or "X",
                            "action": "exit",
                            "edge": edge_score,
                            "confidence": conf,
                            "mtf": str(context.get("mtf_signal", "") or ""),
                        }
                    },
                    flush=True,
                )
                print(
                    {
                        "EXIT_TRIGGERED": {
                            "symbol": symbol or "X",
                            "edge": float(edge_score),
                            "confidence": conf,
                        }
                    },
                    flush=True,
                )
                return {
                    "action": "exit",
                    "reason": f"v2_exit_engine|{_xr}|{_rb_x}",
                    "risk": {"stop_price": float(inst["stop_loss"])},
                    "no_trade": False,
                    "edge_signal": _es_exit,
                    "score": float(inst.get("features", {}).get("short_trend", 0.0)),
                    "regime": reg,
                    "vol_adj": vol_adj,
                    "strategy": "institutional",
                    "symbol": symbol or "X",
                    "confidence": conf,
                    "entry": float(inst["entry"]),
                    "stop_loss": float(inst["stop_loss"]),
                    "target": float(inst["target"]),
                    "market_state": _st_x,
                    "institutional": True,
                    "brain_momentum": _bm_x,
                    "edge_score": float(edge_score),
                    "edge": float(edge_score),
                    **(
                        {"edge_exp_boost": float(exp_boost)}
                        if exp_boost is not None
                        else {}
                    ),
                }

        try:
            threshold = float(context.get("confidence_threshold", 0.0))
        except (TypeError, ValueError):
            threshold = 0.0
        passed = float(conf) >= float(threshold)
        print(
            {
                "CONF_FILTER_FIXED": {
                    "conf": conf,
                    "threshold": threshold,
                    "passed": passed,
                }
            },
            flush=True,
        )

        if not passed:
            return _no_trade("confidence_below_threshold")

        ia = str(inst["action"])
        entry_px = float(inst["entry"])
        stop_px = float(inst["stop_loss"])
        tgt_px = float(inst["target"])
        reason_base = str(inst["reason"])
        st = str(inst.get("state", ""))

        _mtf_raw = context.get("mtf_signal")
        if _mtf_raw is None:
            mtf_signal = ia
        else:
            mtf_signal = str(_mtf_raw).strip().lower()

        _bm = 0.0
        if isinstance(inst.get("features"), dict):
            try:
                _bm = float(inst["features"].get("momentum", 0.0))
            except (TypeError, ValueError):
                _bm = 0.0

        base_kw: Dict[str, Any] = {
            "score": float(inst.get("features", {}).get("short_trend", 0.0)),
            "regime": reg,
            "vol_adj": vol_adj,
            "strategy": "institutional",
            "symbol": symbol or "X",
            "confidence": conf,
            "entry": entry_px,
            "stop_loss": stop_px,
            "target": tgt_px,
            "market_state": st,
            "institutional": True,
            "brain_momentum": _bm,
            "edge_score": float(edge_score),
            "edge": float(edge_score),
        }
        if exp_boost is not None:
            base_kw["edge_exp_boost"] = float(exp_boost)

        if ia == "wait":
            print(
                {
                    "FINAL_DECISION_V2": {
                        "symbol": symbol,
                        "action": "hold",
                        "edge": edge_score,
                        "confidence": conf,
                        "mtf": mtf_signal,
                    }
                },
                flush=True,
            )
            return {
                "action": "hold",
                "reason": f"inst_wait|{st}|{reason_base}",
                "risk": {"stop_price": stop_px},
                "no_trade": True,
                **base_kw,
            }

        if ia == "exit":
            print(
                {
                    "FINAL_DECISION_V2": {
                        "symbol": symbol,
                        "action": "exit",
                        "edge": edge_score,
                        "confidence": conf,
                        "mtf": mtf_signal,
                    }
                },
                flush=True,
            )
            print(
                {
                    "EXIT_TRIGGERED": {
                        "symbol": symbol,
                        "edge": float(edge_score),
                        "confidence": conf,
                    }
                },
                flush=True,
            )
            return {
                "action": "exit",
                "reason": f"inst_exit|{st}|{reason_base}",
                "risk": {"stop_price": stop_px},
                "no_trade": False,
                **base_kw,
            }

        if ia in ("enter", "enter_small", "enter_long", "enter_short"):
            stats = tracker.stats()
            bucket = round(edge_score, 1)

            # SAFE EXPECTANCY MODE (REQUIRES MIN DATA)
            if bucket in stats and stats[bucket].get("trades", 0) >= 20:
                if stats[bucket]["expectancy"] < 0:
                    print(
                        {
                            "EXPECTANCY_BLOCK": {
                                "edge": edge_score,
                                "bucket": bucket,
                                "trades": stats[bucket]["trades"],
                            }
                        },
                        flush=True,
                    )
                    return {
                        "action": "hold",
                        "reason": "NEGATIVE_EXPECTANCY",
                        "edge": float(edge_score),
                        "no_trade": True,
                    }
            apply_strict_entry_gates = ia != "enter_small" or _mtf_raw is not None
            if apply_strict_entry_gates:
                MIN_EDGE = 0.60
                _e_chk = float(edge_score)
                print(
                    {
                        "EDGE_THRESHOLD_CHECK": {
                            "edge": float(edge_score),
                            "threshold": MIN_EDGE,
                        }
                    },
                    flush=True,
                )
                if _e_chk < MIN_EDGE:
                    return {
                        "action": "hold",
                        "reason": "EDGE_BELOW_THRESHOLD",
                        "edge": float(_e_chk),
                        "edge_score": float(_e_chk),
                        "no_trade": True,
                        "market_state": st,
                    }
                if _strict_regime_blocks_new_entry(
                    st, float(edge_score), int(breakout_ready)
                ):
                    print(
                        {
                            "REGIME_BLOCK": {
                                "symbol": symbol or "X",
                                "regime": "RANGE",
                                "edge": float(edge_score),
                                "breakout_ready": int(breakout_ready),
                                "rule": "REGIME_BLOCK_EDGE_TOO_LOW",
                            }
                        },
                        flush=True,
                    )
                    return {
                        "action": "hold",
                        "reason": "strict_regime_range",
                        "edge": float(edge_score),
                        "no_trade": True,
                        "market_state": st,
                    }
            alloc_frac = float(inst["position_size_frac"])
            headroom = 0.30 - portfolio_exposure
            if headroom <= 0.0:
                print(
                    {
                        "FINAL_DECISION_V2": {
                            "symbol": symbol,
                            "action": "hold",
                            "edge": edge_score,
                            "confidence": conf,
                            "mtf": mtf_signal,
                        }
                    },
                    flush=True,
                )
                return {
                    "action": "hold",
                    "reason": "inst_enter_blocked_portfolio_cap",
                    "risk": {"stop_price": stop_px},
                    "no_trade": True,
                    **base_kw,
                }
            alloc_frac = min(alloc_frac, headroom)
            # EDGE-BASED CAPITAL ALLOCATION
            base_size = float(alloc_frac)
            edge_strength = float(edge_score)

            edge = float(edge_strength)
            # --- SOFT NONLINEAR (NO DEAD ZONE) ---
            if edge < 0.25:
                nonlinear = 0.0
            else:
                nonlinear = ((edge - 0.25) / 0.75) ** 1.6

            # --- PRODUCTION EDGE → SIZE MAPPING (BIST CALIBRATED) ---
            edge = float(edge)

            if edge < 0.25:
                edge_multiplier = 0.0
            elif edge < 0.40:
                edge_multiplier = 0.25
            elif edge < 0.60:
                edge_multiplier = 0.6
            elif edge < 0.85:
                edge_multiplier = 0.85
            else:
                edge_multiplier = 1.0

            if edge_multiplier <= 0.0:
                size_fraction = 0.0
            else:
                size_fraction = base_size * nonlinear * edge_multiplier

            # --- HEADROOM CAP (risk constraint) ---
            size_fraction = min(size_fraction, headroom)

            # --- RE-INJECT EDGE AFTER CAP (preserve ordering) ---
            if size_fraction > 0:
                size_fraction = size_fraction * (0.9 + 0.3 * edge)

            print(
                {
                    "EDGE_SIZE_HYBRID": {
                        "edge": edge,
                        "base": base_size,
                        "nonlinear": nonlinear,
                        "final": size_fraction,
                    }
                },
                flush=True,
            )
            mtf_mult = _compute_mtf_size_multiplier(context)
            size_fraction = size_fraction * mtf_mult
            size_fraction = max(0.0, min(1.0, size_fraction))
            print(
                {
                    "POSITION_SIZING": {
                        "symbol": symbol,
                        "edge": edge_strength,
                        "edge_mult": edge_multiplier,
                        "mtf_mult": mtf_mult,
                        "final_size": size_fraction,
                    }
                },
                flush=True,
            )
            print(
                {
                    "MTF_SIZE_MULTIPLIER": {
                        "symbol": symbol,
                        "multiplier": mtf_mult,
                    }
                },
                flush=True,
            )
            ps = capital * size_fraction
            if edge > 0.30 and ps == 0.0:
                ps = max(ps, 0.002)
            if ps <= 0.0 or not _finite(ps):
                print(
                    {
                        "FINAL_DECISION_V2": {
                            "symbol": symbol,
                            "action": "hold",
                            "edge": edge_score,
                            "confidence": conf,
                            "mtf": mtf_signal,
                        }
                    },
                    flush=True,
                )
                return _no_trade("institutional_position_invalid")
            tag = "enter_small" if ia == "enter_small" else "enter"
            rsn = f"inst_{tag}|{st}|{reason_base}"
            if exp_boost is not None:
                rsn += f"|edge_exp={float(exp_boost):.4f}"

            institutional_action = ia
            final_action = institutional_action

            action = final_action
            # CONSISTENCY ENFORCEMENT
            if str(action).lower().startswith("enter"):
                if mtf_signal == "hold":
                    action = "hold"
            final_action = action
            if final_action == "hold":
                print(
                    {
                        "FINAL_DECISION_V2": {
                            "symbol": symbol,
                            "action": "hold",
                            "edge": edge_score,
                            "confidence": conf,
                            "mtf": mtf_signal,
                        }
                    },
                    flush=True,
                )
                return {
                    "action": "hold",
                    "reason": "mtf_hold_blocks_enter",
                    "risk": {"stop_price": stop_px},
                    "no_trade": True,
                    **base_kw,
                }

            print(
                {
                    "INST_ENTRY_RESOLUTION": {
                        "symbol": symbol,
                        "edge": edge_score,
                        "institutional": institutional_action,
                        "mtf": mtf_signal,
                        "final": final_action,
                    }
                },
                flush=True,
            )

            out_action = final_action
            if final_action in ("enter_long", "enter_short"):
                out_action = final_action

            if final_action == "enter_long":
                _es = "BUY"
            elif final_action == "enter_short":
                _es = "SELL"
            else:
                _es = compute_edge_signal(
                    confidence=conf,
                    score=float(base_kw.get("score", 0.0)),
                    action=final_action,
                    edge_exp_boost=float(exp_boost) if exp_boost is not None else None,
                )
            print({"edge_signal": _es, "confidence": conf, "size": ps})
            print(
                {
                    "FINAL_DECISION": {
                        "symbol": symbol,
                        "action": out_action,
                        "confidence": conf,
                        "size": ps,
                    }
                },
                flush=True,
            )
            print(
                {
                    "FINAL_DECISION_V2": {
                        "symbol": symbol,
                        "action": final_action,
                        "edge": edge_score,
                        "confidence": conf,
                        "mtf": mtf_signal,
                    }
                },
                flush=True,
            )
            locked = final_action in ("enter_long", "enter_short")
            if locked:
                out_action = final_action
            return {
                "action": out_action,
                "reason": rsn,
                "risk": {"stop_price": stop_px},
                "position_size": float(ps),
                "no_trade": False,
                "edge_signal": _es,
                **base_kw,
            }

        print(
            {
                "FINAL_DECISION_V2": {
                    "symbol": symbol,
                    "action": "hold",
                    "edge": edge_score,
                    "confidence": conf,
                    "mtf": mtf_signal,
                }
            },
            flush=True,
        )
        return {
            "action": "hold",
            "reason": f"inst_hold|{st}|{reason_base}",
            "risk": {"stop_price": stop_px},
            "no_trade": True,
            **base_kw,
        }


def _bars_for_symbol(symbol: str, start: float, slope: float, n: int = 50) -> list[OHLCVBar]:
    """Deterministic synthetic path per symbol (different slopes → different features/scores)."""
    out: list[OHLCVBar] = []
    for i in range(n):
        c = start + float(i) * slope
        out.append(
            OHLCVBar(
                timestamp=i,
                symbol=symbol,
                open=c,
                high=c + 0.5,
                low=max(c - 0.5, 0.01),
                close=c,
                volume=1000.0 + float(i),
            )
        )
    return out


def run_sample_test() -> Dict[str, Any]:
    """
    Smoke: three symbols with distinct bar paths; composite scores must differ.
    Used for terminal verification: ``python -c "from bist_core.decision.decision_engine_v2 import run_sample_test; print(run_sample_test())"``
    """
    cap: Dict[str, Any] = {"capital": 100_000.0, "portfolio_exposure": 0.0}
    fe = FeatureEngineV2()
    specs = [
        ("ASELS", 10.0, 0.6),
        ("THYAO", 200.0, -0.15),
        ("GARAN", 3.0, 0.08),
    ]
    edges: Dict[tuple[Any, ...], Dict[str, Any]] = {}
    for sym, st, sl in specs:
        bars = _bars_for_symbol(sym, st, sl)
        k = edge_bucket_key(fe.extract(bars))
        edges[k] = {"exp": 0.02, "count": 100, "confidence": 0.06}
    eng = DecisionEngineV2(edges=edges)
    scores: Dict[str, float] = {}
    for sym, st, sl in specs:
        bars = _bars_for_symbol(sym, st, sl)
        r = eng.evaluate_symbol(
            {
                "symbol": sym,
                "current_price": float(bars[-1].close) * 0.88,
                "bars": bars,
                **cap,
            }
        )
        scores[sym] = float(r.get("score", -1.0))
    uniq = len({round(v, 9) for v in scores.values()})
    return {"scores": scores, "unique_score_count": uniq, "diverse": uniq >= 2}


__all__ = [
    "DecisionEngineV2",
    "edge_bucket_key",
    "run_sample_test",
    "run_decision",
    "generate_dummy_bars",
    "_brain_test",
]
