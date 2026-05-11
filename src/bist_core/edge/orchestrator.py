from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from bist_core.brain.regime_engine import RegimeEngine
from bist_core.edge.allocation import (
    CapitalAllocationConfig,
    CapitalAllocationResult,
    allocate_capital_to_edge,
)
from bist_core.edge.paper_trading import PaperTradingConfig, PaperTradingResult, run_edge_paper_trading
from bist_core.edge.registry import EdgeDefinition
from bist_core.edge.self_healing import (
    AutoEdgeKillerConfig,
    EdgeState,
    EdgeStateStore,
    evaluate_edge_state,
)
from bist_core.edge.selection import select_best_edge
from bist_core.edge.validation import (
    EdgeRobustnessConfig,
    EdgeRobustnessResult,
    EdgeValidationConfig,
    EdgeValidationResult,
    run_edge_robustness_validation,
    run_edge_validation_backtest,
)
from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp


@dataclass(frozen=True)
class PRDV3MasterOrchestratorConfig:
    validation_config: EdgeValidationConfig = field(default_factory=EdgeValidationConfig)
    robustness_config: EdgeRobustnessConfig = field(default_factory=EdgeRobustnessConfig)
    auto_edge_killer_config: AutoEdgeKillerConfig = field(default_factory=AutoEdgeKillerConfig)
    allocation_config: CapitalAllocationConfig = field(default_factory=CapitalAllocationConfig)
    paper_trading_config: PaperTradingConfig = field(default_factory=PaperTradingConfig)
    edge_state_store_path: str | Path | None = None


@dataclass(frozen=True)
class PRDV3MasterOrchestratorEdgeEvaluation:
    edge_id: str
    validation_result: EdgeValidationResult
    robustness_result: EdgeRobustnessResult
    edge_state: EdgeState

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "validation_result": self.validation_result.to_dict(),
            "robustness_result": self.robustness_result.to_dict(),
            "edge_state": self.edge_state.to_dict(),
        }


@dataclass(frozen=True)
class PRDV3MasterOrchestratorResult:
    valid: bool
    selected_edge_id: str | None
    selected_edge_state: EdgeState | None
    allocation: CapitalAllocationResult
    execution: PaperTradingResult
    reason: str
    regime: str | None
    edge_evaluations: tuple[PRDV3MasterOrchestratorEdgeEvaluation, ...]
    logs: tuple[dict[str, Any], ...]
    contracts: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "selected_edge_id": self.selected_edge_id,
            "selected_edge_state": None if self.selected_edge_state is None else self.selected_edge_state.to_dict(),
            "allocation": self.allocation.to_dict(),
            "execution": self.execution.to_dict(),
            "reason": self.reason,
            "regime": self.regime,
            "edge_evaluations": [evaluation.to_dict() for evaluation in self.edge_evaluations],
            "logs": [dict(log) for log in self.logs],
            "contracts": {key: dict(value) for key, value in self.contracts.items()},
        }


def _round_value(value: float) -> float:
    return round(float(value), 6)


def _blocked_allocation(reason: str) -> CapitalAllocationResult:
    return CapitalAllocationResult(
        approved=False,
        position_size_pct=0.0,
        risk_amount=0.0,
        share_count=0,
        exposure_amount=0.0,
        explanation=f"NO TRADE: {reason}",
        blocked_reason=reason,
    )


def _empty_execution_metrics(initial_capital: float) -> dict[str, Any]:
    return {
        "total_return": 0.0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "max_drawdown": 0.0,
        "entries_filled": 0,
        "closed_trades": 0,
        "open_positions": 0,
        "total_cost": 0.0,
        "final_equity": _round_value(initial_capital),
    }


def _blocked_execution(reason: str, initial_capital: float) -> PaperTradingResult:
    return PaperTradingResult(
        valid=False,
        blocked_reason=reason,
        metrics=_empty_execution_metrics(initial_capital),
        trades=(),
        open_positions=(),
        equity_curve=(),
        logs=(),
    )


def _is_finite_positive(value: float) -> bool:
    return math.isfinite(float(value)) and float(value) > 0.0


def _dataset_scope(edges: Sequence[EdgeDefinition], bars: Sequence[OHLCVBar]) -> dict[str, Any]:
    symbols = sorted({str(bar.symbol or "").strip() for bar in bars if str(bar.symbol or "").strip()})
    universes = sorted({edge.required_data.universe for edge in edges})
    timeframes = sorted({edge.required_data.timeframe for edge in edges})
    return {
        "symbols": symbols,
        "symbol_count": len(symbols),
        "universe": universes[0] if len(universes) == 1 else "MIXED",
        "timeframe": timeframes[0] if len(timeframes) == 1 else "MIXED",
        "granularity": timeframes[0] if len(timeframes) == 1 else "MIXED",
    }


def _data_contract(dataset_scope: dict[str, Any], status: str, validation_evidence: str, next_action: str, blocking_reason: str | None = None) -> dict[str, Any]:
    contract = {
        "stage": "data",
        "status": status,
        "dataset_scope": dataset_scope,
        "ohlcv_schema": {
            "columns": ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        },
        "validation_summary": validation_evidence,
        "anomaly_summary": "none" if status == "SAFE" else (blocking_reason or "unknown"),
        "validation_evidence": validation_evidence,
        "next_action": next_action,
    }
    if blocking_reason is not None:
        contract["blocking_reason"] = blocking_reason
    return contract


def _strategy_contract(
    dataset_scope: dict[str, Any],
    status: str,
    input_eligibility: str,
    feature_summary: str,
    ranking_summary: str,
    signal_summary: str,
    validation_evidence: str,
    next_action: str,
    blocking_reason: str | None = None,
) -> dict[str, Any]:
    contract = {
        "stage": "strategy",
        "status": status,
        "dataset_scope": dataset_scope,
        "input_eligibility": input_eligibility,
        "feature_summary": feature_summary,
        "ranking_summary": ranking_summary,
        "signal_summary": signal_summary,
        "validation_evidence": validation_evidence,
        "next_action": next_action,
    }
    if blocking_reason is not None:
        contract["blocking_reason"] = blocking_reason
    return contract


def _risk_contract(
    dataset_scope: dict[str, Any],
    status: str,
    input_eligibility: str,
    decision_summary: str,
    constraint_summary: str,
    auditability_summary: str,
    validation_evidence: str,
    next_action: str,
    blocking_reason: str | None = None,
) -> dict[str, Any]:
    contract = {
        "stage": "risk",
        "status": status,
        "dataset_scope": dataset_scope,
        "input_eligibility": input_eligibility,
        "decision_summary": decision_summary,
        "constraint_summary": constraint_summary,
        "auditability_summary": auditability_summary,
        "validation_evidence": validation_evidence,
        "next_action": next_action,
    }
    if blocking_reason is not None:
        contract["blocking_reason"] = blocking_reason
    return contract


def _validate_edges(edges: Sequence[EdgeDefinition]) -> str | None:
    if not edges:
        return "invalid_edges:no_enabled_edges"
    edge_ids = [edge.edge_id for edge in edges]
    if len(set(edge_ids)) != len(edge_ids):
        return "invalid_edges:duplicate_edge_id"
    universes = {edge.required_data.universe for edge in edges}
    if len(universes) != 1:
        return "invalid_edges:mixed_universe"
    timeframes = {edge.required_data.timeframe for edge in edges}
    if len(timeframes) != 1:
        return "invalid_edges:mixed_timeframe"
    return None


def _validate_bars(bars: Sequence[OHLCVBar]) -> str | None:
    if not bars:
        return "invalid_bars:empty"
    symbol = str(bars[0].symbol or "").strip()
    if not symbol:
        return "invalid_bars:empty_symbol"
    previous_timestamp: int | None = None
    for bar in bars:
        timestamp = normalize_timestamp(bar.timestamp)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            return "invalid_bars:non_monotonic_timestamps"
        previous_timestamp = timestamp
        if str(bar.symbol or "").strip() != symbol:
            return "invalid_bars:mixed_symbols"
        if any(float(price) <= 0.0 for price in (bar.open, bar.high, bar.low, bar.close)):
            return "invalid_bars:non_positive_price"
        if float(bar.volume) < 0.0:
            return "invalid_bars:negative_volume"
        if float(bar.high) < max(float(bar.open), float(bar.low), float(bar.close)):
            return "invalid_bars:high_below_bar_range"
        if float(bar.low) > min(float(bar.open), float(bar.high), float(bar.close)):
            return "invalid_bars:low_above_bar_range"
    return None


def _load_previous_states(store_path: str | Path | None) -> tuple[dict[str, EdgeState], str | None]:
    if store_path is None:
        return {}, None
    try:
        return EdgeStateStore(store_path).load(), None
    except (OSError, ValueError, TypeError) as exc:
        return {}, f"invalid_edge_state_store:load:{exc.__class__.__name__}"


def _save_states(store_path: str | Path | None, edge_states: Mapping[str, EdgeState]) -> str | None:
    if store_path is None:
        return None
    try:
        EdgeStateStore(store_path).save(edge_states)
    except (OSError, ValueError, TypeError) as exc:
        return f"invalid_edge_state_store:save:{exc.__class__.__name__}"
    return None


def _finalize_result(
    *,
    valid: bool,
    selected_edge_id: str | None,
    selected_edge_state: EdgeState | None,
    allocation: CapitalAllocationResult,
    execution: PaperTradingResult,
    reason: str,
    regime: str | None,
    edge_evaluations: Sequence[PRDV3MasterOrchestratorEdgeEvaluation],
    logs: Sequence[dict[str, Any]],
    contracts: dict[str, dict[str, Any]],
) -> PRDV3MasterOrchestratorResult:
    return PRDV3MasterOrchestratorResult(
        valid=valid,
        selected_edge_id=selected_edge_id,
        selected_edge_state=selected_edge_state,
        allocation=allocation,
        execution=execution,
        reason=reason,
        regime=regime,
        edge_evaluations=tuple(edge_evaluations),
        logs=tuple(logs),
        contracts=contracts,
    )


def run_prdv3_master_orchestrator(
    edges: Sequence[EdgeDefinition],
    bars: Sequence[OHLCVBar],
    equity: float,
    config: PRDV3MasterOrchestratorConfig | None = None,
) -> PRDV3MasterOrchestratorResult:
    config = config or PRDV3MasterOrchestratorConfig()
    active_edges = tuple(sorted((edge for edge in edges if edge.enabled), key=lambda item: item.edge_id))
    dataset_scope = _dataset_scope(active_edges, bars)
    logs: list[dict[str, Any]] = []
    edge_evaluations: list[PRDV3MasterOrchestratorEdgeEvaluation] = []
    allocation = _blocked_allocation("pipeline_not_started")
    execution = _blocked_execution("pipeline_not_started", float(equity) if math.isfinite(float(equity)) else 0.0)

    edge_error = _validate_edges(active_edges)
    bar_error = _validate_bars(bars)
    if bar_error is not None:
        reason = bar_error
        logs.append({"event": "data_stage_blocked", "reason": reason})
        contracts = {
            "data": _data_contract(dataset_scope, "UNSAFE", reason, "repair_ohlcv_input", reason),
            "strategy": _strategy_contract(
                dataset_scope,
                "BLOCKED",
                "upstream_data_unsafe",
                "not_run",
                "not_run",
                "not_run",
                "data stage blocked",
                "repair_data_stage",
                "upstream_data_unsafe",
            ),
            "risk": _risk_contract(
                dataset_scope,
                "BLOCKED",
                "upstream_strategy_blocked",
                "not_run",
                "not_run",
                "not_run",
                "strategy stage blocked",
                "repair_strategy_stage",
                "upstream_strategy_blocked",
            ),
        }
        return _finalize_result(
            valid=False,
            selected_edge_id=None,
            selected_edge_state=None,
            allocation=_blocked_allocation(reason),
            execution=_blocked_execution(reason, 0.0),
            reason=reason,
            regime=None,
            edge_evaluations=edge_evaluations,
            logs=logs,
            contracts=contracts,
        )

    if edge_error is not None:
        reason = edge_error
        logs.append({"event": "strategy_stage_blocked", "reason": reason})
        contracts = {
            "data": _data_contract(dataset_scope, "SAFE", "bars_validated", "run_strategy_stage"),
            "strategy": _strategy_contract(
                dataset_scope,
                "BLOCKED",
                "data_stage_safe",
                "not_run",
                "not_run",
                "not_run",
                reason,
                "repair_edge_inputs",
                reason,
            ),
            "risk": _risk_contract(
                dataset_scope,
                "BLOCKED",
                "upstream_strategy_blocked",
                "not_run",
                "not_run",
                "not_run",
                "strategy stage blocked",
                "repair_strategy_stage",
                "upstream_strategy_blocked",
            ),
        }
        return _finalize_result(
            valid=False,
            selected_edge_id=None,
            selected_edge_state=None,
            allocation=_blocked_allocation(reason),
            execution=_blocked_execution(reason, 0.0),
            reason=reason,
            regime=None,
            edge_evaluations=edge_evaluations,
            logs=logs,
            contracts=contracts,
        )

    logs.append({"event": "data_stage_safe", "bar_count": len(bars), "symbol": dataset_scope["symbols"][0]})
    previous_states, state_store_error = _load_previous_states(config.edge_state_store_path)
    if state_store_error is not None:
        logs.append({"event": "strategy_stage_blocked", "reason": state_store_error})
        contracts = {
            "data": _data_contract(dataset_scope, "SAFE", "bars_validated", "run_strategy_stage"),
            "strategy": _strategy_contract(
                dataset_scope,
                "BLOCKED",
                "data_stage_safe",
                "not_run",
                "not_run",
                "not_run",
                state_store_error,
                "repair_edge_state_store",
                state_store_error,
            ),
            "risk": _risk_contract(
                dataset_scope,
                "BLOCKED",
                "upstream_strategy_blocked",
                "not_run",
                "not_run",
                "not_run",
                "strategy stage blocked",
                "repair_strategy_stage",
                "upstream_strategy_blocked",
            ),
        }
        return _finalize_result(
            valid=False,
            selected_edge_id=None,
            selected_edge_state=None,
            allocation=_blocked_allocation(state_store_error),
            execution=_blocked_execution(state_store_error, 0.0),
            reason=state_store_error,
            regime=None,
            edge_evaluations=edge_evaluations,
            logs=logs,
            contracts=contracts,
        )

    validation_map: dict[str, EdgeValidationResult] = {}
    state_map: dict[str, EdgeState] = {}
    for edge in active_edges:
        validation_result = run_edge_validation_backtest(edge, bars, config.validation_config)
        robustness_result = run_edge_robustness_validation(
            edge,
            bars,
            validation_config=config.validation_config,
            robustness_config=config.robustness_config,
        )
        edge_state = evaluate_edge_state(
            edge,
            validation_result,
            robustness_result,
            previous_state=previous_states.get(edge.edge_id),
            config=config.auto_edge_killer_config,
        )
        validation_map[edge.edge_id] = validation_result
        state_map[edge.edge_id] = edge_state
        edge_evaluations.append(
            PRDV3MasterOrchestratorEdgeEvaluation(
                edge_id=edge.edge_id,
                validation_result=validation_result,
                robustness_result=robustness_result,
                edge_state=edge_state,
            )
        )
        logs.append(
            {
                "event": "edge_evaluated",
                "edge_id": edge.edge_id,
                "validation_valid": validation_result.valid,
                "validation_blocked_reason": validation_result.blocked_reason,
                "robustness_valid": robustness_result.valid,
                "robustness_blocked_reason": robustness_result.blocked_reason,
                "edge_state_status": edge_state.status,
                "edge_state_disabled_reason": edge_state.disabled_reason,
            }
        )

    state_save_error = _save_states(config.edge_state_store_path, state_map)
    if state_save_error is not None:
        logs.append({"event": "strategy_stage_blocked", "reason": state_save_error})
        contracts = {
            "data": _data_contract(dataset_scope, "SAFE", "bars_validated", "run_strategy_stage"),
            "strategy": _strategy_contract(
                dataset_scope,
                "BLOCKED",
                "data_stage_safe",
                f"evaluated_edges={len(edge_evaluations)}",
                "ranking_not_run",
                "signal_not_run",
                state_save_error,
                "repair_edge_state_store",
                state_save_error,
            ),
            "risk": _risk_contract(
                dataset_scope,
                "BLOCKED",
                "upstream_strategy_blocked",
                "not_run",
                "not_run",
                "not_run",
                "strategy stage blocked",
                "repair_strategy_stage",
                "upstream_strategy_blocked",
            ),
        }
        return _finalize_result(
            valid=False,
            selected_edge_id=None,
            selected_edge_state=None,
            allocation=_blocked_allocation(state_save_error),
            execution=_blocked_execution(state_save_error, 0.0),
            reason=state_save_error,
            regime=None,
            edge_evaluations=edge_evaluations,
            logs=logs,
            contracts=contracts,
        )

    regime = RegimeEngine().detect_regime(bars)
    regime_label = str(regime.regime or "").strip() or None
    selection = select_best_edge(active_edges, regime, bars, edge_states=state_map)
    logs.append(
        {
            "event": "edge_selection_completed",
            "selected_edge_id": selection.selected_edge_id,
            "score": _round_value(selection.score),
            "explanation": selection.explanation,
        }
    )

    feature_summary = f"evaluated_edges={len(edge_evaluations)}; active_edges={sum(1 for state in state_map.values() if state.status != 'DISABLED')}"
    ranking_summary = selection.explanation
    signal_summary = (
        f"selected_edge_id={selection.selected_edge_id}; regime={regime_label}"
        if selection.selected_edge_id is not None
        else "NO TRADE"
    )

    if selection.selected_edge_id is None:
        reason = selection.explanation
        contracts = {
            "data": _data_contract(dataset_scope, "SAFE", "bars_validated", "run_strategy_stage"),
            "strategy": _strategy_contract(
                dataset_scope,
                "BLOCKED",
                "data_stage_safe",
                feature_summary,
                ranking_summary,
                signal_summary,
                f"selection_blocked:{selection.explanation}",
                "repair_strategy_inputs_or_wait",
                selection.explanation,
            ),
            "risk": _risk_contract(
                dataset_scope,
                "BLOCKED",
                "upstream_strategy_blocked",
                "no_decision",
                "selection_blocked",
                "execution_not_started",
                "strategy stage blocked",
                "repair_strategy_stage",
                "upstream_strategy_blocked",
            ),
        }
        return _finalize_result(
            valid=False,
            selected_edge_id=None,
            selected_edge_state=None,
            allocation=_blocked_allocation("selection_blocked"),
            execution=_blocked_execution(selection.explanation, 0.0),
            reason=reason,
            regime=regime_label,
            edge_evaluations=edge_evaluations,
            logs=logs,
            contracts=contracts,
        )

    selected_edge = next(edge for edge in active_edges if edge.edge_id == selection.selected_edge_id)
    selected_state = state_map.get(selection.selected_edge_id)
    if not _is_finite_positive(float(equity)):
        reason = "invalid_current_equity"
        logs.append({"event": "risk_stage_blocked", "reason": reason})
        contracts = {
            "data": _data_contract(dataset_scope, "SAFE", "bars_validated", "run_strategy_stage"),
            "strategy": _strategy_contract(
                dataset_scope,
                "READY",
                "data_stage_safe",
                feature_summary,
                ranking_summary,
                signal_summary,
                "selection_ready",
                "run_risk_stage",
            ),
            "risk": _risk_contract(
                dataset_scope,
                "BLOCKED",
                "strategy_stage_ready",
                f"selected_edge_id={selection.selected_edge_id}",
                reason,
                "execution_not_started",
                reason,
                "provide_valid_equity",
                reason,
            ),
        }
        return _finalize_result(
            valid=False,
            selected_edge_id=selection.selected_edge_id,
            selected_edge_state=selected_state,
            allocation=_blocked_allocation(reason),
            execution=_blocked_execution(reason, 0.0),
            reason=reason,
            regime=regime_label,
            edge_evaluations=edge_evaluations,
            logs=logs,
            contracts=contracts,
        )

    allocation = allocate_capital_to_edge(
        selected_edge=selected_edge,
        edge_score=selection.score,
        validation_result=validation_map[selection.selected_edge_id],
        current_equity=float(equity),
        bars=bars,
        config=config.allocation_config,
        edge_state=selected_state,
    )
    logs.append(
        {
            "event": "allocation_completed",
            "selected_edge_id": selection.selected_edge_id,
            "approved": allocation.approved,
            "share_count": allocation.share_count,
            "blocked_reason": allocation.blocked_reason,
        }
    )
    if allocation.approved is not True:
        reason = allocation.blocked_reason or "allocation_blocked"
        contracts = {
            "data": _data_contract(dataset_scope, "SAFE", "bars_validated", "run_strategy_stage"),
            "strategy": _strategy_contract(
                dataset_scope,
                "READY",
                "data_stage_safe",
                feature_summary,
                ranking_summary,
                signal_summary,
                "selection_ready",
                "run_risk_stage",
            ),
            "risk": _risk_contract(
                dataset_scope,
                "BLOCKED",
                "strategy_stage_ready",
                f"selected_edge_id={selection.selected_edge_id}",
                reason,
                "execution_not_started",
                reason,
                "wait_for_risk_clearance",
                reason,
            ),
        }
        return _finalize_result(
            valid=False,
            selected_edge_id=selection.selected_edge_id,
            selected_edge_state=selected_state,
            allocation=allocation,
            execution=_blocked_execution(reason, float(equity)),
            reason=reason,
            regime=regime_label,
            edge_evaluations=edge_evaluations,
            logs=logs,
            contracts=contracts,
        )

    execution_config = replace(
        config.paper_trading_config,
        initial_capital=float(equity),
        allocation_config=config.allocation_config,
    )
    execution = run_edge_paper_trading(
        [selected_edge],
        {selected_edge.edge_id: validation_map[selected_edge.edge_id]},
        bars,
        execution_config,
        edge_states={selected_edge.edge_id: selected_state} if selected_state is not None else None,
    )
    logs.append(
        {
            "event": "execution_completed",
            "selected_edge_id": selection.selected_edge_id,
            "valid": execution.valid,
            "blocked_reason": execution.blocked_reason,
            "entries_filled": int(execution.metrics.get("entries_filled", 0)),
            "closed_trades": int(execution.metrics.get("closed_trades", 0)),
        }
    )
    logs.extend(dict(log) for log in execution.logs)

    reason = execution.blocked_reason or "execution_valid"
    contracts = {
        "data": _data_contract(dataset_scope, "SAFE", "bars_validated", "run_strategy_stage"),
        "strategy": _strategy_contract(
            dataset_scope,
            "READY",
            "data_stage_safe",
            feature_summary,
            ranking_summary,
            signal_summary,
            "selection_ready",
            "run_risk_stage",
        ),
        "risk": _risk_contract(
            dataset_scope,
            "ALLOWED" if execution.valid else "BLOCKED",
            "strategy_stage_ready",
            f"selected_edge_id={selection.selected_edge_id}; allocation_share_count={allocation.share_count}",
            f"allocation_blocked_reason={allocation.blocked_reason}; execution_blocked_reason={execution.blocked_reason}",
            f"paper_logs={len(execution.logs)}",
            reason,
            "hold_or_monitor_execution" if execution.valid else "repair_risk_stage",
            None if execution.valid else reason,
        ),
    }
    return _finalize_result(
        valid=execution.valid,
        selected_edge_id=selection.selected_edge_id,
        selected_edge_state=selected_state,
        allocation=allocation,
        execution=execution,
        reason=reason,
        regime=regime_label,
        edge_evaluations=edge_evaluations,
        logs=logs,
        contracts=contracts,
    )


__all__ = [
    "PRDV3MasterOrchestratorConfig",
    "PRDV3MasterOrchestratorEdgeEvaluation",
    "PRDV3MasterOrchestratorResult",
    "run_prdv3_master_orchestrator",
]
