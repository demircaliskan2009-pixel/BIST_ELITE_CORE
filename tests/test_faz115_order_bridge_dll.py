"""FAZ115: OrderBridge and OrderBridgeDLL — send_order, human-approval mock, confirmation log."""
from __future__ import annotations

import sys

import pytest

from bist_core.connectors.order_bridge_dll import OrderBridge, OrderBridgeDLL


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


# --- OrderBridge (pyautogui) tests ---


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


# --- OrderBridgeDLL (stub + human-approval mock) tests ---


def test_order_bridge_dll_stub_simulates_order_sent() -> None:
    """Stub with no callback: all orders simulated as sent and confirmation logged."""
    dll = OrderBridgeDLL()
    out = dll.send_order("buy")
    assert out["sent"] is True
    assert out["confirmation"] == "order_sent:buy"
    assert out["order_type"] == "buy"
    assert dll.last_confirmation() == "order_sent:buy"
    assert "order_sent:buy" in dll.get_confirmations()
    dll.send_order("sell")
    assert dll.get_confirmations() == ["order_sent:buy", "order_sent:sell"]


def test_order_bridge_dll_human_approval_mock_approves() -> None:
    """Approval callback returns True: order sent and confirmation logged."""
    dll = OrderBridgeDLL(approval_callback=lambda ot: True)
    out = dll.send_order("sell")
    assert out["sent"] is True
    assert out["confirmation"] == "order_sent:sell"
    assert dll.last_confirmation() == "order_sent:sell"


def test_order_bridge_dll_human_approval_mock_rejects() -> None:
    """Approval callback returns False: order rejected, confirmation logged."""
    dll = OrderBridgeDLL(approval_callback=lambda ot: False)
    out = dll.send_order("buy")
    assert out["sent"] is False
    assert "order_rejected" in out["confirmation"]
    assert dll.last_confirmation() == "order_rejected:buy"


def test_order_bridge_dll_approval_mock_per_type() -> None:
    """Approval can depend on order type (e.g. approve buy, reject sell)."""
    dll = OrderBridgeDLL(approval_callback=lambda ot: ot.lower() == "buy")
    assert dll.send_order("buy")["sent"] is True
    assert dll.send_order("sell")["sent"] is False
    assert dll.get_confirmations() == ["order_sent:buy", "order_rejected:sell"]


def test_order_bridge_dll_invalid_type_raises() -> None:
    dll = OrderBridgeDLL()
    with pytest.raises(ValueError, match="Unsupported order type"):
        dll.send_order("invalid")
