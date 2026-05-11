"""Tests for universe_selector.py — scoring + selection."""

from __future__ import annotations

import math

import pytest

from bist_core.decision.universe_selector import (
    UniverseSelector,
    _DEFAULT_TOP_N,
    _LOOKBACK,
    _REBALANCE_DAYS,
    _SMA_LONG,
    _SMA_SHORT,
    _VOL_CEILING,
    _VOL_FLOOR,
    _VOL_SWEET_HI,
    _VOL_SWEET_LO,
    _W_EFFICIENCY,
    _W_LIQUIDITY,
    _W_TREND,
    _W_VOLATILITY,
    score_efficiency,
    score_liquidity,
    score_symbol,
    score_trend_quality,
    score_volatility_regime,
)


# ===================================================================
# score_trend_quality
# ===================================================================


class TestScoreTrendQuality:
    def test_insufficient_data_returns_neutral(self):
        assert score_trend_quality([1.0] * 10) == 0.5

    def test_uptrend_scores_high(self):
        # Strong uptrend: SMA20 >> SMA50 with 5%+ divergence
        closes = [10.0 + i * 0.1 for i in range(60)]
        score = score_trend_quality(closes)
        assert score > 0.5

    def test_flat_scores_low(self):
        closes = [10.0] * 60
        score = score_trend_quality(closes)
        assert score < 0.1  # zero divergence

    def test_range_zero_to_one(self):
        for vals in [[10.0] * 60, [10.0 + i * 0.5 for i in range(60)]]:
            s = score_trend_quality(vals)
            assert 0.0 <= s <= 1.0

    def test_downtrend_no_bonus(self):
        # Downtrend: SMA20 < SMA50
        closes = [20.0 - i * 0.1 for i in range(60)]
        score_down = score_trend_quality(closes)
        # Uptrend of same magnitude should score higher (bonus)
        closes_up = [10.0 + i * 0.1 for i in range(60)]
        score_up = score_trend_quality(closes_up)
        assert score_up >= score_down


# ===================================================================
# score_volatility_regime
# ===================================================================


class TestScoreVolatilityRegime:
    def test_insufficient_data_returns_neutral(self):
        assert score_volatility_regime([1.0] * 10) == 0.5

    def test_flat_scores_low(self):
        closes = [10.0] * 60
        score = score_volatility_regime(closes)
        assert score <= 0.3  # zero vol

    def test_moderate_vol_scores_high(self):
        # Alternating +2% / -1.5% → daily vol ≈ 1.75% (sweet spot)
        closes = [10.0]
        for i in range(59):
            if i % 2 == 0:
                closes.append(closes[-1] * 1.02)
            else:
                closes.append(closes[-1] * 0.985)
        score = score_volatility_regime(closes)
        assert score > 0.5

    def test_range_zero_to_one(self):
        closes = [10.0 + i * 0.01 for i in range(60)]
        s = score_volatility_regime(closes)
        assert 0.0 <= s <= 1.0

    def test_extreme_vol_scores_low(self):
        # Wild swings → high vol
        closes = [10.0]
        for i in range(59):
            if i % 2 == 0:
                closes.append(closes[-1] * 1.08)
            else:
                closes.append(closes[-1] * 0.92)
        score = score_volatility_regime(closes)
        assert score < 0.5


# ===================================================================
# score_efficiency
# ===================================================================


class TestScoreEfficiency:
    def test_insufficient_data_returns_neutral(self):
        assert score_efficiency([1.0] * 10) == 0.5

    def test_trending_detects_autocorrelation(self):
        # Strong monotonic trend → positive autocorrelation
        closes = [10.0 + i * 0.1 for i in range(60)]
        score = score_efficiency(closes)
        assert score > 0.0

    def test_range_zero_to_one(self):
        closes = [10.0 + i * 0.01 for i in range(60)]
        s = score_efficiency(closes)
        assert 0.0 <= s <= 1.0

    def test_zero_variance_returns_neutral(self):
        # Constant prices → var = 0
        assert score_efficiency([10.0] * 60) == 0.5


# ===================================================================
# score_liquidity
# ===================================================================


class TestScoreLiquidity:
    def test_zero_volume_returns_zero(self):
        assert score_liquidity([10.0] * 20, [0.0] * 20) == 0.0

    def test_empty_returns_zero(self):
        assert score_liquidity([], []) == 0.0

    def test_high_volume_scores_high(self):
        closes = [100.0] * 20
        volumes = [1_000_000.0] * 20  # 100M TRY turnover
        score = score_liquidity(closes, volumes)
        assert score > 0.5

    def test_low_volume_scores_low(self):
        closes = [10.0] * 20
        volumes = [100.0] * 20  # 1K TRY turnover
        score = score_liquidity(closes, volumes)
        assert score == 0.0  # below 1M floor

    def test_range_zero_to_one(self):
        closes = [50.0] * 20
        volumes = [500_000.0] * 20
        s = score_liquidity(closes, volumes)
        assert 0.0 <= s <= 1.0


# ===================================================================
# score_symbol (composite)
# ===================================================================


class TestScoreSymbol:
    def test_returns_all_components(self):
        closes = [10.0 + i * 0.05 for i in range(60)]
        volumes = [500_000.0] * 60
        result = score_symbol(closes, volumes)
        for key in ("trend_quality", "volatility_regime", "efficiency", "liquidity", "composite"):
            assert key in result

    def test_composite_is_weighted_average(self):
        closes = [10.0 + i * 0.05 for i in range(60)]
        volumes = [500_000.0] * 60
        result = score_symbol(closes, volumes)
        expected = (
            _W_TREND * result["trend_quality"]
            + _W_VOLATILITY * result["volatility_regime"]
            + _W_EFFICIENCY * result["efficiency"]
            + _W_LIQUIDITY * result["liquidity"]
        )
        assert abs(result["composite"] - round(expected, 4)) < 0.001

    def test_composite_in_range(self):
        closes = [10.0 + i * 0.05 for i in range(60)]
        volumes = [500_000.0] * 60
        result = score_symbol(closes, volumes)
        assert 0.0 <= result["composite"] <= 1.0


# ===================================================================
# UniverseSelector
# ===================================================================


class TestUniverseSelector:
    def test_warmup_allows_all(self):
        sel = UniverseSelector(top_n=2)
        for i in range(10):
            sel.update_bar("AAA", 10.0 + i * 0.1, 100000, i)
        assert sel.is_allowed("AAA")
        assert sel.is_allowed("UNKNOWN")

    def test_empty_universe_allows_all(self):
        sel = UniverseSelector(top_n=5)
        assert sel.is_allowed("ANY")
        assert sel.universe == set()

    def test_rebalance_selects_top_n(self):
        sel = UniverseSelector(top_n=1, rebalance_days=1)
        # TREND: strong uptrend + high volume
        # FLAT: constant price + near-zero volume
        for day in range(65):
            sel.update_bar("TREND", 10.0 + day * 0.1, 1_000_000, day)
            sel.update_bar("FLAT", 10.0, 100, day)

        assert "TREND" in sel.universe
        assert "FLAT" not in sel.universe
        assert sel.is_allowed("TREND")
        assert not sel.is_allowed("FLAT")

    def test_rankings_sorted_descending(self):
        sel = UniverseSelector(top_n=5, rebalance_days=1)
        for day in range(65):
            sel.update_bar("A", 10.0 + day * 0.2, 500_000, day)
            sel.update_bar("B", 10.0, 100, day)
        rankings = sel.rankings
        assert len(rankings) >= 2
        assert rankings[0][1]["composite"] >= rankings[1][1]["composite"]

    def test_deterministic(self):
        """Same input → same output."""
        results = []
        for _ in range(2):
            sel = UniverseSelector(top_n=2, rebalance_days=1)
            for day in range(65):
                sel.update_bar("X", 10.0 + day * 0.1, 500_000, day)
                sel.update_bar("Y", 10.0, 100, day)
            results.append(sel.scores)
        assert results[0] == results[1]

    def test_scores_populated_after_rebalance(self):
        sel = UniverseSelector(top_n=5, rebalance_days=1)
        for day in range(65):
            sel.update_bar("SYM", 10.0 + day * 0.05, 200_000, day)
        assert "SYM" in sel.scores
        assert "composite" in sel.scores["SYM"]

    def test_top_n_caps_universe_size(self):
        sel = UniverseSelector(top_n=2, rebalance_days=1)
        # Feed 5 symbols with different trend strengths
        for day in range(65):
            for j, sym in enumerate(["A", "B", "C", "D", "E"]):
                sel.update_bar(sym, 10.0 + day * (0.05 * (j + 1)), 500_000, day)
        assert len(sel.universe) <= 2

    def test_rebalance_interval_respected(self):
        sel = UniverseSelector(top_n=5, rebalance_days=5)
        for day in range(65):
            sel.update_bar("A", 10.0 + day * 0.1, 100_000, day)
        assert sel._days_since_rebalance < 5


# ===================================================================
# Constants validation
# ===================================================================


class TestConstants:
    def test_weights_sum_to_one(self):
        total = _W_TREND + _W_VOLATILITY + _W_EFFICIENCY + _W_LIQUIDITY
        assert abs(total - 1.0) < 1e-9

    def test_lookback_ge_sma_long(self):
        assert _LOOKBACK >= _SMA_LONG

    def test_top_n_positive(self):
        assert _DEFAULT_TOP_N > 0

    def test_vol_thresholds_ordered(self):
        assert _VOL_FLOOR < _VOL_SWEET_LO < _VOL_SWEET_HI < _VOL_CEILING


# ===================================================================
# Integration with PortfolioDecisionEngine
# ===================================================================


class TestIntegration:
    def test_portfolio_has_universe_selector(self):
        from bist_core.decision.portfolio_decision import PortfolioDecisionEngine

        engine = PortfolioDecisionEngine()
        assert hasattr(engine, "_universe")
        assert isinstance(engine._universe, UniverseSelector)
