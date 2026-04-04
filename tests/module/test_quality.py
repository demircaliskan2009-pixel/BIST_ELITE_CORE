"""Tests for data quality validation and liquidity metrics."""

from __future__ import annotations

import pytest

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.data.quality import InvalidDataError, basic_checks, compute_liquidity_metrics


def _bar(ts: str, close: float, volume: float = 1000.0) -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts,
        symbol="X",
        open=close,
        high=close + 1,
        low=max(close - 1, 0.01),
        close=close,
        volume=volume,
    )


def test_basic_checks_valid() -> None:
    """Valid bars pass basic_checks."""
    bars = [
        _bar("1704067200", 100.0),
        _bar("1704153600", 101.0),
        _bar("1704240000", 102.0),
    ]
    assert basic_checks(bars) is True


def test_empty_input() -> None:
    """Empty bars raise InvalidDataError."""
    with pytest.raises(InvalidDataError) as exc_info:
        basic_checks([])
    assert "empty" in str(exc_info.value).lower()


def test_timestamp_violation() -> None:
    """Non-increasing timestamps raise InvalidDataError."""
    bars = [
        _bar("1704153600", 101.0),
        _bar("1704067200", 100.0),
    ]
    with pytest.raises(InvalidDataError) as exc_info:
        basic_checks(bars)
    assert "increasing" in str(exc_info.value).lower()


def test_duplicate_timestamp() -> None:
    """Duplicate timestamps raise InvalidDataError."""
    bars = [
        _bar("1704067200", 100.0),
        _bar("1704067200", 101.0),
    ]
    with pytest.raises(InvalidDataError) as exc_info:
        basic_checks(bars)
    assert "duplicate" in str(exc_info.value).lower()


def test_negative_price() -> None:
    """Negative price raises InvalidDataError."""
    bars = [
        _bar("1704067200", -100.0),
    ]
    with pytest.raises(InvalidDataError) as exc_info:
        basic_checks(bars)
    assert "price" in str(exc_info.value).lower()


def test_negative_volume() -> None:
    """Negative volume raises InvalidDataError."""
    bars = [
        OHLCVBar(1704067200, "X", 100, 101, 99, 100, -500),
    ]
    with pytest.raises(InvalidDataError) as exc_info:
        basic_checks(bars)
    assert "volume" in str(exc_info.value).lower()


def test_liquidity_metrics_correctness() -> None:
    """compute_liquidity_metrics returns correct schema and values."""
    bars = [
        _bar("1704067200", 100.0, 1000),
        _bar("1704153600", 101.0, 2000),
        _bar("1704240000", 102.0, 3000),
    ]
    m = compute_liquidity_metrics(bars)
    assert m["bar_count"] == 3
    assert m["avg_volume"] == 2000.0
    # turnover_proxy = mean(close * volume) = (100*1000 + 101*2000 + 102*3000) / 3
    # = (100000 + 202000 + 306000) / 3 = 608000 / 3
    expected_turnover = (100 * 1000 + 101 * 2000 + 102 * 3000) / 3
    assert m["turnover_proxy"] == expected_turnover
    assert "avg_volume" in m
    assert "bar_count" in m
    assert "turnover_proxy" in m


def test_determinism() -> None:
    """Same input produces same output."""
    bars = [
        _bar("1704067200", 100.0, 1000),
        _bar("1704153600", 101.0, 2000),
    ]
    m1 = compute_liquidity_metrics(bars)
    m2 = compute_liquidity_metrics(bars)
    assert m1 == m2
    assert m1["avg_volume"] == m2["avg_volume"]
    assert m1["turnover_proxy"] == m2["turnover_proxy"]


def test_compute_liquidity_empty_raises() -> None:
    """compute_liquidity_metrics raises on empty input."""
    with pytest.raises(InvalidDataError) as exc_info:
        compute_liquidity_metrics([])
    assert "empty" in str(exc_info.value).lower()
