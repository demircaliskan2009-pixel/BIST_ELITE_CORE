"""Paper-first execution engine — order abstraction for live adapters later."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OrderSide = Literal["buy", "sell"]
OrderStatus = Literal["pending", "filled", "partial", "cancelled"]


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    price: float
    size: int
    status: OrderStatus
    filled_size: int = 0


class ExecutionEngine:
    """In-memory order book (paper). Deterministic IDs: ``paper:{seq:010d}``."""

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self._seq: int = 0

    def create_order(self, symbol: str, side: OrderSide, price: float, size: int) -> Order:
        self._seq += 1
        oid = f"paper:{self._seq:010d}"
        o = Order(
            id=oid,
            symbol=str(symbol),
            side=side,
            price=float(price),
            size=int(size),
            status="pending",
            filled_size=0,
        )
        self.orders[oid] = o
        return o

    def process_fill(self, order: Order, market_price: float) -> bool:
        """Paper fill: buy if market <= limit; sell if market >= limit."""
        if order.status != "pending":
            return False
        try:
            mp = float(market_price)
        except (TypeError, ValueError):
            return False
        if order.side == "buy":
            if mp <= float(order.price):
                fill_ratio = 0.7
                filled_size = int(order.size * fill_ratio)
                if filled_size == 0:
                    return False
                order.filled_size = filled_size
                if filled_size == order.size:
                    order.status = "filled"
                else:
                    order.status = "partial"
                self.orders[order.id] = order
                return True
        elif order.side == "sell":
            if mp >= float(order.price):
                fill_ratio = 0.7
                filled_size = int(order.size * fill_ratio)
                if filled_size == 0:
                    return False
                order.filled_size = filled_size
                if filled_size == order.size:
                    order.status = "filled"
                else:
                    order.status = "partial"
                self.orders[order.id] = order
                return True
        return False

    def cancel_order(self, order_id: str) -> bool:
        o = self.orders.get(order_id)
        if o is None or o.status != "pending":
            return False
        o.status = "cancelled"
        self.orders[order_id] = o
        return True


__all__ = ["ExecutionEngine", "Order", "OrderSide", "OrderStatus"]
