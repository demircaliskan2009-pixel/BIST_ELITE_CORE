"""FAZ113: Matriks Terminal adaptörü — pywinauto ile GUI metni, provider arayüzü; simüle etkileşim."""

from __future__ import annotations

import sys
import types
from typing import Any, Dict

import pytest

from bist_core.connectors.matriks_terminal_adapter import (
    MatriksMarketDataProvider,
    MatriksTerminalAdapter,
    _parse_symbol_price_lines,
)
from bist_core.market_data.base import MarketDataProvider


# --- Simulated pywinauto interaction ---


class DummyWindow:
    def __init__(self, text: str = "THYA\t12.50\nAKBNK\t35.00") -> None:
        self._text = text

    def window_text(self) -> str:
        return self._text


class DummyApp:
    def __init__(self, window_text: str = "THYA\t12.50\nAKBNK\t35.00") -> None:
        self._window_text = window_text

    def window(self, title_re: str = "") -> DummyWindow:
        return DummyWindow(self._window_text)


class DummyApplication:
    """Simulated pywinauto.Application(backend=...).connect(title_re=...)."""

    def __init__(self, backend: str = "uia") -> None:
        self._backend = backend
        self._raise_on_connect = False

    def connect(self, title_re: str = "") -> DummyApp:
        if self._raise_on_connect:
            raise Exception("Matriks window not found")
        return DummyApp()


def test_connect_and_get_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate pywinauto: connect finds window, get_data reads GUI text and parses symbols/prices."""
    dummy_pywinauto = types.SimpleNamespace(Application=DummyApplication)
    monkeypatch.setitem(sys.modules, "pywinauto", dummy_pywinauto)

    adapter = MatriksTerminalAdapter()
    adapter.connect(title="Matriks")
    data = adapter.get_data()
    assert "raw_text" in data
    assert "THYA" in data["raw_text"] and "12.50" in data["raw_text"]
    assert data["symbols"] == ["AKBNK", "THYA"]
    assert data["close_map"] == {"AKBNK": 35.0, "THYA": 12.5}


def test_connect_window_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingApp:
        def connect(self, title_re: str = "") -> None:
            raise Exception("Matriks window not found")

    dummy_pywinauto = types.SimpleNamespace(Application=lambda backend: FailingApp())
    monkeypatch.setitem(sys.modules, "pywinauto", dummy_pywinauto)

    adapter = MatriksTerminalAdapter()
    with pytest.raises(RuntimeError, match="Matriks window not found"):
        adapter.connect(title="NonExisting")


def test_get_data_not_connected() -> None:
    adapter = MatriksTerminalAdapter()
    with pytest.raises(RuntimeError, match="Not connected to Matriks terminal"):
        adapter.get_data()


def test_provider_conforms_to_market_data_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    """MatriksMarketDataProvider implements MarketDataProvider (registry interface)."""
    dummy_pywinauto = types.SimpleNamespace(Application=DummyApplication)
    monkeypatch.setitem(sys.modules, "pywinauto", dummy_pywinauto)

    adapter = MatriksTerminalAdapter()
    adapter.connect(title="Matriks")
    provider = MatriksMarketDataProvider(adapter=adapter)

    assert isinstance(provider, MarketDataProvider)
    symbols = provider.symbols("2025-01-01")
    assert symbols == ["AKBNK", "THYA"]
    close_map = provider.close_map("2025-01-01")
    assert close_map == {"AKBNK": 35.0, "THYA": 12.5}
    ok, msg = provider.validate("2025-01-01")
    assert ok is True
    assert msg == "ok"


def test_provider_with_mock_adapter() -> None:
    """Provider works with a mock adapter returning structured data (simulated interaction)."""

    class MockAdapter:
        def get_data(self) -> Dict[str, Any]:
            return {
                "raw_text": "A\t1.0\nB\t2.0",
                "symbols": ["A", "B"],
                "close_map": {"A": 1.0, "B": 2.0},
            }

    provider = MatriksMarketDataProvider(adapter=MockAdapter())
    assert provider.symbols("today") == ["A", "B"]
    assert provider.close_map("today") == {"A": 1.0, "B": 2.0}
    ok, msg = provider.validate("today")
    assert ok is True


def test_provider_validate_fails_when_adapter_raises() -> None:
    class FailingAdapter:
        def get_data(self) -> Dict[str, Any]:
            raise RuntimeError("Not connected")

    provider = MatriksMarketDataProvider(adapter=FailingAdapter())
    ok, msg = provider.validate("today")
    assert ok is False
    assert "Not connected" in msg


def test_parse_symbol_price_lines() -> None:
    """Unit test for symbol/price line parsing used by adapter."""
    symbols, close_map = _parse_symbol_price_lines("X\t10.5\nY\t20.0")
    assert symbols == ["X", "Y"]
    assert close_map == {"X": 10.5, "Y": 20.0}
    symbols2, close_map2 = _parse_symbol_price_lines("")
    assert symbols2 == []
    assert close_map2 == {}
    symbols3, close_map3 = _parse_symbol_price_lines("A  1,5\nB  2,0")
    assert symbols3 == ["A", "B"]
    assert close_map3["A"] == 1.5
    assert close_map3["B"] == 2.0
