from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class StrategySpecMarketType(str, Enum):
    USDT_PERP = "usdt_perp"
    INVERSE_PERP = "inverse_perp"
    SPOT = "spot"
    MARGIN = "margin"
    OPTIONS = "options"
    DATED_FUTURES = "dated_futures"


@dataclass(frozen=True)
class StrategySpec:
    schema_version: str
    strategy_id: str
    strategy_version: str
    strategy_family: str
    edge_family: str
    instrument_universe: tuple[str, ...]
    market_type: StrategySpecMarketType
    venue_assumptions: tuple[str, ...]
    timeframe: str
    bar_definition: str
    entry_conditions: tuple[str, ...]
    exit_conditions: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    risk_caps: dict[str, Any]
    data_requirements: dict[str, Any]
    feature_requirements: dict[str, Any]
    latency_sensitivity: str
    funding_sensitivity: str
    fee_model_requirement: str
    slippage_model_requirement: str
    expected_regime: str
    failure_modes: tuple[str, ...]
    kill_switch_triggers: tuple[str, ...]
    telemetry_fields: tuple[str, ...]
    promotion_requirements: tuple[str, ...]


@dataclass(frozen=True)
class StrategySpecValidationResult:
    accepted: bool
    spec: StrategySpec | None
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.needs_research_reasons and self.accepted:
            raise ValueError("accepted must be False when needs_research_reasons is non-empty")


_REQUIRED_FIELDS = (
    "schema_version",
    "strategy_id",
    "strategy_version",
    "strategy_family",
    "edge_family",
    "instrument_universe",
    "market_type",
    "venue_assumptions",
    "timeframe",
    "bar_definition",
    "entry_conditions",
    "exit_conditions",
    "invalidation_conditions",
    "risk_caps",
    "data_requirements",
    "feature_requirements",
    "latency_sensitivity",
    "funding_sensitivity",
    "fee_model_requirement",
    "slippage_model_requirement",
    "expected_regime",
    "failure_modes",
    "kill_switch_triggers",
    "telemetry_fields",
    "promotion_requirements",
)

_UNSUPPORTED_PR1_MARKET_TYPES = {
    StrategySpecMarketType.SPOT,
    StrategySpecMarketType.MARGIN,
    StrategySpecMarketType.OPTIONS,
    StrategySpecMarketType.DATED_FUTURES,
}

_FORBIDDEN_KEY_TOKENS = (
    "live",
    "private_api",
    "credentials",
    "order_router",
    "scheduler",
    "auto_loop",
    "shadow_live_execution",
)

_BIST_LEAKAGE_TOKENS = (
    "bist",
    "bist30",
    "bist100",
    "borsa",
    "kap",
    "ideal",
    "i\u0307deal",
    "matriks",
)


def validate_strategy_spec(payload: Mapping[str, Any]) -> StrategySpecValidationResult:
    if not isinstance(payload, Mapping):
        return _result(False, None, ("strategy_spec:payload_malformed",), ())

    rejection_reasons: list[str] = []
    needs_research_reasons: list[str] = []

    rejection_reasons.extend(_scan_for_forbidden_keys(payload))
    rejection_reasons.extend(_scan_for_bist_leakage(payload))
    rejection_reasons.extend(_missing_required_field_reasons(payload))

    field_values: dict[str, Any] = {}
    field_values["schema_version"] = _non_empty_string(
        payload.get("schema_version"), "schema_version", rejection_reasons
    )
    field_values["strategy_id"] = _non_empty_string(payload.get("strategy_id"), "strategy_id", rejection_reasons)
    field_values["strategy_version"] = _non_empty_string(
        payload.get("strategy_version"), "strategy_version", rejection_reasons
    )
    field_values["strategy_family"] = _non_empty_string(
        payload.get("strategy_family"), "strategy_family", rejection_reasons
    )
    field_values["edge_family"] = _non_empty_string(payload.get("edge_family"), "edge_family", rejection_reasons)
    field_values["timeframe"] = _non_empty_string(payload.get("timeframe"), "timeframe", rejection_reasons)
    field_values["bar_definition"] = _non_empty_string(
        payload.get("bar_definition"), "bar_definition", rejection_reasons
    )
    field_values["latency_sensitivity"] = _non_empty_string(
        payload.get("latency_sensitivity"), "latency_sensitivity", rejection_reasons
    )
    field_values["fee_model_requirement"] = _non_empty_string(
        payload.get("fee_model_requirement"), "fee_model_requirement", rejection_reasons
    )
    field_values["slippage_model_requirement"] = _non_empty_string(
        payload.get("slippage_model_requirement"), "slippage_model_requirement", rejection_reasons
    )
    field_values["expected_regime"] = _non_empty_string(
        payload.get("expected_regime"), "expected_regime", rejection_reasons
    )

    market_type = _market_type(payload.get("market_type"), rejection_reasons)
    instrument_universe = _string_list(payload.get("instrument_universe"), "instrument_universe", rejection_reasons)
    venue_assumptions = _string_list(payload.get("venue_assumptions"), "venue_assumptions", rejection_reasons)
    entry_conditions = _conditions(payload.get("entry_conditions"), "entry_conditions", rejection_reasons)
    exit_conditions = _conditions(payload.get("exit_conditions"), "exit_conditions", rejection_reasons)
    invalidation_conditions = _conditions(
        payload.get("invalidation_conditions"), "invalidation_conditions", rejection_reasons
    )

    risk_caps = _mapping(payload.get("risk_caps"), "risk_caps", rejection_reasons)
    data_requirements = _mapping(payload.get("data_requirements"), "data_requirements", rejection_reasons)
    feature_requirements = _mapping(payload.get("feature_requirements"), "feature_requirements", rejection_reasons)
    failure_modes = _string_list(payload.get("failure_modes"), "failure_modes", rejection_reasons)
    kill_switch_triggers = _string_list(payload.get("kill_switch_triggers"), "kill_switch_triggers", rejection_reasons)
    telemetry_fields = _string_list(payload.get("telemetry_fields"), "telemetry_fields", rejection_reasons)
    promotion_requirements = _string_list(
        payload.get("promotion_requirements"), "promotion_requirements", rejection_reasons
    )

    if not venue_assumptions:
        rejection_reasons.append("strategy_spec:venue_assumptions_missing")
    else:
        for venue_item in venue_assumptions:
            venue_lower = venue_item.lower()
            if any(token in venue_lower for token in _BIST_LEAKAGE_TOKENS):
                rejection_reasons.append("strategy_spec:venue_assumptions_non_crypto")
                break

    _validate_fee_and_slippage(
        field_values.get("fee_model_requirement"), field_values.get("slippage_model_requirement"), rejection_reasons
    )
    funding_sensitivity = _funding_sensitivity(
        payload.get("funding_sensitivity"), rejection_reasons, needs_research_reasons
    )
    _validate_max_leverage(risk_caps, rejection_reasons)

    unique_rejections = tuple(dict.fromkeys(rejection_reasons))
    unique_needs_research = tuple(dict.fromkeys(needs_research_reasons))
    accepted = unique_rejections == () and unique_needs_research == ()
    if not accepted:
        return _result(False, None, unique_rejections, unique_needs_research)

    spec = StrategySpec(
        schema_version=field_values["schema_version"],
        strategy_id=field_values["strategy_id"],
        strategy_version=field_values["strategy_version"],
        strategy_family=field_values["strategy_family"],
        edge_family=field_values["edge_family"],
        instrument_universe=instrument_universe,
        market_type=market_type,
        venue_assumptions=venue_assumptions,
        timeframe=field_values["timeframe"],
        bar_definition=field_values["bar_definition"],
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        invalidation_conditions=invalidation_conditions,
        risk_caps=risk_caps,
        data_requirements=data_requirements,
        feature_requirements=feature_requirements,
        latency_sensitivity=field_values["latency_sensitivity"],
        funding_sensitivity=funding_sensitivity,
        fee_model_requirement=field_values["fee_model_requirement"],
        slippage_model_requirement=field_values["slippage_model_requirement"],
        expected_regime=field_values["expected_regime"],
        failure_modes=failure_modes,
        kill_switch_triggers=kill_switch_triggers,
        telemetry_fields=telemetry_fields,
        promotion_requirements=promotion_requirements,
    )
    return _result(True, spec, (), ())


def strategy_spec_to_dict(spec: StrategySpec) -> dict[str, Any]:
    return {
        "schema_version": spec.schema_version,
        "strategy_id": spec.strategy_id,
        "strategy_version": spec.strategy_version,
        "strategy_family": spec.strategy_family,
        "edge_family": spec.edge_family,
        "instrument_universe": list(spec.instrument_universe),
        "market_type": spec.market_type.value,
        "venue_assumptions": list(spec.venue_assumptions),
        "timeframe": spec.timeframe,
        "bar_definition": spec.bar_definition,
        "entry_conditions": list(spec.entry_conditions),
        "exit_conditions": list(spec.exit_conditions),
        "invalidation_conditions": list(spec.invalidation_conditions),
        "risk_caps": dict(spec.risk_caps),
        "data_requirements": dict(spec.data_requirements),
        "feature_requirements": dict(spec.feature_requirements),
        "latency_sensitivity": spec.latency_sensitivity,
        "funding_sensitivity": spec.funding_sensitivity,
        "fee_model_requirement": spec.fee_model_requirement,
        "slippage_model_requirement": spec.slippage_model_requirement,
        "expected_regime": spec.expected_regime,
        "failure_modes": list(spec.failure_modes),
        "kill_switch_triggers": list(spec.kill_switch_triggers),
        "telemetry_fields": list(spec.telemetry_fields),
        "promotion_requirements": list(spec.promotion_requirements),
    }


def strategy_spec_from_dict(payload: Mapping[str, Any]) -> StrategySpecValidationResult:
    return validate_strategy_spec(payload)


def canonical_strategy_spec_json(spec: StrategySpec) -> str:
    return json.dumps(strategy_spec_to_dict(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def strategy_spec_digest(spec: StrategySpec) -> str:
    canonical = canonical_strategy_spec_json(spec)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _result(
    accepted: bool,
    spec: StrategySpec | None,
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
) -> StrategySpecValidationResult:
    if needs_research_reasons:
        accepted = False
    return StrategySpecValidationResult(
        accepted=accepted,
        spec=spec,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
    )


def _missing_required_field_reasons(payload: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field_name in _REQUIRED_FIELDS:
        if field_name not in payload:
            reasons.append(f"strategy_spec:{field_name}_missing")
    return reasons


def _non_empty_string(value: object, field_name: str, reasons: list[str]) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        reasons.append(f"strategy_spec:{field_name}_malformed")
        return ""
    trimmed = value.strip()
    if not trimmed:
        reasons.append(f"strategy_spec:{field_name}_empty")
        return ""
    return trimmed


def _string_list(value: object, field_name: str, reasons: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        reasons.append(f"strategy_spec:{field_name}_malformed")
        return ()
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            reasons.append(f"strategy_spec:{field_name}_malformed")
            return ()
        parsed.append(item.strip())
    if not parsed:
        reasons.append(f"strategy_spec:{field_name}_empty")
        return ()
    return tuple(parsed)


def _conditions(value: object, field_name: str, reasons: list[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        if not value.strip():
            reasons.append(f"strategy_spec:{field_name}_empty")
            return ()
        return (value.strip(),)
    if isinstance(value, list | tuple):
        parsed = _string_list(value, field_name, reasons)
        if not parsed:
            reasons.append(f"strategy_spec:{field_name}_empty")
        return parsed
    reasons.append(f"strategy_spec:{field_name}_malformed")
    return ()


def _market_type(value: object, reasons: list[str]) -> StrategySpecMarketType:
    if not isinstance(value, str):
        reasons.append("strategy_spec:market_type_malformed")
        return StrategySpecMarketType.USDT_PERP
    normalized = value.strip().lower()
    try:
        market_type = StrategySpecMarketType(normalized)
    except ValueError:
        reasons.append("strategy_spec:market_type_unknown")
        return StrategySpecMarketType.USDT_PERP
    if market_type in _UNSUPPORTED_PR1_MARKET_TYPES:
        reasons.append("strategy_spec:market_type_unsupported_pr1")
    return market_type


def _mapping(value: object, field_name: str, reasons: list[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        reasons.append(f"strategy_spec:{field_name}_malformed")
        return {}
    if not value:
        reasons.append(f"strategy_spec:{field_name}_empty")
        return {}
    return dict(value)


def _validate_fee_and_slippage(
    fee_model_requirement: str | None,
    slippage_model_requirement: str | None,
    reasons: list[str],
) -> None:
    _validate_non_zero_requirement("fee_model_requirement", fee_model_requirement, reasons)
    _validate_non_zero_requirement("slippage_model_requirement", slippage_model_requirement, reasons)


def _validate_non_zero_requirement(field_name: str, value: object, reasons: list[str]) -> None:
    if value is None:
        reasons.append(f"strategy_spec:{field_name}_missing")
        return
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "none", "0", "zero", "free"}:
            reasons.append(f"strategy_spec:{field_name}_invalid")
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        reasons.append(f"strategy_spec:{field_name}_malformed")
        return
    if float(value) == 0.0:
        reasons.append(f"strategy_spec:{field_name}_invalid")


def _funding_sensitivity(value: object, reasons: list[str], needs_research_reasons: list[str]) -> str:
    if value is None:
        reasons.append("strategy_spec:funding_sensitivity_missing")
        return ""
    if not isinstance(value, str):
        reasons.append("strategy_spec:funding_sensitivity_malformed")
        return ""
    normalized = value.strip()
    if not normalized:
        reasons.append("strategy_spec:funding_sensitivity_missing")
        return ""
    if normalized.lower() in {"unknown", "needs_research", "none"}:
        needs_research_reasons.append("strategy_spec:funding_sensitivity_needs_research")
    return normalized


def _validate_max_leverage(risk_caps: Mapping[str, Any], reasons: list[str]) -> None:
    max_leverage = risk_caps.get("max_leverage") if isinstance(risk_caps, Mapping) else None
    if max_leverage is None:
        reasons.append("strategy_spec:max_leverage_missing")
        return
    if isinstance(max_leverage, bool) or not isinstance(max_leverage, int | float):
        reasons.append("strategy_spec:max_leverage_malformed")
        return
    leverage_value = float(max_leverage)
    if leverage_value <= 0.0:
        reasons.append("strategy_spec:max_leverage_invalid")
        return
    if leverage_value > 3.0:
        reasons.append("strategy_spec:max_leverage_exceeds_cap")


def _scan_for_forbidden_keys(payload: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str):
                    key_lower = key.lower()
                    for forbidden in _FORBIDDEN_KEY_TOKENS:
                        if forbidden in key_lower:
                            reasons.append(f"strategy_spec:forbidden_field_{forbidden}")
                _walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                _walk(item)

    _walk(payload)
    return reasons


def _scan_for_bist_leakage(payload: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []

    def _has_leakage(text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in _BIST_LEAKAGE_TOKENS)

    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str) and _has_leakage(key):
                    reasons.append("strategy_spec:bist_scope_leakage")
                _walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                _walk(item)
        elif isinstance(node, str) and _has_leakage(node):
            reasons.append("strategy_spec:bist_scope_leakage")

    _walk(payload)
    return reasons
