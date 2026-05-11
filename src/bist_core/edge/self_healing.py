from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from bist_core.edge.allocation import CapitalAllocationResult
from bist_core.edge.registry import EdgeDefinition
from bist_core.edge.validation import EdgeRobustnessResult, EdgeValidationResult

ACTIVE = "ACTIVE"
WARNING = "WARNING"
DISABLED = "DISABLED"


@dataclass(frozen=True)
class EdgePerformanceSnapshot:
    validation_timestamp: int
    total_trades: int
    expectancy: float
    max_drawdown: float
    positive_window_ratio: float
    overfit_gap: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_timestamp": self.validation_timestamp,
            "total_trades": self.total_trades,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
            "positive_window_ratio": self.positive_window_ratio,
            "overfit_gap": self.overfit_gap,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EdgePerformanceSnapshot:
        return cls(
            validation_timestamp=int(payload.get("validation_timestamp", 0)),
            total_trades=int(payload.get("total_trades", 0)),
            expectancy=_round_metric(payload.get("expectancy", 0.0)),
            max_drawdown=_round_metric(payload.get("max_drawdown", 0.0)),
            positive_window_ratio=_round_metric(payload.get("positive_window_ratio", 0.0)),
            overfit_gap=_round_metric(payload.get("overfit_gap", 0.0)),
        )


@dataclass(frozen=True)
class EdgeState:
    edge_id: str
    status: str
    last_validation_timestamp: int
    historical_performance_log: tuple[EdgePerformanceSnapshot, ...]
    warning_reasons: tuple[str, ...] = ()
    disabled_reason: str | None = None
    allocation_weight_multiplier: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "status": self.status,
            "last_validation_timestamp": self.last_validation_timestamp,
            "historical_performance_log": [entry.to_dict() for entry in self.historical_performance_log],
            "warning_reasons": list(self.warning_reasons),
            "disabled_reason": self.disabled_reason,
            "allocation_weight_multiplier": self.allocation_weight_multiplier,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EdgeState:
        return cls(
            edge_id=str(payload.get("edge_id", "")).strip(),
            status=str(payload.get("status", DISABLED)).strip() or DISABLED,
            last_validation_timestamp=int(payload.get("last_validation_timestamp", 0)),
            historical_performance_log=tuple(
                EdgePerformanceSnapshot.from_dict(entry)
                for entry in payload.get("historical_performance_log", ())
                if isinstance(entry, Mapping)
            ),
            warning_reasons=tuple(str(reason) for reason in payload.get("warning_reasons", ()) if str(reason).strip()),
            disabled_reason=(
                str(payload.get("disabled_reason")).strip()
                if payload.get("disabled_reason") is not None and str(payload.get("disabled_reason")).strip()
                else None
            ),
            allocation_weight_multiplier=_round_metric(payload.get("allocation_weight_multiplier", 1.0)),
        )


@dataclass(frozen=True)
class AutoEdgeKillerConfig:
    min_trades_threshold: int = 3
    max_drawdown_threshold: float | None = None
    min_positive_ratio: float = 0.5
    max_overfit_gap: float = 2.5
    warning_expectancy_variance_threshold: float = 1.0
    warning_allocation_multiplier: float = 0.5
    max_history_entries: int = 20


def _round_metric(value: Any) -> float:
    return round(float(value), 6)


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _blocked_state(edge: EdgeDefinition, reason: str, previous_state: EdgeState | None) -> EdgeState:
    history = previous_state.historical_performance_log if previous_state is not None else ()
    return EdgeState(
        edge_id=edge.edge_id,
        status=DISABLED,
        last_validation_timestamp=previous_state.last_validation_timestamp if previous_state is not None else 0,
        historical_performance_log=history,
        warning_reasons=(),
        disabled_reason=reason,
        allocation_weight_multiplier=0.0,
    )


def _validate_config(config: AutoEdgeKillerConfig) -> str | None:
    if config.min_trades_threshold < 1:
        return "invalid_config:min_trades_threshold"
    if config.max_drawdown_threshold is not None and config.max_drawdown_threshold <= 0.0:
        return "invalid_config:max_drawdown_threshold"
    if config.min_positive_ratio < 0.0 or config.min_positive_ratio > 1.0:
        return "invalid_config:min_positive_ratio"
    if config.max_overfit_gap < 0.0:
        return "invalid_config:max_overfit_gap"
    if config.warning_expectancy_variance_threshold < 0.0:
        return "invalid_config:warning_expectancy_variance_threshold"
    if config.warning_allocation_multiplier <= 0.0 or config.warning_allocation_multiplier >= 1.0:
        return "invalid_config:warning_allocation_multiplier"
    if config.max_history_entries < 1:
        return "invalid_config:max_history_entries"
    return None


def _validation_timestamp(validation_result: EdgeValidationResult, robustness_result: EdgeRobustnessResult) -> int | None:
    if validation_result.equity_curve:
        return int(validation_result.equity_curve[-1].get("timestamp", 0))
    if robustness_result.base_result.equity_curve:
        return int(robustness_result.base_result.equity_curve[-1].get("timestamp", 0))
    return None


def _performance_snapshot(
    validation_result: EdgeValidationResult,
    robustness_result: EdgeRobustnessResult,
) -> EdgePerformanceSnapshot | None:
    timestamp = _validation_timestamp(validation_result, robustness_result)
    if timestamp is None or timestamp <= 0:
        return None

    total_trades = validation_result.metrics.get("total_trades")
    expectancy = validation_result.metrics.get("expectancy")
    max_drawdown = validation_result.metrics.get("max_drawdown")
    positive_window_ratio = robustness_result.metrics.get("walk_forward_positive_test_window_ratio")
    overfit_gap = robustness_result.metrics.get("walk_forward_avg_expectancy_gap")

    if not all(
        _is_finite_number(metric)
        for metric in (total_trades, expectancy, max_drawdown, positive_window_ratio, overfit_gap)
    ):
        return None

    return EdgePerformanceSnapshot(
        validation_timestamp=timestamp,
        total_trades=int(total_trades),
        expectancy=_round_metric(expectancy),
        max_drawdown=_round_metric(max_drawdown),
        positive_window_ratio=_round_metric(positive_window_ratio),
        overfit_gap=_round_metric(overfit_gap),
    )


def evaluate_edge_state(
    edge: EdgeDefinition,
    validation_result: EdgeValidationResult | None,
    robustness_result: EdgeRobustnessResult | None,
    previous_state: EdgeState | None = None,
    config: AutoEdgeKillerConfig | None = None,
) -> EdgeState:
    config = config or AutoEdgeKillerConfig()
    config_error = _validate_config(config)
    if config_error is not None:
        return _blocked_state(edge, config_error, previous_state)

    if validation_result is None:
        return _blocked_state(edge, "missing_validation_result", previous_state)
    if robustness_result is None:
        return _blocked_state(edge, "missing_robustness_result", previous_state)
    if validation_result.edge_id != edge.edge_id:
        return _blocked_state(edge, "validation_edge_mismatch", previous_state)
    if robustness_result.edge_id != edge.edge_id:
        return _blocked_state(edge, "robustness_edge_mismatch", previous_state)
    if validation_result.valid is not True or validation_result.blocked_reason is not None:
        reason = validation_result.blocked_reason or "invalid_validation_result"
        return _blocked_state(edge, f"validation_failed:{reason}", previous_state)
    if robustness_result.valid is not True or robustness_result.blocked_reason is not None:
        reason = robustness_result.blocked_reason or "invalid_robustness_result"
        return _blocked_state(edge, f"robustness_failed:{reason}", previous_state)

    snapshot = _performance_snapshot(validation_result, robustness_result)
    if snapshot is None:
        return _blocked_state(edge, "missing_validation_metrics", previous_state)

    max_drawdown_threshold = (
        edge.risk_profile.max_expected_drawdown_pct
        if config.max_drawdown_threshold is None
        else float(config.max_drawdown_threshold)
    )
    if snapshot.total_trades < config.min_trades_threshold:
        return _blocked_state(edge, "minimum_trade_count_failed", previous_state)
    if snapshot.expectancy <= 0.0:
        return _blocked_state(edge, "non_positive_expectancy", previous_state)
    if snapshot.max_drawdown > max_drawdown_threshold:
        return _blocked_state(edge, "max_drawdown_threshold_failed", previous_state)
    if snapshot.positive_window_ratio < config.min_positive_ratio:
        return _blocked_state(edge, "positive_window_ratio_failed", previous_state)
    if snapshot.overfit_gap > config.max_overfit_gap:
        return _blocked_state(edge, "overfit_gap_failed", previous_state)

    history = list(previous_state.historical_performance_log if previous_state is not None else ())
    history.append(snapshot)
    if len(history) > config.max_history_entries:
        history = history[-config.max_history_entries :]

    warning_reasons: list[str] = []
    if len(history) >= 2:
        previous_snapshot = history[-2]
        if snapshot.expectancy < previous_snapshot.expectancy:
            warning_reasons.append("declining_performance")
        if snapshot.max_drawdown > previous_snapshot.max_drawdown:
            warning_reasons.append("increasing_drawdown")

    expectancy_series = [entry.expectancy for entry in history]
    if len(expectancy_series) >= 2 and statistics.pstdev(expectancy_series) > config.warning_expectancy_variance_threshold:
        warning_reasons.append("unstable_expectancy_variance")

    status = WARNING if warning_reasons else ACTIVE
    allocation_weight_multiplier = config.warning_allocation_multiplier if status == WARNING else 1.0
    return EdgeState(
        edge_id=edge.edge_id,
        status=status,
        last_validation_timestamp=snapshot.validation_timestamp,
        historical_performance_log=tuple(history),
        warning_reasons=tuple(warning_reasons),
        disabled_reason=None,
        allocation_weight_multiplier=allocation_weight_multiplier,
    )


def apply_edge_state_to_edge_definition(edge: EdgeDefinition, edge_state: EdgeState | None) -> EdgeDefinition:
    if edge_state is None:
        return replace(edge, enabled=False, disabled_reason="missing_edge_state")
    if edge_state.edge_id != edge.edge_id:
        return replace(edge, enabled=False, disabled_reason="edge_state_mismatch")
    if edge_state.status == DISABLED:
        reason = edge_state.disabled_reason or "disabled_by_auto_edge_killer"
        return replace(edge, enabled=False, disabled_reason=reason)
    return edge


def filter_edges_for_selection(
    edges: Sequence[EdgeDefinition],
    edge_states: Mapping[str, EdgeState],
) -> tuple[EdgeDefinition, ...]:
    selection_pool: list[EdgeDefinition] = []
    for edge in edges:
        materialized_edge = apply_edge_state_to_edge_definition(edge, edge_states.get(edge.edge_id))
        if materialized_edge.enabled:
            selection_pool.append(materialized_edge)
    selection_pool.sort(key=lambda item: item.edge_id)
    return tuple(selection_pool)


def apply_edge_state_to_allocation(
    allocation_result: CapitalAllocationResult,
    edge_state: EdgeState | None,
) -> CapitalAllocationResult:
    if allocation_result.approved is not True:
        return allocation_result
    if edge_state is None:
        return CapitalAllocationResult(
            approved=False,
            position_size_pct=0.0,
            risk_amount=0.0,
            share_count=0,
            exposure_amount=0.0,
            explanation="NO TRADE: missing_edge_state",
            blocked_reason="missing_edge_state",
        )
    if edge_state.status == DISABLED:
        return CapitalAllocationResult(
            approved=False,
            position_size_pct=0.0,
            risk_amount=0.0,
            share_count=0,
            exposure_amount=0.0,
            explanation=f"NO TRADE: {edge_state.disabled_reason or 'disabled_by_auto_edge_killer'}",
            blocked_reason="edge_disabled",
        )
    if edge_state.status != WARNING:
        return allocation_result

    scaled_share_count = int(math.floor(allocation_result.share_count * edge_state.allocation_weight_multiplier))
    if scaled_share_count < 1:
        return CapitalAllocationResult(
            approved=False,
            position_size_pct=0.0,
            risk_amount=0.0,
            share_count=0,
            exposure_amount=0.0,
            explanation="NO TRADE: warning_weight_zero",
            blocked_reason="warning_weight_zero",
        )

    scale = scaled_share_count / allocation_result.share_count
    return CapitalAllocationResult(
        approved=True,
        position_size_pct=_round_metric(allocation_result.position_size_pct * scale),
        risk_amount=_round_metric(allocation_result.risk_amount * scale),
        share_count=scaled_share_count,
        exposure_amount=_round_metric(allocation_result.exposure_amount * scale),
        explanation=(
            f"{allocation_result.explanation}; edge_status=WARNING;"
            f" allocation_weight_multiplier={edge_state.allocation_weight_multiplier:.4f}"
        ),
        blocked_reason=None,
    )


class EdgeStateStore:
    def __init__(self, file_path: str | Path) -> None:
        self._file_path = Path(file_path)

    def load(self) -> dict[str, EdgeState]:
        if not self._file_path.is_file():
            return {}
        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return {}
        states: dict[str, EdgeState] = {}
        for entry in payload:
            if not isinstance(entry, Mapping):
                continue
            edge_state = EdgeState.from_dict(entry)
            if edge_state.edge_id:
                states[edge_state.edge_id] = edge_state
        return states

    def save(self, edge_states: Mapping[str, EdgeState]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        ordered = [edge_states[key].to_dict() for key in sorted(edge_states)]
        self._file_path.write_text(json.dumps(ordered, indent=2, sort_keys=True), encoding="utf-8")


__all__ = [
    "ACTIVE",
    "AutoEdgeKillerConfig",
    "DISABLED",
    "EdgePerformanceSnapshot",
    "EdgeState",
    "EdgeStateStore",
    "WARNING",
    "apply_edge_state_to_allocation",
    "apply_edge_state_to_edge_definition",
    "evaluate_edge_state",
    "filter_edges_for_selection",
]
