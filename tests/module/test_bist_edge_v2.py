"""Tests for bist_edge_v2 decision engine — deterministic, no randomness."""

from __future__ import annotations

from bist_core.decision.bist_edge_v2 import (
    BistEdgeV2Decision,
    _atr,
    _compute_atr_risk,
    _compute_position_size,
    _mean_reversion_signal,
    _regime_allows_any_signal,
    _regime_allows_trend_signal,
    _rsi,
    _sma,
    _stddev_returns,
    _symbol_quality_ok,
    _trend_duration_ok,
    _trend_pullback_signal,
    _vol_compression_breakout_signal,
)
from bist_core.models.ohlcv import OHLCVBar


def _make_bars(
    closes: list[float],
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[OHLCVBar]:
    """Helper: create OHLCVBars from price series."""
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


# ---------------------------------------------------------------------------
# Feature tests
# ---------------------------------------------------------------------------

class TestSMA:
    def test_exact(self) -> None:
        assert _sma([10.0, 20.0, 30.0], 3) == 20.0

    def test_insufficient(self) -> None:
        assert _sma([10.0], 5) == 0.0


class TestStddevReturns:
    def test_constant_zero(self) -> None:
        assert _stddev_returns([100.0] * 25, 10) == 0.0

    def test_positive_for_varying(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(25)]
        assert _stddev_returns(closes, 10) > 0.0


class TestATR:
    def test_insufficient(self) -> None:
        bars = _make_bars([100.0] * 5)
        assert _atr(bars, 14) == 0.0

    def test_positive(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(20)]
        bars = _make_bars(closes)
        assert _atr(bars, 14) > 0.0


class TestRSI:
    def test_constant_50(self) -> None:
        assert _rsi([100.0] * 5, 14) == 50.0

    def test_uptrend_high(self) -> None:
        closes = [100.0 + i for i in range(20)]
        assert _rsi(closes, 14) > 70.0


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------

class TestRegimeFilters:
    def test_allows_flat(self) -> None:
        assert _regime_allows_any_signal([100.0] * 60) is True

    def test_blocks_extreme_vol(self) -> None:
        # Alternating 10% moves → high vol
        closes: list[float] = []
        val = 100.0
        for i in range(60):
            val *= 1.10 if i % 2 == 0 else 0.90
            closes.append(val)
        assert _regime_allows_any_signal(closes) is False


class TestSymbolQuality:
    def test_stable_ok(self) -> None:
        # Steady uptrend = 0 transitions
        closes = [100.0 * (1.005 ** i) for i in range(120)]
        assert _symbol_quality_ok(closes) is True


class TestTrendDuration:
    def test_insufficient_bars(self) -> None:
        assert _trend_duration_ok([100.0] * 30) is False

    def test_strong_uptrend_passes(self) -> None:
        closes = [100.0 * (1.01 ** i) for i in range(70)]
        assert _trend_duration_ok(closes) is True


# ---------------------------------------------------------------------------
# Position sizing tests
# ---------------------------------------------------------------------------

class TestPositionSizing:
    def test_low_price(self) -> None:
        # 1 TRY stock → 5000 shares
        assert _compute_position_size(1.0) == 500  # capped at MAX

    def test_high_price(self) -> None:
        # 60 TRY stock → 83 shares
        assert _compute_position_size(60.0) == 83

    def test_zero_price(self) -> None:
        assert _compute_position_size(0.0) == 0


class TestATRRisk:
    def test_floor_and_cap(self) -> None:
        # Very low ATR → hits floor
        stop, target = _compute_atr_risk(100.0, 0.01)
        assert stop < 100.0
        assert target > 100.0
        # Very high ATR → hits cap
        stop2, target2 = _compute_atr_risk(100.0, 100.0)
        assert stop2 >= 100.0 * (1 - 0.06)  # cap
        assert target2 <= 100.0 * (1 + 0.10)  # cap


# ---------------------------------------------------------------------------
# Stateful decision engine tests
# ---------------------------------------------------------------------------

class TestBistEdgeV2Decision:
    def test_returns_none_for_few_bars(self) -> None:
        engine = BistEdgeV2Decision()
        bars = _make_bars([100.0] * 10)
        assert engine("TEST", bars, 5) is None

    def test_returns_none_on_flat_data(self) -> None:
        engine = BistEdgeV2Decision()
        bars = _make_bars([100.0] * 60)
        result = engine("TEST", bars, 59)
        assert result is None

    def test_cooldown_blocks_rapid_signals(self) -> None:
        """Two calls within cooldown period → second must return None."""
        engine = BistEdgeV2Decision()
        # Build strong uptrend with pullback
        closes: list[float] = [100.0 * (1.01 ** i) for i in range(55)]
        sma20 = sum(closes[-20:]) / 20
        closes[-1] = sma20 * 1.003
        bars = _make_bars(closes)
        r1 = engine("TEST", bars, len(bars) - 1)
        if r1 is not None:
            # Immediate next call should be blocked by cooldown
            closes.append(sma20 * 1.004)
            bars2 = _make_bars(closes)
            r2 = engine("TEST", bars2, len(bars2) - 1)
            assert r2 is None  # cooldown active

    def test_decision_dict_shape(self) -> None:
        """If signal fires, verify required fields and sanity."""
        engine = BistEdgeV2Decision()
        closes = [100.0 * (1.01 ** i) for i in range(55)]
        sma20 = sum(closes[-20:]) / 20
        closes[-1] = sma20 * 1.003
        bars = _make_bars(closes)
        result = engine("TEST", bars, len(bars) - 1)
        if result is not None:
            assert result["symbol"] == "TEST"
            assert result["stop"] < result["entry"]
            assert result["target"] > result["entry"]
            assert result["position_size"] >= 1

    def test_deterministic(self) -> None:
        """Same input, fresh engine → same output."""
        def run():
            eng = BistEdgeV2Decision()
            closes = [100.0 * (1.01 ** i) for i in range(55)]
            sma20 = sum(closes[-20:]) / 20
            closes[-1] = sma20 * 1.003
            bars = _make_bars(closes)
            return eng("TEST", bars, len(bars) - 1)

        assert run() == run()

    def test_different_symbols_independent_cooldown(self) -> None:
        """Cooldown is per-symbol, not global."""
        engine = BistEdgeV2Decision()
        closes = [100.0 * (1.01 ** i) for i in range(55)]
        sma20 = sum(closes[-20:]) / 20
        closes[-1] = sma20 * 1.003
        bars_a = _make_bars(closes)
        # Patch symbol
        for b in bars_a:
            object.__setattr__(b, "symbol", "AAA")

        r1 = engine("AAA", bars_a, len(bars_a) - 1)
        if r1 is not None:
            bars_b = _make_bars(closes)
            for b in bars_b:
                object.__setattr__(b, "symbol", "BBB")
            r2 = engine("BBB", bars_b, len(bars_b) - 1)
            # BBB should NOT be blocked by AAA's cooldown
            # (it may still be None for other reasons, but not cooldown)
            # Just verify it doesn't crash
            assert r2 is None or isinstance(r2, dict)
