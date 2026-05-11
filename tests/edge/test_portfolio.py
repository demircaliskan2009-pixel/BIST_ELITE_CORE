from __future__ import annotations

from dataclasses import replace

from bist_core.edge.portfolio import PRDV3PortfolioEngineConfig, run_prdv3_multi_symbol_portfolio_engine
from bist_core.edge.orchestrator import PRDV3MasterOrchestratorConfig
from bist_core.edge.registry import build_builtin_edge_registry
from bist_core.edge.validation import EdgeRobustnessConfig
from bist_core.models.ohlcv import OHLCVBar


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


def _portfolio_config(**kwargs) -> PRDV3PortfolioEngineConfig:
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
    config = PRDV3PortfolioEngineConfig(orchestrator_config=orchestrator_config)
    for key, value in kwargs.items():
        config = replace(config, **{key: value})
    return config


def test_run_prdv3_multi_symbol_portfolio_engine_is_deterministic() -> None:
    edge = _edge()
    symbols = ["AAA", "BBB", "CCC"]
    symbol_data = {symbol: _trend_up_bars(symbol) for symbol in symbols}
    config = _portfolio_config(max_similar_trades=99)

    first = run_prdv3_multi_symbol_portfolio_engine([edge], symbols, symbol_data, 100_000.0, config)
    second = run_prdv3_multi_symbol_portfolio_engine([edge], symbols, symbol_data, 100_000.0, config)

    assert first.to_dict() == second.to_dict()
    assert first.valid is True


def test_run_prdv3_multi_symbol_portfolio_engine_respects_global_exposure_caps() -> None:
    edge = _edge()
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    symbol_data = {
        "AAA": _trend_up_bars("AAA", slope=0.42, spread=0.50),
        "BBB": _trend_up_bars("BBB", slope=0.44, spread=0.52),
        "CCC": _trend_up_bars("CCC", slope=0.46, spread=0.54),
        "DDD": _trend_up_bars("DDD", slope=0.48, spread=0.56),
        "EEE": _trend_up_bars("EEE", slope=0.50, spread=0.58),
    }
    config = _portfolio_config(max_similar_trades=99)

    result = run_prdv3_multi_symbol_portfolio_engine([edge], symbols, symbol_data, 100_000.0, config)

    assert result.valid is True
    assert result.total_exposure <= 0.30
    assert len(result.trade_plan) <= 5
    assert sum(entry.allocation_pct for entry in result.trade_plan) <= 0.30
    assert all(entry.allocation_pct <= 0.10 for entry in result.trade_plan)
    assert sum(entry.position_size for entry in result.trade_plan) <= 30_000.0


def test_run_prdv3_multi_symbol_portfolio_engine_rejects_missing_and_invalid_symbols() -> None:
    edge = _edge()
    valid_bars = _trend_up_bars("AAA")
    invalid_bars = list(_trend_up_bars("BAD"))
    invalid_bars[50] = OHLCVBar(
        timestamp=invalid_bars[49].timestamp,
        symbol="BAD",
        open=invalid_bars[50].open,
        high=invalid_bars[50].high,
        low=invalid_bars[50].low,
        close=invalid_bars[50].close,
        volume=invalid_bars[50].volume,
    )

    result = run_prdv3_multi_symbol_portfolio_engine(
        [edge],
        ["AAA", "MISSING", "BAD"],
        {"AAA": valid_bars, "BAD": invalid_bars},
        100_000.0,
        _portfolio_config(max_similar_trades=99),
    )

    assert result.valid is True
    assert "BAD" in result.risk_report.rejected_symbols
    assert "MISSING" in result.risk_report.rejected_symbols
    assert any(decision.symbol == "AAA" and decision.approved for decision in result.portfolio_decisions)


def test_run_prdv3_multi_symbol_portfolio_engine_has_consistent_rank_order() -> None:
    edge = _edge()
    symbols = ["CCC", "AAA", "BBB"]
    symbol_data = {symbol: _trend_up_bars(symbol) for symbol in symbols}

    result = run_prdv3_multi_symbol_portfolio_engine(
        [edge],
        symbols,
        symbol_data,
        100_000.0,
        _portfolio_config(max_similar_trades=99),
    )

    assert result.valid is True
    assert [entry.symbol for entry in result.trade_plan] == ["AAA", "BBB", "CCC"]


def test_run_prdv3_multi_symbol_portfolio_engine_limits_correlation_clusters() -> None:
    edge = _edge()
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    identical = _trend_up_bars("AAA")
    symbol_data = {
        "AAA": identical,
        "BBB": [replace(bar, symbol="BBB") for bar in identical],
        "CCC": [replace(bar, symbol="CCC") for bar in identical],
        "DDD": [replace(bar, symbol="DDD") for bar in identical],
    }
    config = _portfolio_config(
        max_total_exposure_pct=0.50,
        max_per_trade_pct=0.20,
        max_similar_trades=2,
        max_concurrent_positions=5,
    )

    result = run_prdv3_multi_symbol_portfolio_engine([edge], symbols, symbol_data, 100_000.0, config)

    assert result.valid is True
    assert [entry.symbol for entry in result.trade_plan] == ["AAA", "BBB"]
    assert "CCC" in result.risk_report.rejected_symbols
    assert "DDD" in result.risk_report.rejected_symbols