"""Tests for bist_edge_v1 decision function — deterministic, no randomness."""

from __future__ import annotations

from bist_core.decision.bist_edge_v1 import (
    _stddev_returns,
    _sma,
    _trend_pullback_signal,
    _vol_compression_breakout_signal,
    bist_edge_v1_decision,
)
from bist_core.models.ohlcv import OHLCVBar


def _make_bars(closes: list[float], volumes: list[float] | None = None) -> list[OHLCVBar]:
    """Helper: create OHLCVBars from closes (open=high=low=close for simplicity)."""
    if volumes is None:
        volumes = [1_000_000.0] * len(closes)
    return [
        OHLCVBar(
            timestamp=1_700_000_000 + i * 86400,
            symbol="TEST",
            open=c,
            high=c,
            low=c,
            close=c,
            volume=v,
        )
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


class TestSMA:
    def test_exact(self) -> None:
        assert _sma([10.0, 20.0, 30.0], 3) == 20.0

    def test_insufficient(self) -> None:
        assert _sma([10.0], 5) == 0.0


class TestStddevReturns:
    def test_constant_returns_zero(self) -> None:
        closes = [100.0] * 25
        assert _stddev_returns(closes, 10) == 0.0

    def test_positive_for_varying(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(25)]
        assert _stddev_returns(closes, 10) > 0.0


class TestTrendPullback:
    def test_no_signal_insufficient_bars(self) -> None:
        assert _trend_pullback_signal([100.0] * 30, [1e6] * 30) is False

    def test_signal_in_uptrend_pullback(self) -> None:
        """Construct a deterministic uptrend with a pullback to SMA20."""
        # 50 bars of steady uptrend (1% per bar), then a slight pullback
        closes: list[float] = []
        base = 100.0
        for i in range(55):
            closes.append(base * (1.01 ** i))
        # Pull the last close back near SMA20
        sma20 = sum(closes[-20:]) / 20
        closes[-1] = sma20 * 1.003  # within +0.3% of SMA20
        volumes = [1_000_000.0] * len(closes)
        assert _trend_pullback_signal(closes, volumes) is True


class TestVolCompressionBreakout:
    def test_no_signal_insufficient_bars(self) -> None:
        assert _vol_compression_breakout_signal([100.0] * 20, [1e6] * 20) is False


class TestBistEdgeV1Decision:
    def test_returns_none_for_few_bars(self) -> None:
        bars = _make_bars([100.0] * 10)
        assert bist_edge_v1_decision("TEST", bars, 5) is None

    def test_returns_none_on_flat_data(self) -> None:
        bars = _make_bars([100.0] * 60)
        result = bist_edge_v1_decision("TEST", bars, 59)
        assert result is None  # No trend, no breakout

    def test_decision_dict_shape(self) -> None:
        """If a signal fires, verify dict structure."""
        # Build a strong uptrend then pullback
        closes: list[float] = []
        base = 100.0
        for i in range(55):
            closes.append(base * (1.01 ** i))
        sma20 = sum(closes[-20:]) / 20
        closes[-1] = sma20 * 1.003
        bars = _make_bars(closes)
        result = bist_edge_v1_decision("TEST", bars, len(bars) - 1)
        if result is not None:
            assert "symbol" in result
            assert "entry" in result
            assert "stop" in result
            assert "target" in result
            assert "position_size" in result
            assert result["stop"] < result["entry"]
            assert result["target"] > result["entry"]
            assert result["position_size"] == 10

    def test_deterministic(self) -> None:
        """Same input must produce same output."""
        closes = [100.0 * (1.01 ** i) for i in range(55)]
        sma20 = sum(closes[-20:]) / 20
        closes[-1] = sma20 * 1.003
        bars = _make_bars(closes)
        r1 = bist_edge_v1_decision("TEST", bars, len(bars) - 1)
        r2 = bist_edge_v1_decision("TEST", bars, len(bars) - 1)
        assert r1 == r2
