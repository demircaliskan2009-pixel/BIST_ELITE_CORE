"""FAZ113: Matriks Terminal adaptörü — connect/get_data ve hata senaryoları."""
from __future__ import annotations

import sys
import types

import pytest

from bist_core.connectors.matriks_terminal_adapter import MatriksTerminalAdapter


class DummyWin:
    def __init__(self) -> None:
        self.left = 0
        self.top = 0
        self.width = 100
        self.height = 100


def test_connect_and_get_data(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_gw = types.SimpleNamespace()
    dummy_gw.getWindowsWithTitle = lambda title: [DummyWin()] if "Matriks" in title else []
    dummy_grab = types.SimpleNamespace()
    dummy_grab.grab = lambda bbox=None: "dummy_image"
    monkeypatch.setitem(sys.modules, "pygetwindow", dummy_gw)
    monkeypatch.setitem(sys.modules, "PIL.ImageGrab", dummy_grab)

    adapter = MatriksTerminalAdapter()
    adapter.connect()
    assert isinstance(adapter.window, DummyWin)
    result = adapter.get_data()
    assert result == "dummy_image"


def test_connect_window_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_gw_empty = types.SimpleNamespace()
    dummy_gw_empty.getWindowsWithTitle = lambda title: []
    monkeypatch.setitem(sys.modules, "pygetwindow", dummy_gw_empty)

    adapter = MatriksTerminalAdapter()
    with pytest.raises(RuntimeError, match="Matriks window not found"):
        adapter.connect(title="NonExisting")


def test_get_data_not_connected() -> None:
    adapter = MatriksTerminalAdapter()
    with pytest.raises(RuntimeError, match="Not connected to Matriks terminal"):
        adapter.get_data()
