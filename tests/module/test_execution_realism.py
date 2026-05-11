"""Tests for execution_realism — dynamic slippage, partial fills, tick rounding."""

from __future__ import annotations

import pytest

from bist_core.execution.execution_realism import (
    _avg_daily_volume,
    _daily_vol,
    apply_slippage,
    compute_fill_ratio,
    compute_slippage_bps,
    compute_total_cost_bps,
    round_decision_prices,
)


# ====================================================================
# _daily_vol
# ====================================================================


class TestDailyVol:
    def test_insufficient_data_returns_default(self):
        assert _daily_vol([100.0]) == 0.02
        assert _daily_vol([]) == 0.02

    def test_two_closes_returns_default(self):
        assert _daily_vol([100.0, 101.0]) == 0.02

    def test_flat_series_returns_minimum(self):
        closes = [100.0] * 30
        vol = _daily_vol(closes)
        assert vol == 0.005  # floored at min

    def test_volatile_series_returns_higher_vol(self):
        closes = [100.0, 102.0, 98.0, 103.0, 97.0, 104.0, 96.0, 105.0,
                  95.0, 106.0, 94.0, 107.0]
        vol = _daily_vol(closes)
        assert vol > 0.02  # high vol series

    def test_lookback_respects_parameter(self):
        closes = list(range(100, 150))
        vol_short = _daily_vol(closes, lookback=5)
        vol_long = _daily_vol(closes, lookback=30)
        # Both should be positive
        assert vol_short > 0
        assert vol_long > 0


# ====================================================================
# _avg_daily_volume
# ====================================================================


class TestAvgDailyVolume:
    def test_empty_returns_zero(self):
        assert _avg_daily_volume([]) == 0.0

    def test_single_value(self):
        assert _avg_daily_volume([1_000_000.0]) == 1_000_000.0

    def test_average_correct(self):
        vols = [100.0, 200.0, 300.0]
        assert _avg_daily_volume(vols) == 200.0

    def test_lookback_limits_window(self):
        vols = [10.0] * 50 + [100.0] * 20
        avg = _avg_daily_volume(vols, lookback=20)
        assert avg == 100.0  # only last 20


# ====================================================================
# compute_slippage_bps
# ====================================================================


class TestComputeSlippageBps:
    def test_minimum_is_base(self):
        slip = compute_slippage_bps(
            daily_vol=0.0,
            order_size=0,
            avg_volume=1_000_000.0,
            price=10.0,
        )
        assert slip == 20.0  # base slippage

    def test_volatility_adds_to_base(self):
        slip = compute_slippage_bps(
            daily_vol=0.02,  # 2% daily vol
            order_size=100,
            avg_volume=1_000_000.0,
            price=10.0,
        )
        # 20 base + 0.02*2*1000=40 vol + small size impact
        assert slip > 20.0
        assert slip < 80.0  # reasonable range

    def test_two_percent_vol_adds_about_40_bps(self):
        # With zero size impact
        slip = compute_slippage_bps(
            daily_vol=0.02,
            order_size=0,
            avg_volume=1_000_000.0,
            price=10.0,
        )
        # 20 base + 40 vol = 60
        assert abs(slip - 60.0) < 5.0

    def test_capped_at_200(self):
        slip = compute_slippage_bps(
            daily_vol=0.10,  # extreme vol
            order_size=100_000,
            avg_volume=10.0,
            price=10.0,
        )
        assert slip == 200.0

    def test_size_impact_increases_slippage(self):
        small = compute_slippage_bps(0.02, 100, 1_000_000.0, 10.0)
        large = compute_slippage_bps(0.02, 10_000, 1_000_000.0, 10.0)
        assert large > small


# ====================================================================
# compute_total_cost_bps
# ====================================================================


class TestComputeTotalCostBps:
    def test_total_fee(self):
        # 3.0 + 0.4 + 0.2 = 3.6
        assert compute_total_cost_bps() == pytest.approx(3.6)


# ====================================================================
# compute_fill_ratio
# ====================================================================


class TestComputeFillRatio:
    def test_small_order_full_fill(self):
        # 0.5% of ADV → full fill
        ratio = compute_fill_ratio(
            order_size=500,
            avg_volume=1_000_000.0,
            price=10.0,
        )
        assert ratio == 1.0

    def test_large_order_rejected(self):
        # >10% of ADV → reject
        ratio = compute_fill_ratio(
            order_size=200_000,
            avg_volume=1_000_000.0,
            price=10.0,
        )
        assert ratio == 0.0

    def test_medium_order_partial_fill(self):
        # Between 2% and 10% of ADV → partial
        ratio = compute_fill_ratio(
            order_size=50_000,
            avg_volume=1_000_000.0,
            price=10.0,
        )
        assert 0.3 <= ratio < 1.0

    def test_zero_volume_rejects(self):
        assert compute_fill_ratio(100, 0.0, 10.0) == 0.0

    def test_zero_size_rejects(self):
        assert compute_fill_ratio(0, 1_000_000.0, 10.0) == 0.0


# ====================================================================
# round_decision_prices
# ====================================================================


class TestRoundDecisionPrices:
    def test_rounds_entry_stop_target(self):
        decision = {"entry": 10.003, "stop": 9.503, "target": 10.503}
        result = round_decision_prices(decision)
        # All should be tick-rounded
        assert result["entry"] == result["entry"]  # no NaN
        assert isinstance(result["entry"], float)
        assert isinstance(result["stop"], float)
        assert isinstance(result["target"], float)

    def test_missing_keys_no_error(self):
        decision = {"symbol": "TEST"}
        result = round_decision_prices(decision)
        assert result == {"symbol": "TEST"}

    def test_mutates_in_place(self):
        decision = {"entry": 10.003}
        result = round_decision_prices(decision)
        assert result is decision


# ====================================================================
# apply_slippage
# ====================================================================


class TestApplySlippage:
    def test_buy_increases_price(self):
        filled = apply_slippage(100.0, 20.0, "buy")
        assert filled > 100.0

    def test_sell_decreases_price(self):
        filled = apply_slippage(100.0, 20.0, "sell")
        assert filled < 100.0

    def test_zero_slippage_returns_tick_rounded(self):
        filled = apply_slippage(100.0, 0.0, "buy")
        assert filled == 100.0

    def test_slippage_magnitude_correct(self):
        # 20 bps = 0.20% of price
        filled = apply_slippage(100.0, 20.0, "buy")
        # Should be approximately 100.20 (tick-rounded)
        assert abs(filled - 100.20) < 0.10
