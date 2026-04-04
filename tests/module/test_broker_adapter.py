"""PaperBrokerAdapter — create + fill wiring."""

from __future__ import annotations

from bist_core.execution.broker_adapter import PaperBrokerAdapter
from bist_core.execution.execution_engine import ExecutionEngine


def test_paper_broker_send_order_returns_id_and_fills() -> None:
    eng = ExecutionEngine()
    br = PaperBrokerAdapter(eng)
    oid = br.send_order("GARAN", "buy", 10.0, 100, market_price=10.0)
    assert oid.startswith("paper:")
    assert br.get_order_status(oid) == "partial"


def test_paper_broker_cancel_pending() -> None:
    eng = ExecutionEngine()
    br = PaperBrokerAdapter(eng)
    o = eng.create_order("X", "buy", 100.0, 1)
    assert br.cancel_order(o.id) is True
    assert br.get_order_status(o.id) == "cancelled"
