from __future__ import annotations

from bist_core.edge.paper_trading import PaperTradingConfig, run_edge_paper_trading
from bist_core.edge.registry import build_builtin_edge_registry
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


def _trend_down_bars(n: int = 70, spread: float = 0.8, volume: float = 1_200_000.0) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86_400, 120.0 - i * 0.7, spread=spread, volume=volume) for i in range(n)]


def test_run_edge_paper_trading_is_deterministic() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, bars)
    config = PaperTradingConfig(initial_capital=100_000.0)

    first = run_edge_paper_trading([edge], [validation], bars, config)
    second = run_edge_paper_trading([edge], [validation], bars, config)

    assert first.to_dict() == second.to_dict()
    assert first.valid is True
    assert first.metrics["entries_filled"] >= 1


def test_run_edge_paper_trading_does_not_use_future_data_for_entry() -> None:
    edge = _edge()
    baseline = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, baseline)
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

    baseline_result = run_edge_paper_trading([edge], [validation], baseline)
    mutated_result = run_edge_paper_trading([edge], [validation], mutated)

    assert baseline_result.valid is True
    assert mutated_result.valid is True
    assert baseline_result.trades[0].signal_bar_index == mutated_result.trades[0].signal_bar_index
    assert baseline_result.trades[0].entry_bar_index == mutated_result.trades[0].entry_bar_index
    assert baseline_result.trades[0].entry_fill_price == mutated_result.trades[0].entry_fill_price


def test_run_edge_paper_trading_tracks_one_position_at_a_time() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, bars)

    result = run_edge_paper_trading([edge], [validation], bars)

    assert result.valid is True
    assert len(result.trades) >= 1
    assert result.open_positions == ()
    assert result.equity_curve[-1]["position_qty"] == 0
    assert sum(1 for log in result.logs if log["event"] == "entry_filled") == len(result.trades)

    open_count = 0
    for log in result.logs:
        if log["event"] == "entry_filled":
            open_count += 1
            assert open_count == 1
        if log["event"] in {"exit_filled", "exit_filled_end_of_data"}:
            open_count -= 1
            assert open_count == 0

    assert open_count == 0


def test_run_edge_paper_trading_fail_closes_entry_on_liquidity_block() -> None:
    edge = _edge()
    bars = _trend_down_bars()
    validation = run_edge_validation_backtest(edge, bars)
    baseline_result = run_edge_paper_trading([edge], [validation], bars)
    blocked_bars = list(bars)

    for index in range(baseline_result.trades[0].entry_bar_index, len(blocked_bars)):
        bar = blocked_bars[index]
        blocked_bars[index] = OHLCVBar(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=0.0,
        )

    result = run_edge_paper_trading([edge], [validation], blocked_bars)

    assert result.valid is True
    assert result.trades == ()
    assert result.open_positions == ()
    assert result.metrics["entries_filled"] == 0
    assert any(log["event"] == "entry_blocked_liquidity" for log in result.logs)