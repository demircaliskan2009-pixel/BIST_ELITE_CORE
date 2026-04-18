"""Tests for TCA (Transaction Cost Analysis) module — Phase 9A.

Covers:
  - TCA enums (FillRole, TCAStatus, RegimeTag)
  - MarkoutObservation construction and availability
  - TCARecord frozen invariants
  - compute_shortfall_bps (BUY/SELL, None inputs, zero ref)
  - compute_markout_bps (BUY/SELL, None inputs)
  - build_tca_record full lifecycle (COMPLETE/PARTIAL/PENDING/UNAVAILABLE)
  - Slippage surprise computation
  - Fill ratio computation
  - Markout curve population
  - aggregate_tca_records (empty, single, multiple, status counts)
  - Serialization round-trip (tca_record_to_dict / tca_record_from_dict)
  - Malformed deserialization → ValueError (fail-closed)
"""

from __future__ import annotations

import pytest

from crypto_core.execution.tca import (
    DEFAULT_MARKOUT_HORIZONS,
    FillRole,
    MarkoutObservation,
    RegimeTag,
    TCARecord,
    TCAStatus,
    aggregate_tca_records,
    build_tca_record,
    compute_markout_bps,
    compute_shortfall_bps,
    tca_record_from_dict,
    tca_record_to_dict,
)

# ===================================================================
# Enum tests
# ===================================================================


class TestFillRole:
    def test_values(self) -> None:
        assert FillRole.MAKER.value == "maker"
        assert FillRole.TAKER.value == "taker"
        assert FillRole.UNKNOWN.value == "unknown"


class TestTCAStatus:
    def test_values(self) -> None:
        assert TCAStatus.COMPLETE.value == "complete"
        assert TCAStatus.PARTIAL.value == "partial"
        assert TCAStatus.PENDING.value == "pending"
        assert TCAStatus.UNAVAILABLE.value == "unavailable"


class TestRegimeTag:
    def test_values(self) -> None:
        assert RegimeTag.NORMAL.value == "normal"
        assert RegimeTag.STRESS.value == "stress"
        assert RegimeTag.EVENT.value == "event"


# ===================================================================
# MarkoutObservation tests
# ===================================================================


class TestMarkoutObservation:
    def test_available(self) -> None:
        m = MarkoutObservation(horizon_seconds=1, mid_price_at_horizon=100.5, markout_bps=5.0)
        assert m.is_available is True

    def test_unavailable_none_mid(self) -> None:
        m = MarkoutObservation(horizon_seconds=5, mid_price_at_horizon=None, markout_bps=None)
        assert m.is_available is False

    def test_frozen(self) -> None:
        m = MarkoutObservation(horizon_seconds=1, mid_price_at_horizon=100.0, markout_bps=3.0)
        with pytest.raises(AttributeError):
            m.horizon_seconds = 2  # type: ignore[misc]


# ===================================================================
# TCARecord tests
# ===================================================================


class TestTCARecordFrozen:
    def test_frozen(self) -> None:
        r = TCARecord(
            order_id="o1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            status=TCAStatus.PENDING,
        )
        with pytest.raises(AttributeError):
            r.order_id = "x"  # type: ignore[misc]


class TestDefaultMarkoutHorizons:
    def test_defaults(self) -> None:
        assert DEFAULT_MARKOUT_HORIZONS == (1, 5, 30, 300)


# ===================================================================
# compute_shortfall_bps tests
# ===================================================================


class TestComputeShortfallBps:
    def test_buy_overpay(self) -> None:
        # BUY: exec > ref → positive shortfall (overpaid)
        result = compute_shortfall_bps(100.0, 101.0, is_buy=True)
        assert result is not None
        assert abs(result - 100.0) < 0.01  # 1% = 100 bps

    def test_buy_underpay(self) -> None:
        # BUY: exec < ref → negative shortfall (got a deal)
        result = compute_shortfall_bps(100.0, 99.0, is_buy=True)
        assert result is not None
        assert result < 0.0

    def test_sell_undersell(self) -> None:
        # SELL: exec < ref → positive shortfall (undersold)
        result = compute_shortfall_bps(100.0, 99.0, is_buy=False)
        assert result is not None
        assert result > 0.0

    def test_sell_oversell(self) -> None:
        # SELL: exec > ref → negative shortfall (got better price)
        result = compute_shortfall_bps(100.0, 101.0, is_buy=False)
        assert result is not None
        assert result < 0.0

    def test_none_reference(self) -> None:
        assert compute_shortfall_bps(None, 100.0, is_buy=True) is None

    def test_none_execution(self) -> None:
        assert compute_shortfall_bps(100.0, None, is_buy=True) is None

    def test_zero_reference(self) -> None:
        assert compute_shortfall_bps(0.0, 100.0, is_buy=True) is None

    def test_negative_reference(self) -> None:
        assert compute_shortfall_bps(-1.0, 100.0, is_buy=True) is None


# ===================================================================
# compute_markout_bps tests
# ===================================================================


class TestComputeMarkoutBps:
    def test_buy_favorable(self) -> None:
        # BUY: mid went up after fill → positive markout
        result = compute_markout_bps(100.0, 101.0, is_buy=True)
        assert result is not None
        assert result > 0.0

    def test_buy_adverse(self) -> None:
        # BUY: mid went down after fill → negative markout
        result = compute_markout_bps(100.0, 99.0, is_buy=True)
        assert result is not None
        assert result < 0.0

    def test_sell_favorable(self) -> None:
        # SELL: mid went down after fill → positive markout
        result = compute_markout_bps(100.0, 99.0, is_buy=False)
        assert result is not None
        assert result > 0.0

    def test_sell_adverse(self) -> None:
        # SELL: mid went up after fill → negative markout
        result = compute_markout_bps(100.0, 101.0, is_buy=False)
        assert result is not None
        assert result < 0.0

    def test_none_mid(self) -> None:
        assert compute_markout_bps(100.0, None, is_buy=True) is None

    def test_zero_fill(self) -> None:
        assert compute_markout_bps(0.0, 100.0, is_buy=True) is None


# ===================================================================
# build_tca_record tests
# ===================================================================


class TestBuildTCARecord:
    def test_complete_with_all_markouts(self) -> None:
        r = build_tca_record(
            order_id="o1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            decision_price=100.0,
            arrival_price=100.05,
            execution_price=100.10,
            expected_slippage_bps=5.0,
            spread_cost_bps=2.5,
            impact_cost_bps=2.0,
            fee_cost_bps=5.0,
            funding_cost_bps=1.0,
            filled_quantity=0.1,
            requested_quantity=0.1,
            fill_role=FillRole.TAKER,
            markout_mids={1: 100.12, 5: 100.15, 30: 100.20, 300: 100.50},
            regime_tag=RegimeTag.NORMAL,
        )
        assert r.status == TCAStatus.COMPLETE
        assert r.implementation_shortfall_bps is not None
        assert r.implementation_shortfall_bps > 0.0  # bought higher
        assert r.arrival_shortfall_bps is not None
        assert r.fill_ratio == 1.0
        assert len(r.markouts) == 4
        assert all(m.is_available for m in r.markouts)
        # All markouts should be positive (price went up after BUY)
        for m in r.markouts:
            assert m.markout_bps is not None
            assert m.markout_bps > 0.0

    def test_pending_no_markouts(self) -> None:
        r = build_tca_record(
            order_id="o2",
            symbol="ETHUSDT",
            exchange="bybit",
            intent="sell",
            timestamp_ns=2000,
            decision_price=3000.0,
            arrival_price=3000.0,
            execution_price=2999.0,
        )
        assert r.status == TCAStatus.PENDING
        assert len(r.markouts) == 0

    def test_unavailable_no_prices(self) -> None:
        r = build_tca_record(
            order_id="o3",
            symbol="SOLUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=3000,
        )
        assert r.status == TCAStatus.UNAVAILABLE
        assert r.implementation_shortfall_bps is None
        assert r.arrival_shortfall_bps is None

    def test_partial_markouts(self) -> None:
        r = build_tca_record(
            order_id="o4",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=4000,
            decision_price=50000.0,
            arrival_price=50000.0,
            execution_price=50010.0,
            markout_mids={1: 50015.0, 5: None, 30: 50020.0, 300: None},
        )
        assert r.status == TCAStatus.PARTIAL
        assert len(r.markouts) == 4
        available = [m for m in r.markouts if m.is_available]
        assert len(available) == 2

    def test_slippage_surprise(self) -> None:
        r = build_tca_record(
            order_id="o5",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=5000,
            decision_price=100.0,
            arrival_price=100.0,
            execution_price=100.10,
            expected_slippage_bps=5.0,
        )
        # realized = arrival shortfall, surprise = realized - expected
        assert r.realized_slippage_bps is not None
        assert r.slippage_surprise_bps is not None
        assert abs(r.slippage_surprise_bps - (r.realized_slippage_bps - 5.0)) < 0.001

    def test_fill_ratio_partial(self) -> None:
        r = build_tca_record(
            order_id="o6",
            symbol="ETHUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=6000,
            decision_price=3000.0,
            arrival_price=3000.0,
            execution_price=3001.0,
            filled_quantity=0.05,
            requested_quantity=0.10,
        )
        assert r.fill_ratio is not None
        assert abs(r.fill_ratio - 0.5) < 0.001

    def test_fill_ratio_capped_at_one(self) -> None:
        r = build_tca_record(
            order_id="o7",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=7000,
            decision_price=100.0,
            arrival_price=100.0,
            execution_price=100.0,
            filled_quantity=0.15,
            requested_quantity=0.10,
        )
        assert r.fill_ratio == 1.0


# ===================================================================
# aggregate_tca_records tests
# ===================================================================


class TestAggregateTCA:
    def test_empty(self) -> None:
        agg = aggregate_tca_records([], "test")
        assert agg.record_count == 0
        assert agg.avg_implementation_shortfall_bps is None

    def test_single_record(self) -> None:
        r = build_tca_record(
            order_id="a1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            decision_price=100.0,
            arrival_price=100.0,
            execution_price=100.10,
            fee_cost_bps=5.0,
            fill_role=FillRole.TAKER,
            markout_mids={1: 100.15, 5: 100.20},
        )
        agg = aggregate_tca_records([r], "binance")
        assert agg.record_count == 1
        assert agg.avg_implementation_shortfall_bps is not None
        assert agg.taker_count == 1
        assert agg.maker_count == 0
        assert 1 in agg.avg_markout_by_horizon
        assert 5 in agg.avg_markout_by_horizon

    def test_multiple_records_status_counts(self) -> None:
        r1 = build_tca_record(
            order_id="m1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            decision_price=100.0,
            arrival_price=100.0,
            execution_price=100.1,
            markout_mids={1: 100.2},
        )
        r2 = build_tca_record(
            order_id="m2",
            symbol="BTCUSDT",
            exchange="binance",
            intent="sell",
            timestamp_ns=2000,
        )
        agg = aggregate_tca_records([r1, r2], "binance")
        assert agg.record_count == 2
        assert agg.complete_count == 1
        assert agg.unavailable_count == 1


# ===================================================================
# Serialization tests
# ===================================================================


class TestTCASerialization:
    def test_round_trip(self) -> None:
        r = build_tca_record(
            order_id="s1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=1000,
            decision_price=50000.0,
            arrival_price=50000.0,
            execution_price=50010.0,
            fill_role=FillRole.MAKER,
            regime_tag=RegimeTag.HIGH_VOL,
            markout_mids={1: 50015.0, 5: 50020.0},
        )
        d = tca_record_to_dict(r)
        assert isinstance(d, dict)
        assert d["order_id"] == "s1"
        assert d["fill_role"] == "maker"
        assert d["regime_tag"] == "high_vol"

        restored = tca_record_from_dict(d)
        assert restored.order_id == r.order_id
        assert restored.symbol == r.symbol
        assert restored.status == r.status
        assert restored.fill_role == r.fill_role
        assert restored.regime_tag == r.regime_tag
        assert len(restored.markouts) == len(r.markouts)

    def test_malformed_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed TCA record"):
            tca_record_from_dict({"bad": "data"})
