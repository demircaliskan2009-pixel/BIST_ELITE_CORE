"""
FAZ115: OrderBridge and OrderBridgeDLL — İşlem terminali / DLL veya manuel onay proxy.
OrderBridge: pyautogui ile tuş basımı (buy=F1, sell=F2).
OrderBridgeDLL: DLL veya manuel onay proxy; stub arayüz, human-approval mock ile "order sent" ve log confirmation.
"""

# ruff: noqa: E402
from __future__ import annotations

import importlib
from typing import Any, Callable, List, Optional


class OrderBridge:
    """Hedef pencereye göre alış/satış emri tuş basımı gönderen köprü."""

    def __init__(self, target_window: Optional[Any] = None) -> None:
        self.window = target_window

    def send_order(self, order_type: str) -> None:
        """order_type: 'buy' -> F1, 'sell' -> F2. Pencere varsa activate dener, sonra tuş basar."""
        try:
            gui = importlib.import_module("pyautogui")
        except ImportError:
            raise ImportError("pyautogui module is not available")
        if not self.window:
            raise RuntimeError("No target window specified for order")
        keys = {"buy": "f1", "sell": "f2"}
        key = keys.get(order_type.lower())
        if not key:
            raise ValueError(f"Unsupported order type: {order_type}")
        try:
            if hasattr(self.window, "activate"):
                self.window.activate()
        except Exception:
            pass
        gui.press(key)


# --- OrderBridgeDLL: implements OrderBridgeInterface ---

from bist_core.connectors.order_bridge_base import OrderBridgeInterface


class OrderBridgeDLL(OrderBridgeInterface):
    """
    Implements OrderBridgeInterface: stub/DLL backend with manual-confirmation proxy (human-approval mock).
    Simulates "order sent" and logs confirmation. Replace with real DLL adapter later; FIX and other backends will implement the same interface.
    """

    def __init__(
        self,
        approval_callback: Optional[Callable[[str], bool]] = None,
    ) -> None:
        """
        approval_callback(order_type) -> True to approve (simulate sent), False to reject.
        If None, all orders are treated as approved (stub mode).
        """
        self._approval = approval_callback
        self._confirmations: List[str] = []
        self._keys = {"buy": "f1", "sell": "f2"}

    def send_order(self, order_type: str) -> dict:
        """
        Send order through proxy; requires approval (or stub approves all).
        Returns {"sent": bool, "confirmation": str, "order_type": str}.
        """
        key = self._keys.get(order_type.lower())
        if not key:
            raise ValueError(f"Unsupported order type: {order_type}")
        approved = self._approval(order_type) if self._approval is not None else True
        if not approved:
            msg = f"order_rejected:{order_type}"
            self._confirmations.append(msg)
            return {"sent": False, "confirmation": msg, "order_type": order_type.lower()}
        msg = f"order_sent:{order_type.lower()}"
        self._confirmations.append(msg)
        return {"sent": True, "confirmation": msg, "order_type": order_type.lower()}

    def get_confirmations(self) -> List[str]:
        """Return log of confirmations (order_sent:... or order_rejected:...)."""
        return list(self._confirmations)

    def last_confirmation(self) -> Optional[str]:
        """Last confirmation line, or None."""
        return self._confirmations[-1] if self._confirmations else None
