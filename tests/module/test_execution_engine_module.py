"""ExecutionEngine — paper orders, deterministic IDs, state machine."""

from __future__ import annotations

from bist_core.execution.execution_engine import ExecutionEngine


def test_create_order_deterministic_ids() -> None:
    eng = ExecutionEngine()
    a = eng.create_order("GARAN", "buy", 10.0, 100)
    b = eng.create_order("GARAN", "sell", 10.0, 100)
    assert a.id == "paper:0000000001"
    assert b.id == "paper:0000000002"
    assert a.status == "pending"
    assert eng.orders[a.id] is a


def test_fill_buy_sell_paper_rules() -> None:
    eng = ExecutionEngine()
    buy = eng.create_order("X", "buy", 50.0, 10)
    assert eng.process_fill(buy, 49.0) is True
    assert buy.status == "partial"
    assert buy.filled_size == 7
    sell = eng.create_order("X", "sell", 50.0, 10)
    assert eng.process_fill(sell, 51.0) is True
    assert sell.status == "partial"
    assert sell.filled_size == 7


def test_fill_no_cross_no_fill() -> None:
    eng = ExecutionEngine()
    buy = eng.create_order("X", "buy", 50.0, 10)
    assert eng.process_fill(buy, 50.01) is False
    assert buy.status == "pending"


def test_cancel_pending_only() -> None:
    eng = ExecutionEngine()
    o = eng.create_order("X", "buy", 1.0, 1)
    assert eng.cancel_order(o.id) is True
    assert o.status == "cancelled"
    assert eng.process_fill(o, 0.5) is False
    assert eng.cancel_order(o.id) is False


def test_no_transition_from_filled() -> None:
    eng = ExecutionEngine()
    o = eng.create_order("X", "buy", 10.0, 10)
    eng.process_fill(o, 10.0)
    assert o.status == "partial"
    assert o.filled_size == 7
    assert eng.cancel_order(o.id) is False
