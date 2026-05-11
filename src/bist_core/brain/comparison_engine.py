from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_FACTOR_NAMES = (
    "momentum",
    "trend_strength",
    "liquidity",
    "volatility_regime",
    "volume_trend",
    "price_vs_moving_average",
)


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _norm_linear(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    return _clamp01((value - lo) / (hi - lo))


def _value_from(result: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        v = _as_float(result.get(key))
        if v is not None:
            return v
    signals = result.get("signals")
    if isinstance(signals, Mapping):
        for key in keys:
            v = _as_float(signals.get(key))
            if v is not None:
                return v
    plan = result.get("plan")
    if isinstance(plan, Mapping):
        for key in keys:
            v = _as_float(plan.get(key))
            if v is not None:
                return v
    return None


def _factor_momentum(result: Mapping[str, Any]) -> tuple[float, str]:
    ret1_pct = _value_from(result, "ret1_pct")
    if ret1_pct is None:
        score = _norm_linear(_as_float(result.get("score")) or 0.0, -1.0, 3.0)
        return round(score, 4), "ret1 eksik; score bazlı proxy"
    score = _norm_linear(ret1_pct, -3.0, 3.0)
    return round(score, 4), f"ret1_pct={ret1_pct:.2f}"


def _factor_trend_strength(result: Mapping[str, Any]) -> tuple[float, str]:
    range_pos = _value_from(result, "range_pos")
    if range_pos is not None:
        return round(_clamp01(range_pos), 4), f"range_pos={range_pos:.3f}"
    decision = str(result.get("decision") or "").strip().lower()
    fallback = {"strong_buy": 0.9, "buy": 0.8, "watch": 0.55, "hold": 0.45, "reduce": 0.3, "sell": 0.2}
    score = fallback.get(decision, 0.5)
    return round(score, 4), f"decision={decision or 'n/a'}"


def _factor_liquidity(result: Mapping[str, Any]) -> tuple[float, str]:
    vol_ratio = _value_from(result, "vol_ratio")
    if vol_ratio is not None:
        score = _norm_linear(vol_ratio, 0.4, 2.0)
        return round(score, 4), f"vol_ratio={vol_ratio:.2f}"
    volume = _value_from(result, "volume", "avg_volume")
    if volume is not None:
        score = _norm_linear(volume, 1_000_000.0, 50_000_000.0)
        return round(score, 4), "volume proxy"
    return 0.5, "liquidity proxy=neutral"


def _factor_volatility_regime(result: Mapping[str, Any]) -> tuple[float, str]:
    atr_pct = _value_from(result, "atr_pct", "volatility_pct")
    if atr_pct is not None:
        score = 1.0 - _norm_linear(abs(atr_pct), 0.0, 8.0)
        return round(score, 4), f"atr_pct={atr_pct:.2f}"
    gap = _value_from(result, "live_gap_pct", "entry_gap_pct")
    if gap is not None:
        score = 1.0 - _norm_linear(abs(gap), 0.0, 10.0)
        return round(score, 4), f"gap_proxy={gap:.2f}"
    return 0.5, "volatility proxy=neutral"


def _factor_volume_trend(result: Mapping[str, Any]) -> tuple[float, str]:
    vol_ratio = _value_from(result, "vol_ratio")
    if vol_ratio is not None:
        return round(_norm_linear(vol_ratio, 0.6, 1.8), 4), f"vol_ratio={vol_ratio:.2f}"
    return 0.5, "volume trend proxy=neutral"


def _factor_price_vs_moving_average(result: Mapping[str, Any]) -> tuple[float, str]:
    distance = _value_from(result, "price_vs_ma_pct", "close_vs_ma_pct", "ma_gap_pct")
    if distance is not None:
        return round(_norm_linear(distance, -5.0, 5.0), 4), f"price_vs_ma_pct={distance:.2f}"

    current = _value_from(result, "current_close", "live_current_close", "close")
    ma20 = _value_from(result, "ma20")
    if current is not None and ma20 is not None and ma20 > 0:
        pct = ((current / ma20) - 1.0) * 100.0
        return round(_norm_linear(pct, -5.0, 5.0), 4), f"ma20_gap={pct:.2f}"
    return 0.5, "ma proxy=neutral"


def _factor_pack(result: Mapping[str, Any]) -> dict[str, tuple[float, str]]:
    return {
        "momentum": _factor_momentum(result),
        "trend_strength": _factor_trend_strength(result),
        "liquidity": _factor_liquidity(result),
        "volatility_regime": _factor_volatility_regime(result),
        "volume_trend": _factor_volume_trend(result),
        "price_vs_moving_average": _factor_price_vs_moving_average(result),
    }


def _summary(symbol: str, factor_pack: dict[str, tuple[float, str]]) -> str:
    avg = sum(score for score, _ in factor_pack.values()) / len(_FACTOR_NAMES)
    return f"{symbol} ortalama faktör skoru={avg:.3f}"


def _extract_as_of(result_a: Mapping[str, Any], result_b: Mapping[str, Any]) -> str:
    for source in (result_a, result_b):
        for key in ("as_of", "day", "date", "effective_date", "snapshot_date"):
            raw = source.get(key)
            if raw is not None and str(raw).strip():
                return str(raw).strip()
    return ""


def _extract_live_suppressed(result_a: Mapping[str, Any], result_b: Mapping[str, Any]) -> bool:
    for source in (result_a, result_b):
        meta = source.get("live_context_meta")
        if isinstance(meta, Mapping) and bool(meta.get("suppressed")):
            return True
    return False


def build_dual_rationale_decision(
    symbol_a: str,
    symbol_b: str,
    result_a: Mapping[str, Any] | dict[str, Any] | None,
    result_b: Mapping[str, Any] | dict[str, Any] | None,
) -> dict[str, Any]:
    raw_a = dict(result_a) if isinstance(result_a, Mapping) else {}
    raw_b = dict(result_b) if isinstance(result_b, Mapping) else {}

    if not raw_a or not raw_b:
        return {
            "decision": "inconclusive",
            "rationale": {
                "A": {"summary": "insufficient_data", "factors": []},
                "B": {"summary": "insufficient_data", "factors": []},
            },
            "diff_table": [],
            "meta": {
                "dominant_timeframe": "daily",
                "confirming_timeframe": "weekly",
                "as_of": "",
                "live_suppressed": False,
            },
        }

    factors_a = _factor_pack(raw_a)
    factors_b = _factor_pack(raw_b)

    avg_a = sum(score for score, _ in factors_a.values()) / len(_FACTOR_NAMES)
    avg_b = sum(score for score, _ in factors_b.values()) / len(_FACTOR_NAMES)
    if abs(avg_a - avg_b) < 1e-9:
        decision = "inconclusive"
    elif avg_a > avg_b:
        decision = "A>B"
    else:
        decision = "B>A"

    rationale_a_factors = [
        {"name": name, "score": round(factors_a[name][0], 4), "detail": factors_a[name][1]}
        for name in _FACTOR_NAMES
    ]
    rationale_b_factors = [
        {"name": name, "score": round(factors_b[name][0], 4), "detail": factors_b[name][1]}
        for name in _FACTOR_NAMES
    ]
    diff_table = [
        {
            "factor": name,
            "A_score": round(factors_a[name][0], 4),
            "B_score": round(factors_b[name][0], 4),
            "explanation": f"{symbol_a}:{factors_a[name][1]} | {symbol_b}:{factors_b[name][1]}",
        }
        for name in _FACTOR_NAMES
    ]

    return {
        "decision": decision,
        "rationale": {
            "A": {"summary": _summary(symbol_a, factors_a), "factors": rationale_a_factors},
            "B": {"summary": _summary(symbol_b, factors_b), "factors": rationale_b_factors},
        },
        "diff_table": diff_table,
        "meta": {
            "dominant_timeframe": "daily",
            "confirming_timeframe": "weekly",
            "as_of": _extract_as_of(raw_a, raw_b),
            "live_suppressed": _extract_live_suppressed(raw_a, raw_b),
        },
    }

