from __future__ import annotations

import pytest

from bist_core.execution.broker_adapter import (
    BrokerAdapter,
    BrokerResponse,
    DummyBrokerAdapter,
    OrderStatus,
)
from bist_core.execution.execution_engine_v2 import ExecutionEngine
from bist_core.execution.order_state_machine import Order, OrderState, OrderStateMachine
from bist_core.execution.paper_engine import OrderSide
from bist_core.providers.base import FailClosedError


class RejectingBrokerAdapter(BrokerAdapter):
    def send_order(self, order: Order) -> BrokerResponse:
        return BrokerResponse(
            order_id=order.order_id,
            status=OrderStatus.REJECTED,
            filled_quantity=0,
            avg_price=0.0,
            timestamp=1,
            reason="broker_rejected",
        )

    def cancel_order(self, order_id: str) -> BrokerResponse:
        raise NotImplementedError()

    def get_order_status(self, order_id: str) -> BrokerResponse:
        raise NotImplementedError()


def _validated_order(**overrides: object) -> Order:
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


def test_full_lifecycle() -> None:
    engine = ExecutionEngine(DummyBrokerAdapter(), OrderStateMachine())
    order = _validated_order()

    response = engine.execute_order(order)
    updated_order = engine.process_broker_update(
        BrokerResponse(
            order_id=order.order_id,
            status=OrderStatus.FILLED,
            filled_quantity=100,
            avg_price=42.5,
            timestamp=2,
            reason=None,
        )
    )

    assert response.status is OrderStatus.ACCEPTED
    assert updated_order.state is OrderState.FILLED
    assert updated_order.filled_quantity == 100


def test_rejected_order() -> None:
    engine = ExecutionEngine(RejectingBrokerAdapter(), OrderStateMachine())
    order = _validated_order()

    response = engine.execute_order(order)

    assert response.status is OrderStatus.REJECTED
    assert engine.order_registry[order.order_id].state is OrderState.REJECTED


def test_partial_fill_flow() -> None:
    engine = ExecutionEngine(DummyBrokerAdapter(), OrderStateMachine())
    order = _validated_order(quantity=10)

    engine.execute_order(order)
    partially_filled = engine.process_broker_update(
        BrokerResponse(
            order_id=order.order_id,
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=4,
            avg_price=42.5,
            timestamp=2,
            reason=None,
        )
    )
    assert partially_filled.state is OrderState.PARTIALLY_FILLED
    assert partially_filled.filled_quantity == 4

    filled = engine.process_broker_update(
        BrokerResponse(
            order_id=order.order_id,
            status=OrderStatus.FILLED,
            filled_quantity=10,
            avg_price=42.5,
            timestamp=3,
            reason=None,
        )
    )

    assert filled.state is OrderState.FILLED
    assert filled.filled_quantity == 10


def test_invalid_update_fails() -> None:
    engine = ExecutionEngine(DummyBrokerAdapter(), OrderStateMachine())
    order = _validated_order(quantity=5)

    engine.execute_order(order)

    with pytest.raises(FailClosedError, match="filled_quantity_exceeds_quantity"):
        engine.process_broker_update(
            BrokerResponse(
                order_id=order.order_id,
                status=OrderStatus.FILLED,
                filled_quantity=6,
                avg_price=42.5,
                timestamp=2,
                reason=None,
            )
        )


def test_unknown_order_fails() -> None:
    engine = ExecutionEngine(DummyBrokerAdapter(), OrderStateMachine())

    with pytest.raises(FailClosedError, match="unknown_order_id"):
        engine.process_broker_update(
            BrokerResponse(
                order_id="ORD-4040",
                status=OrderStatus.CANCELLED,
                filled_quantity=0,
                avg_price=0.0,
                timestamp=1,
                reason=None,
            )
        )


def test_duplicate_update_fails() -> None:
    engine = ExecutionEngine(DummyBrokerAdapter(), OrderStateMachine())
    order = _validated_order(quantity=10)

    engine.execute_order(order)
    response = BrokerResponse(
        order_id=order.order_id,
        status=OrderStatus.PARTIALLY_FILLED,
        filled_quantity=4,
        avg_price=42.5,
        timestamp=2,
        reason=None,
    )
    engine.process_broker_update(response)

    with pytest.raises(FailClosedError, match="duplicate_update"):
        engine.process_broker_update(response)