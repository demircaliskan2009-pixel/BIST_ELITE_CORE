"""
FAZ113: Matriks Terminal adaptörü — gerçek zamanlı piyasa verisi için pencere metni okuma.
pywinauto ile GUI metni okunur; MarketDataProvider arayüzüne uyan sarmalayıcı ile registry'de kullanılabilir.
"""
from __future__ import annotations

import importlib
import re
from typing import Any, Dict, List, Optional, Tuple

from bist_core.market_data.base import MarketDataProvider


def _parse_symbol_price_lines(raw_text: str) -> Tuple[List[str], Dict[str, float]]:
    """
    Parse raw window text into symbols and close_map.
    Expects lines like "SYMBOL\tPRICE" or "SYMBOL  PRICE" (tab or whitespace).
    Skips empty lines and lines that don't match symbol/price.
    """
    symbols: List[str] = []
    close_map: Dict[str, float] = {}
    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[\t\s]+", line, maxsplit=1)
        if len(parts) < 2:
            continue
        sym = parts[0].strip()
        try:
            price = float(parts[1].replace(",", ".").strip())
        except ValueError:
            continue
        if sym and sym not in close_map:
            symbols.append(sym)
            close_map[sym] = price
    return (sorted(symbols), close_map)


class MatriksTerminalAdapter:
    """
    Matriks terminal penceresine pywinauto ile bağlanıp GUI metnini okuyan adaptör.
    connect(title) ile pencere bulunur; get_data() ile ham metin veya yapı döner.
    """

    def __init__(self) -> None:
        self._window: Optional[Any] = None
        self._app: Optional[Any] = None

    def connect(self, title: str = "Matriks") -> None:
        """Pencere başlığı ile Matriks terminal penceresini pywinauto ile bulur ve bağlanır."""
        try:
            Application = getattr(
                importlib.import_module("pywinauto"), "Application"
            )
        except (ImportError, AttributeError):
            raise ImportError("pywinauto is not available")
        backend = "uia"
        try:
            app = Application(backend=backend).connect(title_re=re.escape(title))
        except Exception as e:
            raise RuntimeError(f"Matriks window not found: {e}") from e
        self._app = app
        try:
            self._window = app.window(title_re=re.escape(title))
        except Exception as e:
            raise RuntimeError(f"Matriks window not found: {e}") from e

    def get_data(self) -> Dict[str, Any]:
        """
        Bağlı pencereden GUI metnini okur (pywinauto).
        Returns: {"raw_text": str}. Optionally caller can parse via _parse_symbol_price_lines.
        """
        if self._window is None:
            raise RuntimeError("Not connected to Matriks terminal")
        try:
            text = self._window.window_text()
        except Exception as e:
            raise RuntimeError(f"Failed to read window text: {e}") from e
        raw = (text or "").strip()
        symbols, close_map = _parse_symbol_price_lines(raw)
        return {
            "raw_text": raw,
            "symbols": symbols,
            "close_map": close_map,
        }


class MatriksMarketDataProvider:
    """
    MarketDataProvider arayüzüne uyan sarmalayıcı: MatriksTerminalAdapter üzerinden
    gerçek zamanlı (veya son okunan) sembol/fiyat verisini sunar.
    """

    def __init__(self, adapter: Optional[MatriksTerminalAdapter] = None) -> None:
        self._adapter = adapter or MatriksTerminalAdapter()

    def symbols(self, day: str) -> List[str]:
        """Son okunan veriden sembol listesini döner (day real-time için yok sayılabilir)."""
        data = self._adapter.get_data()
        return list(data.get("symbols") or [])

    def close_map(self, day: str) -> Dict[str, float]:
        """Son okunan veriden sembol -> fiyat eşlemesini döner."""
        data = self._adapter.get_data()
        return dict(data.get("close_map") or {})

    def validate(self, day: str) -> tuple[bool, str]:
        """Bağlantı ve veri okunabilir mi kontrol eder."""
        try:
            data = self._adapter.get_data()
            raw = (data.get("raw_text") or "").strip()
            return (True, "ok") if raw else (False, "no data")
        except RuntimeError as e:
            return (False, str(e))
