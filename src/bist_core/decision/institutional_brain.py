"""
Institutional single-TF brain: price structure, regime, risk — deterministic, no RNG.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any

from bist_core.brain.edge_engine import (
    _bars_for_liquidity_sweep,
    _compute_alpha_microstructure_features,
    _feat_liquidity_proxy,
    _feat_mean_reversion_short_term,
    _feat_momentum_burst_norm,
    _feat_vol_clustering,
    _pullback_from_prices,
    _require_closes,
    _trend_strength_from_prices,
    _volatility_from_prices,
    _volumes_aligned,
    signed_momentum_burst_ratio_from_bars,
)
from bist_core.edge_engine import compute_edge
from bist_core.features.feature_engine_v2 import (
    bollinger_distance,
    compute_rsi_zscore,
    ema_slope,
    higher_highs,
    volume_spike,
)
from bist_core.models.ohlcv import OHLCVBar


def _closes(bars: list[OHLCVBar]) -> list[float]:
    return [float(b.close) for b in bars]


def _sma(closes: list[float], n: int) -> float | None:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / float(n)


def _std_20(closes: list[float]) -> float:
    if len(closes) < 20:
        tail = closes
    else:
        tail = closes[-20:]
    if len(tail) < 2:
        return 0.0
    return float(statistics.pstdev(tail))


def _swing_low(bars: list[OHLCVBar], lookback: int = 15) -> float:
    tail = bars[-lookback:] if len(bars) >= lookback else bars
    return min(float(b.low) for b in tail)


def _swing_high(bars: list[OHLCVBar], lookback: int = 15) -> float:
    tail = bars[-lookback:] if len(bars) >= lookback else bars
    return max(float(b.high) for b in tail)


def compute_features(bars: list[OHLCVBar]) -> dict[str, float] | None:
    """OHLCV-derived features (PRD: ≥50 bars; needs SMA30)."""
    if len(bars) < 50:
        return None
    c = _closes(bars)
    last = c[-1]
    sma10 = _sma(c, 10)
    sma30 = _sma(c, 30)
    if sma10 is None or sma30 is None:
        return None
    short_trend = (last - sma10) / max(1e-9, abs(sma10))
    mid_trend = (sma10 - sma30) / max(1e-9, abs(sma30))
    mom = last - c[-5] if len(c) >= 5 else 0.0
    vol = _std_20(c)
    m20 = c[-20:]
    lo20, hi20 = min(m20), max(m20)
    span = hi20 - lo20
    if span <= 1e-12:
        range_pos = 0.5
    else:
        range_pos = (last - lo20) / span
    mean20 = sum(m20) / len(m20)
    vol_norm = vol / max(1e-9, abs(mean20))
    return {
        "last_close": last,
        "short_trend": float(short_trend),
        "mid_trend": float(mid_trend),
        "momentum": float(mom),
        "volatility": float(vol),
        "vol_norm": float(vol_norm),
        "range_position": float(range_pos),
        "sma10": float(sma10),
        "sma30": float(sma30),
    }


def _normalize_mtf_state(raw: str | None) -> str:
    if not raw:
        return ""
    u = str(raw).strip().upper()
    if u in ("UP", "TRENDING_UP", "LONG", "ENTER_LONG", "BULL", "G", "1H_UP"):
        return "UP"
    if u in ("DOWN", "TRENDING_DOWN", "SHORT", "ENTER_SHORT", "BEAR", "1H_DOWN"):
        return "DOWN"
    if "LONG" in u or "UP" in u:
        return "UP"
    if "SHORT" in u or "DOWN" in u:
        return "DOWN"
    return ""


def _infer_mtf_state_from_features(f: dict[str, float]) -> str:
    st = float(f["short_trend"])
    mt = float(f["mid_trend"])
    if st > 0.0006 and mt > 0.0004:
        return "UP"
    if st < -0.0006 and mt < -0.0004:
        return "DOWN"
    return "NEUTRAL"


def _break_neutral_direction(
    symbol: str,
    bar_ts: int,
    trend_strength: float,
    range_position: float,
    short_trend: float,
) -> str:
    """Deterministic non-neutral fallback when primary + momentum fallback are neutral."""
    ts = float(trend_strength)
    rp = float(range_position)
    st = float(short_trend)
    if ts > 0.5:
        return "long"
    if ts < 0.45:
        return "short"
    if rp < 0.42:
        return "long"
    if rp > 0.58:
        return "short"
    if st > 0.0:
        return "long"
    if st < 0.0:
        return "short"
    h = int(
        hashlib.sha256(f"{symbol}|{bar_ts}".encode("utf-8")).hexdigest()[:8],
        16,
    )
    return "long" if (h % 2) == 0 else "short"


def resolve_direction_engine(
    *,
    symbol: str,
    bar_ts: int,
    bars: list[OHLCVBar],
    f: dict[str, float],
    range_position: float,
    mtf_state: str | None,
) -> tuple[str, str, float, float, bool, float | None]:
    """
    BIST direction engine: MTF + trend + liquidity shock; signed momentum secondary only.

    Returns (direction, mtf_resolved, trend_strength, volatility_compression, liquidity_shock, signed_mb).
    """
    closes = _require_closes(bars)
    if closes is None:
        trend_strength = 0.0
        volatility_compression = 0.0
    else:
        trend_strength = float(_trend_strength_from_prices(closes))
        volatility_compression = float(_volatility_from_prices(closes))

    rp = float(range_position)
    sb = _bars_for_liquidity_sweep(bars)
    alpha = _compute_alpha_microstructure_features(sb) if sb is not None and len(sb) >= 51 else None

    signed_mb: float | None = None
    liquidity_shock = False
    if alpha is not None:
        re = float(alpha["range_expansion"])
        mb = float(alpha["momentum_burst"])
        liquidity_shock = re > 1.2 or mb > 1.5
        signed_mb = float(alpha["signed_momentum_burst"])
    else:
        signed_mb = signed_momentum_burst_ratio_from_bars(bars)

    mtf_u = _normalize_mtf_state(mtf_state)
    if not mtf_u:
        inf = _infer_mtf_state_from_features(f)
        mtf_u = inf if inf in ("UP", "DOWN") else "NEUTRAL"

    direction = "neutral"
    if mtf_u == "DOWN" and liquidity_shock:
        direction = "long"
    elif mtf_u == "UP" and trend_strength > 0.55:
        direction = "long"
    elif mtf_u == "DOWN" and trend_strength > 0.55:
        direction = "short"

    if direction == "neutral" and signed_mb is not None and abs(signed_mb) > 1.5:
        direction = "long" if signed_mb > 0 else "short"

    if direction == "neutral":
        direction = _break_neutral_direction(symbol, bar_ts, trend_strength, rp, float(f["short_trend"]))

    print(
        {
            "DIRECTION_ENGINE": {
                "symbol": symbol,
                "mtf": mtf_u,
                "trend": round(trend_strength, 6),
                "shock": liquidity_shock,
                "direction": direction,
            }
        },
        flush=True,
    )

    return direction, mtf_u, trend_strength, volatility_compression, liquidity_shock, signed_mb


def classify_market_state(f: dict[str, float]) -> str:
    """Priority: high vol → VOLATILE; mid range band → RANGE; low vol + up-trend → TRENDING_UP."""
    vn = f["vol_norm"]
    st = f["short_trend"]
    mt = f["mid_trend"]
    rp = f["range_position"]
    high_vol = vn > 0.012
    low_vol = vn < 0.006
    trend_up = st > 0.0008 and mt > 0.0005
    in_range_band = 0.3 <= rp <= 0.7
    if high_vol:
        return "VOLATILE"
    if in_range_band:
        return "RANGE"
    if low_vol and trend_up:
        return "TRENDING_UP"
    return "NEUTRAL"


def _confidence_score(f: dict[str, float], state: str) -> float:
    """Nonlinear 0.2–0.9 from momentum, vol stability, range_position (PRDV3 — no flat band)."""
    st = float(f["short_trend"])
    mom = float(f["momentum"]) / max(1e-9, abs(f["last_close"]) * 0.012)
    rp = float(f["range_position"])
    vn = float(f["vol_norm"])
    dir_raw = math.tanh(st * 18.0) * 0.42 + math.tanh(mom * 2.4) * 0.38
    rp_ext = abs(rp - 0.5) * 2.0
    range_boost = math.tanh(rp_ext * 1.85) * 0.22
    calm = math.tanh((0.018 - vn) * 48.0) * 0.28
    raw = dir_raw + range_boost + calm
    mid = math.tanh(raw * 1.05)
    scaled = 0.55 + 0.38 * mid
    if state == "VOLATILE":
        scaled = 0.24 + 0.42 * math.tanh(raw * 0.85)
    elif state == "RANGE":
        scaled = 0.42 + 0.44 * mid
    elif state == "TRENDING_UP":
        scaled = 0.48 + 0.42 * mid
    return float(max(0.2, min(0.9, scaled)))


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _volumes_from_bars_for_edge(bars: list[Any]) -> list[float]:
    out: list[float] = []
    for b in bars:
        try:
            if isinstance(b, dict) and "volume" in b:
                out.append(float(b["volume"]))
            elif hasattr(b, "volume"):
                out.append(float(getattr(b, "volume")))
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def build_compute_edge_features(
    bars: list[Any],
    f: dict[str, float],
    range_position: float,
) -> dict[str, Any]:
    """Feature bundle for ``bist_core.decision.edge_engine.compute_edge`` (institutional path)."""
    rp = max(0.0, min(1.0, float(range_position)))
    st = float(f.get("short_trend", 0.0) or 0.0)
    mom = float(f.get("momentum", 0.0) or 0.0)
    lc = float(f.get("last_close", 0.0) or 0.0)
    vn = float(f.get("vol_norm", 0.0) or 0.0)

    vol_list = _volumes_from_bars_for_edge(bars)
    out: dict[str, Any] = {
        "range_position": rp,
        "trend_alignment": max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(st * 40.0))),
    }

    closes = _require_closes(bars, min_bars=51)
    if closes is None:
        out["trend_strength"] = max(0.0, min(1.0, abs(st) * 25.0))
        out["ema_slope"] = out["trend_strength"]
        out["pullback_quality"] = 0.35
        den = max(abs(lc), 1e-9)
        out["mean_reversion"] = max(0.0, min(1.0, 0.5 - 0.5 * math.tanh(st * 25.0)))
        out["momentum_burst"] = max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(mom / den * 3.0)))
        out["volatility_compression"] = max(0.0, min(1.0, 1.0 - min(vn / 0.02, 1.0)))
        out["volume_support"] = 0.45
        out["higher_highs"] = 0.0
        out["rsi_zscore"] = 0.0
        out["bollinger_distance"] = 0.0
        out["range_expansion"] = 0.0
        out["volume_spike"] = float(volume_spike(vol_list)) if len(vol_list) >= 20 else 0.0
        return out

    out["trend_strength"] = float(_trend_strength_from_prices(closes))
    out["pullback_quality"] = float(_pullback_from_prices(closes))
    out["volatility_compression"] = float(_volatility_from_prices(closes))
    mr = float(_feat_mean_reversion_short_term(closes))
    out["mean_reversion"] = max(0.0, min(1.0, 0.5 + 0.5 * mr))
    mb = float(_feat_momentum_burst_norm(closes))
    out["momentum_burst"] = max(0.0, min(1.0, 0.5 + 0.5 * mb))
    vc = float(_feat_vol_clustering(closes))
    out["range_expansion"] = max(0.0, min(1.0, 0.5 + 0.5 * vc))
    vols = _volumes_aligned(bars, 50)
    liq = float(_feat_liquidity_proxy(vols))
    out["volume_support"] = max(0.0, min(1.0, 0.5 + 0.5 * liq))

    out["ema_slope"] = max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(float(ema_slope(closes)) * 4.0)))
    rz = float(compute_rsi_zscore(closes))
    out["rsi_zscore"] = max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(rz / 3.0)))
    bd = float(bollinger_distance(closes))
    out["bollinger_distance"] = max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(bd / 2.5)))
    out["higher_highs"] = float(higher_highs(closes))

    sweep = _bars_for_liquidity_sweep(bars)
    alpha = _compute_alpha_microstructure_features(sweep) if sweep is not None and len(sweep) >= 51 else None
    if alpha is not None:
        re = float(alpha["range_expansion"])
        mb_a = float(alpha["momentum_burst"])
        float(alpha["relative_volume"])
        out["range_expansion"] = max(
            float(out["range_expansion"]),
            max(0.0, min(1.0, math.tanh(max(0.0, re - 1.0)))),
        )
        out["momentum_burst"] = max(
            float(out["momentum_burst"]),
            max(0.0, min(1.0, math.tanh(mb_a / 2.5))),
        )
    if len(vol_list) >= 20:
        out["volume_spike"] = float(volume_spike(vol_list))
    elif alpha is not None:
        vs2 = float(alpha["relative_volume"])
        out["volume_spike"] = max(0.0, min(1.0, math.tanh((vs2 - 1.0) * 1.2)))
    else:
        out["volume_spike"] = 0.0
    return out


def _anti_template_epsilon(bar_ts: int) -> float:
    """Deterministic micro-shift when last decisions were identical (no RNG)."""
    return (int(bar_ts) % 17) * 1e-5


def compute_institutional_decision(
    bars: list[OHLCVBar],
    price: float,
    *,
    symbol: str,
    recent_signatures: list[str],
    bar_ts: int,
    mtf_state: str | None = None,
) -> dict[str, Any]:
    """
    Returns decision dict with action in:
    hold | enter | enter_small | exit | wait
    """
    f0 = compute_features(bars)
    if f0 is None:
        out_ins = {
            "action": "hold",
            "confidence": 0.0,
            "position_size_frac": 0.0,
            "entry": float(price),
            "stop_loss": float(price),
            "target": float(price),
            "state": "INSUFFICIENT_DATA",
            "reason": "need>=50bars",
            "signature": "hold|INSUFFICIENT|0",
            "edge_score": 0.0,
            "edge": 0.0,
        }
        print(
            json.dumps(
                {
                    "edge_engine": {
                        "symbol": symbol,
                        "confidence": 0.0,
                        "edge_score": 0.0,
                    }
                },
                ensure_ascii=False,
            )
        )
        return out_ins

    state = classify_market_state(f0)
    eps = 0.0
    if len(recent_signatures) >= 10 and len(set(recent_signatures[-10:])) == 1:
        eps = _anti_template_epsilon(bar_ts)
    rp_raw = float(f0["range_position"])
    rp_sig = _clamp01(rp_raw + eps) if eps else rp_raw
    f = dict(f0)
    f["range_position"] = rp_sig

    conf = _confidence_score(f, state)

    last = f["last_close"]
    vol = f["volatility"]
    swing_lo = _swing_low(bars)
    risk_unit = max(1.5 * vol, last * 0.005)
    stop_loss = min(swing_lo, last - risk_unit)
    take_profit = last + 2.0 * (last - stop_loss) if last > stop_loss else last + 2.0 * risk_unit

    risk_per_trade = 0.01
    pos_frac = conf * risk_per_trade
    pos_frac = max(0.002, min(0.02, pos_frac))

    action = "hold"
    reason_parts: list[str] = []

    if state == "VOLATILE":
        action = "wait"
        reason_parts.append("high_vol_stand_aside")
    elif state == "TRENDING_UP":
        if rp_sig < 0.4:
            action = "enter"
            reason_parts.append("trend_pullback")
        else:
            action = "hold"
            reason_parts.append("trend_no_pullback")
    elif state == "RANGE":
        if rp_sig < 0.35:
            action = "enter_small"
            reason_parts.append("range_near_support")
        elif rp_sig > 0.65:
            action = "exit"
            reason_parts.append("range_near_resistance")
        else:
            action = "hold"
            reason_parts.append("range_mid")
    else:
        action = "hold"
        reason_parts.append("neutral")

    if action == "enter_small":
        pos_frac = max(0.002, min(0.02, pos_frac * 0.5))

    direction, mtf_u, _ts_dir, _vc_dir, _shock_dir, _smb_dir = resolve_direction_engine(
        symbol=symbol,
        bar_ts=bar_ts,
        bars=bars,
        f=f,
        range_position=float(rp_sig),
        mtf_state=mtf_state,
    )

    _edge_last_close = None
    if bars:
        _lb = bars[-1]
        if isinstance(_lb, dict) and "close" in _lb:
            _edge_last_close = float(_lb["close"])
        elif isinstance(_lb, (list, tuple)) and len(_lb) > 4:
            _edge_last_close = float(_lb[4])
        elif hasattr(_lb, "close"):
            _edge_last_close = float(getattr(_lb, "close"))
    print(
        {
            "EDGE_INPUT_CHECK": {
                "bars_len": len(bars),
                "last_close": _edge_last_close,
            }
        },
        flush=True,
    )

    edge_features = build_compute_edge_features(bars, f, float(rp_sig))
    edge_score = float(compute_edge(edge_features, str(state), bars))
    print({"EDGE_SOURCE": "NEW_ENGINE", "EDGE_VALUE": edge_score}, flush=True)
    edge_blend = float(edge_score)
    edge_lin = max(0.0, min(1.0, float(edge_score)))

    edge_raw = float(edge_blend)
    edge_score = edge_raw
    print(
        {
            "EDGE_SHARPEN_SOFT": {
                "symbol": symbol,
                "raw": edge_raw,
                "passthrough": edge_score,
            }
        },
        flush=True,
    )

    if float(edge_score) >= 0.65 and state != "VOLATILE":
        if direction == "short":
            action = "enter_short"
        else:
            action = "enter_long"
        print(
            {
                "EDGE_OVERRIDE_REGIME": {
                    "symbol": symbol,
                    "edge": float(edge_score),
                    "state": state,
                    "direction": direction,
                    "action": action,
                }
            },
            flush=True,
        )

    final_score = edge_blend
    emax = 1.5
    market_state = state

    if float(edge_score) < 0.18 * emax:
        if action not in ("exit", "wait"):
            action = "hold"

    if action == "hold" and market_state == "TRENDING_DOWN" and conf >= 0.6:
        action = "exit"

    if action == "wait":
        pass
    elif action == "exit":
        pass
    elif action in ("enter_long", "enter_short"):
        pass
    elif action == "enter_small":
        pass
    elif action == "enter":
        if direction == "short":
            action = "enter_short"
        elif direction == "long":
            action = "enter_long"
        else:
            action = "hold"
    else:
        action = "hold"

    print(
        {
            "INST_ACTION_FINAL": {
                "symbol": symbol,
                "edge": edge_score,
                "confidence": float(conf),
                "final_action": action,
            }
        },
        flush=True,
    )

    size_multiplier = final_score
    pos_frac = max(0.002, min(0.02, size_multiplier * 0.02))

    sig = f"{action}|{state}|{conf:.4f}|{rp_sig:.4f}"
    reason = f"edge_driven|{state}|fs={final_score:.4f}|edge_lin={edge_lin:.4f}|conf={conf:.4f}"
    print(
        json.dumps(
            {
                "edge_engine": {
                    "symbol": symbol,
                    "confidence": conf,
                    "edge_score": edge_blend,
                }
            },
            ensure_ascii=False,
        )
    )

    if direction == "long":
        edge_signal = "buy"
    elif direction == "short":
        edge_signal = "sell"
    else:
        edge_signal = "flat"

    result: dict[str, Any] = {
        "action": action,
        "confidence": round(conf, 6),
        "position_size_frac": round(pos_frac, 6),
        "entry": round(last, 6),
        "stop_loss": round(stop_loss, 6),
        "target": round(take_profit, 6),
        "state": state,
        "reason": reason[:500],
        "signature": sig,
        "edge_score": round(float(edge_score), 6),
        "edge": round(float(edge_score), 6),
        "edge_signal": edge_signal,
        "direction": direction,
        "symbol": symbol,
        "features": {
            "short_trend": f["short_trend"],
            "mid_trend": f["mid_trend"],
            "momentum": f["momentum"],
            "volatility": f["volatility"],
            "range_position": rp_sig,
            "vol_norm": f["vol_norm"],
        },
    }

    print(
        {
            "EDGE_FLOW_CHECK": {
                "symbol": symbol,
                "edge": result.get("edge"),
                "action": result.get("action"),
            }
        },
        flush=True,
    )

    print(
        {
            "DIRECTION_ASSIGNED": {
                "symbol": result.get("symbol"),
                "direction": direction,
                "mtf_resolved": mtf_u,
                "final_action": result["action"],
                "liquidity_shock": _shock_dir,
            }
        },
        flush=True,
    )

    if result.get("edge", 0) < 0.4 and str(result.get("action") or "").startswith("enter"):
        print(
            {
                "EDGE_TOO_LOW_BLOCKED": result.get("symbol"),
            },
            flush=True,
        )
        result["action"] = "hold"

    return result


__all__ = [
    "build_compute_edge_features",
    "compute_features",
    "classify_market_state",
    "compute_institutional_decision",
    "resolve_direction_engine",
]
