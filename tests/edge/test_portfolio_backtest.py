from __future__ import annotations

from dataclasses import replace

import pytest

from bist_core.edge.orchestrator import PRDV3MasterOrchestratorConfig
from bist_core.edge.paper_trading import PaperTradingConfig
from bist_core.edge.portfolio import PRDV3PortfolioEngineConfig
from bist_core.edge.portfolio_backtest import PRDV3PortfolioBacktestConfig, run_prdv3_portfolio_backtest
from bist_core.edge.registry import build_builtin_edge_registry
from bist_core.edge.validation import EdgeRobustnessConfig
from bist_core.models.ohlcv import OHLCVBar

pytestmark = pytest.mark.slow


def _edge(edge_id: str = "bist_bull_pullback_sma20"):
    registry = build_builtin_edge_registry()
    return next(edge for edge in registry.list_active_edges() if edge.edge_id == edge_id)


def _trend_up_bars(
    symbol: str,
    n: int = 250,
    slope: float = 0.45,
    spread: float = 0.55,
    volume: float = 1_000_000.0,
) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    for index in range(n):
        close_price = 100.0 + index * slope
        open_price = close_price - (spread * 0.2)
        high = max(open_price, close_price) + spread
        low = max(min(open_price, close_price) - spread, 0.01)
        bars.append(
            OHLCVBar(
                timestamp=1_704_067_200 + index * 86_400,
                symbol=symbol,
                open=round(open_price, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close_price, 4),
                volume=volume,
            )
        )
    return bars


def _backtest_config(**kwargs) -> PRDV3PortfolioBacktestConfig:
    orchestrator_config = PRDV3MasterOrchestratorConfig(
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
    portfolio_engine_config = PRDV3PortfolioEngineConfig(
        orchestrator_config=orchestrator_config,
        max_total_exposure_pct=0.30,
        max_per_trade_pct=0.10,
        max_concurrent_positions=5,
        max_similar_trades=99,
    )
    config = PRDV3PortfolioBacktestConfig(
        portfolio_engine_config=portfolio_engine_config,
        paper_trading_config=PaperTradingConfig(
            initial_capital=100_000.0,
            commission_pct=0.001,
            slippage_pct=0.0005,
            max_fill_share_of_bar_volume=0.01,
        ),
    )
    for key, value in kwargs.items():
        config = replace(config, **{key: value})
    return config


def test_run_prdv3_portfolio_backtest_is_deterministic() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    symbols = ["AAA", "BBB", "CCC"]
    historical_data = {symbol: _trend_up_bars(symbol) for symbol in symbols}
    config = _backtest_config()

    first = run_prdv3_portfolio_backtest([edge], symbols, historical_data, 100_000.0, config)
    second = run_prdv3_portfolio_backtest([edge], symbols, historical_data, 100_000.0, config)

    assert first.to_dict() == second.to_dict()
    assert first.valid is True
    assert first.metrics["trade_count"] >= 1


def test_run_prdv3_portfolio_backtest_respects_capital_locking_and_exposure() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    historical_data = {
        symbol: _trend_up_bars(symbol, slope=0.40 + (index * 0.02)) for index, symbol in enumerate(symbols)
    }
    config = _backtest_config(
        portfolio_engine_config=replace(
            _backtest_config().portfolio_engine_config,
            max_total_exposure_pct=0.10,
            max_per_trade_pct=0.05,
            max_concurrent_positions=2,
        )
    )

    result = run_prdv3_portfolio_backtest([edge], symbols, historical_data, 100_000.0, config)

    assert result.valid is True
    assert all(point["total_exposure_pct"] <= 0.10 + 1e-9 for point in result.equity_curve)
    assert all(point["open_positions"] <= 2 for point in result.equity_curve)
    assert all(point["cash"] >= 0.0 for point in result.equity_curve)


def test_run_prdv3_portfolio_backtest_skips_invalid_symbol_data() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    valid = _trend_up_bars("AAA")
    invalid = list(_trend_up_bars("BAD"))
    invalid[20] = OHLCVBar(
        timestamp=invalid[19].timestamp,
        symbol="BAD",
        open=invalid[20].open,
        high=invalid[20].high,
        low=invalid[20].low,
        close=invalid[20].close,
        volume=invalid[20].volume,
    )

    result = run_prdv3_portfolio_backtest(
        [edge],
        ["AAA", "BAD"],
        {"AAA": valid, "BAD": invalid},
        100_000.0,
        _backtest_config(),
    )

    assert result.valid is True
    assert "BAD" in result.skipped_symbols
    assert result.metrics["trade_count"] >= 1


def test_run_prdv3_portfolio_backtest_skips_entries_without_liquidity() -> None:
    edge = _edge("bist_bull_pullback_sma20")
    historical_data = {"AAA": _trend_up_bars("AAA", volume=0.0)}

    result = run_prdv3_portfolio_backtest([edge], ["AAA"], historical_data, 100_000.0, _backtest_config())

    assert result.valid is True
    assert result.metrics["trade_count"] == 0
    assert "AAA" in result.skipped_symbols
    assert any(log["event"] == "symbol_skipped" and log["reason"] == "no_liquidity_history" for log in result.logs)
