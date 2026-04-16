"""Tests for execution order state machine — Phase 6D.

Covers:
- Valid state transitions (entire graph)
- Terminal state locking
- Illegal transition rejection
- Fill accumulation (VWAP)
- Event history immutability
"""

from __future__ import annotations

import time

import pytest

from crypto_core.execution.events import FillEvent, OrderEvent, OrderEventType
from crypto_core.execution.models import ExecutionMode, OrderIntent
from crypto_core.execution.state_machine import (
    _ALLOWED_TRANSITIONS,
    _TERMINAL_STATES,
    IllegalOrderTransitionError,
    Order,
    OrderState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_ns() -> int:
    return time.time_ns()


def _order(qty: float = 0.01) -> Order:
    return Order.create(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        mode=ExecutionMode.PAPER,
        quantity=qty,
        timestamp_ns=_now_ns(),
    )


def _event(order: Order, from_state: OrderState, to_state: OrderState, reason: str = "") -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        event_type=str(to_state),
        from_state=str(from_state),
        to_state=str(to_state),
        timestamp_ns=_now_ns(),
        reason=reason,
    )


def _fill_event(order: Order, qty: float, price: float) -> FillEvent:
    return FillEvent(
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        intent=order.intent,
        filled_quantity=qty,
        fill_price=price,
        timestamp_ns=_now_ns(),
    )


# ---------------------------------------------------------------------------
# Order.create factory
# ---------------------------------------------------------------------------


class TestOrderCreate:
    def test_initial_state_is_created(self) -> None:
        o = _order()
        assert str(o.state) == OrderState.CREATED

    def test_order_id_is_nonempty_string(self) -> None:
        o = _order()
        assert isinstance(o.order_id, str)
        assert len(o.order_id) > 0

    def test_initial_event_history_has_one_event(self) -> None:
        o = _order()
        assert len(o.event_history) == 1
        assert o.event_history[0].event_type == OrderEventType.CREATED

    def test_requested_quantity_preserved(self) -> None:
        o = _order(qty=0.05)
        assert o.requested_quantity == pytest.approx(0.05)
        assert o.remaining_quantity == pytest.approx(0.05)

    def test_no_fills_on_create(self) -> None:
        o = _order()
        assert o.filled_quantity == 0.0
        assert o.average_fill_price is None
        assert o.fill_ratio == pytest.approx(0.0)

    def test_is_not_terminal_on_create(self) -> None:
        assert not _order().is_terminal


# ---------------------------------------------------------------------------
# Allowed transitions — full happy paths
# ---------------------------------------------------------------------------


class TestAllowedTransitions:
    def test_created_to_validated(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        assert str(o.state) == OrderState.VALIDATED

    def test_validated_to_submitted(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        assert str(o.state) == OrderState.SUBMITTED

    def test_submitted_to_filled(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        o.transition(OrderState.FILLED, _event(o, OrderState.SUBMITTED, OrderState.FILLED))
        assert str(o.state) == OrderState.FILLED
        assert o.is_terminal

    def test_submitted_to_cancelled(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        o.transition(OrderState.CANCELLED, _event(o, OrderState.SUBMITTED, OrderState.CANCELLED))
        assert o.is_terminal

    def test_submitted_to_rejected(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        o.transition(OrderState.REJECTED, _event(o, OrderState.SUBMITTED, OrderState.REJECTED))
        assert o.is_terminal

    def test_submitted_to_expired(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        o.transition(OrderState.EXPIRED, _event(o, OrderState.SUBMITTED, OrderState.EXPIRED))
        assert o.is_terminal

    def test_submitted_to_partially_filled(self) -> None:
        o = _order(qty=0.02)
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        o.transition(OrderState.PARTIALLY_FILLED, _event(o, OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED))
        assert str(o.state) == OrderState.PARTIALLY_FILLED
        assert not o.is_terminal

    def test_partially_filled_to_filled(self) -> None:
        o = _order(qty=0.02)
        for st_from, st_to in [
            (OrderState.CREATED, OrderState.VALIDATED),
            (OrderState.VALIDATED, OrderState.SUBMITTED),
        ]:
            o.transition(st_to, _event(o, st_from, st_to))
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        o.transition(OrderState.PARTIALLY_FILLED, _event(o, OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED))
        o.apply_fill(_fill_event(o, 0.01, 50100.0))
        o.transition(OrderState.FILLED, _event(o, OrderState.PARTIALLY_FILLED, OrderState.FILLED))
        assert o.is_terminal

    def test_partially_filled_to_cancelled(self) -> None:
        o = _order(qty=0.02)
        for st_from, st_to in [
            (OrderState.CREATED, OrderState.VALIDATED),
            (OrderState.VALIDATED, OrderState.SUBMITTED),
        ]:
            o.transition(st_to, _event(o, st_from, st_to))
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        o.transition(OrderState.PARTIALLY_FILLED, _event(o, OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED))
        o.transition(OrderState.CANCELLED, _event(o, OrderState.PARTIALLY_FILLED, OrderState.CANCELLED))
        assert o.is_terminal

    def test_created_to_rejected_directly(self) -> None:
        o = _order()
        o.transition(OrderState.REJECTED, _event(o, OrderState.CREATED, OrderState.REJECTED, reason="SIZE_ZERO"))
        assert o.is_terminal

    def test_validated_to_rejected(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.REJECTED, _event(o, OrderState.VALIDATED, OrderState.REJECTED))
        assert o.is_terminal


# ---------------------------------------------------------------------------
# Terminal state locking
# ---------------------------------------------------------------------------


class TestTerminalStateLocking:
    @pytest.mark.parametrize("terminal", list(_TERMINAL_STATES))
    def test_terminal_state_blocks_all_transitions(self, terminal: str) -> None:
        o = _order()
        # Directly force terminal state via private attribute for test isolation
        o.state = OrderState(terminal)
        dummy_event = _event(o, OrderState(terminal), OrderState.VALIDATED)
        with pytest.raises(IllegalOrderTransitionError, match="terminal"):
            o.transition(OrderState.VALIDATED, dummy_event)

    def test_filled_is_terminal(self) -> None:
        assert OrderState.FILLED in _TERMINAL_STATES

    def test_cancelled_is_terminal(self) -> None:
        assert OrderState.CANCELLED in _TERMINAL_STATES

    def test_rejected_is_terminal(self) -> None:
        assert OrderState.REJECTED in _TERMINAL_STATES

    def test_expired_is_terminal(self) -> None:
        assert OrderState.EXPIRED in _TERMINAL_STATES


# ---------------------------------------------------------------------------
# Illegal transition rejection
# ---------------------------------------------------------------------------


class TestIllegalTransitionRejection:
    def test_created_to_submitted_is_illegal(self) -> None:
        o = _order()
        with pytest.raises(IllegalOrderTransitionError):
            o.transition(OrderState.SUBMITTED, _event(o, OrderState.CREATED, OrderState.SUBMITTED))

    def test_created_to_filled_is_illegal(self) -> None:
        o = _order()
        with pytest.raises(IllegalOrderTransitionError):
            o.transition(OrderState.FILLED, _event(o, OrderState.CREATED, OrderState.FILLED))

    def test_validated_to_filled_is_illegal(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        with pytest.raises(IllegalOrderTransitionError):
            o.transition(OrderState.FILLED, _event(o, OrderState.VALIDATED, OrderState.FILLED))

    def test_submitted_to_validated_is_illegal(self) -> None:
        o = _order()
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        with pytest.raises(IllegalOrderTransitionError):
            o.transition(OrderState.VALIDATED, _event(o, OrderState.SUBMITTED, OrderState.VALIDATED))


# ---------------------------------------------------------------------------
# Fill accumulation and VWAP
# ---------------------------------------------------------------------------


class TestFillAccumulation:
    def test_single_fill_vwap(self) -> None:
        o = _order(qty=0.01)
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        assert o.average_fill_price == pytest.approx(50000.0)
        assert o.filled_quantity == pytest.approx(0.01)
        assert o.remaining_quantity == pytest.approx(0.0)

    def test_two_fill_vwap(self) -> None:
        o = _order(qty=0.02)
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        o.apply_fill(_fill_event(o, 0.01, 50200.0))
        assert o.average_fill_price == pytest.approx(50100.0)
        assert o.filled_quantity == pytest.approx(0.02)

    def test_fill_ratio_after_partial_fill(self) -> None:
        o = _order(qty=0.02)
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        assert o.fill_ratio == pytest.approx(0.5)

    def test_fill_ratio_fully_filled(self) -> None:
        o = _order(qty=0.01)
        o.apply_fill(_fill_event(o, 0.01, 50000.0))
        assert o.fill_ratio == pytest.approx(1.0)

    def test_remaining_quantity_floor_at_zero(self) -> None:
        """Overfill should not produce negative remaining."""
        o = _order(qty=0.01)
        o.apply_fill(_fill_event(o, 0.02, 50000.0))  # overfill
        assert o.remaining_quantity == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Event history immutability
# ---------------------------------------------------------------------------


class TestEventHistoryImmutability:
    def test_event_history_returns_tuple(self) -> None:
        o = _order()
        assert isinstance(o.event_history, tuple)

    def test_modifying_returned_tuple_does_not_affect_internal(self) -> None:
        o = _order()
        snapshot = o.event_history
        # Appending to the internal list should NOT affect the snapshot
        assert len(snapshot) == 1
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        assert len(o.event_history) == 2
        assert len(snapshot) == 1  # snapshot is unchanged

    def test_event_history_grows_with_each_transition(self) -> None:
        o = _order()
        assert len(o.event_history) == 1
        o.transition(OrderState.VALIDATED, _event(o, OrderState.CREATED, OrderState.VALIDATED))
        assert len(o.event_history) == 2
        o.transition(OrderState.SUBMITTED, _event(o, OrderState.VALIDATED, OrderState.SUBMITTED))
        assert len(o.event_history) == 3


# ---------------------------------------------------------------------------
# FSM completeness
# ---------------------------------------------------------------------------


class TestFSMCompleteness:
    def test_all_allowed_transition_targets_are_valid_states(self) -> None:
        all_states = {
            str(s)
            for s in [
                OrderState.CREATED,
                OrderState.VALIDATED,
                OrderState.SUBMITTED,
                OrderState.PARTIALLY_FILLED,
                OrderState.FILLED,
                OrderState.CANCELLED,
                OrderState.REJECTED,
                OrderState.EXPIRED,
            ]
        }
        for _from, targets in _ALLOWED_TRANSITIONS.items():
            for target in targets:
                assert target in all_states, f"Unknown target state: {target}"

    def test_terminal_states_not_in_allowed_transitions_as_source(self) -> None:
        for terminal in _TERMINAL_STATES:
            assert terminal not in _ALLOWED_TRANSITIONS, (
                f"Terminal state {terminal!r} should not have outbound transitions"
            )
