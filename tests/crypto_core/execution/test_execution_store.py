"""Tests for ExecutionStateStore — Phase 6E.

Covers:
  - append_event / load round-trip for all event types
  - CREATED event with and without order_meta
  - Multiple orders in one store
  - Terminal order not in orphan list
  - Non-terminal order in orphan list
  - Fail-closed on malformed JSON
  - Fail-closed on missing required fields
  - Fail-closed on wrong schema_version
  - Fail-closed on missing order_meta in CREATED event
  - Fail-closed on orphan order_meta with wrong values
  - Empty store returns empty RestoredExecutionState
  - Replay determinism (multiple append + load)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from crypto_core.execution.events import FillEvent, OrderEvent, OrderEventType
from crypto_core.execution.models import ExecutionMode, OrderIntent
from crypto_core.execution.state_machine import Order, OrderState
from crypto_core.execution.store import (
    ExecutionStateStore,
    ExecutionStoreCorruptError,
    RestoredExecutionState,
    _order_event_to_dict,
    build_order_meta,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "execution_state.jsonl"


@pytest.fixture
def store(store_path: Path) -> ExecutionStateStore:
    return ExecutionStateStore(path=store_path)


def _make_order(ts: int | None = None) -> Order:
    ts = ts or time.time_ns()
    return Order.create(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        mode=ExecutionMode.PAPER,
        quantity=0.01,
        timestamp_ns=ts,
    )


def _created_event(order: Order, ts: int) -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.CREATED,
        from_state=str(OrderState.CREATED),
        to_state=str(OrderState.CREATED),
        timestamp_ns=ts,
        evidence={"symbol": "BTCUSDT"},
    )


def _validated_event(order: Order, ts: int) -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.VALIDATED,
        from_state=str(OrderState.CREATED),
        to_state=str(OrderState.VALIDATED),
        timestamp_ns=ts,
        evidence={},
    )


def _filled_event(order: Order, ts: int) -> OrderEvent:
    fill = FillEvent(
        order_id=order.order_id,
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        filled_quantity=0.01,
        fill_price=50000.0,
        timestamp_ns=ts,
    )
    return OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.FILLED,
        from_state=str(OrderState.SUBMITTED),
        to_state=str(OrderState.FILLED),
        timestamp_ns=ts,
        fill_event=fill,
        evidence={"fill_price": 50000.0},
    )


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_empty_store_returns_empty_state(self, store: ExecutionStateStore) -> None:
        state = store.load()
        assert isinstance(state, RestoredExecutionState)
        assert state.orders == []
        assert state.orphan_order_ids == []
        assert state.total_records == 0

    def test_store_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "store.jsonl"
        s = ExecutionStateStore(path=nested)
        assert nested.parent.exists()
        _ = s.load()  # empty — no error

    def test_single_filled_order(self, store: ExecutionStateStore) -> None:
        ts = 1_000_000_000
        order = _make_order(ts)
        created = _created_event(order, ts)
        meta = build_order_meta(order)

        store.append_event(created, order_meta=meta)

        validated = _validated_event(order, ts + 1)
        store.append_event(validated)

        # Transition to SUBMITTED
        sub_event = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.SUBMITTED,
            from_state=str(OrderState.VALIDATED),
            to_state=str(OrderState.SUBMITTED),
            timestamp_ns=ts + 2,
            evidence={},
        )
        order.transition(OrderState.VALIDATED, validated)
        order.transition(OrderState.SUBMITTED, sub_event)
        store.append_event(sub_event)

        filled = _filled_event(order, ts + 3)
        order.apply_fill(filled.fill_event)
        order.transition(OrderState.FILLED, filled)
        store.append_event(filled)

        state = store.load()
        assert state.total_records == 4
        assert len(state.orders) == 1
        assert state.orphan_order_ids == []  # FILLED is terminal

        restored = state.orders[0]
        assert restored.order_id == order.order_id
        assert str(restored.state) == str(OrderState.FILLED)
        assert restored.filled_quantity == pytest.approx(0.01)
        assert restored.average_fill_price == pytest.approx(50000.0)

    def test_non_terminal_order_is_orphan(self, store: ExecutionStateStore) -> None:
        ts = 2_000_000_000
        order = _make_order(ts)
        meta = build_order_meta(order)
        created = _created_event(order, ts)
        store.append_event(created, order_meta=meta)
        # Only CREATED persisted — order never reached terminal state
        state = store.load()
        assert state.orphan_order_ids == [order.order_id]

    def test_multiple_orders_both_restored(self, store: ExecutionStateStore) -> None:
        ts = 3_000_000_000
        orders = [_make_order(ts + i) for i in range(3)]
        for order in orders:
            meta = build_order_meta(order)
            created = _created_event(order, ts)
            store.append_event(created, order_meta=meta)

        state = store.load()
        assert len(state.orders) == 3
        assert len(state.orphan_order_ids) == 3  # none terminal


class TestFillEventRoundTrip:
    def test_fill_event_serialization(self, store: ExecutionStateStore) -> None:
        ts = 4_000_000_000
        order = _make_order(ts)
        meta = build_order_meta(order)
        created = _created_event(order, ts)
        store.append_event(created, order_meta=meta)

        validated = _validated_event(order, ts + 1)
        order.transition(OrderState.VALIDATED, validated)
        store.append_event(validated)

        sub_event = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.SUBMITTED,
            from_state=str(OrderState.VALIDATED),
            to_state=str(OrderState.SUBMITTED),
            timestamp_ns=ts + 2,
            evidence={},
        )
        order.transition(OrderState.SUBMITTED, sub_event)
        store.append_event(sub_event)

        fill = FillEvent(
            order_id=order.order_id,
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.005,
            fill_price=48000.0,
            timestamp_ns=ts + 3,
            slippage_bps=2.5,
            spread_bps=1.0,
            participation_pct=50.0,
            evidence={"book_depth": 10.0},
        )
        filled_ev = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.FILLED,
            from_state=str(OrderState.SUBMITTED),
            to_state=str(OrderState.FILLED),
            timestamp_ns=ts + 3,
            fill_event=fill,
            evidence={},
        )
        order.apply_fill(fill)
        order.transition(OrderState.FILLED, filled_ev)
        store.append_event(filled_ev)

        state = store.load()
        restored_order = state.orders[0]
        # The fill was applied during replay
        assert restored_order.average_fill_price == pytest.approx(48000.0)
        assert restored_order.filled_quantity == pytest.approx(0.005)

    def test_none_fill_event_preserved(self, store: ExecutionStateStore) -> None:
        ts = 5_000_000_000
        order = _make_order(ts)
        meta = build_order_meta(order)
        created = _created_event(order, ts)
        store.append_event(created, order_meta=meta)

        validated = _validated_event(order, ts + 1)
        store.append_event(validated)

        state = store.load()
        # CREATED + VALIDATED — no fill event on VALIDATED record
        assert state.orders[0].average_fill_price is None


# ---------------------------------------------------------------------------
# Fail-closed validation
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_malformed_json_raises(self, store_path: Path) -> None:
        store_path.write_text('not-json\n{"valid": "json"}\n', encoding="utf-8")
        s = ExecutionStateStore(path=store_path)
        with pytest.raises(ExecutionStoreCorruptError, match="JSON decode error"):
            s.load()

    def test_wrong_schema_version_raises(self, store_path: Path) -> None:
        record = {
            "schema_version": "99",
            "record_type": "order_event",
            "order_id": "x",
            "event_type": "CREATED",
            "from_state": "CREATED",
            "to_state": "CREATED",
            "timestamp_ns": 1,
        }
        store_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        s = ExecutionStateStore(path=store_path)
        with pytest.raises(ExecutionStoreCorruptError, match="schema_version"):
            s.load()

    def test_wrong_record_type_raises(self, store_path: Path) -> None:
        record = {
            "schema_version": "1",
            "record_type": "unknown_type",
            "order_id": "x",
            "event_type": "CREATED",
            "from_state": "CREATED",
            "to_state": "CREATED",
            "timestamp_ns": 1,
        }
        store_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        s = ExecutionStateStore(path=store_path)
        with pytest.raises(ExecutionStoreCorruptError, match="record_type"):
            s.load()

    def test_missing_required_field_raises(self, store_path: Path) -> None:
        record = {
            "schema_version": "1",
            "record_type": "order_event",
            # missing order_id, event_type, from_state, to_state, timestamp_ns
        }
        store_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        s = ExecutionStateStore(path=store_path)
        with pytest.raises(ExecutionStoreCorruptError, match="Missing required fields"):
            s.load()

    def test_first_event_not_created_raises(self, store: ExecutionStateStore, store_path: Path) -> None:
        ts = 6_000_000_000
        order = _make_order(ts)
        # Append a non-CREATED first event (no prior CREATED)
        record = {
            "schema_version": "1",
            "record_type": "order_event",
            "order_id": order.order_id,
            "event_type": "VALIDATED",
            "from_state": str(OrderState.CREATED),
            "to_state": str(OrderState.VALIDATED),
            "timestamp_ns": ts,
            "reason": None,
            "fill_event": None,
            "evidence": {},
        }
        store_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with pytest.raises(ExecutionStoreCorruptError, match="first event"):
            store.load()

    def test_created_event_missing_order_meta_raises(self, store_path: Path) -> None:
        record = {
            "schema_version": "1",
            "record_type": "order_event",
            "order_id": "some-id",
            "event_type": "CREATED",
            "from_state": "CREATED",
            "to_state": "CREATED",
            "timestamp_ns": 1,
            "reason": None,
            "fill_event": None,
            "evidence": {},
            # order_meta deliberately absent
        }
        store_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        s = ExecutionStateStore(path=store_path)
        with pytest.raises(ExecutionStoreCorruptError, match="order_meta"):
            s.load()

    def test_non_dict_line_raises(self, store_path: Path) -> None:
        store_path.write_text('["list", "not", "dict"]\n', encoding="utf-8")
        s = ExecutionStateStore(path=store_path)
        with pytest.raises(ExecutionStoreCorruptError, match="Non-dict record"):
            s.load()

    def test_blank_lines_ignored(self, store: ExecutionStateStore, store_path: Path) -> None:
        ts = 7_000_000_000
        order = _make_order(ts)
        meta = build_order_meta(order)
        created = _created_event(order, ts)
        record_str = json.dumps(_order_event_to_dict(created, order_meta=meta))
        # Surround with blank lines
        store_path.write_text(f"\n\n{record_str}\n\n", encoding="utf-8")
        state = store.load()
        assert state.total_records == 1


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_replay_is_deterministic(self, store: ExecutionStateStore) -> None:
        """Same events persisted twice → identical state on load."""
        ts = 8_000_000_000
        order = _make_order(ts)
        meta = build_order_meta(order)
        created = _created_event(order, ts)
        store.append_event(created, order_meta=meta)
        validated = _validated_event(order, ts + 1)
        store.append_event(validated)

        state1 = store.load()
        state2 = store.load()
        assert state1.orders[0].order_id == state2.orders[0].order_id
        assert str(state1.orders[0].state) == str(state2.orders[0].state)

    def test_build_order_meta_keys(self) -> None:
        ts = 9_000_000_000
        order = _make_order(ts)
        meta = build_order_meta(order)
        assert set(meta.keys()) == {"symbol", "exchange", "intent", "mode", "requested_quantity", "created_at_ns"}
        assert meta["symbol"] == "BTCUSDT"
        assert meta["exchange"] == "binance"
