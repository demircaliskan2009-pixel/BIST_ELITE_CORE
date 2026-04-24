from __future__ import annotations

from bist_core.edge.registry import build_builtin_edge_registry
from bist_core.edge.validation import EdgeValidationConfig, run_edge_validation_backtest
from bist_core.models.ohlcv import OHLCVBar


def _edge():
    registry = build_builtin_edge_registry()
    return next(edge for edge in registry.list_active_edges() if edge.edge_id == "bist_bear_oversold_snap")


def _bar(ts: int, close: float, spread: float = 0.8, volume: float = 1_200_000.0) -> OHLCVBar:
    open_price = close + (spread * 0.2)
    high = max(open_price, close) + spread
    low = max(min(open_price, close) - spread, 0.01)
    return OHLCVBar(ts, "X", round(open_price, 4), round(high, 4), round(low, 4), round(close, 4), volume)


def _trend_down_bars(n: int = 61) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86_400, 120.0 - i * 0.7) for i in range(n)]


def test_edge_validation_backtest_is_deterministic() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    config = EdgeValidationConfig(commission_pct=0.001, slippage_pct=0.0005, initial_capital=1_000.0)

    first = run_edge_validation_backtest(edge, bars, config)
    second = run_edge_validation_backtest(edge, bars, config)

    assert first.to_dict() == second.to_dict()
    assert first.valid is True
    assert first.metrics["total_trades"] == 1
    assert first.metrics["total_cost"] > 0.0
    assert first.trades[0].entry_bar_index == first.trades[0].signal_bar_index + 1
    assert first.trades[0].entry_open_price == bars[first.trades[0].entry_bar_index].open


def test_edge_validation_backtest_does_not_use_future_data_for_entry() -> None:
    edge = _edge()
    baseline = _trend_down_bars()
    mutated = list(baseline)
    last = mutated[-1]
    mutated[-1] = OHLCVBar(
        timestamp=last.timestamp,
        symbol=last.symbol,
        open=last.open,
        high=last.open + 12.0,
        low=max(last.open - 1.0, 0.01),
        close=last.close + 10.0,
        volume=last.volume,
    )

    baseline_result = run_edge_validation_backtest(edge, baseline)
    mutated_result = run_edge_validation_backtest(edge, mutated)

    assert baseline_result.valid is True
    assert mutated_result.valid is True
    assert baseline_result.trades[0].signal_bar_index == mutated_result.trades[0].signal_bar_index
    assert baseline_result.trades[0].entry_bar_index == mutated_result.trades[0].entry_bar_index
    assert baseline_result.trades[0].entry_open_price == mutated_result.trades[0].entry_open_price
    assert baseline_result.trades[0].entry_fill_price == mutated_result.trades[0].entry_fill_price


def test_edge_validation_backtest_fail_closes_on_invalid_data() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    broken = list(bars)
    broken[10] = OHLCVBar(
        timestamp=broken[9].timestamp,
        symbol=broken[10].symbol,
        open=broken[10].open,
        high=broken[10].high,
        low=broken[10].low,
        close=broken[10].close,
        volume=broken[10].volume,
    )

    result = run_edge_validation_backtest(edge, broken)

    assert result.valid is False
    assert result.blocked_reason == "invalid_data:non_monotonic_timestamps"
    assert result.metrics["total_trades"] == 0
    assert result.trades == ()