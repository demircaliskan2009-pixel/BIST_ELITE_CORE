"""
FAZ115: OrderBridge — İşlem terminali için yarı otomatik emir köprüsü.
Hedef pencere (opsiyonel activate) ve pyautogui ile tuş basımı (buy=F1, sell=F2).
"""
from __future__ import annotations

import importlib
from typing import Any, Optional


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
