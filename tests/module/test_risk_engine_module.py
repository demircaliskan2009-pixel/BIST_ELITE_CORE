"""Tests for Trade Risk Engine — position risk validation."""

from __future__ import annotations

import math

from bist_core.risk import TradeRiskEngine


def test_position_size_invalid_rejected() -> None:
    """Reject if position_size <= 0, NaN, or inf."""
    engine = TradeRiskEngine()
    capital = 100_000.0

    assert engine.accept({"size": 0, "risk_pct": 0.015}, capital, 0.0) is False
    assert engine.accept({"size": -1, "risk_pct": 0.015}, capital, 0.0) is False
    assert engine.accept({"size": math.nan, "risk_pct": 0.015}, capital, 0.0) is False
    assert engine.accept({"size": float("inf"), "risk_pct": 0.015}, capital, 0.0) is False


def test_daily_loss_limit_enforced() -> None:
    """Reject if cumulative_risk + new_risk > capital * daily_loss_limit."""
    engine = TradeRiskEngine()
    capital = 100_000.0
    limit = capital * 0.05

    position = {"size": 100.0, "risk_pct": 0.015, "entry": 100.0, "stop": 98.0}
    risk_amount = capital * 0.015

    assert engine.accept(position, capital, 0.0) is True
    assert engine.accept(position, capital, limit - risk_amount) is True
    assert engine.accept(position, capital, limit - risk_amount + 0.01) is False


def test_valid_position_accepted() -> None:
    """Valid position with positive size and within limits is accepted."""
    engine = TradeRiskEngine()
    position = {"size": 750.0, "risk_pct": 0.015, "entry": 100.0, "stop": 98.0}
    assert engine.accept(position, 100_000.0, 0.0) is True


def test_deterministic_behavior() -> None:
    """Same input produces same result."""
    engine = TradeRiskEngine()
    position = {"size": 500.0, "risk_pct": 0.015}
    a = engine.accept(position, 100_000.0, 0.0)
    b = engine.accept(position, 100_000.0, 0.0)
    assert a == b


def test_zero_capital_rejected() -> None:
    """Zero capital rejects."""
    engine = TradeRiskEngine()
    position = {"size": 100.0, "risk_pct": 0.015}
    assert engine.accept(position, 0.0, 0.0) is False
