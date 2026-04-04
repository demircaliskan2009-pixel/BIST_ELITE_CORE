"""Paper trading engine unit tests — order lifecycle, PnL, slippage, deterministic replay."""

from __future__ import annotations

import pytest

from bist_core.execution.paper_engine import (
    OrderSide,
    OrderStatus,
    OrderStateMachine,
    OrderType,
    PaperExecutionEngine,
    PaperTrade,
    PaperTradeJournal,
    SlippageModel,
)


# ── OrderStateMachine ─────────────────────────────────────────────────────

class TestOrderStateMachine:
    def test_initial_state_is_pending(self) -> None:
        sm = OrderStateMachine()
        assert sm.status == OrderStatus.PENDING

    def test_valid_transition_pending_to_open(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        assert sm.status == OrderStatus.OPEN

    def test_valid_transition_open_to_filled(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        sm.transition(OrderStatus.FILLED)
        assert sm.status == OrderStatus.FILLED

    def test_valid_transition_open_to_partially_filled(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        sm.transition(OrderStatus.PARTIALLY_FILLED)
        assert sm.status == OrderStatus.PARTIALLY_FILLED

    def test_valid_transition_partially_filled_to_filled(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        sm.transition(OrderStatus.PARTIALLY_FILLED)
        sm.transition(OrderStatus.FILLED)
        assert sm.status == OrderStatus.FILLED

    def test_valid_transition_open_to_cancelled(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        sm.transition(OrderStatus.CANCELLED)
        assert sm.status == OrderStatus.CANCELLED

    def test_valid_transition_open_to_expired(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        sm.transition(OrderStatus.EXPIRED)
        assert sm.status == OrderStatus.EXPIRED

    def test_invalid_transition_filled_to_open(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        sm.transition(OrderStatus.FILLED)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(OrderStatus.OPEN)

    def test_invalid_transition_cancelled_to_open(self) -> None:
        sm = OrderStateMachine()
        sm.transition(OrderStatus.OPEN)
        sm.transition(OrderStatus.CANCELLED)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(OrderStatus.OPEN)

    def test_invalid_transition_pending_to_filled(self) -> None:
        sm = OrderStateMachine()
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(OrderStatus.FILLED)


# ── SlippageModel ─────────────────────────────────────────────────────────

class TestSlippageModel:
    def test_buy_slippage_increases_price(self) -> None:
        model = SlippageModel(base_slippage_bps=10.0)
        result = model.compute(100.0, OrderSide.BUY)
        assert result > 100.0
        assert result == pytest.approx(100.1, abs=0.001)

    def test_sell_slippage_decreases_price(self) -> None:
        model = SlippageModel(base_slippage_bps=10.0)
        result = model.compute(100.0, OrderSide.SELL)
        assert result < 100.0
        assert result == pytest.approx(99.9, abs=0.001)

    def test_zero_slippage(self) -> None:
        model = SlippageModel(base_slippage_bps=0.0)
        assert model.compute(50.0, OrderSide.BUY) == 50.0
        assert model.compute(50.0, OrderSide.SELL) == 50.0

    def test_adjustments_add_up(self) -> None:
        model = SlippageModel(
            base_slippage_bps=5.0,
            volatility_adjustment=3.0,
            liquidity_adjustment=2.0,
        )
        result = model.compute(100.0, OrderSide.BUY)
        assert result == pytest.approx(100.1, abs=0.001)


# ── PaperTrade ────────────────────────────────────────────────────────────

class TestPaperTrade:
    def test_close_computes_pnl(self) -> None:
        trade = PaperTrade(
            trade_id="t1",
            symbol="ASELS",
            entry_price=100.0,
            stop_price=95.0,
            target_price=110.0,
            position_size=10,
            entry_time="2026-01-01",
        )
        trade.close(110.0, "2026-01-02", fees=5.0)
        assert trade.status == "CLOSED"
        assert trade.pnl == pytest.approx(95.0, abs=0.01)

    def test_r_multiple_positive(self) -> None:
        trade = PaperTrade(
            trade_id="t2",
            symbol="THYAO",
            entry_price=100.0,
            stop_price=95.0,
            target_price=115.0,
            position_size=10,
            entry_time="2026-01-01",
        )
        trade.close(110.0, "2026-01-02", fees=0.0)
        assert trade.r_multiple is not None
        assert trade.r_multiple == pytest.approx(2.0, abs=0.01)

    def test_r_multiple_negative(self) -> None:
        trade = PaperTrade(
            trade_id="t3",
            symbol="GARAN",
            entry_price=100.0,
            stop_price=95.0,
            target_price=110.0,
            position_size=10,
            entry_time="2026-01-01",
        )
        trade.close(95.0, "2026-01-02", fees=0.0)
        assert trade.r_multiple is not None
        assert trade.r_multiple == pytest.approx(-1.0, abs=0.01)

    def test_r_multiple_open_is_none(self) -> None:
        trade = PaperTrade(
            trade_id="t4",
            symbol="AKBNK",
            entry_price=50.0,
            stop_price=48.0,
            target_price=55.0,
            position_size=20,
            entry_time="2026-01-01",
        )
        assert trade.r_multiple is None

    def test_to_dict(self) -> None:
        trade = PaperTrade(
            trade_id="t5",
            symbol="EREGL",
            entry_price=30.0,
            stop_price=28.0,
            target_price=35.0,
            position_size=100,
            entry_time="2026-01-01",
        )
        d = trade.to_dict()
        assert d["trade_id"] == "t5"
        assert d["symbol"] == "EREGL"
        assert d["status"] == "OPEN"


# ── PaperTradeJournal ─────────────────────────────────────────────────────

class TestPaperTradeJournal:
    def _make_trade(
        self,
        tid: str,
        entry: float,
        stop: float,
        target: float,
        size: int,
        exit_price: float | None = None,
    ) -> PaperTrade:
        t = PaperTrade(
            trade_id=tid,
            symbol="SYM",
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            position_size=size,
            entry_time="2026-01-01",
        )
        if exit_price is not None:
            t.close(exit_price, "2026-01-02")
        return t

    def test_open_and_closed_partitioning(self) -> None:
        j = PaperTradeJournal()
        j.add(self._make_trade("1", 100, 95, 110, 10))
        j.add(self._make_trade("2", 100, 95, 110, 10, exit_price=110))
        assert len(j.all_trades) == 2
        assert len(j.open_trades) == 1
        assert len(j.closed_trades) == 1

    def test_performance_metrics_empty(self) -> None:
        j = PaperTradeJournal()
        m = j.performance_metrics()
        assert m["total_trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["max_drawdown"] == 0.0

    def test_performance_metrics_mixed(self) -> None:
        j = PaperTradeJournal()
        j.add(self._make_trade("w1", 100, 95, 110, 10, exit_price=110))
        j.add(self._make_trade("w2", 100, 95, 110, 10, exit_price=105))
        j.add(self._make_trade("l1", 100, 95, 110, 10, exit_price=92))
        m = j.performance_metrics()
        assert m["closed_count"] == 3
        assert m["win_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert m["expectancy"] != 0.0
        assert m["max_drawdown"] >= 0.0
        assert m["profit_factor"] > 0.0

    def test_avg_r_multiple(self) -> None:
        j = PaperTradeJournal()
        j.add(self._make_trade("r1", 100, 95, 115, 10, exit_price=110))
        m = j.performance_metrics()
        assert m["avg_R_multiple"] == pytest.approx(2.0, abs=0.01)


# ── PaperExecutionEngine ─────────────────────────────────────────────────

class TestPaperExecutionEngine:
    def test_execute_decision_creates_open_trade(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
            fee_bps=0.0,
        )
        trade = engine.execute_decision(
            symbol="ASELS",
            entry=100.0,
            stop=95.0,
            target=110.0,
            position_size=10,
            market_price=100.0,
            entry_time="2026-01-01",
        )
        assert trade is not None
        assert trade.status == "OPEN"
        assert trade.symbol == "ASELS"
        assert trade.entry_price == pytest.approx(100.0, abs=0.01)
        assert len(engine.journal.open_trades) == 1

    def test_execute_decision_rejects_invalid_input(self) -> None:
        engine = PaperExecutionEngine()
        assert engine.execute_decision("X", 0, 95, 110, 10, 100.0, "t") is None
        assert engine.execute_decision("X", 100, 0, 110, 10, 100.0, "t") is None
        assert engine.execute_decision("X", 100, 95, 0, 10, 100.0, "t") is None
        assert engine.execute_decision("X", 100, 95, 110, 0, 100.0, "t") is None

    def test_simulate_exit_closes_trade(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
            fee_bps=10.0,
        )
        trade = engine.execute_decision(
            symbol="THYAO",
            entry=50.0,
            stop=48.0,
            target=55.0,
            position_size=100,
            market_price=50.0,
            entry_time="2026-01-01",
        )
        assert trade is not None
        engine.simulate_exit(trade, 55.0, "2026-01-02")
        assert trade.status == "CLOSED"
        assert trade.pnl > 0
        assert trade.fees > 0
        assert len(engine.journal.closed_trades) == 1
        assert len(engine.journal.open_trades) == 0

    def test_slippage_applied_on_fill(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=50.0),
            fee_bps=0.0,
        )
        trade = engine.execute_decision(
            symbol="AKBNK",
            entry=100.0,
            stop=95.0,
            target=110.0,
            position_size=10,
            market_price=100.0,
            entry_time="2026-01-01",
        )
        assert trade is not None
        assert trade.entry_price > 100.0
        assert trade.slippage > 0

    def test_partial_fill(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
        )
        order = engine.submit_order("TEST", OrderSide.BUY, OrderType.MARKET, 100.0, 100)
        filled = engine.fill_order(order, 100.0, fill_quantity=40)
        assert filled is True
        assert order.sm.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == 40

        filled2 = engine.fill_order(order, 100.0, fill_quantity=60)
        assert filled2 is True
        assert order.sm.status == OrderStatus.FILLED
        assert order.filled_quantity == 100

    def test_limit_order_not_filled_above_limit(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
        )
        order = engine.submit_order("TEST", OrderSide.BUY, OrderType.LIMIT, 100.0, 50)
        filled = engine.fill_order(order, 101.0)
        assert filled is False
        assert order.sm.status == OrderStatus.OPEN

    def test_limit_sell_not_filled_below_limit(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
        )
        order = engine.submit_order("TEST", OrderSide.SELL, OrderType.LIMIT, 50.0, 50)
        filled = engine.fill_order(order, 49.0)
        assert filled is False

    def test_cancel_and_expire_orders(self) -> None:
        engine = PaperExecutionEngine()
        o1 = engine.submit_order("A", OrderSide.BUY, OrderType.MARKET, 10.0, 10)
        o2 = engine.submit_order("B", OrderSide.BUY, OrderType.MARKET, 10.0, 10)
        engine.cancel_order(o1)
        engine.expire_order(o2)
        assert o1.sm.status == OrderStatus.CANCELLED
        assert o2.sm.status == OrderStatus.EXPIRED


# ── Deterministic replay ──────────────────────────────────────────────────

class TestDeterministicReplay:
    SNAPSHOT = [
        {
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
            "market_price": 100.0,
            "entry_time": "2026-01-01",
            "exit_price": 110.0,
            "exit_time": "2026-01-05",
        },
        {
            "symbol": "THYAO",
            "entry": 50.0,
            "stop": 48.0,
            "target": 55.0,
            "position_size": 20,
            "market_price": 50.0,
            "entry_time": "2026-01-01",
            "exit_price": 48.0,
            "exit_time": "2026-01-03",
        },
        {
            "symbol": "GARAN",
            "entry": 30.0,
            "stop": 28.0,
            "target": 35.0,
            "position_size": 50,
            "market_price": 30.0,
            "entry_time": "2026-01-01",
        },
    ]

    def test_replay_produces_deterministic_results(self) -> None:
        slippage = SlippageModel(base_slippage_bps=0.0)
        engine1 = PaperExecutionEngine(slippage=slippage, fee_bps=0.0)
        engine2 = PaperExecutionEngine(slippage=slippage, fee_bps=0.0)

        trades1 = engine1.replay_trades(self.SNAPSHOT)
        trades2 = engine2.replay_trades(self.SNAPSHOT)

        assert len(trades1) == len(trades2) == 3

        for t1, t2 in zip(trades1, trades2):
            assert t1.symbol == t2.symbol
            assert t1.entry_price == t2.entry_price
            assert t1.pnl == t2.pnl
            assert t1.status == t2.status

    def test_replay_fills_and_exits(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
            fee_bps=0.0,
        )
        trades = engine.replay_trades(self.SNAPSHOT)
        assert len(trades) == 3
        assert trades[0].status == "CLOSED"
        assert trades[0].pnl > 0
        assert trades[1].status == "CLOSED"
        assert trades[1].pnl < 0
        assert trades[2].status == "OPEN"

    def test_replay_metrics(self) -> None:
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
            fee_bps=0.0,
        )
        engine.replay_trades(self.SNAPSHOT)
        m = engine.journal.performance_metrics()
        assert m["total_trades"] == 3
        assert m["closed_count"] == 2
        assert m["open_count"] == 1
        assert m["win_rate"] == pytest.approx(0.5, abs=0.01)
        assert m["max_drawdown"] >= 0.0

    def test_replay_skips_invalid_rows(self) -> None:
        bad_data = [
            {"symbol": "", "entry": 100, "stop": 95, "target": 110, "position_size": 10, "market_price": 100, "entry_time": "t"},
            {"symbol": "X", "entry": None, "stop": 95, "target": 110, "position_size": 10, "market_price": 100, "entry_time": "t"},
            {"symbol": "X", "entry": 100, "stop": 95, "target": 110, "position_size": 0, "market_price": 100, "entry_time": "t"},
        ]
        engine = PaperExecutionEngine()
        trades = engine.replay_trades(bad_data)
        assert len(trades) == 0
