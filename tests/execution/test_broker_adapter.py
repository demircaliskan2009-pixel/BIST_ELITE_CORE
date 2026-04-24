from __future__ import annotations

import pytest

from bist_core.execution.broker_adapter import (
    BrokerResponse,
    DummyBrokerAdapter,
    OrderStatus,
)
from bist_core.execution.order_state_machine import Order, OrderState
from bist_core.execution.paper_engine import OrderSide
from bist_core.providers.base import FailClosedError


def _validated_order(**overrides: object) -> Order:
    payload = {
        "order_id": "ORD-0001",
        "symbol": "ASELS",
        "side": OrderSide.BUY,
        "quantity": 100,
        "filled_quantity": 0,
        "price": 42.5,
        "state": OrderState.VALIDATED,
        "timestamp": 1,
        "last_update": 2,
    }
    payload.update(overrides)
    return Order(**payload)


def test_send_order_returns_accepted() -> None:
    adapter = DummyBrokerAdapter()

    response = adapter.send_order(_validated_order())

    assert response == BrokerResponse(
        order_id="ORD-0001",
        status=OrderStatus.ACCEPTED,
        filled_quantity=0,
        avg_price=0.0,
        timestamp=1,
        reason=None,
    )


def test_cancel_order_works() -> None:
    adapter = DummyBrokerAdapter()
    adapter.send_order(_validated_order())

    response = adapter.cancel_order("ORD-0001")

    assert response.status is OrderStatus.CANCELLED
    assert response.order_id == "ORD-0001"
    assert response.timestamp == 2
    assert adapter.get_order_status("ORD-0001") == response


def test_unknown_order_fails_closed() -> None:
    adapter = DummyBrokerAdapter()

    with pytest.raises(FailClosedError, match="unknown_order_id"):
        adapter.get_order_status("ORD-4040")

    with pytest.raises(FailClosedError, match="unknown_order_id"):
        adapter.cancel_order("ORD-4040")


def test_deterministic_behavior() -> None:
    first_adapter = DummyBrokerAdapter()
    second_adapter = DummyBrokerAdapter()

    first_send = first_adapter.send_order(_validated_order())
    second_send = second_adapter.send_order(_validated_order())
    first_cancel = first_adapter.cancel_order("ORD-0001")
    second_cancel = second_adapter.cancel_order("ORD-0001")

    assert first_send == second_send
    assert first_cancel == second_cancel


def test_invalid_quantity_fails_closed() -> None:
    adapter = DummyBrokerAdapter()

    with pytest.raises(FailClosedError, match="invalid_quantity"):
        adapter.send_order(_validated_order(quantity=0))


def test_invalid_state_fails_closed() -> None:
    adapter = DummyBrokerAdapter()

    with pytest.raises(FailClosedError, match="invalid_state"):
        adapter.send_order(_validated_order(state=OrderState.NEW))