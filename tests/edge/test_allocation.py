from __future__ import annotations

from dataclasses import replace

from bist_core.edge.allocation import (
    CapitalAllocationConfig,
    allocate_capital_to_edge,
)
from bist_core.edge.registry import build_builtin_edge_registry
from bist_core.edge.self_healing import AutoEdgeKillerConfig, evaluate_edge_state
from bist_core.edge.validation import EdgeRobustnessResult
from bist_core.edge.validation import run_edge_validation_backtest
from bist_core.models.ohlcv import OHLCVBar


def _edge():
    registry = build_builtin_edge_registry()
    return next(edge for edge in registry.list_active_edges() if edge.edge_id == "bist_bear_oversold_snap")


def _bar(ts: int, close: float, spread: float = 0.8, volume: float = 1_200_000.0) -> OHLCVBar:
    open_price = close + (spread * 0.2)
    high = max(open_price, close) + spread
    low = max(min(open_price, close) - spread, 0.01)
    return OHLCVBar(ts, "X", round(open_price, 4), round(high, 4), round(low, 4), round(close, 4), volume)


def _trend_down_bars(n: int = 61, spread: float = 0.8) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86_400, 120.0 - i * 0.7, spread=spread) for i in range(n)]


def test_allocate_capital_to_edge_is_deterministic() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, bars)

    first = allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, bars)
    second = allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, bars)

    assert first.to_dict() == second.to_dict()
    assert first.approved is True
    assert first.position_size_pct <= 25.0


def test_allocate_capital_to_edge_reduces_size_for_high_risk_validation() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    base_validation = run_edge_validation_backtest(edge, bars)
    stressed_validation = replace(
        base_validation,
        metrics={**base_validation.metrics, "max_drawdown": 0.20, "total_trades": 5},
    )

    base_result = allocate_capital_to_edge(edge, 0.9105, base_validation, 100_000.0, bars)
    stressed_result = allocate_capital_to_edge(edge, 0.9105, stressed_validation, 100_000.0, bars)

    assert base_result.approved is True
    assert stressed_result.approved is True
    assert stressed_result.position_size_pct < base_result.position_size_pct
    assert stressed_result.risk_amount < base_result.risk_amount


def test_allocate_capital_to_edge_reduces_size_for_low_score() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, bars)

    high_score = allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, bars)
    low_score = allocate_capital_to_edge(edge, 0.20, validation, 100_000.0, bars)

    assert high_score.approved is True
    assert low_score.approved is True
    assert low_score.position_size_pct < high_score.position_size_pct
    assert low_score.risk_amount < high_score.risk_amount


def test_allocate_capital_to_edge_reduces_size_for_high_volatility() -> None:
    edge = _edge()
    low_vol_bars = _trend_down_bars(spread=0.8)
    high_vol_bars = _trend_down_bars(spread=1.6)
    validation = run_edge_validation_backtest(edge, low_vol_bars)

    low_vol_result = allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, low_vol_bars)
    high_vol_result = allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, high_vol_bars)

    assert low_vol_result.approved is True
    assert high_vol_result.approved is True
    assert high_vol_result.position_size_pct < low_vol_result.position_size_pct
    assert high_vol_result.risk_amount < low_vol_result.risk_amount


def test_allocate_capital_to_edge_fail_closes_on_invalid_inputs() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    invalid_validation = run_edge_validation_backtest(edge, bars)
    invalid_validation = replace(invalid_validation, valid=False, blocked_reason="invalid_data")

    result = allocate_capital_to_edge(edge, 0.9105, invalid_validation, 100_000.0, bars)

    assert result.approved is False
    assert result.blocked_reason == "invalid_validation_result"
    assert result.position_size_pct == 0.0
    assert result.risk_amount == 0.0


def test_allocate_capital_to_edge_fail_closes_when_exposure_cap_blocks_size() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, bars)
    config = CapitalAllocationConfig(max_exposure_pct=0.01)

    result = allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, bars, config)

    assert result.approved is False
    assert result.blocked_reason == "position_size_zero"


def test_allocate_capital_to_edge_scales_warning_state_weight() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, bars)
    previous_validation = run_edge_validation_backtest(edge, bars)
    previous_validation = replace(
        previous_validation,
        metrics={**previous_validation.metrics, "expectancy": 2.0, "max_drawdown": 0.02},
        equity_curve=({"timestamp": 1_704_067_200, "equity": 100_000.0, "close": 100.0},),
    )
    previous_robustness = EdgeRobustnessResult(
        valid=True,
        edge_id=edge.edge_id,
        blocked_reason=None,
        base_result=previous_validation,
        walk_forward_windows=(),
        stress_results=(),
        metrics={"walk_forward_positive_test_window_ratio": 0.75, "walk_forward_avg_expectancy_gap": 0.5},
    )
    previous_state = evaluate_edge_state(
        edge,
        previous_validation,
        previous_robustness,
        config=AutoEdgeKillerConfig(min_trades_threshold=1),
    )
    warning_validation = replace(
        validation,
        metrics={**validation.metrics, "expectancy": 1.0, "max_drawdown": 0.05},
        equity_curve=({"timestamp": 1_704_153_600, "equity": 100_100.0, "close": 101.0},),
    )
    warning_robustness = EdgeRobustnessResult(
        valid=True,
        edge_id=edge.edge_id,
        blocked_reason=None,
        base_result=warning_validation,
        walk_forward_windows=(),
        stress_results=(),
        metrics={"walk_forward_positive_test_window_ratio": 0.75, "walk_forward_avg_expectancy_gap": 0.5},
    )
    warning_state = evaluate_edge_state(
        edge,
        warning_validation,
        warning_robustness,
        previous_state=previous_state,
        config=AutoEdgeKillerConfig(min_trades_threshold=1),
    )

    result = allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, bars, edge_state=warning_state)

    assert result.approved is True
    assert result.share_count > 0
    assert result.share_count < allocate_capital_to_edge(edge, 0.9105, validation, 100_000.0, bars).share_count