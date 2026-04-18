"""Tests for attribution decomposition primitives — Phase 9A.

Covers:
  - AttributionStatus enum values
  - TradeAttribution frozen invariant
  - build_trade_attribution COMPLETE status (all components, residual ≈ 0)
  - build_trade_attribution PARTIAL status (some components None)
  - build_trade_attribution DRIFT status (residual exceeds tolerance)
  - build_trade_attribution UNAVAILABLE status (no total_pnl_bps)
  - Residual calculation correctness
  - aggregate_attributions (empty, single, multiple, status counts)
  - Serialization round-trip (attribution_to_dict / attribution_from_dict)
  - Malformed deserialization → ValueError (fail-closed)
"""

from __future__ import annotations

import pytest

from crypto_core.execution.attribution import (
    DRIFT_TOLERANCE_BPS,
    AttributionStatus,
    TradeAttribution,
    aggregate_attributions,
    attribution_from_dict,
    attribution_to_dict,
    build_trade_attribution,
)

# ===================================================================
# Enum tests
# ===================================================================


class TestAttributionStatus:
    def test_values(self) -> None:
        assert AttributionStatus.COMPLETE.value == "complete"
        assert AttributionStatus.PARTIAL.value == "partial"
        assert AttributionStatus.DRIFT.value == "drift"
        assert AttributionStatus.UNAVAILABLE.value == "unavailable"


# ===================================================================
# TradeAttribution frozen test
# ===================================================================


class TestTradeAttributionFrozen:
    def test_frozen(self) -> None:
        a = TradeAttribution(
            order_id="o1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            status=AttributionStatus.COMPLETE,
        )
        with pytest.raises(AttributeError):
            a.order_id = "x"  # type: ignore[misc]


# ===================================================================
# build_trade_attribution tests
# ===================================================================


class TestBuildTradeAttribution:
    def test_complete_zero_residual(self) -> None:
        # total = sum of all components → residual ≈ 0
        a = build_trade_attribution(
            order_id="c1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            total_pnl_bps=10.0,
            forecast_alpha_bps=15.0,
            fees_bps=-3.0,
            funding_bps=-1.0,
            slippage_bps=-2.0,
            markout_bps=1.0,
            venue_contribution_bps=0.5,
            execution_mode_bps=-0.5,
        )
        assert a.status == AttributionStatus.COMPLETE
        assert a.residual_bps is not None
        assert abs(a.residual_bps) < DRIFT_TOLERANCE_BPS + 0.001

    def test_partial_missing_components(self) -> None:
        a = build_trade_attribution(
            order_id="p1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=2000,
            total_pnl_bps=10.0,
            forecast_alpha_bps=12.0,
            fees_bps=-3.0,
            # funding, slippage, markout, venue, mode all None
        )
        assert a.status == AttributionStatus.PARTIAL
        assert a.residual_bps is not None
        # residual = 10 - (12 + (-3)) = 10 - 9 = 1
        assert abs(a.residual_bps - 1.0) < 0.001

    def test_drift_large_residual(self) -> None:
        a = build_trade_attribution(
            order_id="d1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="sell",
            timestamp_ns=3000,
            total_pnl_bps=10.0,
            forecast_alpha_bps=5.0,
            fees_bps=-1.0,
            funding_bps=0.0,
            slippage_bps=-1.0,
            markout_bps=0.0,
            venue_contribution_bps=0.0,
            execution_mode_bps=0.0,
            # sum = 5-1+0-1+0+0+0 = 3; residual = 10-3 = 7
        )
        assert a.status == AttributionStatus.DRIFT
        assert a.residual_bps is not None
        assert abs(a.residual_bps - 7.0) < 0.001

    def test_unavailable_no_total(self) -> None:
        a = build_trade_attribution(
            order_id="u1",
            symbol="ETHUSDT",
            exchange="bybit",
            intent="buy",
            timestamp_ns=4000,
            # total_pnl_bps = None (default)
            forecast_alpha_bps=5.0,
        )
        assert a.status == AttributionStatus.UNAVAILABLE
        assert a.total_pnl_bps is None
        assert a.residual_bps is None
        assert a.forecast_alpha_bps == 5.0

    def test_regime_and_event_tags(self) -> None:
        a = build_trade_attribution(
            order_id="t1",
            symbol="SOLUSDT",
            exchange="binance",
            intent="sell",
            timestamp_ns=5000,
            total_pnl_bps=2.0,
            regime_tag="stress",
            event_tag="FOMC",
            execution_mode="taker",
            hold_duration_s=120.0,
        )
        assert a.regime_tag == "stress"
        assert a.event_tag == "FOMC"
        assert a.execution_mode == "taker"
        assert a.hold_duration_s == 120.0

    def test_evidence_populated(self) -> None:
        a = build_trade_attribution(
            order_id="e1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=6000,
            total_pnl_bps=5.0,
            forecast_alpha_bps=5.0,
            fees_bps=0.0,
            funding_bps=0.0,
            slippage_bps=0.0,
            markout_bps=0.0,
            venue_contribution_bps=0.0,
            execution_mode_bps=0.0,
        )
        assert "builder" in a.evidence
        assert "component_sum" in a.evidence
        assert "residual" in a.evidence


# ===================================================================
# aggregate_attributions tests
# ===================================================================


class TestAggregateAttributions:
    def test_empty(self) -> None:
        agg = aggregate_attributions([], "test")
        assert agg.record_count == 0
        assert agg.avg_total_pnl_bps is None

    def test_single_record(self) -> None:
        a = build_trade_attribution(
            order_id="a1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            total_pnl_bps=10.0,
            forecast_alpha_bps=12.0,
            fees_bps=-2.0,
            funding_bps=0.0,
            slippage_bps=0.0,
            markout_bps=0.0,
            venue_contribution_bps=0.0,
            execution_mode_bps=0.0,
        )
        agg = aggregate_attributions([a], "binance")
        assert agg.record_count == 1
        assert agg.avg_total_pnl_bps == 10.0

    def test_multiple_records_status_counts(self) -> None:
        a1 = build_trade_attribution(
            order_id="m1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            total_pnl_bps=10.0,
            forecast_alpha_bps=10.0,
            fees_bps=0.0,
            funding_bps=0.0,
            slippage_bps=0.0,
            markout_bps=0.0,
            venue_contribution_bps=0.0,
            execution_mode_bps=0.0,
        )
        a2 = build_trade_attribution(
            order_id="m2",
            symbol="BTCUSDT",
            exchange="binance",
            intent="sell",
            timestamp_ns=2000,
            # no total → UNAVAILABLE
        )
        agg = aggregate_attributions([a1, a2], "binance")
        assert agg.record_count == 2
        assert agg.complete_count == 1
        assert agg.unavailable_count == 1

    def test_avg_calculation(self) -> None:
        records = [
            build_trade_attribution(
                order_id=f"avg{i}",
                symbol="BTCUSDT",
                exchange="binance",
                intent="buy",
                timestamp_ns=i * 1000,
                total_pnl_bps=float(i * 5),
                forecast_alpha_bps=float(i * 6),
                fees_bps=-1.0,
                funding_bps=0.0,
                slippage_bps=0.0,
                markout_bps=0.0,
                venue_contribution_bps=0.0,
                execution_mode_bps=0.0,
            )
            for i in range(1, 4)
        ]
        agg = aggregate_attributions(records, "test")
        # avg total = (5 + 10 + 15) / 3 = 10
        assert agg.avg_total_pnl_bps is not None
        assert abs(agg.avg_total_pnl_bps - 10.0) < 0.01
        # avg fees = -1.0 (all same)
        assert agg.avg_fees_bps is not None
        assert abs(agg.avg_fees_bps - (-1.0)) < 0.01


# ===================================================================
# Serialization tests
# ===================================================================


class TestAttributionSerialization:
    def test_round_trip(self) -> None:
        a = build_trade_attribution(
            order_id="s1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            total_pnl_bps=8.0,
            forecast_alpha_bps=10.0,
            fees_bps=-2.0,
            funding_bps=0.0,
            slippage_bps=0.0,
            markout_bps=0.0,
            venue_contribution_bps=0.0,
            execution_mode_bps=0.0,
            regime_tag="normal",
            event_tag="ETF_decision",
            execution_mode="taker",
        )
        d = attribution_to_dict(a)
        assert isinstance(d, dict)
        assert d["order_id"] == "s1"
        assert d["regime_tag"] == "normal"
        assert d["event_tag"] == "ETF_decision"

        restored = attribution_from_dict(d)
        assert restored.order_id == a.order_id
        assert restored.status == a.status
        assert restored.total_pnl_bps == a.total_pnl_bps
        assert restored.regime_tag == a.regime_tag

    def test_malformed_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed attribution"):
            attribution_from_dict({"bad": "data"})
