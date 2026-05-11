"""Tests for meta_engine module — regime classification + capital allocation."""

from __future__ import annotations

import pytest

from bist_core.decision.meta_engine import (
    MetaDecisionEngine,
    Regime,
    classify_regime,
    _REGIME_CAPITAL_MULT,
    _EDGE_REGIME_PENALTY,
    _PENALTY_FACTOR,
    _VOL_THRESHOLD,
    _RANGE_BAND,
    _TREND_CONFIRM_BARS,
    _identify_edge,
)
from bist_core.models.ohlcv import OHLCVBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bars(
    closes: list[float],
    symbol: str = "TEST",
    volumes: list[float] | None = None,
) -> list[OHLCVBar]:
    if volumes is None:
        volumes = [1_000_000.0] * len(closes)
    return [
        OHLCVBar(
            timestamp=1_700_000_000 + i * 86400,
            symbol=symbol,
            open=c,
            high=c * 1.01,
            low=c * 0.99,
            close=c,
            volume=v,
        )
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


# ---------------------------------------------------------------------------
# Regime classifier tests
# ---------------------------------------------------------------------------


class TestClassifyRegime:
    def test_insufficient_data_returns_ranging(self):
        closes = [10.0] * 20
        assert classify_regime(closes) == Regime.RANGING

    def test_steady_uptrend(self):
        """Steadily rising prices → TRENDING_UP."""
        closes = [10.0 + i * 0.2 for i in range(80)]
        result = classify_regime(closes)
        assert result == Regime.TRENDING_UP

    def test_steady_downtrend(self):
        """Steadily falling prices → TRENDING_DOWN."""
        closes = [50.0 - i * 0.2 for i in range(80)]
        result = classify_regime(closes)
        assert result == Regime.TRENDING_DOWN

    def test_flat_prices_ranging(self):
        """Flat prices → RANGING."""
        closes = [10.0 + (i % 3) * 0.005 for i in range(80)]
        result = classify_regime(closes)
        assert result == Regime.RANGING

    def test_high_volatility(self):
        """Large alternating swings → HIGH_VOLATILITY."""
        import math
        closes = [10.0 + 2.0 * math.sin(i * 0.5) for i in range(80)]
        result = classify_regime(closes)
        assert result == Regime.HIGH_VOLATILITY

    def test_deterministic(self):
        """Same input → same output."""
        closes = [10.0 + i * 0.1 for i in range(80)]
        r1 = classify_regime(closes)
        r2 = classify_regime(closes)
        assert r1 == r2


class TestRegimeEnum:
    def test_all_regimes_have_capital_mult(self):
        for regime in Regime:
            assert regime in _REGIME_CAPITAL_MULT

    def test_capital_mult_in_range(self):
        for regime, mult in _REGIME_CAPITAL_MULT.items():
            assert 0.1 <= mult <= 2.0, f"{regime}: {mult}"

    def test_trending_up_has_highest_mult(self):
        assert _REGIME_CAPITAL_MULT[Regime.TRENDING_UP] >= max(
            _REGIME_CAPITAL_MULT[Regime.TRENDING_DOWN],
            _REGIME_CAPITAL_MULT[Regime.HIGH_VOLATILITY],
        )


# ---------------------------------------------------------------------------
# Edge-regime penalty tests
# ---------------------------------------------------------------------------


class TestEdgeRegimePenalty:
    def test_trend_pullback_penalized_in_high_vol(self):
        assert Regime.HIGH_VOLATILITY in _EDGE_REGIME_PENALTY["trend_pullback"]

    def test_trend_pullback_penalized_in_down(self):
        assert Regime.TRENDING_DOWN in _EDGE_REGIME_PENALTY["trend_pullback"]

    def test_mean_reversion_no_penalty(self):
        assert len(_EDGE_REGIME_PENALTY["mean_reversion"]) == 0

    def test_penalty_factor_reasonable(self):
        assert 0.1 <= _PENALTY_FACTOR <= 0.9


# ---------------------------------------------------------------------------
# MetaDecisionEngine tests
# ---------------------------------------------------------------------------


class TestMetaDecisionEngine:
    def test_instantiation(self):
        engine = MetaDecisionEngine()
        assert engine._edge is not None

    def test_returns_none_for_insufficient_bars(self):
        engine = MetaDecisionEngine()
        bars = _make_bars([10.0])
        assert engine("TEST", bars, 0) is None

    def test_deterministic_output(self):
        bars = _make_bars([10.0 + i * 0.1 for i in range(60)])
        e1 = MetaDecisionEngine()
        e2 = MetaDecisionEngine()
        r1 = e1("DET", bars, 59)
        r2 = e2("DET", bars, 59)
        assert r1 == r2

    def test_decision_includes_regime(self):
        """If a signal fires, it must include regime info."""
        engine = MetaDecisionEngine()
        # Create uptrend bars that might trigger a signal
        closes = [10.0 + i * 0.15 for i in range(80)]
        bars = _make_bars(closes)
        result = engine("YKBNK", bars, 79)
        # May be None — no guarantee signal fires on synthetic data.
        # But if it fires, it must have regime and capital_mult.
        if result is not None:
            assert "regime" in result
            assert "capital_mult" in result
            assert "edge" in result

    def test_decision_has_required_fields(self):
        """Any non-None decision must have symbol, entry, stop, target."""
        engine = MetaDecisionEngine()
        closes = [10.0 + i * 0.1 for i in range(80)]
        bars = _make_bars(closes)
        result = engine("SYM", bars, 79)
        if result is not None:
            for field in ("symbol", "entry", "stop", "target"):
                assert field in result


# ---------------------------------------------------------------------------
# Edge identification tests
# ---------------------------------------------------------------------------


class TestIdentifyEdge:
    def test_returns_string(self):
        closes = [10.0] * 60
        volumes = [1_000_000.0] * 60
        result = _identify_edge(closes, volumes)
        assert isinstance(result, str)

    def test_unknown_for_no_signal(self):
        closes = [10.0] * 60
        volumes = [1_000_000.0] * 60
        result = _identify_edge(closes, volumes)
        assert result == "unknown"


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_vol_threshold_positive(self):
        assert _VOL_THRESHOLD > 0

    def test_range_band_positive(self):
        assert _RANGE_BAND > 0

    def test_trend_confirm_bars_positive(self):
        assert _TREND_CONFIRM_BARS >= 1
