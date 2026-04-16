"""Tests for PaperVenueAdapter — Phase 6D.

Covers:
- Degraded fill (book absent, allow_degraded_fill=True)
- Rejection when book absent and allow_degraded_fill=False
- Full fill (book present, order within depth)
- Partial fill + residual cancel (order exceeds depth)
- Fill rejection (book present but pricer rejects)
- request_cancel: happy path + terminal guard
- request_replace: replaces quantity on a submitted order
"""

from __future__ import annotations

import time

import pytest

from crypto_core.execution.events import OrderEventType
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.models import BookContext, ExecutionMode, OrderIntent
from crypto_core.execution.paper_adapter import PaperAdapterConfig, PaperVenueAdapter
from crypto_core.execution.state_machine import Order, OrderState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_ns() -> int:
    return time.time_ns()


def _buy_order(qty: float = 0.01, *, price_hint: float = 50000.0) -> Order:
    o = Order.create(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        mode=ExecutionMode.PAPER,
        quantity=qty,
        timestamp_ns=_now_ns(),
    )
    # Embed price_hint in first event evidence (lifecycle engine does this)
    from crypto_core.execution.events import OrderEvent

    first = o._event_history[0]
    o._event_history[-1] = OrderEvent(
        order_id=first.order_id,
        event_type=first.event_type,
        from_state=first.from_state,
        to_state=first.to_state,
        timestamp_ns=first.timestamp_ns,
        reason=first.reason,
        evidence={**(first.evidence or {}), "price_hint": price_hint},
    )
    return o


def _healthy_book(
    bid: float = 49990.0, ask: float = 50010.0, bid_qty: float = 5.0, ask_qty: float = 5.0
) -> BookContext:
    return BookContext(
        bid_price=bid,
        ask_price=ask,
        bid_size=bid_qty,
        ask_size=ask_qty,
    )


def _adapter(
    max_spread_bps: float = 100.0,
    allow_degraded: bool = True,
    max_participation_pct: float = 200.0,
    max_slippage_bps: float = 200.0,
) -> PaperVenueAdapter:
    cfg = PaperAdapterConfig(
        fill_pricer=FillPricerConfig(
            max_spread_bps=max_spread_bps,
            max_participation_pct=max_participation_pct,
            max_slippage_bps=max_slippage_bps,
        ),
        allow_degraded_fill=allow_degraded,
    )
    return PaperVenueAdapter(cfg)


def _advance_to_validated(order: Order) -> None:
    from crypto_core.execution.events import OrderEvent

    order.transition(
        OrderState.VALIDATED,
        OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.VALIDATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.VALIDATED),
            timestamp_ns=_now_ns(),
        ),
    )


# ---------------------------------------------------------------------------
# Adapter metadata
# ---------------------------------------------------------------------------


class TestAdapterMetadata:
    def test_mode_is_paper(self) -> None:
        assert _adapter().mode == ExecutionMode.PAPER

    def test_not_live_capable(self) -> None:
        assert _adapter().live_capable is False


# ---------------------------------------------------------------------------
# Degraded fill (no book)
# ---------------------------------------------------------------------------


class TestDegradedFill:
    def test_fill_at_price_hint_when_book_absent_and_allowed(self) -> None:
        adapter = _adapter(allow_degraded=True)
        order = _buy_order(qty=0.01, price_hint=50000.0)
        events = adapter.submit_order(order, book=None, pricing=None)
        # Expect: SUBMITTED + FILLED
        event_types = [e.event_type for e in events]
        assert OrderEventType.SUBMITTED in event_types
        filled = [e for e in events if e.event_type == OrderEventType.FILLED]
        assert len(filled) == 1
        assert filled[0].fill_event is not None
        assert filled[0].fill_event.filled_quantity == pytest.approx(0.01)
        assert filled[0].fill_event.fill_price == pytest.approx(50000.0)

    def test_rejection_when_book_absent_and_not_allowed(self) -> None:
        adapter = _adapter(allow_degraded=False)
        order = _buy_order(price_hint=50000.0)
        events = adapter.submit_order(order, book=None, pricing=None)
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.REJECTED
        assert "book_unavailable" in events[0].reason

    def test_rejection_when_price_hint_missing(self) -> None:
        """Order without price_hint in evidence → rejected even in degraded mode."""
        adapter = _adapter(allow_degraded=True)
        order = Order.create(
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            mode=ExecutionMode.PAPER,
            quantity=0.01,
            timestamp_ns=_now_ns(),
        )
        # No price_hint embedded → should reject
        events = adapter.submit_order(order, book=None, pricing=None)
        assert events[0].event_type == OrderEventType.REJECTED


# ---------------------------------------------------------------------------
# Full fill (book present, order within depth)
# ---------------------------------------------------------------------------


class TestFullFill:
    def test_full_fill_within_depth(self) -> None:
        adapter = _adapter(max_spread_bps=100.0)
        order = _buy_order(qty=0.01, price_hint=50000.0)
        book = _healthy_book(bid_qty=5.0, ask_qty=5.0)  # within depth
        events = adapter.submit_order(order, book=book, pricing=None)
        event_types = [e.event_type for e in events]
        assert OrderEventType.SUBMITTED in event_types
        assert OrderEventType.FILLED in event_types
        assert OrderEventType.REJECTED not in event_types

    def test_fill_price_above_mid_for_buy(self) -> None:
        adapter = _adapter(max_spread_bps=100.0)
        order = _buy_order(qty=0.01, price_hint=50000.0)
        book = _healthy_book()
        events = adapter.submit_order(order, book=book, pricing=None)
        filled = next(e for e in events if e.event_type == OrderEventType.FILLED)
        assert filled.fill_event.fill_price > 50000.0  # mid is 50000, buy fills above

    def test_fill_event_has_slippage_and_spread(self) -> None:
        adapter = _adapter()
        order = _buy_order(qty=0.01, price_hint=50000.0)
        book = _healthy_book()
        events = adapter.submit_order(order, book=book, pricing=None)
        filled = next(e for e in events if e.event_type == OrderEventType.FILLED)
        fe = filled.fill_event
        assert fe.spread_bps is not None and fe.spread_bps > 0.0
        assert fe.slippage_bps is not None


# ---------------------------------------------------------------------------
# Partial fill (order exceeds depth)
# ---------------------------------------------------------------------------


class TestPartialFill:
    def test_partial_fill_then_cancel(self) -> None:
        adapter = _adapter(max_spread_bps=100.0)
        # Order size 1.0, depth only 0.5
        order = _buy_order(qty=1.0, price_hint=50000.0)
        book = _healthy_book(ask_qty=0.5)
        events = adapter.submit_order(order, book=book, pricing=None)
        event_types = [e.event_type for e in events]
        assert OrderEventType.SUBMITTED in event_types
        assert OrderEventType.PARTIALLY_FILLED in event_types
        assert OrderEventType.CANCELLED in event_types

    def test_partial_fill_quantity_matches_depth(self) -> None:
        adapter = _adapter(max_spread_bps=100.0)
        order = _buy_order(qty=1.0, price_hint=50000.0)
        book = _healthy_book(ask_qty=0.5)
        events = adapter.submit_order(order, book=book, pricing=None)
        partial = next(e for e in events if e.event_type == OrderEventType.PARTIALLY_FILLED)
        assert partial.fill_event.filled_quantity == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Pricer rejection
# ---------------------------------------------------------------------------


class TestPricerRejection:
    def test_rejection_on_excessive_spread(self) -> None:
        # max_spread_bps=3 → book spread 4bps exceeds gate
        adapter = _adapter(max_spread_bps=3.0)
        order = _buy_order(qty=0.01, price_hint=50000.0)
        book = _healthy_book(bid=49990.0, ask=50010.0)  # 40bps spread
        events = adapter.submit_order(order, book=book, pricing=None)
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.REJECTED

    def test_rejection_on_crossed_book(self) -> None:
        adapter = _adapter()
        order = _buy_order(qty=0.01, price_hint=50000.0)
        book = BookContext(bid_price=50020.0, ask_price=49980.0)  # crossed
        events = adapter.submit_order(order, book=book, pricing=None)
        assert events[0].event_type == OrderEventType.REJECTED


# ---------------------------------------------------------------------------
# request_cancel
# ---------------------------------------------------------------------------


class TestRequestCancel:
    def test_cancel_non_terminal_order(self) -> None:
        adapter = _adapter()
        order = _buy_order()
        _advance_to_validated(order)
        event = adapter.request_cancel(order, reason="USER_REQUEST", timestamp_ns=_now_ns())
        assert event.event_type == OrderEventType.CANCELLED

    def test_cancel_terminal_order_returns_rejection(self) -> None:
        """Cancelling an already-terminal order should return a REJECTED event."""
        adapter = _adapter()
        order = _buy_order()
        order.state = OrderState.FILLED  # force terminal
        event = adapter.request_cancel(order, reason="USER_REQUEST", timestamp_ns=_now_ns())
        assert event.event_type == OrderEventType.REJECTED


# ---------------------------------------------------------------------------
# request_replace (cancel + resubmit)
# ---------------------------------------------------------------------------


class TestRequestReplace:
    def test_replace_increases_quantity(self) -> None:
        adapter = _adapter(max_spread_bps=100.0)
        order = _buy_order(qty=0.01, price_hint=50000.0)
        _advance_to_validated(order)
        book = _healthy_book()
        events = adapter.request_replace(
            order=order,
            new_quantity=0.02,
            book=book,
            pricing=None,
            timestamp_ns=_now_ns(),
        )
        event_types = [e.event_type for e in events]
        # Replace = cancel + submit sequence
        assert OrderEventType.CANCELLED in event_types

    def test_replace_terminal_order_returns_rejection(self) -> None:
        adapter = _adapter()
        order = _buy_order()
        order.state = OrderState.FILLED
        events = adapter.request_replace(
            order=order,
            new_quantity=0.02,
            book=_healthy_book(),
            pricing=None,
            timestamp_ns=_now_ns(),
        )
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.REJECTED
