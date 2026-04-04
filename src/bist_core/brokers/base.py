"""Broker interface: place_orders, cancel, get_positions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class Broker(Protocol):
    """Interface for order execution and position queries."""

    def place_orders(self, orders_intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Submit orders; returns list of fill records (order_id, symbol, side, qty, price, notional, etc.)."""
        ...

    def cancel(self, order_id: Optional[str] = None) -> bool:
        """Cancel order(s). If order_id is None, cancel all pending. Returns True if any cancelled."""
        ...

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return current positions (e.g. symbol, qty, avg_price)."""
        ...
