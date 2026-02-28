"""FAZ116: OrderBridgeInterface (abstract base) + OrderBridgeDLL implementation + Flask arayüzü."""

from __future__ import annotations

import pytest

from bist_core.connectors.order_bridge_base import OrderBridgeInterface
from bist_core.connectors.order_bridge_dll import OrderBridgeDLL
from bist_core.connectors.order_bridge_interface import app, order_bridge, pending_orders


def test_order_bridge_interface_is_abstract() -> None:
    """OrderBridgeInterface is an abstract base; send_order is abstract."""
    assert hasattr(OrderBridgeInterface, "send_order")
    assert "send_order" in getattr(OrderBridgeInterface, "__abstractmethods__", set())


def test_order_bridge_dll_implements_interface() -> None:
    """OrderBridgeDLL implements OrderBridgeInterface (abstract base for order routing)."""
    assert issubclass(OrderBridgeDLL, OrderBridgeInterface)
    dll = OrderBridgeDLL()
    result = dll.send_order("buy")
    assert isinstance(result, dict)
    assert "sent" in result
    assert "confirmation" in result
    assert "order_type" in result
    assert result["order_type"] == "buy"


def test_confirm_order(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict = {}

    def dummy_send(order_type: str) -> None:
        called["order_type"] = order_type

    monkeypatch.setattr(order_bridge, "send_order", dummy_send)
    pending_orders.clear()
    pending_orders.append({"id": 1, "type": "buy"})
    client = app.test_client()
    res = client.get("/confirm/1")
    assert res.status_code == 200
    assert b"Order confirmed" in res.data
    assert called.get("order_type") == "buy"
    assert pending_orders == []


def test_confirm_order_not_found() -> None:
    pending_orders.clear()
    client = app.test_client()
    res = client.get("/confirm/999")
    assert res.status_code == 404


def test_index_page() -> None:
    pending_orders.clear()
    client = app.test_client()
    res = client.get("/")
    assert b"Bekleyen emir yok" in res.data
    pending_orders.append({"id": 5, "type": "sell"})
    res = client.get("/")
    data = res.data.decode("utf-8")
    assert "Emir 5" in data and "SELL" in data and "Onayla" in data
