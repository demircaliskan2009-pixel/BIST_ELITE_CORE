from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.regime_engine import (
    LOW_LIQUIDITY,
    NO_REGIME,
    RANGE,
    TREND_DOWN,
    TREND_UP,
    VOLATILE,
    MarketRegime,
)
from bist_core.edge.registry import EdgeCondition, EdgeDefinition, EdgeLogic, EdgeRegistry
from bist_core.features.feature_registry import get_feature

# Explicit weights — no randomness
W_MOMENTUM = 0.35
W_TREND = 0.30
W_RSI = 0.20
W_VOL_PENALTY = 0.15

# No-trade threshold
SCORE_THRESHOLD = 0.10

# Top-N default
TOP_N = 3

EDGE_REGIME_WEIGHT = 0.30
EDGE_SIGNAL_WEIGHT = 0.35
EDGE_RISK_WEIGHT = 0.20
EDGE_CONFIRMATION_WEIGHT = 0.15

_REGIME_ALIASES: dict[str, tuple[str, ...]] = {
    "bull": (TREND_UP,),
    "bear": (TREND_DOWN,),
    "sideways": (RANGE,),
    "range": (RANGE,),
    "trend": (TREND_UP, TREND_DOWN),
    "volatile": (VOLATILE,),
    "low_liquidity": (LOW_LIQUIDITY,),
    TREND_UP: (TREND_UP,),
    TREND_DOWN: (TREND_DOWN,),
    RANGE: (RANGE,),
    VOLATILE: (VOLATILE,),
    LOW_LIQUIDITY: (LOW_LIQUIDITY,),
    NO_REGIME: (NO_REGIME,),
}

_RAW_BAR_FIELDS = ("open", "high", "low", "close", "volume", "timestamp")
_CONTROL_FIELDS = ("regime", "entry_price", "bars_since_entry")
_PRICE_LIKE_FEATURES = {"open", "high", "low", "close", "sma_20", "sma_50", "ema_20"}
_PERCENTAGE_FEATURES = {"momentum_20", "returns"}


@dataclass(frozen=True)
class EdgeScoreComponents:
    regime_score: float
    signal_score: float
    risk_score: float
    confirmation_score: float

    def to_dict(self) -> dict[str, float]:
        return {
            "regime_score": self.regime_score,
            "signal_score": self.signal_score,
            "risk_score": self.risk_score,
            "confirmation_score": self.confirmation_score,
        }


@dataclass(frozen=True)
class EdgeScoreResult:
    edge_id: str
    total_score: float
    components: EdgeScoreComponents
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "total_score": self.total_score,
            "components": self.components.to_dict(),
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class _ConditionResult:
    satisfied: bool
    strength: float
    pressure: float
    explanation: str


@dataclass(frozen=True)
class _LogicResult:
    satisfied: bool
    score: float
    pressure: float
    explanations: tuple[str, ...]
    error: str | None = None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _round_score(value: float) -> float:
    return round(float(value), 4)


def _zero_edge_score(edge_id: str, reason: str) -> EdgeScoreResult:
    return EdgeScoreResult(
        edge_id=edge_id,
        total_score=0.0,
        components=EdgeScoreComponents(0.0, 0.0, 0.0, 0.0),
        explanation=f"score=0 fail_closed: {reason}",
    )


def _regime_payload(regime: MarketRegime | Mapping[str, Any]) -> dict[str, Any] | None:
    if isinstance(regime, MarketRegime):
        return {
            "label": regime.regime,
            "confidence": float(regime.confidence),
            "metrics": regime.metrics.to_dict(),
            "explanation": regime.explanation,
        }
    if isinstance(regime, Mapping):
        label = str(regime.get("regime") or "").strip()
        confidence = regime.get("confidence")
        metrics = regime.get("metrics")
        if not label or confidence is None or not isinstance(metrics, Mapping):
            return None
        return {
            "label": label,
            "confidence": float(confidence),
            "metrics": {str(key): float(value) for key, value in metrics.items()},
            "explanation": str(regime.get("explanation") or ""),
        }
    return None


def _canonical_regimes(token: str) -> tuple[str, ...]:
    text = str(token or "").strip()
    return _REGIME_ALIASES.get(text, (text,))


def _is_regime_compatible(edge: EdgeDefinition, regime_label: str) -> bool:
    current = set(_canonical_regimes(regime_label))
    expected: set[str] = set()
    for token in edge.regime_applicability:
        expected.update(_canonical_regimes(token))
    return bool(current & expected)


def _required_feature_names(edge: EdgeDefinition) -> tuple[str, ...]:
    names = set(edge.feature_set)
    for logic in (edge.entry_logic, edge.exit_logic, edge.invalidation_conditions):
        for condition in logic.conditions:
            left = str(condition.left or "").strip()
            if left and left not in _RAW_BAR_FIELDS and left not in _CONTROL_FIELDS:
                names.add(left)
            if isinstance(condition.right, str):
                right = condition.right.strip()
                if right and right not in _RAW_BAR_FIELDS and right not in _CONTROL_FIELDS:
                    names.add(right)
    names.difference_update(_RAW_BAR_FIELDS)
    names.difference_update(_CONTROL_FIELDS)
    return tuple(sorted(names))


def _compute_feature_snapshot(
    edge: EdgeDefinition,
    bars: Sequence[OHLCVBar],
    regime_label: str,
) -> tuple[dict[str, float | int | str], str | None]:
    if len(bars) < int(edge.required_data.min_history_bars):
        return {}, f"insufficient_history:{len(bars)}<{edge.required_data.min_history_bars}"
    if not bars:
        return {}, "missing_bars"

    last_bar = bars[-1]
    values: dict[str, float | int | str] = {
        "open": float(last_bar.open),
        "high": float(last_bar.high),
        "low": float(last_bar.low),
        "close": float(last_bar.close),
        "volume": float(last_bar.volume),
        "timestamp": int(last_bar.timestamp),
        "regime": regime_label,
    }

    if values["close"] <= 0:
        return {}, "invalid_close_price"

    for name in _required_feature_names(edge):
        try:
            series = get_feature(name)(bars)
        except KeyError:
            return {}, f"unknown_feature:{name}"
        if not series:
            return {}, f"missing_feature_series:{name}"
        last_value = series[-1]
        if last_value is None:
            return {}, f"missing_feature_value:{name}"
        numeric_value = float(last_value)
        if numeric_value != numeric_value:
            return {}, f"nan_feature_value:{name}"
        values[name] = numeric_value

    return values, None


def _resolve_operand(
    operand: str,
    values: Mapping[str, float | int | str],
) -> tuple[float | int | str | None, str | None]:
    token = str(operand or "").strip()
    if not token:
        return None, "empty_operand"
    if token in {"entry_price", "bars_since_entry"}:
        return None, f"unsupported_control_field:{token}"
    if token not in values:
        return None, f"missing_operand:{token}"
    return values[token], None


def _condition_scale(
    left_name: str,
    right_name: str | None,
    left_value: float,
    right_value: float,
    reference_close: float,
) -> float:
    keys = {left_name}
    if right_name:
        keys.add(right_name)

    if any(name.startswith("rsi_") for name in keys):
        return 10.0
    if any(name.startswith("atr_") for name in keys):
        return max(reference_close * 0.02, 0.01)
    if any(name in _PERCENTAGE_FEATURES for name in keys):
        return 0.02
    if any(name == "volume" for name in keys):
        return max(abs(left_value), abs(right_value), 1.0) * 0.25
    if any(name in _PRICE_LIKE_FEATURES for name in keys):
        return max(abs(left_value), abs(right_value), reference_close, 1.0) * 0.01
    return max(abs(left_value), abs(right_value), 1.0) * 0.10


def _evaluate_condition(
    condition: EdgeCondition,
    values: Mapping[str, float | int | str],
) -> _ConditionResult | None:
    left_name = str(condition.left).strip()
    operator = str(condition.operator).strip()
    left_value, error = _resolve_operand(left_name, values)
    if error is not None:
        return None

    if left_name == "regime":
        current_regimes = set(_canonical_regimes(str(left_value)))
        if operator in {"in", "not_in"}:
            raw_values = condition.right if isinstance(condition.right, tuple) else (condition.right,)
            expected: set[str] = set()
            for item in raw_values:
                expected.update(_canonical_regimes(str(item)))
            satisfied = bool(current_regimes & expected)
            if operator == "not_in":
                satisfied = not satisfied
            strength = 1.0 if satisfied else 0.0
            pressure = 1.0 if not satisfied else 0.0
            return _ConditionResult(
                satisfied=satisfied,
                strength=strength,
                pressure=pressure,
                explanation=f"{left_name} {operator} {tuple(sorted(expected))} => {satisfied}",
            )

        expected = set(_canonical_regimes(str(condition.right)))
        satisfied = bool(current_regimes & expected)
        if operator == "!=":
            satisfied = not satisfied
        strength = 1.0 if satisfied else 0.0
        pressure = 1.0 if not satisfied else 0.0
        return _ConditionResult(
            satisfied=satisfied,
            strength=strength,
            pressure=pressure,
            explanation=f"{left_name} {operator} {tuple(sorted(expected))} => {satisfied}",
        )

    if not isinstance(left_value, (int, float)):
        return None

    right_name: str | None = None
    right_value: float
    if isinstance(condition.right, str):
        right_name = condition.right.strip()
        resolved_right, error = _resolve_operand(right_name, values)
        if error is not None or not isinstance(resolved_right, (int, float)):
            return None
        right_value = float(resolved_right)
    elif isinstance(condition.right, (int, float)):
        right_value = float(condition.right)
    else:
        return None

    left_number = float(left_value)
    scale = _condition_scale(left_name, right_name, left_number, right_value, float(values["close"]))
    tolerance = scale * 0.05

    if operator in {">", ">="}:
        signed_margin = (left_number - right_value) / scale
        satisfied = left_number > right_value if operator == ">" else left_number >= right_value
    elif operator in {"<", "<="}:
        signed_margin = (right_value - left_number) / scale
        satisfied = left_number < right_value if operator == "<" else left_number <= right_value
    elif operator == "==":
        signed_margin = 1.0 - (abs(left_number - right_value) / scale)
        satisfied = abs(left_number - right_value) <= tolerance
    elif operator == "!=":
        signed_margin = abs(left_number - right_value) / scale
        satisfied = abs(left_number - right_value) > tolerance
    else:
        return None

    strength = _clamp01(signed_margin) if satisfied else 0.0
    pressure = 1.0 if satisfied else _clamp01(1.0 + signed_margin)
    explanation = (
        f"{left_name} {operator} {right_name or right_value}:"
        f" left={left_number:.6f} right={right_value:.6f}"
        f" satisfied={satisfied}"
    )
    return _ConditionResult(
        satisfied=satisfied,
        strength=strength,
        pressure=pressure,
        explanation=explanation,
    )


def _evaluate_logic(logic: EdgeLogic, values: Mapping[str, float | int | str]) -> _LogicResult:
    condition_results: list[_ConditionResult] = []
    for condition in logic.conditions:
        result = _evaluate_condition(condition, values)
        if result is None:
            return _LogicResult(False, 0.0, 0.0, (), error=f"unresolved_condition:{condition.left}")
        condition_results.append(result)

    if not condition_results:
        return _LogicResult(False, 0.0, 0.0, (), error="empty_logic")

    if logic.match == "all":
        satisfied = all(item.satisfied for item in condition_results)
        score = sum(item.strength for item in condition_results) / len(condition_results) if satisfied else 0.0
    else:
        satisfied = any(item.satisfied for item in condition_results)
        score = max((item.strength for item in condition_results), default=0.0) if satisfied else 0.0

    pressure = max((item.pressure for item in condition_results), default=0.0)
    return _LogicResult(
        satisfied=satisfied,
        score=_round_score(score),
        pressure=_round_score(pressure),
        explanations=tuple(item.explanation for item in condition_results),
    )


def _current_risk_bucket(regime_payload: Mapping[str, Any]) -> str:
    label = str(regime_payload["label"])
    metrics = regime_payload["metrics"]
    atr_ratio = float(metrics.get("atr_ratio", 0.0))
    return_std = float(metrics.get("return_std", 0.0))
    if label in {LOW_LIQUIDITY, VOLATILE}:
        return "high"
    if atr_ratio >= 0.02 or return_std >= 0.012:
        return "medium"
    return "low"


def _risk_score(edge: EdgeDefinition, regime_payload: Mapping[str, Any]) -> float:
    alignment_table = {
        ("low", "low"): 1.0,
        ("low", "medium"): 0.55,
        ("low", "high"): 0.0,
        ("medium", "low"): 0.8,
        ("medium", "medium"): 1.0,
        ("medium", "high"): 0.6,
        ("high", "low"): 0.45,
        ("high", "medium"): 0.75,
        ("high", "high"): 1.0,
    }
    current_bucket = _current_risk_bucket(regime_payload)
    bucket_alignment = alignment_table[(edge.risk_profile.volatility_bucket, current_bucket)]
    metrics = regime_payload["metrics"]
    realized_risk = max(float(metrics.get("atr_ratio", 0.0)) * 3.0, float(metrics.get("return_std", 0.0)) * 4.0, 0.01)
    drawdown_alignment = _clamp01(float(edge.risk_profile.max_expected_drawdown_pct) / realized_risk)
    return _round_score((bucket_alignment + drawdown_alignment) / 2.0)


def _confirmation_score(
    regime_payload: Mapping[str, Any],
    exit_logic: _LogicResult,
    invalidation_logic: _LogicResult,
) -> float:
    metrics = regime_payload["metrics"]
    volume_confirmation = _clamp01(float(metrics.get("recent_volume_ratio", 0.0)) / 1.1)
    exit_clearance = _clamp01(1.0 - float(exit_logic.pressure))
    invalidation_clearance = _clamp01(1.0 - float(invalidation_logic.pressure))
    return _round_score((volume_confirmation + exit_clearance + invalidation_clearance) / 3.0)


def score_edge(
    edge: EdgeDefinition,
    regime: MarketRegime | Mapping[str, Any],
    bars: Sequence[OHLCVBar],
) -> EdgeScoreResult:
    if not edge.enabled:
        return _zero_edge_score(edge.edge_id, "edge_disabled")

    regime_payload = _regime_payload(regime)
    if regime_payload is None:
        return _zero_edge_score(edge.edge_id, "insufficient_regime_context")

    regime_label = str(regime_payload["label"])
    if regime_label == NO_REGIME:
        return _zero_edge_score(edge.edge_id, "no_regime")
    if not _is_regime_compatible(edge, regime_label):
        return _zero_edge_score(edge.edge_id, f"regime_mismatch:{regime_label}")

    feature_values, feature_error = _compute_feature_snapshot(edge, bars, regime_label)
    if feature_error is not None:
        return _zero_edge_score(edge.edge_id, feature_error)

    entry_logic = _evaluate_logic(edge.entry_logic, feature_values)
    if entry_logic.error is not None:
        return _zero_edge_score(edge.edge_id, entry_logic.error)
    if not entry_logic.satisfied:
        return _zero_edge_score(edge.edge_id, "unclear_signal")

    invalidation_logic = _evaluate_logic(edge.invalidation_conditions, feature_values)
    if invalidation_logic.error is not None:
        return _zero_edge_score(edge.edge_id, invalidation_logic.error)
    if invalidation_logic.satisfied:
        return _zero_edge_score(edge.edge_id, "invalidation_active")

    exit_logic = _evaluate_logic(edge.exit_logic, feature_values)
    if exit_logic.error is not None:
        return _zero_edge_score(edge.edge_id, exit_logic.error)
    if exit_logic.satisfied:
        return _zero_edge_score(edge.edge_id, "exit_signal_active")

    regime_score = _round_score(float(regime_payload["confidence"]))
    signal_score = _round_score(entry_logic.score)
    risk_score = _risk_score(edge, regime_payload)
    confirmation_score = _confirmation_score(regime_payload, exit_logic, invalidation_logic)
    total_score = _round_score(
        regime_score * EDGE_REGIME_WEIGHT
        + signal_score * EDGE_SIGNAL_WEIGHT
        + risk_score * EDGE_RISK_WEIGHT
        + confirmation_score * EDGE_CONFIRMATION_WEIGHT
    )

    components = EdgeScoreComponents(
        regime_score=regime_score,
        signal_score=signal_score,
        risk_score=risk_score,
        confirmation_score=confirmation_score,
    )
    explanation = (
        f"regime_score={regime_score:.4f}; signal_score={signal_score:.4f};"
        f" risk_score={risk_score:.4f}; confirmation_score={confirmation_score:.4f};"
        f" total_score={total_score:.4f}; regime={regime_label};"
        f" entry={'; '.join(entry_logic.explanations)}"
    )
    return EdgeScoreResult(edge.edge_id, total_score, components, explanation)


def score_edges(
    registry: EdgeRegistry,
    regime: MarketRegime | Mapping[str, Any],
    bars: Sequence[OHLCVBar],
) -> tuple[EdgeScoreResult, ...]:
    results = [score_edge(edge, regime, bars) for edge in registry.list_active_edges()]
    results.sort(key=lambda item: item.edge_id)
    return tuple(results)


def _safe(val: float | None, default: float = 0.0) -> float:
    if val is None or val != val:  # None or NaN
        return default
    return float(val)


def _momentum_signal(returns: float) -> float:
    """Normalize 20-bar return to [-1, 1]. Cap at ±10%."""
    capped = max(-0.10, min(0.10, returns))
    return capped / 0.10


def _trend_signal(ema_20: float, sma_50: float) -> float:
    """EMA20 vs SMA50 crossover signal. Normalized to [-1, 1]."""
    if sma_50 <= 0:
        return 0.0
    diff_pct = (ema_20 - sma_50) / sma_50
    return max(-1.0, min(1.0, diff_pct / 0.05))


def _rsi_signal(rsi: float) -> float:
    """RSI mean-reversion signal. Oversold=+1, overbought=-1."""
    rsi = max(0.0, min(100.0, rsi))
    if rsi < 30:
        return 1.0
    if rsi > 70:
        return -1.0
    return (50.0 - rsi) / 50.0


def _vol_penalty(atr: float, price: float) -> float:
    """ATR as % of price. Higher vol → higher penalty [0, 1]."""
    if price <= 0:
        return 0.0
    atr_pct = atr / price
    return min(1.0, atr_pct / 0.10)


def score_symbol(
    symbol: str,
    features: dict[str, list[float | None]],
    last_price: float,
) -> dict[str, Any] | None:
    """Score symbol from pre-computed features only.
    Strict fail-closed: any missing/None/NaN value returns None immediately.
    No default substitution. No silent correction. No bar access.
    """
    def _last(key: str) -> float | None:
        vals = features.get(key)
        if not vals:
            return None
        v = vals[-1]
        if v is None:
            return None
        v = float(v)
        if v != v:  # NaN check
            return None
        return v

    if last_price is None or float(last_price) <= 0:
        return None

    required = ["momentum_20", "ema_20", "sma_50", "rsi_14", "atr_14"]
    for k in required:
        if k not in features or not features[k]:
            return None

    ret = _last("momentum_20")
    if ret is None:
        return None

    ema = _last("ema_20")
    if ema is None:
        return None

    sma = _last("sma_50")
    if sma is None:
        return None

    rsi = _last("rsi_14")
    if rsi is None:
        return None

    atr = _last("atr_14")
    if atr is None:
        return None

    if ema == 0.0 and sma == 0.0:
        return None

    m = _momentum_signal(ret)
    t = _trend_signal(ema, sma)
    r = _rsi_signal(rsi)
    v = _vol_penalty(atr, float(last_price))

    conflict = (m > 0 and t < 0) or (m < 0 and t > 0)
    if conflict:
        score_penalty = 0.30
    else:
        score_penalty = 0.0

    score = W_MOMENTUM * m + W_TREND * t + W_RSI * r - W_VOL_PENALTY * v - score_penalty
    score = round(max(-1.0, min(1.0, score)), 6)

    return {
        "symbol": symbol,
        "score": score,
        "features": {
            "momentum": round(m, 4),
            "trend": round(t, 4),
            "rsi_signal": round(r, 4),
            "vol_penalty": round(v, 4),
        },
        "reason": f"m={m:.2f} t={t:.2f} r={r:.2f} v={v:.2f}",
    }


def rank_symbols(
    scored: list[dict[str, Any]],
    top_n: int = TOP_N,
    threshold: float = SCORE_THRESHOLD,
    force_top: bool = True,
) -> list[dict[str, Any]]:
    """Sort by score descending. Filter below threshold.
    If force_top=True and all filtered: return positive scores; else top_n by score.
    """
    above = [s for s in scored if s["score"] >= threshold]
    above.sort(key=lambda x: x["score"], reverse=True)
    if above:
        return above[:top_n]
    if force_top:
        positive = [s for s in scored if s["score"] > 0]
        positive.sort(key=lambda x: x["score"], reverse=True)
        if positive:
            return positive[:top_n]
        all_sorted = sorted(scored, key=lambda x: x["score"], reverse=True)
        return all_sorted[:top_n]
    return []


__all__ = [
    "EDGE_CONFIRMATION_WEIGHT",
    "EDGE_REGIME_WEIGHT",
    "EDGE_RISK_WEIGHT",
    "EDGE_SIGNAL_WEIGHT",
    "EdgeScoreComponents",
    "EdgeScoreResult",
    "SCORE_THRESHOLD",
    "TOP_N",
    "rank_symbols",
    "score_edge",
    "score_edges",
    "score_symbol",
]
