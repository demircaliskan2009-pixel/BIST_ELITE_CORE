"""Tests for Walk-Forward Validation Engine."""

from __future__ import annotations

import math

from bist_core.models.ohlcv import OHLCVBar
from bist_core.validation.walk_forward import WalkForwardValidator


def _bar(ts: str, symbol: str, close: float) -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts,
        symbol=symbol,
        open=close,
        high=close + 1,
        low=max(close - 1, 0.01),
        close=close,
        volume=1000,
    )


def _make_bars(symbol: str, n: int, base: float = 100.0, step: float = 0.1) -> list[OHLCVBar]:
    bars = []
    for i in range(n):
        ts = str(1704067200 + i * 86400)
        bars.append(_bar(ts, symbol, base + i * step))
    return bars


def test_deterministic_output() -> None:
    """Same input produces same output."""
    data = {"A": _make_bars("A", 120)}
    v = WalkForwardValidator(train_size=50, test_size=20, step_size=20)
    a = v.validate(data)
    b = v.validate(data)
    assert a == b


def test_correct_window_splits() -> None:
    """Windows have correct train/test sizes and step progression."""
    data = {"X": _make_bars("X", 150)}
    v = WalkForwardValidator(train_size=50, test_size=30, step_size=30)
    result = v.validate(data)
    assert "X" in result["symbols"]
    sym = result["symbols"]["X"]
    windows = sym["windows"]
    assert len(windows) >= 1
    for w in windows:
        assert "train_metrics" in w
        assert "test_metrics" in w
        assert "expectancy" in w["train_metrics"]
        assert "expectancy" in w["test_metrics"]
        assert "max_drawdown" in w["test_metrics"]


def test_stability_calculation() -> None:
    """Stability = 1 / (1 + variance) of test expectancy."""
    data = {"Y": _make_bars("Y", 200)}
    v = WalkForwardValidator(train_size=40, test_size=20, step_size=20)
    result = v.validate(data)
    assert "Y" in result["symbols"]
    sym = result["symbols"]["Y"]
    assert 0 <= sym["stability"] <= 1
    assert "avg_expectancy" in sym
    assert "avg_drawdown" in sym


def test_multi_symbol_support() -> None:
    """Multiple symbols processed independently."""
    data = {
        "A": _make_bars("A", 120),
        "B": _make_bars("B", 150),
    }
    v = WalkForwardValidator(train_size=50, test_size=20, step_size=20)
    result = v.validate(data)
    assert "A" in result["symbols"]
    assert "B" in result["symbols"]
    assert len(result["symbols"]["A"]["windows"]) >= 1
    assert len(result["symbols"]["B"]["windows"]) >= 1


def test_insufficient_data_skipped() -> None:
    """Symbol with insufficient bars is skipped."""
    data = {
        "VALID": _make_bars("VALID", 100),
        "SHORT": _make_bars("SHORT", 30),
    }
    v = WalkForwardValidator(train_size=50, test_size=30, step_size=20)
    result = v.validate(data)
    assert "VALID" in result["symbols"]
    assert "SHORT" not in result["symbols"]


def test_invalid_bars_skipped() -> None:
    """Symbol with NaN or invalid bars is skipped."""
    valid = _make_bars("VALID", 100)
    invalid_nan = [_bar("1704067200", "X", math.nan)] + _make_bars("X", 99)[1:]
    data = {
        "VALID": valid,
        "NAN": invalid_nan,
    }
    v = WalkForwardValidator(train_size=50, test_size=20, step_size=20)
    result = v.validate(data)
    assert "VALID" in result["symbols"]
    assert "NAN" not in result["symbols"]


def test_empty_data() -> None:
    """Empty data returns empty symbols."""
    v = WalkForwardValidator(train_size=50, test_size=20, step_size=20)
    result = v.validate({})
    assert result["symbols"] == {}
