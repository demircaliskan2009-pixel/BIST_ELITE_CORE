from __future__ import annotations

from dataclasses import replace

from bist_core.edge.orchestrator import (
    PRDV3MasterOrchestratorConfig,
    run_prdv3_master_orchestrator,
)
from bist_core.edge.registry import EdgeRiskProfile, build_builtin_edge_registry
from bist_core.edge.self_healing import EdgeStateStore, evaluate_edge_state
from bist_core.edge.validation import EdgeRobustnessConfig, run_edge_robustness_validation, run_edge_validation_backtest
from bist_core.models.ohlcv import OHLCVBar


def _edge(edge_id: str = "bist_bear_oversold_snap"):
    registry = build_builtin_edge_registry()
    return next(edge for edge in registry.list_active_edges() if edge.edge_id == edge_id)


def _bar(ts: int, close: float, spread: float = 0.8, volume: float = 1_200_000.0) -> OHLCVBar:
    open_price = close + (spread * 0.2)
    high = max(open_price, close) + spread
    low = max(min(open_price, close) - spread, 0.01)
    return OHLCVBar(ts, "X", round(open_price, 4), round(high, 4), round(low, 4), round(close, 4), volume)


def _trend_down_bars(n: int = 70, spread: float = 0.8, volume: float = 1_200_000.0) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86_400, 120.0 - i * 0.7, spread=spread, volume=volume) for i in range(n)]


def _append_bar(
    output: list[OHLCVBar],
    timestamp: int,
    close_price: float,
    delta: float,
    volume: float,
    spread: float,
) -> tuple[float, int]:
    next_close = max(close_price + delta, 5.0)
    open_price = close_price + (delta * 0.3)
    high = max(open_price, next_close) + spread
    low = max(min(open_price, next_close) - spread, 0.01)
    output.append(
        OHLCVBar(
            timestamp=timestamp,
            symbol="X",
            open=round(open_price, 4),
            high=round(high, 4),
            low=round(low, 4),
            close=round(next_close, 4),
            volume=volume,
        )
    )
    return next_close, timestamp + 86_400


def _stable_bear_cycles(cycles: int = 4) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    timestamp = 1_704_067_200
    close_price = 125.0
    for _ in range(cycles):
        for _ in range(60):
            close_price, timestamp = _append_bar(bars, timestamp, close_price, -0.7, 1_200_000.0, 0.8)
        for _ in range(6):
            close_price, timestamp = _append_bar(bars, timestamp, close_price, 2.2, 1_300_000.0, 0.9)
        for _ in range(24):
            close_price, timestamp = _append_bar(bars, timestamp, close_price, 0.4, 1_250_000.0, 0.4)
        close_price += 3.0
    return bars


def _trend_up_bars(n: int = 250, spread: float = 0.55, volume: float = 1_000_000.0) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    for index in range(n):
        close_price = 100.0 + index * 0.45
        open_price = close_price - (spread * 0.2)
        high = max(open_price, close_price) + spread
        low = max(min(open_price, close_price) - spread, 0.01)
        bars.append(
            OHLCVBar(
                timestamp=1_704_067_200 + index * 86_400,
                symbol="X",
                open=round(open_price, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close_price, 4),
                volume=volume,
            )
        )
    return bars


def _orchestrator_config(**kwargs):
    config = PRDV3MasterOrchestratorConfig(
        robustness_config=EdgeRobustnessConfig(
            train_bars=120,
            test_bars=90,
            step_bars=20,
            min_walk_forward_windows=2,
            min_trade_count=1,
            min_expectancy_threshold=-1.0,
            max_avg_train_test_expectancy_gap=10.0,
            min_positive_test_window_ratio=0.0,
            max_test_expectancy_range=10.0,
        )
    )
    for key, value in kwargs.items():
        config = replace(config, **{key: value})
    return config


def test_run_prdv3_master_orchestrator_is_deterministic() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    bars = _trend_up_bars()
    config = _orchestrator_config()

    first = run_prdv3_master_orchestrator([edge], bars, 100_000.0, config)
    second = run_prdv3_master_orchestrator([edge], bars, 100_000.0, config)

    assert first.to_dict() == second.to_dict()
    assert first.valid is True
    assert first.selected_edge_id == edge.edge_id


def test_run_prdv3_master_orchestrator_filters_disabled_edges() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    disabled_clone = replace(
        edge,
        edge_id="bist_bull_pullback_sma20_disabled",
        risk_profile=EdgeRiskProfile(edge.risk_profile.volatility_bucket, 0.0000001, edge.risk_profile.max_holding_bars),
    )
    active_clone = replace(edge, edge_id="bist_bull_pullback_sma20_active")
    bars = _trend_up_bars()

    result = run_prdv3_master_orchestrator([disabled_clone, active_clone], bars, 100_000.0, _orchestrator_config())

    assert result.valid is True
    assert result.selected_edge_id == "bist_bull_pullback_sma20_active"
    disabled_eval = next(item for item in result.edge_evaluations if item.edge_id == "bist_bull_pullback_sma20_disabled")
    assert disabled_eval.edge_state.status == "DISABLED"


def test_run_prdv3_master_orchestrator_reduces_warning_allocation() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    bars = _trend_up_bars()
    config = _orchestrator_config()
    baseline = run_prdv3_master_orchestrator([edge], bars, 100_000.0, config)
    validation_result = run_edge_validation_backtest(edge, bars)
    robustness_result = run_edge_robustness_validation(edge, bars, robustness_config=config.robustness_config)
    previous_validation = replace(
        validation_result,
        metrics={**validation_result.metrics, "expectancy": float(validation_result.metrics["expectancy"]) + 1.0, "max_drawdown": 0.01},
        equity_curve=({"timestamp": 1_704_067_200, "equity": 100_000.0, "close": 100.0},),
    )
    previous_robustness = replace(
        robustness_result,
        base_result=previous_validation,
        metrics={
            **robustness_result.metrics,
            "walk_forward_positive_test_window_ratio": max(float(robustness_result.metrics["walk_forward_positive_test_window_ratio"]), 0.75),
            "walk_forward_avg_expectancy_gap": min(float(robustness_result.metrics["walk_forward_avg_expectancy_gap"]), 0.5),
        },
    )
    previous_state = evaluate_edge_state(edge, previous_validation, previous_robustness)

    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        store_path = Path(tmp_dir) / "edge_states.json"
        EdgeStateStore(store_path).save({edge.edge_id: previous_state})
        warning_result = run_prdv3_master_orchestrator(
            [edge],
            bars,
            100_000.0,
            _orchestrator_config(edge_state_store_path=store_path),
        )

    assert baseline.allocation.approved is True
    assert warning_result.allocation.approved is True
    assert warning_result.selected_edge_state is not None
    assert warning_result.selected_edge_state.status == "WARNING"
    assert warning_result.allocation.share_count < baseline.allocation.share_count


def test_run_prdv3_master_orchestrator_fail_closes_when_no_trade_exists() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    bars = _trend_up_bars(40)

    result = run_prdv3_master_orchestrator([edge], bars, 100_000.0)

    assert result.valid is False
    assert result.selected_edge_id is None
    assert result.reason == "NO TRADE: no_active_edges_after_state_filter"
    assert result.contracts["strategy"]["status"] == "BLOCKED"
    assert result.contracts["risk"]["status"] == "BLOCKED"


def test_run_prdv3_master_orchestrator_is_contract_consistent() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    bars = _trend_up_bars()

    result = run_prdv3_master_orchestrator([edge], bars, 100_000.0, _orchestrator_config())

    assert result.valid is True
    assert result.selected_edge_id == edge.edge_id
    assert result.selected_edge_state is not None
    assert result.selected_edge_state.edge_id == edge.edge_id
    assert result.allocation.approved is True
    assert result.execution.valid is True
    assert result.contracts["data"]["status"] == "SAFE"
    assert result.contracts["strategy"]["status"] == "READY"
    assert result.contracts["risk"]["status"] == "ALLOWED"
    assert all(trade.edge_id == edge.edge_id for trade in result.execution.trades)