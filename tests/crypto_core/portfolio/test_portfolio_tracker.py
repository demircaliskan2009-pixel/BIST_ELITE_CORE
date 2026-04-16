"""Comprehensive tests for Position Tracker and Portfolio State (Phase 5D).

Test scope:
  - Position model correctness
  - PositionTracker: open / increase / reduce / close / flip for both sides
  - Mark price updates → unrealized PnL changes
  - Malformed fill rejection (fail-closed)
  - Deterministic replay equivalence
  - Portfolio snapshot calculations
  - Guard integration (NT-R02, NT-R03, NT-R04, NT-R06)
  - Risk integration (portfolio field, DTL)
  - Orchestrator integration (tracker → pipeline)

PRD reference: §1.21 NT-R, §1.26 Margin.
"""

from __future__ import annotations

import pytest

from crypto_core.execution.models import ExecutionMode, OrderIntent
from crypto_core.guard.models import RiskGuardInput
from crypto_core.portfolio.fills import FillValidationError, SyntheticFill
from crypto_core.portfolio.models import PositionSide
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.risk.contracts import PortfolioRiskSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0 = 1_000_000_000_000  # fixed timestamp ns


def _fill(
    symbol: str = "BTCUSDT",
    exchange: str = "binance",
    intent: OrderIntent = OrderIntent.BUY,
    quantity: float = 1.0,
    fill_price: float = 50_000.0,
    leverage: float = 1.0,
    mode: ExecutionMode = ExecutionMode.PAPER,
    order_id: str = "order-001",
    timestamp_ns: int = _T0,
) -> SyntheticFill:
    return SyntheticFill(
        symbol=symbol,
        exchange=exchange,
        intent=intent,
        quantity=quantity,
        fill_price=fill_price,
        leverage=leverage,
        mode=mode,
        order_id=order_id,
        timestamp_ns=timestamp_ns,
    )


def _tracker(nav: float = 100_000.0) -> PositionTracker:
    return PositionTracker(initial_nav_usd=nav)


# ---------------------------------------------------------------------------
# SyntheticFill model
# ---------------------------------------------------------------------------


class TestSyntheticFill:
    def test_fill_is_frozen(self) -> None:
        f = _fill()
        with pytest.raises(AttributeError):
            f.quantity = 999.0  # type: ignore[misc]

    def test_fill_fields(self) -> None:
        f = _fill(symbol="ETHUSDT", quantity=2.5, fill_price=3000.0, intent=OrderIntent.SELL)
        assert f.symbol == "ETHUSDT"
        assert f.quantity == 2.5
        assert f.fill_price == 3000.0
        assert f.intent == OrderIntent.SELL


# ---------------------------------------------------------------------------
# PositionTracker — construction
# ---------------------------------------------------------------------------


class TestTrackerConstruction:
    def test_default_state(self) -> None:
        t = _tracker(nav=10_000.0)
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.nav_usd == pytest.approx(10_000.0)
        assert snap.cash_usd == pytest.approx(10_000.0)
        assert snap.active_position_count == 0
        assert snap.total_notional_usd == pytest.approx(0.0)

    def test_invalid_nav_raises(self) -> None:
        with pytest.raises(ValueError, match="initial_nav_usd"):
            PositionTracker(initial_nav_usd=0.0)
        with pytest.raises(ValueError, match="initial_nav_usd"):
            PositionTracker(initial_nav_usd=-1.0)


# ---------------------------------------------------------------------------
# Open position
# ---------------------------------------------------------------------------


class TestOpenLong:
    def test_open_long_creates_position(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(intent=OrderIntent.BUY, quantity=1.0, fill_price=50_000.0))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 1
        pos = snap.positions[0]
        assert pos.side == PositionSide.LONG
        assert pos.quantity == pytest.approx(1.0)
        assert pos.avg_entry_price == pytest.approx(50_000.0)
        assert pos.mark_price == pytest.approx(50_000.0)
        assert pos.unrealized_pnl == pytest.approx(0.0)

    def test_open_long_notional(self) -> None:
        t = _tracker(nav=100_000.0)
        t.apply_fill(_fill(quantity=2.0, fill_price=50_000.0))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.total_notional_usd == pytest.approx(100_000.0)
        assert snap.gross_exposure_pct == pytest.approx(100.0)


class TestOpenShort:
    def test_open_short_creates_position(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=0.5, fill_price=40_000.0))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 1
        pos = snap.positions[0]
        assert pos.side == PositionSide.SHORT
        assert pos.quantity == pytest.approx(0.5)
        assert pos.avg_entry_price == pytest.approx(40_000.0)
        assert pos.unrealized_pnl == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Increase positions
# ---------------------------------------------------------------------------


class TestIncreaseLong:
    def test_weighted_average_entry(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(quantity=1.0, fill_price=52_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        assert pos.quantity == pytest.approx(2.0)
        assert pos.avg_entry_price == pytest.approx(51_000.0)  # (50k + 52k) / 2

    def test_unequal_sizes(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=3.0, fill_price=30_000.0, order_id="o1"))
        t.apply_fill(_fill(quantity=1.0, fill_price=34_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        # (3*30k + 1*34k) / 4 = 31000
        assert pos.avg_entry_price == pytest.approx(31_000.0)
        assert pos.quantity == pytest.approx(4.0)


class TestIncreaseShort:
    def test_short_avg_entry(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=60_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=58_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        assert pos.side == PositionSide.SHORT
        assert pos.quantity == pytest.approx(2.0)
        assert pos.avg_entry_price == pytest.approx(59_000.0)


# ---------------------------------------------------------------------------
# Partial reduce
# ---------------------------------------------------------------------------


class TestPartialReduceLong:
    def test_partial_close_long(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=4.0, fill_price=50_000.0, order_id="o1"))
        # Reduce by 1 at 51000 → realize (51k - 50k) * 1 = +1000
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=51_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        assert pos.quantity == pytest.approx(3.0)
        assert pos.side == PositionSide.LONG
        assert pos.realized_pnl == pytest.approx(1_000.0)
        assert snap.daily_realized_pnl_usd == pytest.approx(1_000.0)


class TestPartialReduceShort:
    def test_partial_close_short(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=4.0, fill_price=60_000.0, order_id="o1"))
        # Reduce by 1 at 59000 → realize (60k - 59k) * 1 = +1000
        t.apply_fill(_fill(intent=OrderIntent.BUY, quantity=1.0, fill_price=59_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        assert pos.quantity == pytest.approx(3.0)
        assert pos.side == PositionSide.SHORT
        assert pos.realized_pnl == pytest.approx(1_000.0)


# ---------------------------------------------------------------------------
# Full close
# ---------------------------------------------------------------------------


class TestCloseLong:
    def test_close_long_exact(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=55_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 0
        assert snap.daily_realized_pnl_usd == pytest.approx(5_000.0)
        assert snap.total_notional_usd == pytest.approx(0.0)

    def test_close_long_at_loss(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=45_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.daily_realized_pnl_usd == pytest.approx(-5_000.0)


class TestCloseShort:
    def test_close_short_at_profit(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=60_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.BUY, quantity=1.0, fill_price=55_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 0
        assert snap.daily_realized_pnl_usd == pytest.approx(5_000.0)


# ---------------------------------------------------------------------------
# Flip
# ---------------------------------------------------------------------------


class TestFlipLongToShort:
    def test_flip_long_to_short(self) -> None:
        """Sell 2 units when only 1 is long → close 1 long, open 1 short."""
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        # sell 2: close 1 long + open 1 short
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=2.0, fill_price=52_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 1
        pos = snap.positions[0]
        assert pos.side == PositionSide.SHORT
        assert pos.quantity == pytest.approx(1.0)
        assert pos.avg_entry_price == pytest.approx(52_000.0)
        # Realized PnL from closing 1 long: (52k - 50k) * 1 = 2000
        assert snap.daily_realized_pnl_usd == pytest.approx(2_000.0)


class TestFlipShortToLong:
    def test_flip_short_to_long(self) -> None:
        """Buy 2 units when only 1 is short → close 1 short, open 1 long."""
        t = _tracker()
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=60_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.BUY, quantity=2.0, fill_price=58_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 1
        pos = snap.positions[0]
        assert pos.side == PositionSide.LONG
        assert pos.quantity == pytest.approx(1.0)
        assert pos.avg_entry_price == pytest.approx(58_000.0)
        assert snap.daily_realized_pnl_usd == pytest.approx(2_000.0)  # (60k - 58k) * 1


# ---------------------------------------------------------------------------
# Mark price update
# ---------------------------------------------------------------------------


class TestMarkPriceUpdate:
    def test_mark_update_changes_unrealized(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0))
        t.update_mark("BTCUSDT", "binance", 53_000.0)
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        assert pos.mark_price == pytest.approx(53_000.0)
        assert pos.unrealized_pnl == pytest.approx(3_000.0)

    def test_mark_update_short(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=60_000.0))
        t.update_mark("BTCUSDT", "binance", 58_000.0)
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        assert pos.unrealized_pnl == pytest.approx(2_000.0)

    def test_mark_update_unknown_symbol_ignored(self) -> None:
        """update_mark on unknown symbol must not raise."""
        t = _tracker()
        t.update_mark("XYZUSDT", "binance", 100.0)  # silent ignore

    def test_mark_update_zero_ignored(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0))
        t.update_mark("BTCUSDT", "binance", 0.0)  # invalid price, ignored
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.positions[0].mark_price == pytest.approx(50_000.0)


# ---------------------------------------------------------------------------
# Malformed fill rejection (fail-closed)
# ---------------------------------------------------------------------------


class TestFillValidation:
    def test_zero_quantity_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="quantity"):
            t.apply_fill(_fill(quantity=0.0))

    def test_negative_quantity_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="quantity"):
            t.apply_fill(_fill(quantity=-1.0))

    def test_zero_price_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="fill_price"):
            t.apply_fill(_fill(fill_price=0.0))

    def test_negative_price_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="fill_price"):
            t.apply_fill(_fill(fill_price=-1.0))

    def test_leverage_below_min_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="leverage"):
            t.apply_fill(_fill(leverage=0.5))

    def test_leverage_above_max_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="leverage"):
            t.apply_fill(_fill(leverage=4.0))

    def test_empty_symbol_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="symbol"):
            t.apply_fill(_fill(symbol=""))

    def test_empty_exchange_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="exchange"):
            t.apply_fill(_fill(exchange=""))

    def test_empty_order_id_rejected(self) -> None:
        t = _tracker()
        with pytest.raises(FillValidationError, match="order_id"):
            t.apply_fill(_fill(order_id=""))


# ---------------------------------------------------------------------------
# Deterministic replay equivalence
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Same fill stream applied twice to independent trackers → identical snapshots."""

    def _build_fills(self) -> list[SyntheticFill]:
        return [
            _fill(quantity=1.0, fill_price=50_000.0, order_id="f1"),
            _fill(quantity=0.5, fill_price=51_000.0, order_id="f2"),
            _fill(intent=OrderIntent.SELL, quantity=0.3, fill_price=52_000.0, order_id="f3"),
        ]

    def test_identical_state_after_replay(self) -> None:
        fills = self._build_fills()
        t1 = _tracker(nav=100_000.0)
        t2 = _tracker(nav=100_000.0)
        for f in fills:
            t1.apply_fill(f)
            t2.apply_fill(f)
        s1 = t1.portfolio_snapshot(snapshot_ns=_T0)
        s2 = t2.portfolio_snapshot(snapshot_ns=_T0)
        assert s1.daily_realized_pnl_usd == pytest.approx(s2.daily_realized_pnl_usd)
        assert s1.active_position_count == s2.active_position_count
        assert s1.total_notional_usd == pytest.approx(s2.total_notional_usd)
        if s1.positions and s2.positions:
            assert s1.positions[0].avg_entry_price == pytest.approx(s2.positions[0].avg_entry_price)
            assert s1.positions[0].quantity == pytest.approx(s2.positions[0].quantity)


# ---------------------------------------------------------------------------
# Portfolio snapshot calculations
# ---------------------------------------------------------------------------


class TestPortfolioSnapshot:
    def test_daily_pnl_pct(self) -> None:
        t = _tracker(nav=100_000.0)
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=52_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        # Realized +2000; effective NAV = 100k + 2k = 102k → 2000/102000 * 100 ≈ 1.96%
        expected_pct = 2_000.0 / snap.nav_usd * 100.0
        assert snap.daily_realized_pnl_pct == pytest.approx(expected_pct, rel=1e-6)

    def test_concentration_max_pct(self) -> None:
        t = _tracker(nav=100_000.0)
        t.apply_fill(_fill(symbol="BTCUSDT", quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(symbol="ETHUSDT", quantity=5.0, fill_price=3_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        # BTC: 50k / ~115k nav = ~43.5%; ETH: 15k / ~115k = ~13%
        # concentration_max should reflect the larger (BTC)
        assert snap.concentration_max_pct == pytest.approx(50_000.0 / snap.nav_usd * 100.0, abs=0.01)

    def test_net_exposure_pct_long_and_short(self) -> None:
        t = _tracker(nav=100_000.0)
        t.apply_fill(_fill(symbol="BTCUSDT", quantity=1.0, fill_price=10_000.0, order_id="o1"))
        t.apply_fill(_fill(symbol="ETHUSDT", intent=OrderIntent.SELL, quantity=2.0, fill_price=5_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        # long 10k, short 10k → net = 0
        assert snap.net_exposure_pct == pytest.approx(0.0, abs=0.01)

    def test_margin_unavailable_by_default(self) -> None:
        t = _tracker()
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.margin_used_pct is None

    def test_margin_available_when_set(self) -> None:
        t = PositionTracker(initial_nav_usd=100_000.0, margin_used_pct=45.0)
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.margin_used_pct == pytest.approx(45.0)

    def test_dtl_count_zero_without_liq_price(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.dtl_available_count == 0

    def test_open_risk_pct_available_with_nav(self) -> None:
        t = _tracker(nav=100_000.0)
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.open_risk_pct is not None
        assert snap.open_risk_pct == pytest.approx(50_000.0 / snap.nav_usd * 100.0, abs=0.01)


# ---------------------------------------------------------------------------
# Day reset
# ---------------------------------------------------------------------------


class TestDayReset:
    def test_reset_clears_realized_pnl(self) -> None:
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=55_000.0, order_id="o2"))
        snap_before = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap_before.daily_realized_pnl_usd == pytest.approx(5_000.0)
        t.reset_day_pnl()
        snap_after = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap_after.daily_realized_pnl_usd == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Guard integration — NT-R rules with real portfolio state
# ---------------------------------------------------------------------------


class TestGuardIntegrationNTR:
    """Prove that NT-R02–R04 and NT-R06 block using real tracker values."""

    def _make_ctx(self, risk_input: RiskGuardInput):
        from crypto_core.guard.models import NoTradeContext

        return NoTradeContext(
            symbol="BTCUSDT",
            exchange="binance",
            current_ns=_T0,
            book_last_update_ns=_T0,  # fresh book — avoids NT-D01 stale data
            book_has_snapshot=True,
            book_bid_count=10,
            book_ask_count=10,
            feed_connection_state="connected",
            feed_recovery_state="ready",
            system_state="NORMAL",
            risk=risk_input,
        )

    def _evaluate(self, risk_input: RiskGuardInput):
        from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard

        guard = NoTradeGuard(NoTradeConfig())
        return guard.evaluate(self._make_ctx(risk_input))

    # NT-R02: daily loss limit
    def test_nt_r02_daily_loss_blocks(self) -> None:
        """Tracker with -3% daily PnL → NT-R02 fires (limit 2%)."""
        t = PositionTracker(initial_nav_usd=100_000.0)
        # Realize -3000 = -3%
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=47_000.0, order_id="o2"))
        risk_input = t.to_risk_guard_input(kill_switch_level=0, snapshot_ns=_T0)
        decision = self._evaluate(risk_input)
        assert not decision.allowed
        assert "NT-R02" in str(decision.reason)

    def test_nt_r02_within_limit_passes(self) -> None:
        """Tracker with -1% daily PnL → NT-R02 does NOT fire."""
        t = PositionTracker(initial_nav_usd=100_000.0)
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(intent=OrderIntent.SELL, quantity=1.0, fill_price=49_000.0, order_id="o2"))
        risk_input = t.to_risk_guard_input(kill_switch_level=0, snapshot_ns=_T0)
        decision = self._evaluate(risk_input)
        # NT-R02 should not fire (loss is 1% < 2% limit)
        assert decision.reason != "NT-R02_daily_loss_limit"

    # NT-R03: open risk cap
    def test_nt_r03_open_risk_cap_blocks(self) -> None:
        """Position notional > 4% of NAV → NT-R03 fires."""
        # NAV=100k; position = 5 BTC @ 10k = 50k notional = 50% open risk → blocks (cap 4%)
        t = PositionTracker(initial_nav_usd=100_000.0)
        t.apply_fill(_fill(quantity=5.0, fill_price=10_000.0, order_id="o1"))
        risk_input = t.to_risk_guard_input(kill_switch_level=0, snapshot_ns=_T0)
        decision = self._evaluate(risk_input)
        assert not decision.allowed
        assert "NT-R03" in str(decision.reason)

    def test_nt_r03_within_cap_passes(self) -> None:
        """Small position well under 4% cap → NT-R03 does not fire."""
        t = PositionTracker(initial_nav_usd=100_000.0)
        # 0.001 BTC @ 50k = 50 USD = 0.05% of 100k NAV
        t.apply_fill(_fill(quantity=0.001, fill_price=50_000.0, order_id="o1"))
        risk_input = t.to_risk_guard_input(kill_switch_level=0, snapshot_ns=_T0)
        decision = self._evaluate(risk_input)
        assert decision.reason not in ("NT-R03_open_risk_cap", "NT-R02_daily_loss_limit")

    # NT-R04: position concentration
    def test_nt_r04_concentration_blocks(self) -> None:
        """max_single_position_pct=30% with open_risk_pct=None → NT-R04 fires.

        Note: if open_risk_pct were also available, NT-R03 would fire first (30 > 4).
        NT-R04 is isolated here by passing open_risk_pct=None so NT-R03 skips.
        """
        risk_input = RiskGuardInput(
            kill_switch_level=0,
            daily_pnl_pct=0.0,  # no daily loss
            open_risk_pct=None,  # NT-R03 skipped
            max_single_position_pct=30.0,  # 30% > 25% cap
        )
        decision = self._evaluate(risk_input)
        assert not decision.allowed
        assert "NT-R04" in str(decision.reason)

    # NT-R06: margin utilization
    def test_nt_r06_margin_blocks(self) -> None:
        """Margin utilization > 80% → NT-R06 fires."""
        t = PositionTracker(initial_nav_usd=100_000.0, margin_used_pct=85.0)
        risk_input = t.to_risk_guard_input(kill_switch_level=0, snapshot_ns=_T0)
        decision = self._evaluate(risk_input)
        assert not decision.allowed
        assert "NT-R06" in str(decision.reason)

    def test_nt_r06_margin_unavailable_skips(self) -> None:
        """margin_used_pct=None → NT-R06 skipped, not blocked."""
        t = PositionTracker(initial_nav_usd=100_000.0)  # no margin data
        risk_input = t.to_risk_guard_input(kill_switch_level=0, snapshot_ns=_T0)
        assert risk_input.margin_used_pct is None
        # With no other blocks, should pass
        decision = self._evaluate(risk_input)
        assert decision.reason not in ("NT-R06_margin_utilization",)


# ---------------------------------------------------------------------------
# Risk integration — PortfolioRiskSnapshot wiring
# ---------------------------------------------------------------------------


class TestRiskIntegration:
    def test_portfolio_risk_snapshot_non_none(self) -> None:
        """to_portfolio_risk_snapshot returns a valid PortfolioRiskSnapshot."""
        t = _tracker(nav=50_000.0)
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0))
        prs = t.to_portfolio_risk_snapshot(snapshot_ns=_T0)
        assert isinstance(prs, PortfolioRiskSnapshot)
        assert prs.active_position_count == 1
        assert prs.total_exposure_usd == pytest.approx(50_000.0)
        assert prs.max_leverage_in_use == pytest.approx(1.0)

    def test_portfolio_risk_snapshot_empty(self) -> None:
        t = _tracker(nav=100_000.0)
        prs = t.to_portfolio_risk_snapshot(snapshot_ns=_T0)
        assert prs.active_position_count == 0
        assert prs.total_exposure_usd == pytest.approx(0.0)
        assert prs.max_leverage_in_use == pytest.approx(0.0)

    def test_dtl_none_when_no_liq_price(self) -> None:
        """Position without liquidation price → dtl_pct is None."""
        t = _tracker()
        t.apply_fill(_fill(quantity=1.0, fill_price=50_000.0))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        pos = snap.positions[0]
        assert pos.dtl_pct is None
        assert pos.liquidation_price is None


# ---------------------------------------------------------------------------
# Multiple symbols
# ---------------------------------------------------------------------------


class TestMultipleSymbols:
    def test_two_symbols_tracked_independently(self) -> None:
        t = _tracker(nav=200_000.0)
        t.apply_fill(_fill(symbol="BTCUSDT", quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(symbol="ETHUSDT", quantity=10.0, fill_price=3_000.0, order_id="o2"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 2
        assert snap.total_notional_usd == pytest.approx(50_000.0 + 30_000.0)

    def test_close_one_symbol_leaves_other(self) -> None:
        t = _tracker(nav=200_000.0)
        t.apply_fill(_fill(symbol="BTCUSDT", quantity=1.0, fill_price=50_000.0, order_id="o1"))
        t.apply_fill(_fill(symbol="ETHUSDT", quantity=10.0, fill_price=3_000.0, order_id="o2"))
        t.apply_fill(_fill(symbol="BTCUSDT", intent=OrderIntent.SELL, quantity=1.0, fill_price=52_000.0, order_id="o3"))
        snap = t.portfolio_snapshot(snapshot_ns=_T0)
        assert snap.active_position_count == 1
        assert snap.positions[0].symbol == "ETHUSDT"


# ---------------------------------------------------------------------------
# Orchestrator integration (pipeline wiring)
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    """End-to-end: tracker → pipeline → guard/risk uses real portfolio state."""

    def _make_data(self, symbol: str = "BTCUSDT") -> object:
        from crypto_core.orchestrator.models import MarketDataInput

        return MarketDataInput(
            symbol=symbol,
            exchange="binance",
            timestamp_ns=_T0,
            book_last_update_ns=_T0,  # fresh — avoids NT-D01 stale data
            book_has_snapshot=True,
            book_bid_count=5,
            book_ask_count=5,
            feed_connection_state="connected",
            feed_recovery_state="ready",
        )

    def test_tracker_wired_in_orchestrator_no_block(self) -> None:
        """Pipeline with tracker but no positions passes normally."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator
        from crypto_core.risk.contracts import KS_LEVEL_NORMAL

        t = PositionTracker(initial_nav_usd=100_000.0)
        orch = PipelineOrchestrator(position_tracker=t)
        result = orch.process(self._make_data(), kill_switch_level=KS_LEVEL_NORMAL)
        # No positions → all portfolio NT-R fields should NOT trigger
        assert result.no_trade_decision.reason not in (
            "NT-R03_open_risk_cap",
            "NT-R04_position_concentration",
        )

    def test_tracker_triggers_nt_r03_in_pipeline(self) -> None:
        """Pipeline with tracker having large position → NT-R03 fires at guard."""
        from crypto_core.guard.no_trade_guard import NoTradeConfig
        from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
        from crypto_core.risk.contracts import KS_LEVEL_NORMAL

        t = PositionTracker(initial_nav_usd=100_000.0)
        # Open 5 BTC @ 10k = 50k notional = 50% open risk (cap 4%)
        t.apply_fill(_fill(symbol="BTCUSDT", quantity=5.0, fill_price=10_000.0, order_id="p1"))

        cfg = PipelineConfig(
            guard=NoTradeConfig(),
            emit_telemetry=False,
        )
        orch = PipelineOrchestrator(config=cfg, position_tracker=t)
        result = orch.process(self._make_data(), kill_switch_level=KS_LEVEL_NORMAL)

        assert result.block_stage == "guard"
        assert "NT-R03" in str(result.block_reason)

    def test_tracker_triggers_nt_r02_in_pipeline(self) -> None:
        """Pipeline with tracker having -3% daily PnL → NT-R02 fires."""
        from crypto_core.guard.no_trade_guard import NoTradeConfig
        from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
        from crypto_core.risk.contracts import KS_LEVEL_NORMAL

        t = PositionTracker(initial_nav_usd=100_000.0)
        # Realize -3000 loss
        t.apply_fill(_fill(symbol="BTCUSDT", quantity=1.0, fill_price=50_000.0, order_id="p1"))
        t.apply_fill(_fill(symbol="BTCUSDT", intent=OrderIntent.SELL, quantity=1.0, fill_price=47_000.0, order_id="p2"))

        cfg = PipelineConfig(guard=NoTradeConfig(), emit_telemetry=False)
        orch = PipelineOrchestrator(config=cfg, position_tracker=t)
        result = orch.process(self._make_data(), kill_switch_level=KS_LEVEL_NORMAL)

        assert result.block_stage == "guard"
        assert "NT-R02" in str(result.block_reason)

    def test_deterministic_replay_pipeline(self) -> None:
        """Replay identical synthetic execution stream → identical results."""
        from crypto_core.guard.no_trade_guard import NoTradeConfig
        from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator

        fills = [
            _fill(quantity=0.001, fill_price=50_000.0, order_id="r1"),
        ]

        def run_pipeline() -> object:
            t = PositionTracker(initial_nav_usd=100_000.0)
            for f in fills:
                t.apply_fill(f)
            cfg = PipelineConfig(guard=NoTradeConfig(), emit_telemetry=False)
            orch = PipelineOrchestrator(config=cfg, position_tracker=t)
            return orch.process(self._make_data())

        r1 = run_pipeline()
        r2 = run_pipeline()
        assert r1.block_stage == r2.block_stage
        assert r1.block_reason == r2.block_reason
        assert r1.no_trade_decision.allowed == r2.no_trade_decision.allowed
