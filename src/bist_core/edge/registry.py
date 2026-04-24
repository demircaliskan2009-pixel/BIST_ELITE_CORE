from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Iterable, Sequence

from bist_core.features.feature_registry import list_features

IMKBH_UNIVERSE = "IMKBH"
ALLOWED_REGIMES = ("bull", "bear", "sideways", "trend", "range")
ALLOWED_MATCH_MODES = ("all", "any")
ALLOWED_OPERATORS = (">", ">=", "<", "<=", "==", "!=", "in", "not_in")
RAW_BAR_FIELDS = ("open", "high", "low", "close", "volume", "timestamp")
CONTROL_REFERENCE_FIELDS = ("regime", "entry_price", "bars_since_entry")
ALLOWED_RISK_BUCKETS = ("low", "medium", "high")
ALLOWED_TIMEFRAMES = ("01", "05", "15", "30", "60", "1m", "5m", "15m", "30m", "60m", "G", "1d", "daily", "1w", "weekly")
NON_DETERMINISTIC_TOKENS = (
    "random",
    "rand",
    "maybe",
    "discretionary",
    "subjective",
    "heuristic",
    "approx",
    "approximately",
    "ai",
    "llm",
)
LEAKAGE_TOKENS = (
    "future",
    "forward_return",
    "future_return",
    "next_bar",
    "next_close",
    "next_open",
    "lead_return",
    "leading_return",
    "leakage",
    "tomorrow",
    "realized_pnl",
    "realized_return",
    "target_label",
    "label",
    "outcome",
)
FEATURE_BAR_FIELD_DEPENDENCIES = {
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "volume": ("volume",),
    "timestamp": ("timestamp",),
    "sma_20": ("close",),
    "sma_50": ("close",),
    "ema_20": ("close",),
    "rsi_14": ("close",),
    "atr_14": ("high", "low", "close"),
    "returns": ("close",),
    "momentum_20": ("close",),
}


@dataclass(frozen=True)
class EdgeCondition:
    left: str
    operator: str
    right: float | int | str | tuple[str, ...]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "operator": self.operator,
            "right": self.right,
            "description": self.description,
        }


@dataclass(frozen=True)
class EdgeLogic:
    match: str
    conditions: tuple[EdgeCondition, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "match": self.match,
            "conditions": [condition.to_dict() for condition in self.conditions],
        }


@dataclass(frozen=True)
class EdgeRiskProfile:
    volatility_bucket: str
    max_expected_drawdown_pct: float
    max_holding_bars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "volatility_bucket": self.volatility_bucket,
            "max_expected_drawdown_pct": self.max_expected_drawdown_pct,
            "max_holding_bars": self.max_holding_bars,
        }


@dataclass(frozen=True)
class EdgeRequiredData:
    universe: str
    timeframe: str
    bar_fields: tuple[str, ...]
    min_history_bars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe": self.universe,
            "timeframe": self.timeframe,
            "bar_fields": list(self.bar_fields),
            "min_history_bars": self.min_history_bars,
        }


@dataclass(frozen=True)
class EdgeDefinition:
    edge_id: str
    hypothesis: str
    feature_set: tuple[str, ...]
    regime_applicability: tuple[str, ...]
    entry_logic: EdgeLogic
    exit_logic: EdgeLogic
    invalidation_conditions: EdgeLogic
    risk_profile: EdgeRiskProfile
    required_data: EdgeRequiredData
    enabled: bool = True
    disabled_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "hypothesis": self.hypothesis,
            "feature_set": list(self.feature_set),
            "regime_applicability": list(self.regime_applicability),
            "entry_logic": self.entry_logic.to_dict(),
            "exit_logic": self.exit_logic.to_dict(),
            "invalidation_conditions": self.invalidation_conditions.to_dict(),
            "risk_profile": self.risk_profile.to_dict(),
            "required_data": self.required_data.to_dict(),
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
        }


@dataclass(frozen=True)
class EdgeValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def _defined_feature_names() -> tuple[str, ...]:
    names = set(list_features())
    names.update(RAW_BAR_FIELDS)
    return tuple(sorted(names))


def _contains_non_deterministic_language(value: str) -> bool:
    lowered = str(value or "").strip().casefold()
    if not lowered:
        return False
    words = set(re.findall(r"[a-z0-9_]+", lowered))
    return any(token in words for token in NON_DETERMINISTIC_TOKENS)


def _contains_leakage_language(value: str) -> bool:
    lowered = str(value or "").strip().casefold()
    if not lowered:
        return False
    words = set(re.findall(r"[a-z0-9_]+", lowered))
    return any(token in words for token in LEAKAGE_TOKENS)


def _edge_logic_fields(feature_set: Sequence[str]) -> set[str]:
    return set(feature_set) | set(CONTROL_REFERENCE_FIELDS)


def _validate_condition(
    condition: EdgeCondition,
    *,
    logic_name: str,
    feature_set: Sequence[str],
) -> list[str]:
    errors: list[str] = []
    allowed_logic_fields = _edge_logic_fields(feature_set)

    left = str(condition.left or "").strip()
    if not left:
        errors.append(f"{logic_name}: condition.left is required")
    elif left not in allowed_logic_fields:
        errors.append(f"{logic_name}: undefined left operand {left!r}")

    operator = str(condition.operator or "").strip()
    if operator not in ALLOWED_OPERATORS:
        errors.append(f"{logic_name}: ambiguous operator {operator!r}")

    description = str(condition.description or "").strip()
    if not description:
        errors.append(f"{logic_name}: condition description is required")
    elif _contains_non_deterministic_language(description):
        errors.append(f"{logic_name}: non-deterministic language in description {description!r}")
    elif _contains_leakage_language(description):
        errors.append(f"{logic_name}: leakage language in description {description!r}")

    right = condition.right
    if operator in {"in", "not_in"}:
        values = right if isinstance(right, tuple) else (right,)
        if left != "regime":
            errors.append(f"{logic_name}: operator {operator!r} is only supported for regime checks")
        for value in values:
            token = str(value or "").strip()
            if token not in ALLOWED_REGIMES:
                errors.append(f"{logic_name}: unsupported regime value {token!r}")
        return errors

    if isinstance(right, tuple):
        errors.append(f"{logic_name}: tuple right operand requires 'in' or 'not_in' operator")
        return errors

    if left == "regime":
        token = str(right or "").strip()
        if token not in ALLOWED_REGIMES:
            errors.append(f"{logic_name}: unsupported regime comparator {token!r}")
        return errors

    if isinstance(right, str):
        token = right.strip()
        if _contains_non_deterministic_language(token):
            errors.append(f"{logic_name}: non-deterministic right operand {token!r}")
        elif _contains_leakage_language(token):
            errors.append(f"{logic_name}: leakage right operand {token!r}")
        elif token not in allowed_logic_fields:
            errors.append(f"{logic_name}: undefined right operand {token!r}")
    elif not isinstance(right, (int, float)):
        errors.append(f"{logic_name}: unsupported right operand type {type(right).__name__}")

    return errors


def _validate_logic(logic: EdgeLogic, *, logic_name: str, feature_set: Sequence[str]) -> list[str]:
    errors: list[str] = []
    if logic.match not in ALLOWED_MATCH_MODES:
        errors.append(f"{logic_name}: invalid match mode {logic.match!r}")
    if not logic.conditions:
        errors.append(f"{logic_name}: at least one condition is required")
    for condition in logic.conditions:
        errors.extend(_validate_condition(condition, logic_name=logic_name, feature_set=feature_set))
    return errors


def _validate_feature_set(feature_set: Sequence[str]) -> list[str]:
    errors: list[str] = []
    defined = set(_defined_feature_names())
    if not feature_set:
        errors.append("feature_set is required")
        return errors

    seen: set[str] = set()
    for feature in feature_set:
        name = str(feature or "").strip()
        if not name:
            errors.append("feature_set contains empty feature name")
            continue
        if name in seen:
            errors.append(f"feature_set contains duplicate feature {name!r}")
            continue
        seen.add(name)
        if _contains_leakage_language(name):
            errors.append(f"feature_set contains leakage-prone feature {name!r}")
            continue
        if name not in defined:
            errors.append(f"feature_set contains undefined feature {name!r}")
    return errors


def _validate_feature_dependencies(feature_set: Sequence[str], bar_fields: Sequence[str]) -> list[str]:
    errors: list[str] = []
    available = {str(field).strip() for field in bar_fields}
    for feature in feature_set:
        name = str(feature).strip()
        required_fields = FEATURE_BAR_FIELD_DEPENDENCIES.get(name)
        if not required_fields:
            continue
        missing = [field for field in required_fields if field not in available]
        if missing:
            errors.append(
                f"feature_set feature {name!r} requires bar_fields {tuple(required_fields)!r}; missing {tuple(missing)!r}"
            )
    return errors


def _validate_timeframe(timeframe: str) -> list[str]:
    errors: list[str] = []
    token = str(timeframe or "").strip()
    if not token:
        errors.append("required_data.timeframe is required")
        return errors
    if any(separator in token for separator in (",", "+", "/", "|", " ")):
        errors.append(f"required_data.timeframe must describe a single timeframe, got {token!r}")
        return errors
    if token not in ALLOWED_TIMEFRAMES:
        errors.append(f"required_data.timeframe {token!r} is unsupported")
    return errors


def _extract_regime_guard(logic: EdgeLogic) -> tuple[str, tuple[str, ...]] | None:
    for condition in logic.conditions:
        if str(condition.left).strip() != "regime":
            continue
        operator = str(condition.operator).strip()
        if operator == "in":
            values = condition.right if isinstance(condition.right, tuple) else (condition.right,)
            return operator, tuple(str(value).strip() for value in values)
        if operator == "==":
            return operator, (str(condition.right).strip(),)
        if operator == "not_in":
            values = condition.right if isinstance(condition.right, tuple) else (condition.right,)
            return operator, tuple(str(value).strip() for value in values)
        if operator == "!=":
            return operator, (str(condition.right).strip(),)
    return None


def _validate_regime_transition_rules(edge: EdgeDefinition) -> list[str]:
    errors: list[str] = []
    applicable = tuple(str(item).strip() for item in edge.regime_applicability)

    entry_guard = _extract_regime_guard(edge.entry_logic)
    if entry_guard is None:
        errors.append("entry_logic must contain an explicit regime guard")
    else:
        operator, values = entry_guard
        entry_values = set(values)
        applicable_values = set(applicable)
        if operator not in {"in", "=="}:
            errors.append("entry_logic regime guard must use 'in' or '=='")
        elif not entry_values or not entry_values.issubset(applicable_values):
            errors.append("entry_logic regime guard must be a subset of regime_applicability")

    invalidation_guard = _extract_regime_guard(edge.invalidation_conditions)
    if invalidation_guard is None:
        errors.append("invalidation_conditions must contain a regime transition guard")
    else:
        operator, values = invalidation_guard
        value_set = set(values)
        applicable_values = set(applicable)
        if operator == "not_in":
            if value_set != applicable_values:
                errors.append("invalidation_conditions regime guard must mirror regime_applicability via not_in")
        elif operator == "!=":
            if len(applicable_values) != 1 or value_set != applicable_values:
                errors.append("invalidation_conditions '!=' regime guard is only valid for single-regime edges")
        else:
            errors.append("invalidation_conditions regime guard must use 'not_in' or '!='")

    return errors


def _validate_required_data(required_data: EdgeRequiredData) -> list[str]:
    errors: list[str] = []
    if str(required_data.universe or "").strip() != IMKBH_UNIVERSE:
        errors.append(f"required_data.universe must be {IMKBH_UNIVERSE!r}")
    errors.extend(_validate_timeframe(required_data.timeframe))
    if required_data.min_history_bars < 1:
        errors.append("required_data.min_history_bars must be >= 1")
    if not required_data.bar_fields:
        errors.append("required_data.bar_fields is required")
    for field_name in required_data.bar_fields:
        token = str(field_name or "").strip()
        if token not in RAW_BAR_FIELDS:
            errors.append(f"required_data.bar_fields contains unsupported field {token!r}")
    return errors


def _validate_risk_profile(risk_profile: EdgeRiskProfile) -> list[str]:
    errors: list[str] = []
    if risk_profile.volatility_bucket not in ALLOWED_RISK_BUCKETS:
        errors.append(f"risk_profile.volatility_bucket must be one of {ALLOWED_RISK_BUCKETS}")
    if not 0.0 < float(risk_profile.max_expected_drawdown_pct) <= 1.0:
        errors.append("risk_profile.max_expected_drawdown_pct must be in (0, 1]")
    if int(risk_profile.max_holding_bars) < 1:
        errors.append("risk_profile.max_holding_bars must be >= 1")
    return errors


def validate_edge_definition(edge: EdgeDefinition) -> EdgeValidationResult:
    errors: list[str] = []

    edge_id = str(edge.edge_id or "").strip()
    if not edge_id:
        errors.append("edge_id is required")
    elif not edge_id.replace("_", "").isalnum() or edge_id.lower() != edge_id:
        errors.append("edge_id must be lowercase alphanumeric with underscores only")

    if not str(edge.hypothesis or "").strip():
        errors.append("hypothesis is required")
    elif _contains_non_deterministic_language(edge.hypothesis):
        errors.append("hypothesis contains non-deterministic language")
    elif _contains_leakage_language(edge.hypothesis):
        errors.append("hypothesis contains leakage-prone language")

    errors.extend(_validate_feature_set(edge.feature_set))
    errors.extend(_validate_feature_dependencies(edge.feature_set, edge.required_data.bar_fields))

    if not edge.regime_applicability:
        errors.append("regime_applicability is required")
    else:
        for regime in edge.regime_applicability:
            token = str(regime or "").strip()
            if token not in ALLOWED_REGIMES:
                errors.append(f"regime_applicability contains unsupported regime {token!r}")

    errors.extend(_validate_logic(edge.entry_logic, logic_name="entry_logic", feature_set=edge.feature_set))
    errors.extend(_validate_logic(edge.exit_logic, logic_name="exit_logic", feature_set=edge.feature_set))
    errors.extend(
        _validate_logic(
            edge.invalidation_conditions,
            logic_name="invalidation_conditions",
            feature_set=edge.feature_set,
        )
    )
    errors.extend(_validate_risk_profile(edge.risk_profile))
    errors.extend(_validate_required_data(edge.required_data))
    errors.extend(_validate_regime_transition_rules(edge))

    if edge.disabled_reason is not None and not str(edge.disabled_reason).strip():
        errors.append("disabled_reason must be non-empty when provided")

    return EdgeValidationResult(valid=not errors, errors=tuple(errors))


class EdgeRegistry:
    def __init__(self, edges: Iterable[EdgeDefinition] | None = None) -> None:
        self._edges: dict[str, EdgeDefinition] = {}
        for edge in edges or ():
            result = self.add_edge(edge)
            if not result.valid:
                joined = "; ".join(result.errors)
                raise ValueError(f"invalid_edge_definition:{joined}")

    def add_edge(self, edge: EdgeDefinition) -> EdgeValidationResult:
        result = self.validate_edge_structure(edge)
        if not result.valid:
            return result
        if edge.edge_id in self._edges:
            return EdgeValidationResult(valid=False, errors=(f"duplicate edge_id {edge.edge_id!r}",))
        self._edges[edge.edge_id] = edge
        return EdgeValidationResult(valid=True)

    def disable_edge(self, edge_id: str, reason: str) -> bool:
        key = str(edge_id or "").strip()
        note = str(reason or "").strip()
        current = self._edges.get(key)
        if current is None or not note:
            return False
        self._edges[key] = replace(current, enabled=False, disabled_reason=note)
        return True

    def validate_edge_structure(self, edge: EdgeDefinition) -> EdgeValidationResult:
        return validate_edge_definition(edge)

    def list_active_edges(self) -> tuple[EdgeDefinition, ...]:
        active = [edge for edge in self._edges.values() if edge.enabled]
        active.sort(key=lambda item: item.edge_id)
        return tuple(active)

    def list_all_edges(self) -> tuple[EdgeDefinition, ...]:
        edges = list(self._edges.values())
        edges.sort(key=lambda item: item.edge_id)
        return tuple(edges)


def builtin_bist_edges() -> tuple[EdgeDefinition, ...]:
    bear_oversold_snap = EdgeDefinition(
        edge_id="bist_bear_oversold_snap",
        hypothesis=(
            "IMKBH symbols in bear regime can produce an oversold snap setup while price remains below SMA20, "
            "SMA20 remains below SMA50, RSI14 stays oversold, and momentum_20 remains negative."
        ),
        feature_set=("close", "rsi_14", "sma_20", "sma_50", "atr_14", "momentum_20"),
        regime_applicability=("bear",),
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("regime", "in", ("bear",), "Only trade when bear regime is active."),
                EdgeCondition("close", "<", "sma_20", "Price must remain below SMA20 during the snap setup."),
                EdgeCondition("sma_20", "<", "sma_50", "Short trend must remain below structural trend."),
                EdgeCondition("rsi_14", "<=", 30.0, "RSI14 must remain in an oversold state."),
                EdgeCondition("momentum_20", "<", 0.0, "Twenty-bar momentum must remain negative."),
            ),
        ),
        exit_logic=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("close", ">=", "sma_20", "Exit when price mean reverts back to SMA20."),
                EdgeCondition("rsi_14", ">=", 45.0, "Exit when RSI14 normalizes out of the oversold band."),
                EdgeCondition("momentum_20", ">=", 0.0, "Exit when twenty-bar momentum is no longer negative."),
            ),
        ),
        invalidation_conditions=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("regime", "not_in", ("bear",), "Fail closed when bear regime is no longer active."),
                EdgeCondition("close", ">=", "sma_50", "Reject if price recovers above SMA50 structural resistance."),
                EdgeCondition("atr_14", "<=", 0.0, "Reject if ATR14 cannot be computed from valid bars."),
            ),
        ),
        risk_profile=EdgeRiskProfile(
            volatility_bucket="high",
            max_expected_drawdown_pct=0.08,
            max_holding_bars=5,
        ),
        required_data=EdgeRequiredData(
            universe=IMKBH_UNIVERSE,
            timeframe="1d",
            bar_fields=("open", "high", "low", "close", "volume", "timestamp"),
            min_history_bars=60,
        ),
    )

    trend_pullback = EdgeDefinition(
        edge_id="bist_bull_pullback_sma20",
        hypothesis=(
            "IMKBH symbols in bull regime can continue higher after a shallow pullback that holds above SMA20 "
            "while SMA20 remains above SMA50 and momentum_20 stays positive."
        ),
        feature_set=("close", "sma_20", "sma_50", "atr_14", "momentum_20"),
        regime_applicability=("bull",),
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("regime", "in", ("bull",), "Only trade when bull regime is active."),
                EdgeCondition("sma_20", ">", "sma_50", "Short trend must remain above structural trend."),
                EdgeCondition("momentum_20", ">", 0.0, "Twenty-bar momentum must stay positive."),
                EdgeCondition("close", ">=", "sma_20", "Price must hold at or above SMA20 support."),
            ),
        ),
        exit_logic=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("close", "<", "sma_20", "Exit when price loses SMA20 support."),
                EdgeCondition("momentum_20", "<=", 0.0, "Exit when continuation momentum turns non-positive."),
            ),
        ),
        invalidation_conditions=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("regime", "not_in", ("bull",), "Fail closed when bull regime is no longer active."),
                EdgeCondition("atr_14", "<=", 0.0, "Reject if ATR14 cannot be computed from valid bars."),
            ),
        ),
        risk_profile=EdgeRiskProfile(
            volatility_bucket="medium",
            max_expected_drawdown_pct=0.07,
            max_holding_bars=10,
        ),
        required_data=EdgeRequiredData(
            universe=IMKBH_UNIVERSE,
            timeframe="1d",
            bar_fields=("open", "high", "low", "close", "volume", "timestamp"),
            min_history_bars=60,
        ),
    )

    sideways_reversion = EdgeDefinition(
        edge_id="bist_sideways_rsi_reversion",
        hypothesis=(
            "IMKBH symbols in sideways regime can mean revert toward SMA20 after RSI14 reaches an oversold state "
            "while the closing price remains above SMA50 support."
        ),
        feature_set=("close", "sma_20", "sma_50", "rsi_14", "atr_14"),
        regime_applicability=("sideways",),
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("regime", "in", ("sideways",), "Only trade when sideways regime is active."),
                EdgeCondition("close", ">=", "sma_50", "Price must remain above SMA50 structural support."),
                EdgeCondition("close", "<", "sma_20", "Entry requires price below SMA20 mean level."),
                EdgeCondition("rsi_14", "<=", 35.0, "RSI14 must show an oversold reversion state."),
            ),
        ),
        exit_logic=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("close", ">=", "sma_20", "Exit when price reverts back to SMA20."),
                EdgeCondition("rsi_14", ">=", 55.0, "Exit when RSI14 normalizes above the reversion band."),
            ),
        ),
        invalidation_conditions=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("regime", "not_in", ("sideways",), "Fail closed when the market leaves sideways regime."),
                EdgeCondition("close", "<", "sma_50", "Reject if price breaks below SMA50 support."),
                EdgeCondition("atr_14", "<=", 0.0, "Reject if ATR14 cannot be computed from valid bars."),
            ),
        ),
        risk_profile=EdgeRiskProfile(
            volatility_bucket="low",
            max_expected_drawdown_pct=0.05,
            max_holding_bars=7,
        ),
        required_data=EdgeRequiredData(
            universe=IMKBH_UNIVERSE,
            timeframe="1d",
            bar_fields=("open", "high", "low", "close", "volume", "timestamp"),
            min_history_bars=60,
        ),
    )
    return (bear_oversold_snap, trend_pullback, sideways_reversion)


def build_builtin_edge_registry() -> EdgeRegistry:
    return EdgeRegistry(edges=builtin_bist_edges())


__all__ = [
    "ALLOWED_OPERATORS",
    "ALLOWED_REGIMES",
    "ALLOWED_TIMEFRAMES",
    "EdgeCondition",
    "EdgeDefinition",
    "EdgeLogic",
    "EdgeRegistry",
    "EdgeRequiredData",
    "EdgeRiskProfile",
    "EdgeValidationResult",
    "IMKBH_UNIVERSE",
    "build_builtin_edge_registry",
    "builtin_bist_edges",
    "validate_edge_definition",
]
