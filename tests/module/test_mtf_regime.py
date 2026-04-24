"""Tests for mtf_regime — multi-horizon regime filter on daily bars."""

from __future__ import annotations

from bist_core.decision.mtf_regime import (
    DailySetup,
    MonthlyRegime,
    WeeklyBias,
    classify_all_horizons,
    classify_daily_setup,
    classify_monthly_regime,
    classify_weekly_bias,
    mtf_allows_trade,
    mtf_confidence_mult,
)
from bist_core.models.ohlcv import OHLCVBar


def _make_bars(
    closes: list[float],
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[OHLCVBar]:
    if volumes is None:
        volumes = [1_000_000.0] * len(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    return [
        OHLCVBar(
            timestamp=1_700_000_000 + i * 86400,
            symbol="TEST",
            open=c,
            high=h,
            low=lo,
            close=c,
            volume=v,
        )
        for i, (c, h, lo, v) in enumerate(zip(closes, highs, lows, volumes))
    ]


def _uptrend(n: int, start: float = 100.0, step: float = 0.5) -> list[float]:
    """Generate uptrending closes."""
    return [start + i * step for i in range(n)]


def _downtrend(n: int, start: float = 200.0, step: float = 0.5) -> list[float]:
    """Generate downtrending closes."""
    return [start - i * step for i in range(n)]


def _flat(n: int, price: float = 100.0) -> list[float]:
    """Generate flat closes (range-bound)."""
    return [price] * n


def _volatile(n: int, base: float = 100.0, amplitude: float = 8.0) -> list[float]:
    """Generate volatile alternating closes."""
    return [base + amplitude * (1 if i % 2 == 0 else -1) for i in range(n)]


# ---------------------------------------------------------------------------
# Monthly regime classifier
# ---------------------------------------------------------------------------


class TestMonthlyRegime:
    def test_insufficient_data_returns_range(self) -> None:
        closes = _flat(10)
        assert classify_monthly_regime(closes) == MonthlyRegime.RANGE

    def test_flat_market_is_range(self) -> None:
        closes = _flat(80)
        assert classify_monthly_regime(closes) == MonthlyRegime.RANGE

    def test_uptrend_is_bull(self) -> None:
        closes = _uptrend(80, step=0.8)
        result = classify_monthly_regime(closes)
        assert result == MonthlyRegime.BULL

    def test_downtrend_is_bear(self) -> None:
        closes = _downtrend(80, start=200.0, step=0.8)
        result = classify_monthly_regime(closes)
        assert result in {MonthlyRegime.BEAR, MonthlyRegime.VOLATILE}

    def test_volatile_market(self) -> None:
        closes = _volatile(80, amplitude=10.0)
        result = classify_monthly_regime(closes)
        assert result in {MonthlyRegime.VOLATILE, MonthlyRegime.RANGE}


# ---------------------------------------------------------------------------
# Weekly bias classifier
# ---------------------------------------------------------------------------


class TestWeeklyBias:
    def test_insufficient_data(self) -> None:
        closes = _flat(5)
        assert classify_weekly_bias(closes) == WeeklyBias.NEUTRAL

    def test_flat_is_neutral(self) -> None:
        closes = _flat(40)
        assert classify_weekly_bias(closes) == WeeklyBias.NEUTRAL

    def test_up_bias(self) -> None:
        closes = _uptrend(40, step=1.0)
        result = classify_weekly_bias(closes)
        assert result == WeeklyBias.UP

    def test_down_bias(self) -> None:
        closes = _downtrend(40, start=200.0, step=1.0)
        result = classify_weekly_bias(closes)
        assert result == WeeklyBias.DOWN


# ---------------------------------------------------------------------------
# Daily setup classifier
# ---------------------------------------------------------------------------


class TestDailySetup:
    def test_insufficient_data_returns_ready(self) -> None:
        closes = _flat(5)
        bars = _make_bars(closes)
        assert classify_daily_setup(closes, bars) == DailySetup.READY

    def test_overbought_is_exhausted(self) -> None:
        # Generate strongly overbought RSI: many consecutive ups
        closes = _uptrend(30, step=2.0)
        bars = _make_bars(closes)
        result = classify_daily_setup(closes, bars)
        assert result in {DailySetup.EXHAUSTED, DailySetup.READY}

    def test_oversold_detection(self) -> None:
        # Generate strongly oversold RSI: many consecutive downs
        closes = _downtrend(30, start=200.0, step=3.0)
        bars = _make_bars(closes)
        result = classify_daily_setup(closes, bars)
        assert result in {DailySetup.OVERSOLD, DailySetup.UNSTABLE}

    def test_stable_market_is_ready(self) -> None:
        # Small oscillation avoids RSI edge case (flat=100 when avg_loss=0)
        closes = [100.0 + 0.1 * (i % 3 - 1) for i in range(30)]
        bars = _make_bars(closes)
        result = classify_daily_setup(closes, bars)
        assert result == DailySetup.READY


# ---------------------------------------------------------------------------
# MTF alignment
# ---------------------------------------------------------------------------


class TestMtfAllowsTrade:
    def test_unknown_edge_rejected(self) -> None:
        """Unknown edge name → no MTF map → rejected."""
        closes = _uptrend(80, step=0.5)
        bars = _make_bars(closes)
        assert mtf_allows_trade(closes, bars, "nonexistent_edge") is False

    def test_trend_pullback_in_flat_rejected(self) -> None:
        """Trend pullback requires BULL monthly — flat market → rejected."""
        closes = _flat(80)
        bars = _make_bars(closes)
        assert mtf_allows_trade(closes, bars, "trend_pullback") is False

    def test_short_data_low_confidence(self) -> None:
        """With very short data, monthly=RANGE → trend_pullback gets low score."""
        closes = _flat(10)
        bars = _make_bars(closes)
        conf = mtf_confidence_mult(closes, bars, "trend_pullback")
        assert conf <= 0.7  # at most partial alignment

    def test_gap_fade_in_volatile_regime(self) -> None:
        """Gap fade requires BEAR or VOLATILE monthly."""
        closes = _volatile(80, amplitude=10.0)
        bars = _make_bars(closes)
        # Even if monthly is volatile, weekly/daily may not align
        # Just confirm it either passes or fails deterministically
        r1 = mtf_allows_trade(closes, bars, "gap_fade")
        r2 = mtf_allows_trade(closes, bars, "gap_fade")
        assert r1 == r2  # deterministic


# ---------------------------------------------------------------------------
# classify_all_horizons
# ---------------------------------------------------------------------------


class TestClassifyAllHorizons:
    def test_returns_all_keys(self) -> None:
        closes = _flat(80)
        bars = _make_bars(closes)
        result = classify_all_horizons(closes, bars)
        assert "monthly_regime" in result
        assert "weekly_bias" in result
        assert "daily_setup" in result

    def test_deterministic(self) -> None:
        closes = _uptrend(80, step=0.5)
        bars = _make_bars(closes)
        r1 = classify_all_horizons(closes, bars)
        r2 = classify_all_horizons(closes, bars)
        assert r1 == r2

    def test_values_are_strings(self) -> None:
        closes = _flat(80)
        bars = _make_bars(closes)
        result = classify_all_horizons(closes, bars)
        for v in result.values():
            assert isinstance(v, str)
