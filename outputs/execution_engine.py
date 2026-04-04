from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any

SLIPPAGE_PCT = 0.0005  # 0.05% default


class OrderState(Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


@dataclass
class Order:
    symbol: str
    entry: float
    stop: float
    target: float
    size: float
    state: OrderState = OrderState.CREATED
    fill_price: float = 0.0
    exit_price: float = 0.0
    net_pnl: float = 0.0
    reject_reason: str = ""

    def is_open(self) -> bool:
        return self.state == OrderState.FILLED

    def is_closed(self) -> bool:
        return self.state in (OrderState.CLOSED, OrderState.REJECTED)


class ExecutionEngine:
    """Stateful order execution engine. Deterministic, fail-closed, no randomness."""

    def __init__(self, slippage_pct: float = SLIPPAGE_PCT) -> None:
        self._slippage_pct = slippage_pct
        self._open_orders: dict[str, Order] = {}
        self._closed_orders: list[Order] = []

    def submit(self, symbol: str, entry: float, stop: float,
               target: float, size: float) -> Order:
        """Submit new order. Fail-closed on invalid inputs."""
        if entry <= 0 or stop <= 0 or target <= 0 or size < 1:
            o = Order(symbol=symbol, entry=entry, stop=stop,
                      target=target, size=size, state=OrderState.REJECTED,
                      reject_reason="invalid_inputs")
            self._closed_orders.append(o)
            return o
        if stop >= entry:
            o = Order(symbol=symbol, entry=entry, stop=stop,
                      target=target, size=size, state=OrderState.REJECTED,
                      reject_reason="stop_gte_entry")
            self._closed_orders.append(o)
            return o
        if symbol in self._open_orders:
            o = Order(symbol=symbol, entry=entry, stop=stop,
                      target=target, size=size, state=OrderState.REJECTED,
                      reject_reason="duplicate_symbol")
            self._closed_orders.append(o)
            return o

        fill_price = round(entry * (1 + self._slippage_pct), 6)
        o = Order(symbol=symbol, entry=entry, stop=stop,
                  target=target, size=size,
                  state=OrderState.FILLED, fill_price=fill_price)
        self._open_orders[symbol] = o
        return o

    def update(self, symbol: str, current_price: float) -> Order | None:
        """Update open order against current price. Close on stop/target hit."""
        o = self._open_orders.get(symbol)
        if o is None or not o.is_open():
            return None
        if current_price <= 0:
            return None

        hit_stop = current_price <= o.stop
        hit_target = current_price >= o.target

        if hit_stop or hit_target:
            exit_price = o.stop if hit_stop else o.target
            exit_fill = round(exit_price * (1 - self._slippage_pct if hit_stop
                              else 1 + self._slippage_pct), 6)
            gross_pnl = (exit_fill - o.fill_price) * o.size
            cost = (o.fill_price + exit_fill) * o.size * 0.001
            net_pnl = round(gross_pnl - cost, 6)
            o.exit_price = exit_fill
            o.net_pnl = net_pnl
            o.state = OrderState.CLOSED
            del self._open_orders[symbol]
            self._closed_orders.append(o)
            return o
        return None

    def open_positions(self) -> dict[str, Order]:
        return dict(self._open_orders)

    def closed_orders(self) -> list[Order]:
        return list(self._closed_orders)

    def force_close(self, symbol: str, current_price: float) -> Order | None:
        """Force close open position at current price with slippage."""
        o = self._open_orders.get(symbol)
        if o is None:
            return None
        if current_price <= 0:
            return None
        exit_fill = round(current_price * (1 - self._slippage_pct), 6)
        gross_pnl = (exit_fill - o.fill_price) * o.size
        cost = (o.fill_price + exit_fill) * o.size * 0.001
        o.net_pnl = round(gross_pnl - cost, 6)
        o.exit_price = exit_fill
        o.state = OrderState.CLOSED
        del self._open_orders[symbol]
        self._closed_orders.append(o)
        return o
