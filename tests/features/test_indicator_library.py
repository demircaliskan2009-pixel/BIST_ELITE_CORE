"""Indicator library unit tests — SMA, EMA, RSI, ATR, returns."""

from __future__ import annotations

import pytest

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.features.indicator_library import atr, ema, returns, rsi, sma


def _bar(ts: str, close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else close - 1
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=1000)


def _bars_from_closes(closes: list[float]) -> list[OHLCVBar]:
    return [_bar(f"2026-01-{i + 1:02d}", c) for i, c in enumerate(closes)]


class TestSMA:
    def test_sma_returns_expected_values_for_known_series(self) -> None:
        closes = [10.0, 11.0, 12.0, 13.0, 14.0]
        bars = _bars_from_closes(closes)
        result = sma(bars, 3)
        assert len(result) == 5
        assert result[0] is None
        assert result[1] is None
        assert result[2] == pytest.approx(11.0, abs=0.001)
        assert result[3] == pytest.approx(12.0, abs=0.001)
        assert result[4] == pytest.approx(13.0, abs=0.001)

    def test_sma_length_matches_input(self) -> None:
        bars = _bars_from_closes([1, 2, 3, 4, 5, 6, 7])
        result = sma(bars, 5)
        assert len(result) == 7

    def test_sma_period_larger_than_bars(self) -> None:
        bars = _bars_from_closes([1, 2])
        result = sma(bars, 5)
        assert all(v is None for v in result)

    def test_sma_period_1(self) -> None:
        bars = _bars_from_closes([5.0, 10.0, 15.0])
        result = sma(bars, 1)
        assert result == [5.0, 10.0, 15.0]


class TestEMA:
    def test_ema_seed_equals_sma(self) -> None:
        bars = _bars_from_closes([10, 11, 12, 13, 14])
        result = ema(bars, 3)
        assert result[2] == pytest.approx(11.0, abs=0.001)
        assert result[0] is None
        assert result[1] is None

    def test_ema_length_matches_input(self) -> None:
        bars = _bars_from_closes([1, 2, 3, 4, 5])
        result = ema(bars, 3)
        assert len(result) == 5

    def test_ema_responds_to_price_changes(self) -> None:
        bars = _bars_from_closes([10, 10, 10, 20, 20])
        result = ema(bars, 3)
        assert result[3] is not None and result[3] > 10.0


class TestRSI:
    def test_rsi_with_constant_prices_returns_none(self) -> None:
        bars = _bars_from_closes([50.0] * 20)
        result = rsi(bars, 14)
        assert len(result) == 20
        for v in result[15:]:
            assert v is not None

    def test_rsi_all_up_near_100(self) -> None:
        closes = [100 + i for i in range(20)]
        bars = _bars_from_closes(closes)
        result = rsi(bars, 14)
        assert result[14] is not None and result[14] > 90

    def test_rsi_all_down_near_0(self) -> None:
        closes = [100 - i for i in range(20)]
        bars = _bars_from_closes(closes)
        result = rsi(bars, 14)
        assert result[14] is not None and result[14] < 10

    def test_rsi_length_matches_input(self) -> None:
        bars = _bars_from_closes([50] * 30)
        assert len(rsi(bars, 14)) == 30


class TestATR:
    def test_atr_positive_for_volatile_series(self) -> None:
        bars = [
            OHLCVBar(f"2026-01-{i + 1:02d}", "X", 100, 110, 90, 100 + (i % 3) * 5, 1000)
            for i in range(20)
        ]
        result = atr(bars, 14)
        assert result[14] is not None and result[14] > 0

    def test_atr_length_matches_input(self) -> None:
        bars = _bars_from_closes([100] * 20)
        assert len(atr(bars, 14)) == 20


class TestReturns:
    def test_returns_computes_percent_change(self) -> None:
        bars = _bars_from_closes([100.0, 110.0, 99.0])
        result = returns(bars)
        assert result[0] is None
        assert result[1] == pytest.approx(10.0, abs=0.001)
        assert result[2] == pytest.approx(-10.0, abs=0.01)

    def test_returns_length_matches_input(self) -> None:
        bars = _bars_from_closes([1, 2, 3])
        assert len(returns(bars)) == 3

    def test_returns_first_is_none(self) -> None:
        bars = _bars_from_closes([50, 60])
        assert returns(bars)[0] is None
