from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bist_core.execution.broker_adapter import BrokerAdapter, BrokerResponse, OrderStatus
from bist_core.execution.order_state_machine import Order, OrderStateMachine
from bist_core.providers.base import FailClosedError


@dataclass(frozen=True)
class _ProcessedBrokerUpdate:
    status: OrderStatus
    filled_quantity: int
    avg_price: float
    timestamp: int
    reason: str | None


def _fail_closed(message: str) -> None:
    raise FailClosedError(message)


def _validate_response(response: Any) -> BrokerResponse:
    if not isinstance(response, BrokerResponse):
        _fail_closed("invalid_broker_response:type")
    if not isinstance(response.order_id, str) or not response.order_id.strip():
        _fail_closed("invalid_broker_response:order_id")
    if not isinstance(response.status, OrderStatus):
        _fail_closed("invalid_broker_response:status")
    if isinstance(response.filled_quantity, bool) or not isinstance(response.filled_quantity, int) or response.filled_quantity < 0:
        _fail_closed("invalid_broker_response:filled_quantity")
    if response.avg_price < 0.0:
        _fail_closed("invalid_broker_response:avg_price")
    if isinstance(response.timestamp, bool) or not isinstance(response.timestamp, int) or response.timestamp < 0:
        _fail_closed("invalid_broker_response:timestamp")
    return response


class ExecutionEngine:
    def __init__(self, broker_adapter: BrokerAdapter, state_machine: OrderStateMachine) -> None:
        if not isinstance(state_machine, OrderStateMachine):
            _fail_closed("invalid_state_machine")
        self.broker_adapter = broker_adapter
        self.state_machine = state_machine
        self.order_registry: dict[str, Order] = {}
        self._processed_updates: dict[str, _ProcessedBrokerUpdate] = {}

    def execute_order(self, order: Order) -> BrokerResponse:
        self.state_machine.validate(order)
        self.state_machine.send(order)
        self.order_registry[order.order_id] = order

        response = _validate_response(self.broker_adapter.send_order(order))
        if response.order_id != order.order_id:
            _fail_closed("broker_response_order_id_mismatch")

        if response.status is OrderStatus.ACCEPTED:
            return response
        if response.status is OrderStatus.REJECTED:
            self.state_machine.reject(order)
            self._processed_updates[order.order_id] = _ProcessedBrokerUpdate(
                status=response.status,
                filled_quantity=response.filled_quantity,
                avg_price=response.avg_price,
                timestamp=response.timestamp,
                reason=response.reason,
            )
            return response
        _fail_closed("invalid_broker_response:initial_status")

    def process_broker_update(self, response: BrokerResponse) -> Order:
        validated_response = _validate_response(response)
        order = self.order_registry.get(validated_response.order_id)
        if order is None:
            _fail_closed("unknown_order_id")

        processed_update = _ProcessedBrokerUpdate(
            status=validated_response.status,
            filled_quantity=validated_response.filled_quantity,
            avg_price=validated_response.avg_price,
            timestamp=validated_response.timestamp,
            reason=validated_response.reason,
        )
        previous_update = self._processed_updates.get(validated_response.order_id)
        if previous_update == processed_update:
            _fail_closed("duplicate_update")
        if previous_update is not None and validated_response.timestamp <= previous_update.timestamp:
            _fail_closed("duplicate_update")

        if validated_response.status is OrderStatus.PARTIALLY_FILLED:
            fill_delta = validated_response.filled_quantity - order.filled_quantity
            if fill_delta <= 0:
                _fail_closed("duplicate_update")
            self.state_machine.on_fill(order, fill_delta)
        elif validated_response.status is OrderStatus.FILLED:
            fill_delta = validated_response.filled_quantity - order.filled_quantity
            if fill_delta <= 0:
                _fail_closed("duplicate_update")
            self.state_machine.on_fill(order, fill_delta)
        elif validated_response.status is OrderStatus.CANCELLED:
            self.state_machine.cancel(order)
        elif validated_response.status is OrderStatus.REJECTED:
            self.state_machine.reject(order)
        elif validated_response.status is OrderStatus.ACCEPTED:
            _fail_closed("invalid_broker_response:update_status")
        else:
            _fail_closed("invalid_broker_response:update_status")

        self._processed_updates[validated_response.order_id] = processed_update
        return order


__all__ = ["ExecutionEngine"]
