from __future__ import annotations

import pytest

from bist_core.execution.order_state_machine import Order, OrderState, OrderStateMachine
from bist_core.execution.paper_engine import OrderSide
from bist_core.providers.base import FailClosedError


def _new_order(**overrides: object) -> Order:
    payload = {
        "order_id": "ORD-0001",
        "symbol": "ASELS",
        "side": OrderSide.BUY,
        "quantity": 100,
        "filled_quantity": 0,
        "price": 42.5,
        "state": OrderState.NEW,
        "timestamp": 1,
        "last_update": 1,
    }
    payload.update(overrides)
    return Order(**payload)


def test_valid_lifecycle() -> None:
    machine = OrderStateMachine()
    order = _new_order()

    machine.validate(order)
    machine.send(order)
    machine.on_fill(order, 40)
    machine.on_fill(order, 60)

    assert order.state == OrderState.FILLED
    assert order.filled_quantity == 100
    assert order.last_update == 5


def test_invalid_transitions_fail() -> None:
    machine = OrderStateMachine()
    order = _new_order()

    with pytest.raises(FailClosedError, match="invalid_transition:NEW->SENT"):
        machine.send(order)

    machine.validate(order)
    machine.send(order)
    machine.reject(order)

    with pytest.raises(FailClosedError, match="invalid_transition:REJECTED->CANCELLED"):
        machine.cancel(order)


def test_partial_fills_accumulate_correctly() -> None:
    machine = OrderStateMachine()
    order = _new_order(quantity=10)

    machine.validate(order)
    machine.send(order)
    machine.on_fill(order, 3)
    machine.on_fill(order, 2)

    assert order.state == OrderState.PARTIALLY_FILLED
    assert order.filled_quantity == 5


def test_full_fill_closes_order() -> None:
    machine = OrderStateMachine()
    order = _new_order(quantity=10)

    machine.validate(order)
    machine.send(order)
    machine.on_fill(order, 10)

    assert order.state == OrderState.FILLED
    assert order.filled_quantity == 10

    with pytest.raises(FailClosedError, match="invalid_transition:FILLED->PARTIALLY_FILLED"):
        machine.on_fill(order, 1)


def test_cancel_after_fill_fails() -> None:
    machine = OrderStateMachine()
    order = _new_order(quantity=5)

    machine.validate(order)
    machine.send(order)
    machine.on_fill(order, 5)

    with pytest.raises(FailClosedError, match="invalid_transition:FILLED->CANCELLED"):
        machine.cancel(order)


def test_negative_values_fail_closed() -> None:
    machine = OrderStateMachine()
    order = _new_order(quantity=-1)

    with pytest.raises(FailClosedError, match="invalid_quantity:negative"):
        machine.validate(order)


def test_overfill_fails_closed() -> None:
    machine = OrderStateMachine()
    order = _new_order(quantity=5)

    machine.validate(order)
    machine.send(order)

    with pytest.raises(FailClosedError, match="filled_quantity_exceeds_quantity"):
        machine.on_fill(order, 6)
