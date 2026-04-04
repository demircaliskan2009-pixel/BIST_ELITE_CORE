"""RegimeEngine — deterministic classification."""

from __future__ import annotations

from bist_core.market.regime_engine import RegimeEngine


def test_short_series_unknown() -> None:
    eng = RegimeEngine()
    assert eng.detect([100.0 + i for i in range(5)]) == "unknown"


def test_flat_range() -> None:
    eng = RegimeEngine()
    closes = [100.0] * 15
    assert eng.detect(closes) == "range"


def test_linear_trend() -> None:
    eng = RegimeEngine()
    closes = [50.0 + i * 2.0 for i in range(15)]
    assert eng.detect(closes) == "trend"
