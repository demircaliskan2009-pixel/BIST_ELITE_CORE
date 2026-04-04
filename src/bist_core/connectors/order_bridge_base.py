"""
Abstract base for order routing. Implementations: OrderBridgeDLL (stub/DLL), FIX and other backends.
Defined in a separate module to avoid circular imports with order_bridge_dll and order_bridge_interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class OrderBridgeInterface(ABC):
    """Abstract base for order routing. send_order(order_type) -> dict with sent, confirmation, order_type."""

    @abstractmethod
    def send_order(self, order_type: str) -> dict:
        """
        Route order to backend. order_type e.g. 'buy', 'sell'.
        Returns dict with at least: sent (bool), confirmation (str), order_type (str).
        Raises ValueError for unsupported order_type.
        """
        ...
