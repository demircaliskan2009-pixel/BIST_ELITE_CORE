"""FAZ115: OrderBridge — send_order (buy/sell), pencere yok ve geçersiz tür hataları."""
from __future__ import annotations

import sys

import pytest

from bist_core.connectors.order_bridge_dll import OrderBridge


class DummyWindow:
    def __init__(self) -> None:
        self.activated = False

    def activate(self) -> None:
        self.activated = True


class DummyPyAutoGUI:
    def __init__(self) -> None:
        self.pressed_keys: list[str] = []

    def press(self, key: str) -> None:
        self.pressed_keys.append(key)


def test_send_order_success(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_window = DummyWindow()
    dummy_gui = DummyPyAutoGUI()
    monkeypatch.setitem(sys.modules, "pyautogui", dummy_gui)
    bridge = OrderBridge(target_window=dummy_window)
    bridge.send_order("buy")
    assert dummy_window.activated is True
    assert "f1" in dummy_gui.pressed_keys
    dummy_window.activated = False
    bridge.send_order("sell")
    assert dummy_window.activated is True
    assert "f2" in dummy_gui.pressed_keys


def test_send_order_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pyautogui", DummyPyAutoGUI())
    bridge = OrderBridge(target_window=None)
    with pytest.raises(RuntimeError, match="No target window specified"):
        bridge.send_order("buy")


def test_send_order_invalid_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pyautogui", DummyPyAutoGUI())
    bridge = OrderBridge(target_window=DummyWindow())
    with pytest.raises(ValueError, match="Unsupported order type"):
        bridge.send_order("invalid")
