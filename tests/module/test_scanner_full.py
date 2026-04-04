"""Full Scanner System tests — flow, rules, schema, determinism."""

from __future__ import annotations

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.scan import (
    AdaptiveScanEngine,
    BasicSanityRule,
    LiquidityRule,
    Scanner,
    VolatilityRule,
)


def _bar(
    ts: str,
    close: float,
    volume: float = 1000.0,
    high: float | None = None,
    low: float | None = None,
) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=volume)


def test_full_scan_flow() -> None:
    """Full scan: load, validate, compute, apply rules, build candidate."""
    def loader(symbol: str) -> list[OHLCVBar]:
        return [
            _bar("1704067200", 100.0, 5000),
            _bar("1704153600", 105.0, 6000),
        ]

    rules = AdaptiveScanEngine()
    scanner = Scanner(loader, ["GARAN"], rules)
    candidates = scanner.scan()
    assert len(candidates) == 1
    c = candidates[0]
    assert c["symbol"] == "GARAN"
    assert c["momentum"] == 5.0
    assert c["volatility"] == 2.0
    assert c["passed_filters"] is True
    assert c["score_modifier"] == 1.0
    assert isinstance(c["reasons"], dict)


def test_rule_filtering() -> None:
    """Rules filter out symbols that fail."""
    def loader(symbol: str) -> list[OHLCVBar]:
        if symbol == "HIGH_VOL":
            return [
                _bar("1704067200", 100.0, 10000),
                _bar("1704153600", 101.0, 10000),
            ]
        if symbol == "LOW_VOL":
            return [
                _bar("1704067200", 100.0, 100),
                _bar("1704153600", 101.0, 100),
            ]
        return []

    rules = AdaptiveScanEngine([LiquidityRule(threshold=1000.0)])
    scanner = Scanner(loader, ["HIGH_VOL", "LOW_VOL"], rules)
    candidates = scanner.scan()
    assert len(candidates) == 1
    assert candidates[0]["symbol"] == "HIGH_VOL"


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


def test_empty_result() -> None:
    """No valid candidates returns empty list."""
    def loader(symbol: str) -> list[OHLCVBar]:
        return [
            _bar("1704067200", 100.0, 50),
            _bar("1704153600", 101.0, 50),
        ]

    rules = AdaptiveScanEngine([LiquidityRule(threshold=1000.0)])
    scanner = Scanner(loader, ["X"], rules)
    candidates = scanner.scan()
    assert candidates == []


def test_score_modifier_applied() -> None:
    """Score modifier is correctly set in candidate."""
    def loader(symbol: str) -> list[OHLCVBar]:
        return [
            _bar("1704067200", 100.0),
            _bar("1704153600", 101.0),
            _bar("1704240000", 102.0),
        ]

    rules = AdaptiveScanEngine([BasicSanityRule(minimum=1)])
    scanner = Scanner(loader, ["GARAN"], rules)
    candidates = scanner.scan()
    assert len(candidates) == 1
    assert candidates[0]["score_modifier"] == 1.0
    assert candidates[0]["passed_filters"] is True
    assert "sanity" in candidates[0]["reasons"]
