"""Tests for Regime Engine — deterministic market regime detection."""

from __future__ import annotations

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.regime import (
    RegimeEngine,
    TRENDING_UP,
    TRENDING_DOWN,
    RANGE,
    HIGH_VOLATILITY,
    UNKNOWN,
)


def _bar(ts: str, close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=1000)


def test_trending_up() -> None:
    """Strong uptrend, moderate volatility → TRENDING_UP."""
    bars = [
        _bar("1704067200", 98.0, high=99, low=97),
        _bar("1704153600", 100.0, high=101, low=99),
        _bar("1704240000", 103.0, high=104, low=102),
    ]
    engine = RegimeEngine()
    assert engine.detect(bars) == TRENDING_UP


def test_trending_down() -> None:
    """Strong downtrend → TRENDING_DOWN."""
    bars = [
        _bar("1704067200", 105.0, high=106, low=104),
        _bar("1704153600", 102.0, high=103, low=101),
        _bar("1704240000", 98.0, high=99, low=97),
    ]
    engine = RegimeEngine()
    assert engine.detect(bars) == TRENDING_DOWN


def test_range() -> None:
    """Small trend, low std_dev → RANGE."""
    bars = [
        _bar("1704067200", 100.0, high=100.5, low=99.5),
        _bar("1704153600", 100.2, high=100.7, low=99.7),
        _bar("1704240000", 100.1, high=100.6, low=99.6),
    ]
    engine = RegimeEngine()
    assert engine.detect(bars) == RANGE


def test_high_volatility() -> None:
    """High volatility (wide bars) → HIGH_VOLATILITY."""
    bars = [
        _bar("1704067200", 100.0, high=105, low=95),
        _bar("1704153600", 101.0, high=106, low=96),
        _bar("1704240000", 99.0, high=104, low=94),
    ]
    engine = RegimeEngine()
    assert engine.detect(bars) == HIGH_VOLATILITY


def test_determinism() -> None:
    """Same bars produce same regime."""
    bars = [
        _bar("1704067200", 98.0, high=99, low=97),
        _bar("1704153600", 100.0, high=101, low=99),
        _bar("1704240000", 103.0, high=104, low=102),
    ]
    engine = RegimeEngine()
    a = engine.detect(bars)
    b = engine.detect(bars)
    assert a == b == TRENDING_UP


def test_insufficient_bars() -> None:
    """Empty or single bar → UNKNOWN (fail-closed)."""
    engine = RegimeEngine()
    assert engine.detect([]) == UNKNOWN
    assert engine.detect([_bar("1704067200", 100.0)]) == UNKNOWN
