from __future__ import annotations

from pathlib import Path

from bist_core.edge.allocation import CapitalAllocationResult
from bist_core.edge.registry import build_builtin_edge_registry
from bist_core.edge.self_healing import (
    ACTIVE,
    WARNING,
    AutoEdgeKillerConfig,
    EdgeStateStore,
    apply_edge_state_to_allocation,
    evaluate_edge_state,
    filter_edges_for_selection,
)
from bist_core.edge.validation import EdgeRobustnessResult, EdgeValidationResult


def _edge():
    registry = build_builtin_edge_registry()
    return next(edge for edge in registry.list_active_edges() if edge.edge_id == "bist_bear_oversold_snap")


def _validation_result(
    *,
    total_trades: int = 6,
    expectancy: float = 1.25,
    max_drawdown: float = 0.04,
    timestamp: int = 1_704_067_200,
) -> EdgeValidationResult:
    return EdgeValidationResult(
        valid=True,
        edge_id="bist_bear_oversold_snap",
        blocked_reason=None,
        metrics={
            "total_trades": total_trades,
            "expectancy": expectancy,
            "max_drawdown": max_drawdown,
        },
        trades=(),
        equity_curve=({"timestamp": timestamp, "equity": 100_000.0, "close": 100.0},),
    )


def _robustness_result(
    validation_result: EdgeValidationResult,
    *,
    valid: bool = True,
    blocked_reason: str | None = None,
    positive_window_ratio: float = 0.75,
    overfit_gap: float = 1.0,
) -> EdgeRobustnessResult:
    return EdgeRobustnessResult(
        valid=valid,
        edge_id="bist_bear_oversold_snap",
        blocked_reason=blocked_reason,
        base_result=validation_result,
        walk_forward_windows=(),
        stress_results=(),
        metrics={
            "walk_forward_positive_test_window_ratio": positive_window_ratio,
            "walk_forward_avg_expectancy_gap": overfit_gap,
        },
    )


def _allocation_result() -> CapitalAllocationResult:
    return CapitalAllocationResult(
        approved=True,
        position_size_pct=10.0,
        risk_amount=1_000.0,
        share_count=100,
        exposure_amount=10_000.0,
        explanation="baseline",
        blocked_reason=None,
    )


def test_unstable_edge_is_disabled() -> None:
    edge = _edge()
    validation_result = _validation_result()
    robustness_result = _robustness_result(validation_result, valid=False, blocked_reason="overfit_expectancy_gap")

    state = evaluate_edge_state(edge, validation_result, robustness_result)

    assert state.status == "DISABLED"
    assert state.disabled_reason == "robustness_failed:overfit_expectancy_gap"


def test_stable_edge_remains_active() -> None:
    edge = _edge()
    validation_result = _validation_result()
    robustness_result = _robustness_result(validation_result)

    state = evaluate_edge_state(edge, validation_result, robustness_result)

    assert state.status == ACTIVE
    assert state.disabled_reason is None
    assert state.warning_reasons == ()
    assert state.allocation_weight_multiplier == 1.0


def test_borderline_edge_becomes_warning_and_reduces_allocation() -> None:
    edge = _edge()
    previous_validation = _validation_result(expectancy=2.0, max_drawdown=0.03, timestamp=1_704_067_200)
    previous_robustness = _robustness_result(previous_validation, overfit_gap=0.5)
    previous_state = evaluate_edge_state(edge, previous_validation, previous_robustness)

    current_validation = _validation_result(expectancy=1.0, max_drawdown=0.05, timestamp=1_704_153_600)
    current_robustness = _robustness_result(current_validation, overfit_gap=0.6)
    warning_state = evaluate_edge_state(edge, current_validation, current_robustness, previous_state=previous_state)
    scaled_allocation = apply_edge_state_to_allocation(_allocation_result(), warning_state)

    assert warning_state.status == WARNING
    assert "declining_performance" in warning_state.warning_reasons
    assert "increasing_drawdown" in warning_state.warning_reasons
    assert scaled_allocation.approved is True
    assert scaled_allocation.share_count == 50
    assert scaled_allocation.position_size_pct == 5.0


def test_edge_state_evaluation_is_deterministic() -> None:
    edge = _edge()
    validation_result = _validation_result()
    robustness_result = _robustness_result(validation_result)

    first = evaluate_edge_state(edge, validation_result, robustness_result)
    second = evaluate_edge_state(edge, validation_result, robustness_result)

    assert first.to_dict() == second.to_dict()


def test_missing_validation_data_is_disabled_without_silent_acceptance() -> None:
    edge = _edge()

    state = evaluate_edge_state(edge, None, None)

    assert state.status == "DISABLED"
    assert state.disabled_reason == "missing_validation_result"


def test_selection_pool_excludes_disabled_edges() -> None:
    edge = _edge()
    validation_result = _validation_result(total_trades=1)
    robustness_result = _robustness_result(validation_result)
    disabled_state = evaluate_edge_state(
        edge,
        validation_result,
        robustness_result,
        config=AutoEdgeKillerConfig(min_trades_threshold=3),
    )

    selection_pool = filter_edges_for_selection([edge], {edge.edge_id: disabled_state})

    assert selection_pool == ()


def test_edge_state_store_round_trip(tmp_path: Path) -> None:
    edge = _edge()
    validation_result = _validation_result()
    robustness_result = _robustness_result(validation_result)
    state = evaluate_edge_state(edge, validation_result, robustness_result)
    store = EdgeStateStore(tmp_path / "edge_states.json")

    store.save({edge.edge_id: state})
    loaded = store.load()

    assert loaded[edge.edge_id].to_dict() == state.to_dict()