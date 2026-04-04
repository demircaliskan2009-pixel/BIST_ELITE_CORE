"""Regime engine unit tests — bull, bear, sideways, insufficient, determinism."""

from __future__ import annotations

import pytest

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.regime_engine import RegimeEngine


def _bar(ts: str, close: float) -> OHLCVBar:
    return OHLCVBar(ts, "X", close, close + 1, max(close - 1, 0.01), close, 1_000_000)


def _trending_up_bars(n: int = 60) -> list[OHLCVBar]:
    return [_bar(f"2026-01-{i + 1:02d}", 100.0 + i * 0.5) for i in range(n)]


def _trending_down_bars(n: int = 60) -> list[OHLCVBar]:
    return [_bar(f"2026-01-{i + 1:02d}", 130.0 - i * 0.5) for i in range(n)]


def _flat_bars(n: int = 60, price: float = 100.0) -> list[OHLCVBar]:
    return [_bar(f"2026-01-{i + 1:02d}", price) for i in range(n)]


class TestDetectRegime:
    def test_detect_bull_regime(self) -> None:
        bars = _trending_up_bars(60)
        engine = RegimeEngine(fast_period=20, slow_period=50)
        regime = engine.detect_regime(bars)
        assert regime is not None
        assert regime.regime == "bull"
        assert regime.strength > 0
        assert regime.sma_fast > regime.sma_slow

    def test_detect_bear_regime(self) -> None:
        bars = _trending_down_bars(60)
        engine = RegimeEngine(fast_period=20, slow_period=50)
        regime = engine.detect_regime(bars)
        assert regime is not None
        assert regime.regime == "bear"
        assert regime.strength > 0
        assert regime.sma_fast < regime.sma_slow

    def test_detect_sideways_regime(self) -> None:
        bars = _flat_bars(60)
        engine = RegimeEngine(fast_period=20, slow_period=50)
        regime = engine.detect_regime(bars)
        assert regime is not None
        assert regime.regime == "sideways"

    def test_insufficient_bars_returns_none(self) -> None:
        bars = _flat_bars(10)
        engine = RegimeEngine(fast_period=20, slow_period=50)
        assert engine.detect_regime(bars) is None

    def test_to_dict(self) -> None:
        bars = _trending_up_bars(60)
        regime = RegimeEngine().detect_regime(bars)
        assert regime is not None
        d = regime.to_dict()
        assert "regime" in d
        assert "strength" in d
        assert "sma_fast" in d
        assert "sma_slow" in d
        assert "timestamp" in d

    def test_deterministic_output(self) -> None:
        bars = _trending_up_bars(60)
        engine = RegimeEngine()
        r1 = engine.detect_regime(bars)
        r2 = engine.detect_regime(bars)
        assert r1 is not None and r2 is not None
        assert r1.to_dict() == r2.to_dict()
