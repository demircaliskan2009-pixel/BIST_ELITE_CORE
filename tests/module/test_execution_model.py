"""Tests for ExecutionModel — deterministic, no randomness."""

from __future__ import annotations

import pytest

from bist_core.execution.execution_model import ExecutionModel, apply_to_trade


def test_deterministic_output() -> None:
    m = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
    a = m.apply_execution("BUY", 100.0, 105.0, 100.0)
    b = m.apply_execution("BUY", 100.0, 105.0, 100.0)
    assert a == b
    assert a["entry_fill"] == b["entry_fill"]
    assert a["exit_fill"] == b["exit_fill"]
    assert a["net_pnl"] == b["net_pnl"]


def test_cost_calculation() -> None:
    m = ExecutionModel(slippage_bps=0, spread_bps=0, commission_bps=10.0)
    r = m.apply_execution("BUY", 100.0, 110.0, 100.0)
    gross = (110.0 - 100.0) * 100.0
    assert r["gross_pnl"] == gross
    cost = (100.0 * 100.0 + 110.0 * 100.0) * 10.0 / 10000.0
    assert abs(r["cost"] - cost) < 0.01
    assert r["net_pnl"] == gross - cost


def test_slippage_application() -> None:
    m = ExecutionModel(slippage_bps=10.0, spread_bps=0, commission_bps=0)
    r = m.apply_execution("BUY", 100.0, 105.0, 100.0)
    assert r["entry_fill"] > 100.0
    assert r["exit_fill"] < 105.0
    assert r["entry_fill"] == pytest.approx(100.1, rel=0.01)
    assert r["exit_fill"] == pytest.approx(104.9, rel=0.01)


def test_spread_application() -> None:
    m = ExecutionModel(slippage_bps=0, spread_bps=20.0, commission_bps=0)
    r = m.apply_execution("BUY", 100.0, 105.0, 100.0)
    assert r["entry_fill"] > 100.0
    assert r["exit_fill"] < 105.0


def test_pnl_correctness() -> None:
    m = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
    r = m.apply_execution("BUY", 100.0, 105.0, 100.0)
    gross = (r["exit_fill"] - r["entry_fill"]) * 100.0
    assert abs(r["gross_pnl"] - gross) < 0.01
    assert abs(r["net_pnl"] - (gross - r["cost"])) < 0.01


def test_apply_to_trade() -> None:
    m = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
    trade = {"entry": 100.0, "exit": 105.0, "size": 50.0}
    out = apply_to_trade(trade, m)
    assert "entry_fill" in out
    assert "exit_fill" in out
    assert "gross_pnl" in out
    assert "net_pnl" in out
    assert "cost" in out
    assert out["pnl"] == out["net_pnl"]


def test_invalid_inputs_raise() -> None:
    m = ExecutionModel()
    with pytest.raises(ValueError, match="Invalid"):
        m.apply_execution("BUY", 100.0, 105.0, 0.0)
    with pytest.raises(ValueError, match="Invalid"):
        m.apply_execution("BUY", 100.0, 105.0, -1.0)
    with pytest.raises(ValueError, match="Invalid"):
        m.apply_execution("BUY", 0.0, 105.0, 100.0)
