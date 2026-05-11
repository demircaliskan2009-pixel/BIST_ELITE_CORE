from __future__ import annotations

from bist_core.execution.broker_adapter import (
    BrokerAdapter,
    BrokerResponse,
    OrderStatus,
    _fail_closed,
    _validate_order_for_broker,
    _validate_order_id,
)
from bist_core.execution.order_state_machine import Order


class RealBrokerAdapter(BrokerAdapter):
    """Structural real-broker adapter: validates and maps orders, but does not call any API yet."""

    def __init__(self) -> None:
        self.broker_order_map: dict[str, str] = {}
        self._last_known_status: dict[str, BrokerResponse] = {}
        self._broker_payloads: dict[str, dict[str, object]] = {}
        self._clock = 0

    def _next_timestamp(self) -> int:
        self._clock += 1
        return self._clock

    def _broker_id_for(self, order_id: str) -> str:
        return f"real:{order_id}"

    def _to_broker_payload(self, order: Order, broker_id: str) -> dict[str, object]:
        return {
            "broker_order_id": broker_id,
            "system_order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side.value if hasattr(order.side, "value") else str(order.side),
            "quantity": order.quantity,
            "price": float(order.price),
        }

    def send_order(self, order: Order) -> BrokerResponse:
        validated_order = _validate_order_for_broker(order)
        order_id = _validate_order_id(validated_order.order_id)
        if order_id in self.broker_order_map:
            _fail_closed("duplicate_order_id")
        broker_id = self._broker_id_for(order_id)
        self.broker_order_map[order_id] = broker_id
        self._broker_payloads[order_id] = self._to_broker_payload(validated_order, broker_id)
        response = BrokerResponse(
            order_id=order_id,
            status=OrderStatus.ACCEPTED,
            filled_quantity=0,
            avg_price=0.0,
            timestamp=self._next_timestamp(),
            reason=None,
        )
        self._last_known_status[order_id] = response
        return response

    def cancel_order(self, order_id: str) -> BrokerResponse:
        normalized_order_id = _validate_order_id(order_id)
        if normalized_order_id not in self.broker_order_map:
            _fail_closed("unknown_order_id")
        previous = self._last_known_status.get(normalized_order_id)
        if previous is None:
            _fail_closed("unknown_order_id")
        if previous.status is not OrderStatus.ACCEPTED:
            _fail_closed("invalid_state")
        response = BrokerResponse(
            order_id=normalized_order_id,
            status=OrderStatus.CANCELLED,
            filled_quantity=previous.filled_quantity,
            avg_price=previous.avg_price,
            timestamp=self._next_timestamp(),
            reason=None,
        )
        self._last_known_status[normalized_order_id] = response
        return response

    def get_order_status(self, order_id: str) -> BrokerResponse:
        normalized_order_id = _validate_order_id(order_id)
        if normalized_order_id not in self.broker_order_map:
            _fail_closed("unknown_order_id")
        response = self._last_known_status.get(normalized_order_id)
        if response is None:
            _fail_closed("unknown_order_id")
        return response


__all__ = ["RealBrokerAdapter"]
