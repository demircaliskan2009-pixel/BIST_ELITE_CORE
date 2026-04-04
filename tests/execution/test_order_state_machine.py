"""Order state machine unit tests — lifecycle, rejection, stops, targets, integration."""

from __future__ import annotations

import pytest

from bist_core.execution.order_state_machine import (
    ExecutionOrderStatus,
    ExecutionOrderType,
    ExecutionStateMachine,
    ManagedOrder,
    OrderStateMachineController,
    RiskLimits,
    reset_order_counter,
)
from bist_core.execution.paper_engine import (
    PaperExecutionEngine,
    SlippageModel,
)


@pytest.fixture(autouse=True)
def _reset_ids():
    reset_order_counter()
    yield
    reset_order_counter()


def _zero_engine() -> PaperExecutionEngine:
    return PaperExecutionEngine(slippage=SlippageModel(base_slippage_bps=0.0), fee_bps=0.0)


# ── ExecutionStateMachine ─────────────────────────────────────────────────

class TestExecutionStateMachine:
    def test_initial_state(self) -> None:
        sm = ExecutionStateMachine()
        assert sm.status == ExecutionOrderStatus.CREATED

    def test_full_happy_path(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.SUBMITTED)
        sm.transition(ExecutionOrderStatus.ACCEPTED)
        sm.transition(ExecutionOrderStatus.FILLED)
        assert sm.status == ExecutionOrderStatus.FILLED
        assert sm.is_terminal is True
        assert sm.history == [
            ExecutionOrderStatus.CREATED,
            ExecutionOrderStatus.SUBMITTED,
            ExecutionOrderStatus.ACCEPTED,
            ExecutionOrderStatus.FILLED,
        ]

    def test_partial_fill_path(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.SUBMITTED)
        sm.transition(ExecutionOrderStatus.ACCEPTED)
        sm.transition(ExecutionOrderStatus.PARTIALLY_FILLED)
        sm.transition(ExecutionOrderStatus.FILLED)
        assert sm.status == ExecutionOrderStatus.FILLED

    def test_rejection_from_created(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.REJECTED)
        assert sm.status == ExecutionOrderStatus.REJECTED
        assert sm.is_terminal is True

    def test_rejection_from_submitted(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.SUBMITTED)
        sm.transition(ExecutionOrderStatus.REJECTED)
        assert sm.is_terminal is True

    def test_cancel_from_accepted(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.SUBMITTED)
        sm.transition(ExecutionOrderStatus.ACCEPTED)
        sm.transition(ExecutionOrderStatus.CANCELLED)
        assert sm.is_terminal is True

    def test_expire_from_accepted(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.SUBMITTED)
        sm.transition(ExecutionOrderStatus.ACCEPTED)
        sm.transition(ExecutionOrderStatus.EXPIRED)
        assert sm.is_terminal is True

    def test_invalid_filled_to_open(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.SUBMITTED)
        sm.transition(ExecutionOrderStatus.ACCEPTED)
        sm.transition(ExecutionOrderStatus.FILLED)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(ExecutionOrderStatus.CREATED)

    def test_invalid_rejected_to_submitted(self) -> None:
        sm = ExecutionStateMachine()
        sm.transition(ExecutionOrderStatus.REJECTED)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(ExecutionOrderStatus.SUBMITTED)

    def test_invalid_created_to_filled(self) -> None:
        sm = ExecutionStateMachine()
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(ExecutionOrderStatus.FILLED)


# ── RiskLimits ────────────────────────────────────────────────────────────

class TestRiskLimits:
    def test_valid_order_no_errors(self) -> None:
        r = RiskLimits()
        errors = r.validate(100.0, 95.0, 110.0, 10)
        assert errors == []

    def test_position_too_small(self) -> None:
        r = RiskLimits(min_position_size=5)
        errors = r.validate(100.0, 95.0, 110.0, 2)
        assert any("min" in e for e in errors)

    def test_position_too_large(self) -> None:
        r = RiskLimits(max_position_size=100)
        errors = r.validate(100.0, 95.0, 110.0, 200)
        assert any("max" in e for e in errors)

    def test_stop_distance_too_small(self) -> None:
        r = RiskLimits(min_stop_distance_pct=1.0)
        errors = r.validate(100.0, 99.8, 110.0, 10)
        assert any("stop distance" in e for e in errors)

    def test_risk_exceeds_capital(self) -> None:
        r = RiskLimits(max_risk_per_trade_pct=1.0)
        errors = r.validate(100.0, 90.0, 120.0, 100, capital=10_000.0)
        assert any("risk" in e for e in errors)

    def test_zero_entry_rejected(self) -> None:
        r = RiskLimits()
        errors = r.validate(0.0, 95.0, 110.0, 10)
        assert any("entry" in e for e in errors)


# ── OrderStateMachineController ───────────────────────────────────────────

class TestOrderCreation:
    def test_create_from_valid_decision(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert order.status == ExecutionOrderStatus.CREATED
        assert order.symbol == "ASELS"
        assert order.rejection_reasons == []

    def test_reject_invalid_position_size(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "THYAO",
            "entry": 50.0,
            "stop": 48.0,
            "target": 55.0,
            "position_size": 0,
        })
        assert order.status == ExecutionOrderStatus.REJECTED
        assert len(order.rejection_reasons) > 0

    def test_reject_empty_symbol(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert order.status == ExecutionOrderStatus.REJECTED

    def test_reject_zero_entry(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "GARAN",
            "entry": 0.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert order.status == ExecutionOrderStatus.REJECTED


class TestOrderSubmission:
    def test_submit_fills_and_creates_trade(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        ctrl.submit_order(order, market_price=100.0, entry_time="2026-01-01")
        assert order.status == ExecutionOrderStatus.FILLED
        assert order.trade is not None
        assert order.trade.status == "OPEN"
        assert order.trade.entry_price == pytest.approx(100.0, abs=0.01)

    def test_submit_rejected_order_is_noop(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert order.status == ExecutionOrderStatus.REJECTED
        ctrl.submit_order(order, market_price=100.0, entry_time="t")
        assert order.status == ExecutionOrderStatus.REJECTED

    def test_order_to_dict(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "EREGL",
            "entry": 30.0,
            "stop": 28.0,
            "target": 35.0,
            "position_size": 50,
        })
        ctrl.submit_order(order, market_price=30.0, entry_time="2026-01-01")
        d = order.to_dict()
        assert d["status"] == "FILLED"
        assert d["trade"] is not None
        assert d["trade"]["symbol"] == "EREGL"


class TestStopTargetTrigger:
    def test_stop_trigger(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "AKBNK",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        ctrl.submit_order(order, market_price=100.0, entry_time="2026-01-01")
        result = ctrl.check_stop_target(order, current_price=94.0, current_time="2026-01-02")
        assert result == "stop_triggered"
        assert order.trade is not None
        assert order.trade.status == "CLOSED"
        assert order.trade.pnl < 0
        assert order.exit_reason == "stop_triggered"

    def test_target_trigger(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "THYAO",
            "entry": 50.0,
            "stop": 48.0,
            "target": 55.0,
            "position_size": 20,
        })
        ctrl.submit_order(order, market_price=50.0, entry_time="2026-01-01")
        result = ctrl.check_stop_target(order, current_price=56.0, current_time="2026-01-03")
        assert result == "target_triggered"
        assert order.trade is not None
        assert order.trade.status == "CLOSED"
        assert order.trade.pnl > 0
        assert order.exit_reason == "target_triggered"

    def test_no_trigger_in_range(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "GARAN",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        ctrl.submit_order(order, market_price=100.0, entry_time="2026-01-01")
        result = ctrl.check_stop_target(order, current_price=102.0, current_time="2026-01-02")
        assert result is None
        assert order.trade is not None
        assert order.trade.status == "OPEN"

    def test_stop_at_exact_stop_price(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "TUPRS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        ctrl.submit_order(order, market_price=100.0, entry_time="2026-01-01")
        result = ctrl.check_stop_target(order, current_price=95.0, current_time="2026-01-02")
        assert result == "stop_triggered"

    def test_target_at_exact_target_price(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "TUPRS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        ctrl.submit_order(order, market_price=100.0, entry_time="2026-01-01")
        result = ctrl.check_stop_target(order, current_price=110.0, current_time="2026-01-02")
        assert result == "target_triggered"


class TestManualActions:
    def test_cancel_open_order(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        ctrl.cancel_order(order)
        assert order.status == ExecutionOrderStatus.CANCELLED
        assert order.exit_reason == "manual_cancel"

    def test_expire_order(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        ctrl.expire_order(order)
        assert order.status == ExecutionOrderStatus.EXPIRED
        assert order.exit_reason == "expired"

    def test_cancel_terminal_is_noop(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        order = ctrl.create_order_from_decision({
            "symbol": "",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert order.sm.is_terminal
        ctrl.cancel_order(order)
        assert order.status == ExecutionOrderStatus.REJECTED


class TestBatchExecution:
    def test_execute_decisions_batch(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        decisions = [
            {"symbol": "ASELS", "entry": 100.0, "stop": 95.0, "target": 110.0, "position_size": 10},
            {"symbol": "THYAO", "entry": 50.0, "stop": 48.0, "target": 55.0, "position_size": 20},
        ]
        prices = {"ASELS": 100.0, "THYAO": 50.0}
        results = ctrl.execute_decisions(decisions, prices, "2026-01-01")
        assert len(results) == 2
        assert all(o.status == ExecutionOrderStatus.FILLED for o in results)
        assert all(o.trade is not None for o in results)

    def test_execute_decisions_rejects_missing_price(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        decisions = [
            {"symbol": "ASELS", "entry": 100.0, "stop": 95.0, "target": 110.0, "position_size": 10},
        ]
        results = ctrl.execute_decisions(decisions, {}, "2026-01-01")
        assert results[0].status == ExecutionOrderStatus.REJECTED


class TestTickSimulation:
    def test_tick_triggers_stop(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        decisions = [
            {"symbol": "ASELS", "entry": 100.0, "stop": 95.0, "target": 110.0, "position_size": 10},
            {"symbol": "THYAO", "entry": 50.0, "stop": 48.0, "target": 55.0, "position_size": 20},
        ]
        prices = {"ASELS": 100.0, "THYAO": 50.0}
        ctrl.execute_decisions(decisions, prices, "2026-01-01")
        events = ctrl.tick({"ASELS": 93.0, "THYAO": 52.0}, "2026-01-02")
        assert "ASELS:stop_triggered" in events
        assert len(events) == 1

    def test_tick_triggers_target(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        decisions = [
            {"symbol": "GARAN", "entry": 30.0, "stop": 28.0, "target": 35.0, "position_size": 50},
        ]
        ctrl.execute_decisions(decisions, {"GARAN": 30.0}, "2026-01-01")
        events = ctrl.tick({"GARAN": 36.0}, "2026-01-02")
        assert "GARAN:target_triggered" in events

    def test_tick_no_events_in_range(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        ctrl.execute_decisions(
            [{"symbol": "ASELS", "entry": 100.0, "stop": 95.0, "target": 110.0, "position_size": 10}],
            {"ASELS": 100.0},
            "2026-01-01",
        )
        events = ctrl.tick({"ASELS": 103.0}, "2026-01-02")
        assert events == []


class TestDeterminism:
    def test_identical_inputs_produce_identical_outputs(self) -> None:
        decisions = [
            {"symbol": "ASELS", "entry": 100.0, "stop": 95.0, "target": 110.0, "position_size": 10},
            {"symbol": "THYAO", "entry": 50.0, "stop": 48.0, "target": 55.0, "position_size": 20},
        ]
        prices = {"ASELS": 100.0, "THYAO": 50.0}

        reset_order_counter()
        ctrl1 = OrderStateMachineController(engine=_zero_engine())
        r1 = ctrl1.execute_decisions(decisions, prices, "2026-01-01")

        reset_order_counter()
        ctrl2 = OrderStateMachineController(engine=_zero_engine())
        r2 = ctrl2.execute_decisions(decisions, prices, "2026-01-01")

        for o1, o2 in zip(r1, r2):
            assert o1.order_id == o2.order_id
            assert o1.status == o2.status
            assert o1.trade is not None and o2.trade is not None
            assert o1.trade.entry_price == o2.trade.entry_price
            assert o1.trade.pnl == o2.trade.pnl


class TestIntegrationWithJournal:
    def test_trades_appear_in_journal(self) -> None:
        ctrl = OrderStateMachineController(engine=_zero_engine())
        ctrl.execute_decisions(
            [{"symbol": "ASELS", "entry": 100.0, "stop": 95.0, "target": 110.0, "position_size": 10}],
            {"ASELS": 100.0},
            "2026-01-01",
        )
        assert len(ctrl.engine.journal.open_trades) == 1

        ctrl.tick({"ASELS": 112.0}, "2026-01-02")
        assert len(ctrl.engine.journal.closed_trades) == 1
        m = ctrl.engine.journal.performance_metrics()
        assert m["closed_count"] == 1
        assert m["win_rate"] == 1.0
