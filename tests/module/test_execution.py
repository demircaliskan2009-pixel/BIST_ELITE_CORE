"""Tests for Execution Intelligence Layer — Position, Executor, Portfolio, Logger."""

from __future__ import annotations

import pytest

from bist_core.execution.position import Position
from bist_core.execution.executor import PaperExecutor, compute_risk_size
from bist_core.execution.portfolio import Portfolio
from bist_core.execution.logger import TradeLogger


def test_open_position() -> None:
    """Position tracks entry, stop, target, size."""
    pos = Position(symbol="GARAN", entry=100.0, stop=95.0, target=110.0, size=10.0)
    assert pos.symbol == "GARAN"
    assert pos.entry == 100.0
    assert pos.is_stop_hit(94.0) is True
    assert pos.is_stop_hit(96.0) is False
    assert pos.is_target_hit(111.0) is True
    assert pos.is_target_hit(109.0) is False


def test_close_position_profit() -> None:
    """Close at target → profit."""
    portfolio = Portfolio(capital=10000.0)
    pos = Position(symbol="GARAN", entry=100.0, stop=95.0, target=110.0, size=10.0)
    portfolio.open_position(pos)
    assert portfolio.current_value() == 10000.0
    portfolio.close_position(pos, pos.target)
    assert portfolio.current_value() == 10000.0 - 1000.0 + 1100.0


def test_close_position_loss() -> None:
    """Close at stop → loss."""
    portfolio = Portfolio(capital=10000.0)
    pos = Position(symbol="GARAN", entry=100.0, stop=95.0, target=110.0, size=10.0)
    portfolio.open_position(pos)
    portfolio.close_position(pos, pos.stop)
    assert portfolio.current_value() == 10000.0 - 1000.0 + 950.0


def test_no_trade_skipped() -> None:
    """NO_TRADE decision does not create position."""
    executor = PaperExecutor()
    decision = {"action": "NO_TRADE", "symbol": "X"}
    result = executor.execute(decision)
    assert result["executed"] is False
    assert result["position"] is None


def test_portfolio_update() -> None:
    """Portfolio tracks capital and positions."""
    portfolio = Portfolio(capital=10000.0)
    pos = Position(symbol="GARAN", entry=100.0, stop=95.0, target=110.0, size=5.0)
    portfolio.open_position(pos)
    assert portfolio.current_value() == 10000.0
    assert len(portfolio.open_positions) == 1
    portfolio.close_position(pos, 105.0)
    assert portfolio.current_value() == 10000.0 - 500.0 + 525.0


def test_logger_records() -> None:
    """TradeLogger records trades."""
    logger = TradeLogger()
    logger.log_trade({"symbol": "GARAN", "pnl": 100.0})
    logger.log_trade({"symbol": "ASELS", "pnl": -50.0})
    history = logger.history()
    assert len(history) == 2
    assert history[0]["symbol"] == "GARAN"
    assert history[1]["symbol"] == "ASELS"


def test_determinism() -> None:
    """Same operations produce same results."""
    portfolio = Portfolio(capital=1000.0)
    pos = Position(symbol="X", entry=10.0, stop=9.0, target=12.0, size=1.0)
    portfolio.open_position(pos)
    a = portfolio.current_value()
    portfolio.close_position(pos, 11.0)
    b = portfolio.current_value()
    portfolio2 = Portfolio(capital=1000.0)
    pos2 = Position(symbol="X", entry=10.0, stop=9.0, target=12.0, size=1.0)
    portfolio2.open_position(pos2)
    portfolio2.close_position(pos2, 11.0)
    assert b == portfolio2.current_value()


def test_full_trade_flow() -> None:
    """Decision → Executor → Portfolio → Logger."""
    from bist_core.decision import DecisionEngine

    decision = {
        "symbol": "GARAN",
        "action": "BUY",
        "entry": 100.0,
        "stop": 98.0,
        "target": 104.0,
        "confidence": 0.8,
        "score": 5.0,
        "reasons": {},
    }
    executor = PaperExecutor()
    portfolio = Portfolio(capital=10000.0)
    logger = TradeLogger()

    result = executor.execute(decision)
    assert result["executed"] is True
    assert result["position"] is not None

    pos = result["position"]
    portfolio.open_position(pos)
    logger.log_trade({
        "symbol": pos.symbol,
        "entry": pos.entry,
        "stop": pos.stop,
        "target": pos.target,
        "size": pos.size,
    })

    assert len(portfolio.open_positions) == 1
    assert portfolio.current_value() == 10000.0
    assert len(logger.history()) == 1

    portfolio.close_position(pos, pos.target)
    logger.log_trade({
        "symbol": pos.symbol,
        "exit": pos.target,
        "pnl": (pos.target - pos.entry) * pos.size,
    })

    assert len(portfolio.open_positions) == 0
    assert portfolio.current_value() == 10000.0 - 100.0 + 104.0
    assert len(logger.history()) == 2


def test_executor_buy_creates_position() -> None:
    """BUY decision creates position."""
    executor = PaperExecutor()
    decision = {
        "symbol": "GARAN",
        "action": "BUY",
        "entry": 100.0,
        "stop": 95.0,
        "target": 110.0,
        "reasons": {},
    }
    result = executor.execute(decision)
    assert result["executed"] is True
    assert result["position"].symbol == "GARAN"
    assert result["position"].entry == 100.0
    assert result["position"].size == 1.0


def test_risk_based_position_sizing() -> None:
    """Executor uses capital * 0.01 / abs(entry - stop) when capital provided."""
    executor = PaperExecutor()
    decision = {
        "symbol": "GARAN",
        "action": "BUY",
        "entry": 100.0,
        "stop": 98.0,
        "target": 104.0,
        "reasons": {},
    }
    result = executor.execute(decision, capital=100_000.0)
    assert result["executed"] is True
    expected_size = 100_000.0 * 0.01 / 2.0
    assert result["position"].size == pytest.approx(expected_size, rel=1e-6)


def test_compute_risk_size() -> None:
    """compute_risk_size: size = capital * 0.01 / abs(entry - stop)."""
    assert compute_risk_size(100_000, 100, 98) == 500.0
    assert compute_risk_size(100_000, 100, 95) == pytest.approx(200.0, rel=1e-6)
    assert compute_risk_size(0, 100, 98) == 0.0
    assert compute_risk_size(100_000, 100, 100) == 0.0
