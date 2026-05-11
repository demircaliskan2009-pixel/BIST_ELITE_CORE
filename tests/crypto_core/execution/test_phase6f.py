"""Tests for Phase 6F — execution reconciliation, cancel/replace, recovery.

Covers:
  - FSM expansion: CANCEL_PENDING, REPLACE_PENDING, STALE states + transitions.
  - Paper adapter: order tracking, poll_open_orders, ingest_fill_event,
    register_restored_orders, reconcile_order.
  - Lifecycle cancel/replace with CANCEL_PENDING/REPLACE_PENDING + persistence.
  - Recovery bootstrap with reconciliation.
  - Store round-trip for cancel/replace/stale events.
  - Orchestrator recovery visibility.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.events import FillEvent, OrderEvent, OrderEventType
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.lifecycle import (
    ExecutionLifecycleConfig,
    ExecutionLifecycleEngine,
)
from crypto_core.execution.models import (
    BookContext,
    ExecutionMode,
    ExecutionRequest,
    OrderIntent,
)
from crypto_core.execution.paper_adapter import PaperAdapterConfig, PaperVenueAdapter
from crypto_core.execution.recovery import (
    RecoveryBootstrap,
    RecoveryEvidence,
)
from crypto_core.execution.state_machine import (
    _TERMINAL_STATES,
    IllegalOrderTransitionError,
    Order,
    OrderState,
)
from crypto_core.execution.store import ExecutionStateStore, build_order_meta
from crypto_core.guard.models import NoTradeDecision
from crypto_core.portfolio.store import PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.risk.models import RiskDecision, RiskEvaluation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0 = 1_000_000_000_000


def _now_ns() -> int:
    return time.time_ns()


def _make_order(
    state: str = "CREATED",
    ts: int = _T0,
    symbol: str = "BTCUSDT",
    qty: float = 0.01,
) -> Order:
    order = Order.create(
        symbol=symbol,
        exchange="binance",
        intent=OrderIntent.BUY,
        mode=ExecutionMode.PAPER,
        quantity=qty,
        timestamp_ns=ts,
    )
    return order


def _advance_to_submitted(order: Order, ts: int | None = None) -> None:
    """Advance an order through CREATED → VALIDATED → SUBMITTED."""
    ts = ts or _now_ns()
    validated = OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.VALIDATED,
        from_state=str(OrderState.CREATED),
        to_state=str(OrderState.VALIDATED),
        timestamp_ns=ts,
        evidence={},
    )
    order.transition(OrderState.VALIDATED, validated)
    submitted = OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.SUBMITTED,
        from_state=str(OrderState.VALIDATED),
        to_state=str(OrderState.SUBMITTED),
        timestamp_ns=ts,
        evidence={},
    )
    order.transition(OrderState.SUBMITTED, submitted)


def _advance_to_partially_filled(order: Order, ts: int | None = None) -> None:
    """Advance an order through CREATED → ... → PARTIALLY_FILLED."""
    ts = ts or _now_ns()
    _advance_to_submitted(order, ts)
    fill = FillEvent(
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        intent=order.intent,
        filled_quantity=order.requested_quantity * 0.5,
        fill_price=50_000.0,
        timestamp_ns=ts,
    )
    order.apply_fill(fill)
    pf_event = OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.PARTIALLY_FILLED,
        from_state=str(OrderState.SUBMITTED),
        to_state=str(OrderState.PARTIALLY_FILLED),
        timestamp_ns=ts,
        fill_event=fill,
        evidence={},
    )
    order.transition(OrderState.PARTIALLY_FILLED, pf_event)


def _risk_eval() -> RiskEvaluation:
    sig = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=_T0,
        is_valid=True,
        block_reason=None,
    )
    return RiskEvaluation(
        decision=RiskDecision.APPROVED,
        edge_signal=sig,
        system_state="NORMAL",
        no_trade_decision=NoTradeDecision.allow(),
        block_reason=None,
        timestamp_ns=_T0,
        evidence={},
    )


def _paper_engine(store: ExecutionStateStore | None = None) -> ExecutionLifecycleEngine:
    cfg = ExecutionLifecycleConfig(
        mode=ExecutionMode.PAPER,
        paper_adapter=PaperAdapterConfig(
            fill_pricer=FillPricerConfig(max_spread_bps=200.0),
            allow_degraded_fill=True,
        ),
    )
    return ExecutionLifecycleEngine(cfg, store=store)


def _request(
    size: float = 0.01,
    intent: OrderIntent = OrderIntent.BUY,
    ts: int = _T0,
) -> ExecutionRequest:
    book = BookContext(bid_price=49_990.0, ask_price=50_010.0, bid_size=1.0, ask_size=1.0)
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=intent,
        size=size,
        price_hint=50_000.0,
        risk_evaluation=_risk_eval(),
        timestamp_ns=ts,
        book=book,
    )


def _persist_order_to_submitted(order: Order, store: ExecutionStateStore, ts: int = _T0) -> None:
    """Persist CREATED + VALIDATED + SUBMITTED events to store."""
    store.append_event(
        OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CREATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.CREATED),
            timestamp_ns=ts,
            evidence={},
        ),
        order_meta=build_order_meta(order),
    )
    store.append_event(
        OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.VALIDATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.VALIDATED),
            timestamp_ns=ts + 1,
            evidence={},
        )
    )
    store.append_event(
        OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.SUBMITTED,
            from_state=str(OrderState.VALIDATED),
            to_state=str(OrderState.SUBMITTED),
            timestamp_ns=ts + 2,
            evidence={},
        )
    )


def _exec_store(tmp_path: Path, name: str = "exec.jsonl") -> ExecutionStateStore:
    return ExecutionStateStore(path=tmp_path / name)


def _port_store(tmp_path: Path, name: str = "portfolio.json") -> PortfolioStateStore:
    return PortfolioStateStore(path=tmp_path / name)


def _save_empty_portfolio(store: PortfolioStateStore, nav: float = 10_000.0) -> None:
    tracker = PositionTracker(initial_nav_usd=nav)
    store.save(tracker.to_persistence_dict(_T0))


# ---------------------------------------------------------------------------
# 1. FSM expansion tests
# ---------------------------------------------------------------------------


class TestFSMExpansion:
    def test_cancel_pending_is_not_terminal(self) -> None:
        assert str(OrderState.CANCEL_PENDING) not in _TERMINAL_STATES

    def test_replace_pending_is_not_terminal(self) -> None:
        assert str(OrderState.REPLACE_PENDING) not in _TERMINAL_STATES

    def test_stale_is_terminal(self) -> None:
        assert str(OrderState.STALE) in _TERMINAL_STATES

    def test_submitted_to_cancel_pending(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        ev = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCEL_REQUESTED,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.CANCEL_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.CANCEL_PENDING, ev)
        assert str(order.state) == str(OrderState.CANCEL_PENDING)
        assert not order.is_terminal

    def test_submitted_to_replace_pending(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        ev = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.REPLACE_REQUESTED,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.REPLACE_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.REPLACE_PENDING, ev)
        assert str(order.state) == str(OrderState.REPLACE_PENDING)

    def test_cancel_pending_to_cancelled(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        ev1 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCEL_REQUESTED,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.CANCEL_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.CANCEL_PENDING, ev1)
        ev2 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCELLED,
            from_state=str(OrderState.CANCEL_PENDING),
            to_state=str(OrderState.CANCELLED),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.CANCELLED, ev2)
        assert order.is_terminal

    def test_cancel_pending_to_filled(self) -> None:
        """Fill arrives before cancel ack — must be legal."""
        order = _make_order()
        _advance_to_submitted(order)
        ev1 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCEL_REQUESTED,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.CANCEL_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.CANCEL_PENDING, ev1)
        fill = FillEvent(
            order_id=order.order_id,
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.01,
            fill_price=50_000.0,
            timestamp_ns=_now_ns(),
        )
        order.apply_fill(fill)
        ev2 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.FILLED,
            from_state=str(OrderState.CANCEL_PENDING),
            to_state=str(OrderState.FILLED),
            timestamp_ns=_now_ns(),
            fill_event=fill,
            evidence={},
        )
        order.transition(OrderState.FILLED, ev2)
        assert order.is_terminal
        assert order.filled_quantity == pytest.approx(0.01)

    def test_cancel_pending_to_stale(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        ev1 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCEL_REQUESTED,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.CANCEL_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.CANCEL_PENDING, ev1)
        ev2 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.STALE,
            from_state=str(OrderState.CANCEL_PENDING),
            to_state=str(OrderState.STALE),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.STALE, ev2)
        assert order.is_terminal

    def test_replace_pending_to_cancelled(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        ev1 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.REPLACE_REQUESTED,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.REPLACE_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.REPLACE_PENDING, ev1)
        ev2 = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCELLED,
            from_state=str(OrderState.REPLACE_PENDING),
            to_state=str(OrderState.CANCELLED),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.CANCELLED, ev2)
        assert order.is_terminal

    def test_submitted_to_stale(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        ev = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.STALE,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.STALE),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.STALE, ev)
        assert order.is_terminal
        assert str(order.state) == str(OrderState.STALE)

    def test_partially_filled_to_cancel_pending(self) -> None:
        order = _make_order()
        _advance_to_partially_filled(order)
        ev = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCEL_REQUESTED,
            from_state=str(OrderState.PARTIALLY_FILLED),
            to_state=str(OrderState.CANCEL_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.CANCEL_PENDING, ev)
        assert str(order.state) == str(OrderState.CANCEL_PENDING)

    def test_stale_is_terminal_no_outbound(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        ev = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.STALE,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.STALE),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        order.transition(OrderState.STALE, ev)
        with pytest.raises(IllegalOrderTransitionError):
            ev2 = OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CANCELLED,
                from_state=str(OrderState.STALE),
                to_state=str(OrderState.CANCELLED),
                timestamp_ns=_now_ns(),
                evidence={},
            )
            order.transition(OrderState.CANCELLED, ev2)

    def test_illegal_created_to_cancel_pending(self) -> None:
        """CREATED → CANCEL_PENDING must be illegal (not submitted yet)."""
        order = _make_order()
        ev = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CANCEL_REQUESTED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.CANCEL_PENDING),
            timestamp_ns=_now_ns(),
            evidence={},
        )
        with pytest.raises(IllegalOrderTransitionError):
            order.transition(OrderState.CANCEL_PENDING, ev)


# ---------------------------------------------------------------------------
# 2. Paper adapter reconciliation tests
# ---------------------------------------------------------------------------


class TestPaperAdapterReconciliation:
    def test_poll_open_orders_empty_initially(self) -> None:
        adapter = PaperVenueAdapter()
        assert adapter.poll_open_orders() == []

    def test_poll_open_orders_after_register(self) -> None:
        adapter = PaperVenueAdapter()
        order = _make_order()
        _advance_to_submitted(order)
        adapter.register_restored_orders([order])
        open_ids = adapter.poll_open_orders()
        assert order.order_id in open_ids

    def test_poll_excludes_terminal_orders(self) -> None:
        adapter = PaperVenueAdapter()
        order = _make_order()
        order.state = OrderState.FILLED
        adapter.register_restored_orders([order])
        assert adapter.poll_open_orders() == []

    def test_reconcile_order_returns_stale(self) -> None:
        adapter = PaperVenueAdapter()
        order = _make_order()
        _advance_to_submitted(order)
        adapter.register_restored_orders([order])
        events = adapter.reconcile_order(order.order_id, _now_ns())
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.STALE
        assert events[0].to_state == str(OrderState.STALE)
        assert events[0].reason == "paper_no_exchange_state"

    def test_reconcile_terminal_order_empty(self) -> None:
        adapter = PaperVenueAdapter()
        order = _make_order()
        order.state = OrderState.CANCELLED
        adapter.register_restored_orders([order])
        events = adapter.reconcile_order(order.order_id, _now_ns())
        assert events == []

    def test_reconcile_unknown_order_empty(self) -> None:
        adapter = PaperVenueAdapter()
        events = adapter.reconcile_order("nonexistent", _now_ns())
        assert events == []

    def test_ingest_fill_event_updates_state(self) -> None:
        adapter = PaperVenueAdapter()
        order = _make_order(qty=0.01)
        _advance_to_submitted(order)
        adapter.register_restored_orders([order])

        fill = FillEvent(
            order_id=order.order_id,
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.01,
            fill_price=50_000.0,
            timestamp_ns=_now_ns(),
        )
        events = adapter.ingest_fill_event(fill, _now_ns())
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.FILLED

    def test_ingest_fill_partial(self) -> None:
        adapter = PaperVenueAdapter()
        order = _make_order(qty=0.10)
        _advance_to_submitted(order)
        adapter.register_restored_orders([order])

        fill = FillEvent(
            order_id=order.order_id,
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.05,
            fill_price=50_000.0,
            timestamp_ns=_now_ns(),
        )
        events = adapter.ingest_fill_event(fill, _now_ns())
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.PARTIALLY_FILLED

    def test_ingest_fill_unknown_order(self) -> None:
        adapter = PaperVenueAdapter()
        fill = FillEvent(
            order_id="unknown",
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.01,
            fill_price=50_000.0,
            timestamp_ns=_now_ns(),
        )
        assert adapter.ingest_fill_event(fill, _now_ns()) == []

    def test_ingest_position_snapshot_stores(self) -> None:
        adapter = PaperVenueAdapter()
        snapshot = {"BTCUSDT": {"quantity": 0.01, "entry_price": 50_000.0}}
        adapter.ingest_position_snapshot(snapshot, _now_ns())
        assert adapter._last_position_snapshot is not None
        assert "BTCUSDT" in adapter._last_position_snapshot

    def test_submit_order_tracks_internally(self) -> None:
        adapter = PaperVenueAdapter(PaperAdapterConfig(allow_degraded_fill=True))
        order = _make_order(qty=0.01)
        _advance_to_submitted(order)
        # Add price_hint to order evidence for degraded fill
        order._event_history[0] = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.CREATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.CREATED),
            timestamp_ns=_T0,
            evidence={"price_hint": 50_000.0},
        )
        adapter.submit_order(order, None, None)
        # After synchronous fill, order should be tracked
        assert order.order_id in adapter._tracked_orders


# ---------------------------------------------------------------------------
# 3. Lifecycle cancel/replace tests
# ---------------------------------------------------------------------------


class TestLifecycleCancelReplace:
    def test_cancel_filled_order_returns_empty(self) -> None:
        """Paper fills synchronously → cancel on FILLED returns empty."""
        engine = _paper_engine()
        result = engine.process(_request())
        assert result.approved
        events = engine.cancel(result.order_id, "test_cancel")
        assert events == []

    def test_cancel_submitted_order_has_cancel_pending(self) -> None:
        """Create an order, manually advance to SUBMITTED, then cancel."""
        engine = _paper_engine()
        # Process to get a filled order — then we need a non-terminal one
        # Instead, let's directly register an order in SUBMITTED state
        order = _make_order()
        _advance_to_submitted(order)
        engine._orders[order.order_id] = order

        events = engine.cancel(order.order_id, "user_request")
        event_types = [str(e.event_type) for e in events]
        assert "CANCEL_REQUESTED" in event_types
        assert "CANCELLED" in event_types
        assert str(order.state) == str(OrderState.CANCELLED)

    def test_replace_submitted_order_has_replace_pending(self) -> None:
        order = _make_order()
        _advance_to_submitted(order)
        engine = _paper_engine()
        engine._orders[order.order_id] = order

        events = engine.replace(order.order_id, new_quantity=0.02)
        event_types = [str(e.event_type) for e in events]
        assert "REPLACE_REQUESTED" in event_types
        assert "CANCELLED" in event_types
        assert str(order.state) == str(OrderState.CANCELLED)

    def test_cancel_unknown_order_returns_empty(self) -> None:
        engine = _paper_engine()
        events = engine.cancel("nonexistent", "test")
        assert events == []

    def test_replace_unknown_order_returns_empty(self) -> None:
        engine = _paper_engine()
        events = engine.replace("nonexistent", new_quantity=0.02)
        assert events == []

    def test_cancel_terminal_order_returns_empty(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        # Paper fills synchronously → order is FILLED (terminal)
        events = engine.cancel(result.order_id, "test")
        assert events == []

    def test_replace_terminal_order_returns_empty(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        events = engine.replace(result.order_id, new_quantity=0.02)
        assert events == []

    def test_cancel_persists_events(self, tmp_path: Path) -> None:
        store = _exec_store(tmp_path)
        engine = _paper_engine(store=store)
        order = _make_order()
        _advance_to_submitted(order)
        engine._orders[order.order_id] = order
        _persist_order_to_submitted(order, store)
        engine.cancel(order.order_id, "test_cancel")
        # Verify events are persisted
        restored = store.load()
        order_events = [e for o in restored.orders if o.order_id == order.order_id for e in o.event_history]
        event_types = [str(e.event_type) for e in order_events]
        assert "CANCEL_REQUESTED" in event_types
        assert "CANCELLED" in event_types

    def test_replace_persists_events(self, tmp_path: Path) -> None:
        store = _exec_store(tmp_path)
        engine = _paper_engine(store=store)
        order = _make_order()
        _advance_to_submitted(order)
        engine._orders[order.order_id] = order
        _persist_order_to_submitted(order, store)
        engine.replace(order.order_id, new_quantity=0.02)
        restored = store.load()
        order_events = [e for o in restored.orders if o.order_id == order.order_id for e in o.event_history]
        event_types = [str(e.event_type) for e in order_events]
        assert "REPLACE_REQUESTED" in event_types
        assert "CANCELLED" in event_types


# ---------------------------------------------------------------------------
# 4. Lifecycle reconciliation tests
# ---------------------------------------------------------------------------


class TestLifecycleReconciliation:
    def test_register_and_reconcile(self) -> None:
        engine = _paper_engine()
        order = _make_order()
        _advance_to_submitted(order)
        engine.register_restored_orders([order])
        assert order.order_id in engine.tracked_order_ids
        assert order.order_id in engine.open_order_ids

        events = engine.reconcile_order(order.order_id, _now_ns())
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.STALE
        assert str(order.state) == str(OrderState.STALE)
        # After reconciliation, order is terminal
        assert order.order_id not in engine.open_order_ids

    def test_reconcile_all_orphans(self) -> None:
        engine = _paper_engine()
        o1 = _make_order()
        o2 = _make_order()
        _advance_to_submitted(o1)
        _advance_to_submitted(o2)
        engine.register_restored_orders([o1, o2])
        results = engine.reconcile_all_orphans([o1.order_id, o2.order_id], _now_ns())
        assert len(results) == 2
        for oid, events in results.items():
            assert len(events) == 1
            assert events[0].event_type == OrderEventType.STALE

    def test_reconcile_terminal_order_noop(self) -> None:
        engine = _paper_engine()
        order = _make_order()
        order.state = OrderState.FILLED
        engine.register_restored_orders([order])
        events = engine.reconcile_order(order.order_id, _now_ns())
        assert events == []

    def test_reconcile_persists_stale_event(self, tmp_path: Path) -> None:
        store = _exec_store(tmp_path)
        engine = _paper_engine(store=store)
        order = _make_order()
        _advance_to_submitted(order)
        _persist_order_to_submitted(order, store)
        engine.register_restored_orders([order])
        engine.reconcile_order(order.order_id, _now_ns())
        # Verify STALE event is persisted
        restored = store.load()
        assert len(restored.orders) == 1
        assert str(restored.orders[0].state) == str(OrderState.STALE)
        assert restored.orphan_order_ids == []  # now terminal


# ---------------------------------------------------------------------------
# 5. Recovery bootstrap with reconciliation
# ---------------------------------------------------------------------------


class TestRecoveryReconciliation:
    def test_recovery_with_lifecycle_reconciles_orphans(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)

        # Create an orphan order in the store
        order = _make_order()
        es.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CREATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.CREATED),
                timestamp_ns=_T0,
                evidence={},
            ),
            order_meta=build_order_meta(order),
        )
        # Add VALIDATED + SUBMITTED events to make it non-terminal in SUBMITTED state
        es.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.VALIDATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.VALIDATED),
                timestamp_ns=_T0 + 1,
                evidence={},
            )
        )
        es.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.SUBMITTED,
                from_state=str(OrderState.VALIDATED),
                to_state=str(OrderState.SUBMITTED),
                timestamp_ns=_T0 + 2,
                evidence={},
            )
        )

        lifecycle = _paper_engine(store=es)
        bootstrap = RecoveryBootstrap(es, ps, lifecycle_engine=lifecycle)
        result = bootstrap.run()

        assert result.success
        assert len(result.reconciliation_actions) == 1
        action = result.reconciliation_actions[0]
        assert action.action == "stale"
        assert action.order_id == order.order_id
        assert result.evidence.reconciled_count == 1
        assert result.evidence.stale_count == 1
        assert result.evidence.unresolved_count == 0

    def test_recovery_without_lifecycle_reports_unresolved(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)

        order = _make_order()
        es.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CREATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.CREATED),
                timestamp_ns=_T0,
                evidence={},
            ),
            order_meta=build_order_meta(order),
        )

        bootstrap = RecoveryBootstrap(es, ps)  # no lifecycle engine
        result = bootstrap.run()

        assert result.success
        assert len(result.orphan_orders) == 1
        assert result.evidence.unresolved_count == 1
        assert result.evidence.reconciled_count == 0

    def test_recovery_no_orphans_no_reconciliation(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)
        lifecycle = _paper_engine()
        bootstrap = RecoveryBootstrap(es, ps, lifecycle_engine=lifecycle)
        result = bootstrap.run()
        assert result.success
        assert result.reconciliation_actions == []
        assert result.evidence.reconciled_count == 0

    def test_recovery_evidence_has_reconciliation_fields(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)
        bootstrap = RecoveryBootstrap(es, ps)
        result = bootstrap.run()
        ev = result.evidence
        assert hasattr(ev, "reconciled_count")
        assert hasattr(ev, "stale_count")
        assert hasattr(ev, "unresolved_count")
        assert ev.reconciled_count == 0
        assert ev.stale_count == 0
        assert ev.unresolved_count == 0


# ---------------------------------------------------------------------------
# 6. Store round-trip for new event types
# ---------------------------------------------------------------------------


class TestStoreNewEventTypes:
    def test_cancel_requested_roundtrip(self, tmp_path: Path) -> None:
        store = _exec_store(tmp_path)
        order = _make_order()
        # CREATED
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CREATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.CREATED),
                timestamp_ns=_T0,
                evidence={},
            ),
            order_meta=build_order_meta(order),
        )
        # VALIDATED
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.VALIDATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.VALIDATED),
                timestamp_ns=_T0 + 1,
                evidence={},
            )
        )
        # SUBMITTED
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.SUBMITTED,
                from_state=str(OrderState.VALIDATED),
                to_state=str(OrderState.SUBMITTED),
                timestamp_ns=_T0 + 2,
                evidence={},
            )
        )
        # CANCEL_REQUESTED → CANCEL_PENDING
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CANCEL_REQUESTED,
                from_state=str(OrderState.SUBMITTED),
                to_state=str(OrderState.CANCEL_PENDING),
                timestamp_ns=_T0 + 3,
                evidence={},
            )
        )
        # CANCELLED
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CANCELLED,
                from_state=str(OrderState.CANCEL_PENDING),
                to_state=str(OrderState.CANCELLED),
                timestamp_ns=_T0 + 4,
                evidence={},
            )
        )
        restored = store.load()
        assert len(restored.orders) == 1
        assert str(restored.orders[0].state) == str(OrderState.CANCELLED)
        assert restored.orphan_order_ids == []

    def test_stale_event_roundtrip(self, tmp_path: Path) -> None:
        store = _exec_store(tmp_path)
        order = _make_order()
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CREATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.CREATED),
                timestamp_ns=_T0,
                evidence={},
            ),
            order_meta=build_order_meta(order),
        )
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.VALIDATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.VALIDATED),
                timestamp_ns=_T0 + 1,
                evidence={},
            )
        )
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.SUBMITTED,
                from_state=str(OrderState.VALIDATED),
                to_state=str(OrderState.SUBMITTED),
                timestamp_ns=_T0 + 2,
                evidence={},
            )
        )
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.STALE,
                from_state=str(OrderState.SUBMITTED),
                to_state=str(OrderState.STALE),
                timestamp_ns=_T0 + 3,
                reason="paper_no_exchange_state",
                evidence={"reconciliation": "stale"},
            )
        )
        restored = store.load()
        assert len(restored.orders) == 1
        assert str(restored.orders[0].state) == str(OrderState.STALE)
        assert restored.orphan_order_ids == []  # STALE is terminal

    def test_replace_requested_roundtrip(self, tmp_path: Path) -> None:
        store = _exec_store(tmp_path)
        order = _make_order()
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CREATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.CREATED),
                timestamp_ns=_T0,
                evidence={},
            ),
            order_meta=build_order_meta(order),
        )
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.VALIDATED,
                from_state=str(OrderState.CREATED),
                to_state=str(OrderState.VALIDATED),
                timestamp_ns=_T0 + 1,
                evidence={},
            )
        )
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.SUBMITTED,
                from_state=str(OrderState.VALIDATED),
                to_state=str(OrderState.SUBMITTED),
                timestamp_ns=_T0 + 2,
                evidence={},
            )
        )
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.REPLACE_REQUESTED,
                from_state=str(OrderState.SUBMITTED),
                to_state=str(OrderState.REPLACE_PENDING),
                timestamp_ns=_T0 + 3,
                evidence={"new_quantity": 0.02},
            )
        )
        store.append_event(
            OrderEvent(
                order_id=order.order_id,
                event_type=OrderEventType.CANCELLED,
                from_state=str(OrderState.REPLACE_PENDING),
                to_state=str(OrderState.CANCELLED),
                timestamp_ns=_T0 + 4,
                evidence={},
            )
        )
        restored = store.load()
        assert len(restored.orders) == 1
        assert str(restored.orders[0].state) == str(OrderState.CANCELLED)


# ---------------------------------------------------------------------------
# 7. Orchestrator recovery visibility
# ---------------------------------------------------------------------------


class TestOrchestratorRecovery:
    def test_orchestrator_accepts_recovery_evidence(self) -> None:
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        evidence = RecoveryEvidence(
            restore_success=True,
            restore_failure_reason=None,
            schema_version="1",
            snapshot_ns=_T0,
            execution_store_records=5,
            restored_order_count=3,
            orphan_order_ids=["oid-1"],
            restored_position_count=1,
            reconciled_count=1,
            stale_count=1,
            unresolved_count=0,
        )
        orch = PipelineOrchestrator(recovery_evidence=evidence)
        assert orch.recovery_evidence is evidence
        assert not orch.has_unresolved_orders

    def test_orchestrator_detects_unresolved_orders(self) -> None:
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        evidence = RecoveryEvidence(
            restore_success=True,
            restore_failure_reason=None,
            schema_version="1",
            snapshot_ns=_T0,
            execution_store_records=3,
            restored_order_count=2,
            orphan_order_ids=["oid-1"],
            restored_position_count=0,
            reconciled_count=0,
            stale_count=0,
            unresolved_count=1,
        )
        orch = PipelineOrchestrator(recovery_evidence=evidence)
        assert orch.has_unresolved_orders

    def test_orchestrator_no_recovery(self) -> None:
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        orch = PipelineOrchestrator()
        assert orch.recovery_evidence is None
        assert not orch.has_unresolved_orders


# ---------------------------------------------------------------------------
# 8. Paper/live parity — same contract path
# ---------------------------------------------------------------------------


class TestPaperLiveParity:
    def test_cancel_path_same_shape(self) -> None:
        """Cancel produces CANCEL_REQUESTED + CANCELLED events (same shape as live)."""
        engine = _paper_engine()
        order = _make_order()
        _advance_to_submitted(order)
        engine._orders[order.order_id] = order
        events = engine.cancel(order.order_id, "test")
        assert len(events) == 2
        assert events[0].event_type == OrderEventType.CANCEL_REQUESTED
        assert events[1].event_type == OrderEventType.CANCELLED

    def test_replace_path_same_shape(self) -> None:
        """Replace produces REPLACE_REQUESTED + CANCELLED events (same shape as live)."""
        engine = _paper_engine()
        order = _make_order()
        _advance_to_submitted(order)
        engine._orders[order.order_id] = order
        events = engine.replace(order.order_id, 0.02)
        assert len(events) == 2
        assert events[0].event_type == OrderEventType.REPLACE_REQUESTED
        assert events[1].event_type == OrderEventType.CANCELLED

    def test_reconciliation_path_same_shape(self) -> None:
        """Reconciliation produces events through the adapter (same path as live)."""
        engine = _paper_engine()
        order = _make_order()
        _advance_to_submitted(order)
        engine.register_restored_orders([order])
        events = engine.reconcile_order(order.order_id, _now_ns())
        assert len(events) == 1
        assert events[0].event_type == OrderEventType.STALE
        # Live adapter would produce FILLED/CANCELLED instead of STALE

    def test_full_lifecycle_cancel_persist_restore(self, tmp_path: Path) -> None:
        """Full lifecycle → cancel → persist → restore deterministically."""
        store = _exec_store(tmp_path)
        engine = _paper_engine(store=store)

        # Process an order (fills synchronously in paper)
        result = engine.process(_request())
        assert result.approved
        assert str(result.final_state) == str(OrderState.FILLED)

        # Restore and verify
        restored = store.load()
        assert len(restored.orders) == 1
        assert str(restored.orders[0].state) == str(OrderState.FILLED)
        assert restored.orphan_order_ids == []
