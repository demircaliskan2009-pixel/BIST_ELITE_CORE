"""Tests for Scanner — symbol candidate selection from OHLCV data."""

from __future__ import annotations

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.scan import AdaptiveScanEngine, Scanner


def _bar(ts: str, close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=1000)


def test_basic_scan() -> None:
    """Scan returns candidates with momentum and volatility."""
    def loader(symbol: str) -> list[OHLCVBar]:
        if symbol == "GARAN":
            return [
                _bar("1704067200", 100.0),
                _bar("1704153600", 105.0),
            ]
        if symbol == "ASELS":
            return [
                _bar("1704067200", 50.0),
                _bar("1704153600", 48.0),
            ]
        return []

    rules = AdaptiveScanEngine()
    scanner = Scanner(loader, ["GARAN", "ASELS"], rules)
    candidates = scanner.scan()
    assert len(candidates) == 2
    symbols = {c["symbol"] for c in candidates}
    assert symbols == {"GARAN", "ASELS"}
    for c in candidates:
        assert "momentum" in c
        assert "volatility" in c
        assert "passed_filters" in c
        assert "score_modifier" in c
        assert "reasons" in c
    garan = next(c for c in candidates if c["symbol"] == "GARAN")
    assert garan["momentum"] == 5.0
    asels = next(c for c in candidates if c["symbol"] == "ASELS")
    assert asels["momentum"] == -2.0


def test_invalid_data_skipped() -> None:
    """Invalid data causes symbol to be skipped."""
    def loader(symbol: str) -> list[OHLCVBar]:
        if symbol == "VALID":
            return [
                _bar("1704067200", 100.0),
                _bar("1704153600", 101.0),
            ]
        if symbol == "INVALID":
            return [
                OHLCVBar(1704067200, "X", -1, 101, 99, 100, 1000),
            ]
        return []

    rules = AdaptiveScanEngine()
    scanner = Scanner(loader, ["VALID", "INVALID"], rules)
    candidates = scanner.scan()
    assert len(candidates) == 1
    assert candidates[0]["symbol"] == "VALID"


def test_empty_symbols() -> None:
    """Empty symbols list returns empty candidates."""
    def loader(symbol: str) -> list[OHLCVBar]:
        return [_bar("1704067200", 100.0)]

    rules = AdaptiveScanEngine()
    scanner = Scanner(loader, [], rules)
    candidates = scanner.scan()
    assert candidates == []


def test_determinism() -> None:
    """Same input produces same output."""
    def loader(symbol: str) -> list[OHLCVBar]:
        return [
            _bar("1704067200", 100.0),
            _bar("1704153600", 102.0),
        ]

    rules = AdaptiveScanEngine()
    scanner = Scanner(loader, ["A", "B"], rules)
    a = scanner.scan()
    b = scanner.scan()
    assert a == b
    assert len(a) == 2
    assert a[0]["momentum"] == 2.0
    assert a[0]["volatility"] == 2.0
