"""Tests for Scanner Engine — candidate trade setup selection."""

from __future__ import annotations

import math
import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.scanner import Scanner


def _bar(ts: int, close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=1000)


def _make_bars(n: int, base_close: float = 100.0, step: float = 0.5) -> list[OHLCVBar]:
    bars = []
    for i in range(n):
        ts = 1704067200 + i * 86400
        c = base_close + i * step
        bars.append(_bar(ts, c))
    return bars


def test_deterministic_output() -> None:
    """Same input produces same output."""
    data = {
        "A": _make_bars(50, 100.0, 0.1),
        "B": _make_bars(50, 50.0, -0.2),
    }
    scanner = Scanner()
    a = scanner.scan(data)
    b = scanner.scan(data)
    assert a == b
    assert len(a) == 2


def test_filtering_invalid_symbols() -> None:
    """Symbols with < 50 bars, NaN, or invalid OHLC are skipped."""
    valid_bars = _make_bars(50)
    data = {
        "VALID": valid_bars,
        "TOO_FEW": _make_bars(49),
        "NAN": [OHLCVBar(1704067200, "X", math.nan, 101, 99, 100, 1000)] + _make_bars(50)[1:],
        "INVALID_OHLC": [
            OHLCVBar(1704067200, "X", -1, 101, 99, 100, 1000),
        ] + _make_bars(50)[1:],
    }
    scanner = Scanner()
    results = scanner.scan(data)
    assert len(results) == 1
    assert results[0]["symbol"] == "VALID"


def test_sorting_correctness() -> None:
    """Results sorted by score descending."""
    up_bars = _make_bars(50, 100.0, 1.0)
    down_bars = _make_bars(50, 100.0, -0.5)
    flat_bars = _make_bars(50, 100.0, 0.0)
    data = {
        "DOWN": down_bars,
        "UP": up_bars,
        "FLAT": flat_bars,
    }
    scanner = Scanner()
    results = scanner.scan(data)
    assert len(results) == 3
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0]["symbol"] == "UP"
    assert results[0]["trend"] == "up"
    symbols = {r["symbol"] for r in results}
    assert symbols == {"UP", "DOWN", "FLAT"}


def test_output_schema() -> None:
    """Each result has required fields."""
    data = {"X": _make_bars(50)}
    scanner = Scanner()
    results = scanner.scan(data)
    assert len(results) == 1
    r = results[0]
    assert "symbol" in r
    assert "score" in r
    assert "signal_strength" in r
    assert "volatility" in r
    assert "trend" in r
    assert r["trend"] in ("up", "down", "neutral")


def test_empty_data() -> None:
    """Empty data returns empty list."""
    scanner = Scanner()
    assert scanner.scan({}) == []


def test_all_invalid() -> None:
    """All symbols invalid returns empty list."""
    data = {
        "A": _make_bars(10),
        "B": _make_bars(30),
    }
    scanner = Scanner()
    assert scanner.scan(data) == []
