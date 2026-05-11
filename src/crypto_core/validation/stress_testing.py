"""Deterministic Stage 3 stress-testing validation foundation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

_ALLOWED_SIDES = ("long", "short")
_ALLOWED_SCENARIO_IDS = ("high_vol", "low_liquidity", "flash_crash")
_ALLOWED_GATE_ACTIONS = ("disable_edge", "skip_regime", "reduce_size")


@dataclass(frozen=True)
class StressTrade:
    trade_id: str
    side: Literal["long", "short"]
    entry_notional: float
    gross_pnl_before_costs: float
    realized_slippage_cost: float
    fixed_cost_ex_slippage: float = 0.0
    depth_notional_at_execution: float | None = None
    open_notional_during_event: float | None = None


@dataclass(frozen=True)
class RegimeGateEvidence:
    scenario_id: str
    documented: bool
    gate_id: str
    evidence_ref: str
    gate_action: Literal["disable_edge", "skip_regime", "reduce_size"]


@dataclass(frozen=True)
class StressScenario:
    scenario_id: Literal["high_vol", "low_liquidity", "flash_crash"]
    return_scale: float
    slippage_scale: float
    depth_scale: float | None = None
    adverse_gap_pct: float | None = None
    recovery_minutes: int | None = None
    allows_regime_gate: bool = False


@dataclass(frozen=True)
class StressScenarioResult:
    scenario_id: str
    trade_count: int
    tested_notional: float
    total_stressed_pnl: float
    stressed_expectancy: float
    mean_slippage_penalty: float
    mean_gap_penalty: float
    max_depth_usage_ratio: float | None
    passed: bool
    regime_gate_used: bool
    passed_with_regime_gate: bool
    rejection_reason: str | None


@dataclass(frozen=True)
class StressValidationResult:
    all_passed: bool
    scenario_results: tuple[StressScenarioResult, ...]
    rejection_reasons: tuple[str, ...]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _trade_reason(index: int, code: str) -> str:
    return f"trade[{index}]:{code}"


def _scenario_reason(index: int, code: str) -> str:
    return f"scenario[{index}]:{code}"


def _regime_gate_reason(index: int, code: str) -> str:
    return f"regime_gate[{index}]:{code}"


def _validate_trade(trade: StressTrade | None, index: int) -> tuple[str, ...]:
    if not isinstance(trade, StressTrade):
        return (_trade_reason(index, "malformed"),)
    reasons: list[str] = []
    if not _is_non_empty_str(trade.trade_id):
        reasons.append(_trade_reason(index, "empty_trade_id"))
    if trade.side not in _ALLOWED_SIDES:
        reasons.append(_trade_reason(index, "invalid_side"))
    if not _is_number(trade.entry_notional) or float(trade.entry_notional) <= 0.0:
        reasons.append(_trade_reason(index, "malformed_entry_notional"))
    if not _is_number(trade.gross_pnl_before_costs):
        reasons.append(_trade_reason(index, "malformed_gross_pnl_before_costs"))
    if not _is_number(trade.realized_slippage_cost) or float(trade.realized_slippage_cost) < 0.0:
        reasons.append(_trade_reason(index, "malformed_realized_slippage_cost"))
    if not _is_number(trade.fixed_cost_ex_slippage) or float(trade.fixed_cost_ex_slippage) < 0.0:
        reasons.append(_trade_reason(index, "malformed_fixed_cost_ex_slippage"))
    return tuple(reasons)


def _validate_scenario(scenario: StressScenario | None, index: int) -> tuple[str, ...]:
    if not isinstance(scenario, StressScenario):
        return (_scenario_reason(index, "malformed"),)
    reasons: list[str] = []
    if scenario.scenario_id not in _ALLOWED_SCENARIO_IDS:
        reasons.append(_scenario_reason(index, "unknown_scenario_id"))
    if not _is_number(scenario.return_scale) or float(scenario.return_scale) <= 0.0:
        reasons.append(_scenario_reason(index, "malformed_return_scale"))
    if not _is_number(scenario.slippage_scale) or float(scenario.slippage_scale) <= 0.0:
        reasons.append(_scenario_reason(index, "malformed_slippage_scale"))
    if not isinstance(scenario.allows_regime_gate, bool):
        reasons.append(_scenario_reason(index, "malformed_allows_regime_gate"))
    if scenario.scenario_id == "high_vol":
        if scenario.depth_scale is not None:
            reasons.append(_scenario_reason(index, "unexpected_depth_scale"))
        if scenario.adverse_gap_pct is not None:
            reasons.append(_scenario_reason(index, "unexpected_adverse_gap_pct"))
        if scenario.recovery_minutes is not None:
            reasons.append(_scenario_reason(index, "unexpected_recovery_minutes"))
        if scenario.allows_regime_gate:
            reasons.append(_scenario_reason(index, "unexpected_regime_gate"))
    elif scenario.scenario_id == "low_liquidity":
        if not _is_number(scenario.depth_scale) or float(scenario.depth_scale) <= 0.0:
            reasons.append(_scenario_reason(index, "malformed_depth_scale"))
        if scenario.adverse_gap_pct is not None:
            reasons.append(_scenario_reason(index, "unexpected_adverse_gap_pct"))
        if scenario.recovery_minutes is not None:
            reasons.append(_scenario_reason(index, "unexpected_recovery_minutes"))
        if scenario.allows_regime_gate:
            reasons.append(_scenario_reason(index, "unexpected_regime_gate"))
    elif scenario.scenario_id == "flash_crash":
        if scenario.depth_scale is not None:
            reasons.append(_scenario_reason(index, "unexpected_depth_scale"))
        if not _is_number(scenario.adverse_gap_pct) or float(scenario.adverse_gap_pct) < 0.0:
            reasons.append(_scenario_reason(index, "malformed_adverse_gap_pct"))
        if not isinstance(scenario.recovery_minutes, int) or isinstance(scenario.recovery_minutes, bool):
            reasons.append(_scenario_reason(index, "malformed_recovery_minutes"))
        elif scenario.recovery_minutes <= 0:
            reasons.append(_scenario_reason(index, "malformed_recovery_minutes"))
    return tuple(reasons)


def _validate_regime_gate(gate: RegimeGateEvidence | None, index: int) -> tuple[str, ...]:
    if not isinstance(gate, RegimeGateEvidence):
        return (_regime_gate_reason(index, "malformed"),)
    reasons: list[str] = []
    if gate.scenario_id != "flash_crash":
        reasons.append(_regime_gate_reason(index, "invalid_scenario_id"))
    if gate.documented is not True:
        reasons.append(_regime_gate_reason(index, "undocumented"))
    if not _is_non_empty_str(gate.gate_id):
        reasons.append(_regime_gate_reason(index, "empty_gate_id"))
    if not _is_non_empty_str(gate.evidence_ref):
        reasons.append(_regime_gate_reason(index, "empty_evidence_ref"))
    if gate.gate_action not in _ALLOWED_GATE_ACTIONS:
        reasons.append(_regime_gate_reason(index, "invalid_gate_action"))
    return tuple(reasons)


def _failed_scenario_result(
    scenario_id: str,
    trade_count: int,
    tested_notional: float,
    rejection_reason: str,
) -> StressScenarioResult:
    return StressScenarioResult(
        scenario_id=scenario_id,
        trade_count=trade_count,
        tested_notional=tested_notional,
        total_stressed_pnl=0.0,
        stressed_expectancy=0.0,
        mean_slippage_penalty=0.0,
        mean_gap_penalty=0.0,
        max_depth_usage_ratio=None,
        passed=False,
        regime_gate_used=False,
        passed_with_regime_gate=False,
        rejection_reason=rejection_reason,
    )


def default_stress_scenarios() -> tuple[StressScenario, StressScenario, StressScenario]:
    return (
        StressScenario(
            scenario_id="high_vol",
            return_scale=1.5,
            slippage_scale=2.0,
            depth_scale=None,
            adverse_gap_pct=None,
            recovery_minutes=None,
            allows_regime_gate=False,
        ),
        StressScenario(
            scenario_id="low_liquidity",
            return_scale=1.0,
            slippage_scale=3.0,
            depth_scale=0.2,
            adverse_gap_pct=None,
            recovery_minutes=None,
            allows_regime_gate=False,
        ),
        StressScenario(
            scenario_id="flash_crash",
            return_scale=1.0,
            slippage_scale=3.0,
            depth_scale=None,
            adverse_gap_pct=0.10,
            recovery_minutes=5,
            allows_regime_gate=True,
        ),
    )


def _evaluate_scenario(
    trades: tuple[StressTrade, ...],
    scenario: StressScenario,
    has_valid_flash_crash_gate: bool,
) -> StressScenarioResult:
    tested_notional = math.fsum(float(trade.entry_notional) for trade in trades)
    trade_count = len(trades)
    total_stressed_pnl = 0.0
    total_slippage_penalty = 0.0
    total_gap_penalty = 0.0
    max_depth_usage_ratio: float | None = None
    for trade in trades:
        gap_penalty = 0.0
        if scenario.scenario_id == "low_liquidity":
            if not _is_number(trade.depth_notional_at_execution) or float(trade.depth_notional_at_execution) <= 0.0:
                return _failed_scenario_result(
                    scenario.scenario_id,
                    trade_count,
                    tested_notional,
                    "low_liquidity:missing_depth_notional_at_execution",
                )
            stressed_depth = float(trade.depth_notional_at_execution) * float(scenario.depth_scale)
            if stressed_depth <= 0.0:
                return _failed_scenario_result(
                    scenario.scenario_id,
                    trade_count,
                    tested_notional,
                    "low_liquidity:missing_depth_notional_at_execution",
                )
            depth_usage_ratio = float(trade.entry_notional) / stressed_depth
            if max_depth_usage_ratio is None or depth_usage_ratio > max_depth_usage_ratio:
                max_depth_usage_ratio = depth_usage_ratio
        if scenario.scenario_id == "flash_crash":
            if not _is_number(trade.open_notional_during_event) or float(trade.open_notional_during_event) < 0.0:
                return _failed_scenario_result(
                    scenario.scenario_id,
                    trade_count,
                    tested_notional,
                    "flash_crash:missing_open_notional_during_event",
                )
            gap_penalty = float(scenario.adverse_gap_pct) * float(trade.open_notional_during_event)
        slippage_penalty = float(scenario.slippage_scale) * float(trade.realized_slippage_cost)
        total_slippage_penalty += slippage_penalty
        total_gap_penalty += gap_penalty
        total_stressed_pnl += (
            float(scenario.return_scale) * float(trade.gross_pnl_before_costs)
            - slippage_penalty
            - float(trade.fixed_cost_ex_slippage)
            - gap_penalty
        )
    stressed_expectancy = total_stressed_pnl / tested_notional
    mean_slippage_penalty = total_slippage_penalty / trade_count
    mean_gap_penalty = total_gap_penalty / trade_count
    passed = stressed_expectancy >= 0.0
    regime_gate_used = False
    passed_with_regime_gate = False
    rejection_reason: str | None = None
    if not passed:
        if scenario.scenario_id == "flash_crash" and scenario.allows_regime_gate and has_valid_flash_crash_gate:
            passed = True
            regime_gate_used = True
            passed_with_regime_gate = True
        else:
            rejection_reason = f"{scenario.scenario_id}:negative_expectancy"
    return StressScenarioResult(
        scenario_id=scenario.scenario_id,
        trade_count=trade_count,
        tested_notional=tested_notional,
        total_stressed_pnl=total_stressed_pnl,
        stressed_expectancy=stressed_expectancy,
        mean_slippage_penalty=mean_slippage_penalty,
        mean_gap_penalty=mean_gap_penalty,
        max_depth_usage_ratio=max_depth_usage_ratio,
        passed=passed,
        regime_gate_used=regime_gate_used,
        passed_with_regime_gate=passed_with_regime_gate,
        rejection_reason=rejection_reason,
    )


def validate_stress_testing(
    trades: list[StressTrade | None] | tuple[StressTrade | None, ...] | None,
    scenarios: list[StressScenario | None] | tuple[StressScenario | None, ...] | None = None,
    regime_gates: list[RegimeGateEvidence | None] | tuple[RegimeGateEvidence | None, ...] | None = (),
) -> StressValidationResult:
    governance_errors: list[str] = []
    if regime_gates is None:
        ordered_regime_gates: tuple[RegimeGateEvidence | None, ...] = ()
    else:
        try:
            ordered_regime_gates = tuple(regime_gates)
        except TypeError:
            ordered_regime_gates = ()
            governance_errors.append("regime_gates_unreadable")
    if trades is None:
        for index, gate in enumerate(ordered_regime_gates):
            governance_errors.extend(_validate_regime_gate(gate, index))
        return StressValidationResult(False, (), ("trades_missing", *governance_errors))
    try:
        ordered_trades = tuple(trades)
    except TypeError:
        for index, gate in enumerate(ordered_regime_gates):
            governance_errors.extend(_validate_regime_gate(gate, index))
        return StressValidationResult(False, (), ("trades_unreadable", *governance_errors))
    if not ordered_trades:
        for index, gate in enumerate(ordered_regime_gates):
            governance_errors.extend(_validate_regime_gate(gate, index))
        return StressValidationResult(False, (), ("trades_empty", *governance_errors))
    input_errors: list[str] = []
    seen_trade_ids: set[str] = set()
    valid_trades: list[StressTrade] = []
    for index, trade in enumerate(ordered_trades):
        trade_errors = list(_validate_trade(trade, index))
        if not trade_errors:
            trade_id = str(trade.trade_id)
            if trade_id in seen_trade_ids:
                trade_errors.append(_trade_reason(index, "duplicate_trade_id"))
            else:
                seen_trade_ids.add(trade_id)
                valid_trades.append(trade)
        input_errors.extend(trade_errors)
    for index, gate in enumerate(ordered_regime_gates):
        governance_errors.extend(_validate_regime_gate(gate, index))
    if scenarios is None:
        ordered_scenarios = default_stress_scenarios()
    else:
        try:
            ordered_scenarios = tuple(scenarios)
        except TypeError:
            return StressValidationResult(
                False,
                (),
                (*input_errors, "scenarios_unreadable", *governance_errors),
            )
    if not ordered_scenarios:
        return StressValidationResult(False, (), (*input_errors, "scenarios_empty", *governance_errors))
    scenario_definition_errors: list[str] = []
    for index, scenario in enumerate(ordered_scenarios):
        scenario_definition_errors.extend(_validate_scenario(scenario, index))
    if input_errors or scenario_definition_errors:
        return StressValidationResult(
            False,
            (),
            (*input_errors, *scenario_definition_errors, *governance_errors),
        )
    has_valid_flash_crash_gate = any(
        gate is not None
        and isinstance(gate, RegimeGateEvidence)
        and not _validate_regime_gate(gate, index)
        and gate.scenario_id == "flash_crash"
        for index, gate in enumerate(ordered_regime_gates)
    )
    scenario_results = tuple(
        _evaluate_scenario(tuple(valid_trades), scenario, has_valid_flash_crash_gate) for scenario in ordered_scenarios
    )
    scenario_rejection_reasons = tuple(
        result.rejection_reason for result in scenario_results if result.rejection_reason is not None
    )
    rejection_reasons = (*scenario_rejection_reasons, *governance_errors)
    return StressValidationResult(
        all_passed=not rejection_reasons,
        scenario_results=scenario_results,
        rejection_reasons=rejection_reasons,
    )
