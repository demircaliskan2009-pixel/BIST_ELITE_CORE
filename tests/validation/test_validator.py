"""Tests for bist_core.validation.validator — deterministic, no network."""

from __future__ import annotations

from bist_core.models.ohlcv import OHLCVBar
from bist_core.validation.validator import Validator


def _bars(symbol: str, n: int, close: float = 100.0) -> list[OHLCVBar]:
    out = []
    for i in range(n):
        ts = 1704067200 + i * 86400
        c = close + i * 0.01
        out.append(
            OHLCVBar(
                symbol=symbol,
                open=c,
                high=c + 1,
                low=max(c - 1, 0.01),
                close=c,
                volume=1000.0,
                timestamp=ts,
            )
        )
    return out


def test_compute_expectancy_empty() -> None:
    v = Validator()
    assert v.compute_expectancy([]) == 0.0


def test_compute_expectancy_wins_losses() -> None:
    v = Validator()
    trades = [
        {"pnl": 10.0},
        {"pnl": -5.0},
        {"pnl": 20.0},
    ]
    exp = v.compute_expectancy(trades)
    assert isinstance(exp, float)


def test_compute_drawdown_monotonic_peak() -> None:
    v = Validator()
    dd = v.compute_drawdown([100.0, 110.0, 105.0, 90.0])
    assert dd <= 0.0
    assert dd < 0.0


def test_walk_forward_insufficient_bars() -> None:
    v = Validator()
    data = {"X": _bars("X", 5)}
    wf = v.walk_forward(data)
    assert wf["train_expectancy"] == 0.0
    assert wf["test_expectancy"] == 0.0
    assert wf["overfit_score"] == 0.0


def test_walk_forward_with_data() -> None:
    v = Validator()
    data = {"GARAN": _bars("GARAN", 30)}
    wf = v.walk_forward(data)
    assert "train_expectancy" in wf
    assert "test_expectancy" in wf
    assert "overfit_score" in wf


def test_run_parity_test_smoke() -> None:
    v = Validator()
    data = {"GARAN": _bars("GARAN", 30)}
    p = v.run_parity_test(data)
    assert "parity_score" in p
    assert "pnl_diff" in p
    assert "trade_diff" in p


def test_run_full_validation_smoke() -> None:
    v = Validator()
    data = {"GARAN": _bars("GARAN", 30)}
    out = v.run_full_validation(data)
    assert "parity" in out
    assert "expectancy" in out
    assert "walk_forward" in out
    assert "drawdown" in out
