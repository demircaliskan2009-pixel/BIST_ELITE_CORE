"""Tests for Pipeline — end-to-end scan → rank → validate → decide → portfolio."""

from __future__ import annotations

from bist_core.models.ohlcv import OHLCVBar
from bist_core.pipeline import Pipeline


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
    return [_bar(str(1704067200 + i * 86400), symbol, base + i * step) for i in range(n)]


def test_full_pipeline_determinism() -> None:
    """Same input produces same output."""
    data = {
        "A": _make_bars("A", 100),
        "B": _make_bars("B", 100),
    }
    pipeline = Pipeline()
    a = pipeline.run(data)
    b = pipeline.run(data)
    assert a["candidates"] == b["candidates"]
    assert a["ranked"] == b["ranked"]
    assert a["decisions"] == b["decisions"]
    assert a["portfolio"] == b["portfolio"]


def test_correct_flow() -> None:
    """Pipeline produces candidates → ranked → validation → decisions → portfolio."""
    data = {"X": _make_bars("X", 100)}
    pipeline = Pipeline()
    result = pipeline.run(data)
    assert "candidates" in result
    assert "ranked" in result
    assert "validation" in result
    assert "decisions" in result
    assert "portfolio" in result
    assert isinstance(result["candidates"], list)
    assert isinstance(result["ranked"], list)
    assert isinstance(result["validation"], dict)
    assert "symbols" in result["validation"]
    assert isinstance(result["decisions"], list)
    assert isinstance(result["portfolio"], list)


def test_current_prices_integration() -> None:
    """When current_prices provided, decisions get context fields."""
    data = {"Y": _make_bars("Y", 100)}
    pipeline = Pipeline()
    current_prices = {"Y": 102.0}
    result = pipeline.run(data, current_prices=current_prices)
    decisions = result["decisions"]
    if decisions:
        d = decisions[0]
        assert "current_price" in d
        assert "entry_delta" in d
        assert "entry_status" in d
