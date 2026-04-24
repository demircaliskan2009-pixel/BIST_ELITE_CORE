from __future__ import annotations

import math

from bist_core.execution.broker_adapter import BrokerResponse, OrderStatus
from bist_core.execution.order_state_machine import Order, OrderState
from bist_core.execution.paper_engine import OrderSide
from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp
from bist_core.providers.base import FailClosedError


def _fail_closed(message: str) -> None:
    raise FailClosedError(message)


def _validate_order(order: Order) -> Order:
    if not isinstance(order, Order):
        _fail_closed("invalid_order:type")
    if not str(order.order_id or "").strip():
        _fail_closed("invalid_order_id")
    if not str(order.symbol or "").strip():
        _fail_closed("invalid_symbol")
    if order.state not in {OrderState.SENT, OrderState.PARTIALLY_FILLED}:
        _fail_closed("invalid_state")
    if isinstance(order.quantity, bool) or not isinstance(order.quantity, int) or order.quantity <= 0:
        _fail_closed("invalid_quantity")
    if isinstance(order.filled_quantity, bool) or not isinstance(order.filled_quantity, int) or order.filled_quantity < 0:
        _fail_closed("invalid_filled_quantity")
    if order.filled_quantity > order.quantity:
        _fail_closed("filled_quantity_exceeds_quantity")
    try:
        side = order.side if isinstance(order.side, OrderSide) else OrderSide(str(order.side).strip().upper())
    except ValueError as exc:
        raise FailClosedError("invalid_side") from exc
    order.side = side
    try:
        price = float(order.price)
    except (TypeError, ValueError) as exc:
        raise FailClosedError("invalid_price") from exc
    if not math.isfinite(price) or price <= 0.0:
        _fail_closed("invalid_price")
    order.price = price
    return order


def _validate_bar(bar: OHLCVBar) -> OHLCVBar:
    if not isinstance(bar, OHLCVBar):
        _fail_closed("invalid_market_bar:type")
    try:
        timestamp = normalize_timestamp(bar.timestamp)
    except ValueError as exc:
        raise FailClosedError("invalid_market_bar:timestamp") from exc
    try:
        open_price = float(bar.open)
        high_price = float(bar.high)
        low_price = float(bar.low)
        close_price = float(bar.close)
        volume = float(bar.volume)
    except (TypeError, ValueError) as exc:
        raise FailClosedError("invalid_market_bar:ohlcv_type") from exc
    if not all(math.isfinite(value) for value in (open_price, high_price, low_price, close_price, volume)):
        _fail_closed("invalid_market_bar:non_finite")
    if min(open_price, high_price, low_price, close_price) <= 0.0:
        _fail_closed("invalid_market_bar:price")
    if volume < 0.0:
        _fail_closed("invalid_market_bar:negative_volume")
    if high_price < max(open_price, low_price, close_price):
        _fail_closed("invalid_market_bar:high_bound")
    if low_price > min(open_price, high_price, close_price):
        _fail_closed("invalid_market_bar:low_bound")
    return OHLCVBar(
        timestamp=timestamp,
        symbol=bar.symbol,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        is_dummy=bar.is_dummy,
    )


class FillEngine:
    def simulate_fill(self, order: Order, market_bar: OHLCVBar) -> BrokerResponse | None:
        validated_order = _validate_order(order)
        validated_bar = _validate_bar(market_bar)
        remaining_quantity = validated_order.quantity - validated_order.filled_quantity
        if remaining_quantity <= 0:
            _fail_closed("order_has_no_remaining_quantity")

        if validated_order.side is OrderSide.BUY:
            if validated_order.price < validated_bar.low:
                return None
            fill_price = min(validated_order.price, validated_bar.high)
        else:
            if validated_order.price > validated_bar.high:
                return None
            fill_price = max(validated_order.price, validated_bar.low)

        max_fill = int(math.floor(validated_bar.volume * 0.01))
        if max_fill <= 0:
            return None

        fill_quantity = min(remaining_quantity, max_fill)
        status = OrderStatus.FILLED if fill_quantity == remaining_quantity else OrderStatus.PARTIALLY_FILLED
        return BrokerResponse(
            order_id=validated_order.order_id,
            status=status,
            filled_quantity=validated_order.filled_quantity + fill_quantity,
            avg_price=round(float(fill_price), 6),
            timestamp=validated_bar.timestamp,
            reason=None,
        )


__all__ = ["FillEngine"]
