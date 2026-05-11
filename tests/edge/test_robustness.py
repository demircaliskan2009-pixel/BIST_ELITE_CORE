from __future__ import annotations

from bist_core.edge.registry import build_builtin_edge_registry
from bist_core.edge.validation import (
    EdgeRobustnessConfig,
    run_edge_robustness_validation,
)
from bist_core.models.ohlcv import OHLCVBar


def _edge():
    registry = build_builtin_edge_registry()
    return next(edge for edge in registry.list_active_edges() if edge.edge_id == "bist_bear_oversold_snap")


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


def _unstable_bear_cycles() -> list[OHLCVBar]:
    bars = _stable_bear_cycles(3)
    timestamp = bars[-1].timestamp + 86_400
    close_price = float(bars[-1].close) + 8.0
    for _ in range(60):
        close_price, timestamp = _append_bar(bars, timestamp, close_price, -1.6, 700_000.0, 1.8)
    for _ in range(20):
        close_price, timestamp = _append_bar(bars, timestamp, close_price, -2.2, 450_000.0, 2.4)
    for _ in range(20):
        close_price, timestamp = _append_bar(bars, timestamp, close_price, 0.2, 500_000.0, 1.2)
    return bars


def test_edge_robustness_validation_accepts_consistent_periods() -> None:
    edge = _edge()
    bars = _stable_bear_cycles()
    config = EdgeRobustnessConfig(
        train_bars=120,
        test_bars=90,
        step_bars=45,
        min_walk_forward_windows=2,
        min_trade_count=3,
        min_expectancy_threshold=-3.0,
        max_avg_train_test_expectancy_gap=3.0,
        min_positive_test_window_ratio=0.0,
        max_test_expectancy_range=3.5,
    )

    result = run_edge_robustness_validation(edge, bars, robustness_config=config)

    assert result.valid is True
    assert result.blocked_reason is None
    assert len(result.walk_forward_windows) >= 2
    assert result.metrics["walk_forward_avg_expectancy_gap"] <= 3.0
    assert result.metrics["walk_forward_test_expectancy_range"] <= 3.5
    assert len(result.stress_results) == 3


def test_edge_robustness_validation_rejects_unstable_edge() -> None:
    edge = _edge()
    bars = _unstable_bear_cycles()
    config = EdgeRobustnessConfig(
        train_bars=120,
        test_bars=90,
        step_bars=45,
        min_walk_forward_windows=2,
        min_trade_count=1,
        min_expectancy_threshold=-3.0,
        max_avg_train_test_expectancy_gap=1.0,
        min_positive_test_window_ratio=0.0,
        max_test_expectancy_range=1.0,
    )

    result = run_edge_robustness_validation(edge, bars, robustness_config=config)

    assert result.valid is False
    assert result.blocked_reason in {"overfit_expectancy_gap", "unstable_expectancy_range", "minimum_expectancy_failed:stress:gap"}
    assert len(result.walk_forward_windows) >= 2