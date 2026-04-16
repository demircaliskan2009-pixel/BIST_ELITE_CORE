"""Durable execution state persistence — Phase 6E.

Append-safe JSONL log for order lifecycle events.  Each line is one JSON record.
The CREATED record carries the full order metadata (order_meta) needed to
reconstruct Order objects during restore.

Record format::

    {"schema_version": "1", "record_type": "order_event",
     "order_id": "...", "event_type": "CREATED",
     "from_state": "CREATED", "to_state": "CREATED",
     "timestamp_ns": 1234567890, "reason": null,
     "fill_event": null, "evidence": {...},
     "order_meta": {
         "symbol": "BTCUSDT", "exchange": "binance",
         "intent": "buy", "mode": "paper",
         "requested_quantity": 0.01, "created_at_ns": 1234567890
     }}

Restore rules:
  - Read all lines.  Any malformed line → raise ExecutionStoreCorruptError
    (fail-closed; do NOT skip bad lines).
  - Group by order_id, replay events in timestamp order.
  - Non-terminal orders at end of replay → identified as orphans.

Invariants:
  - Append-only: never mutate or delete existing records.
  - No silent data coercion on read.
  - Thread safety: NOT guaranteed — single-threaded pipeline use only.
  - Path management: caller is responsible for providing a valid path.

PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from crypto_core.execution.events import FillEvent, OrderEvent, OrderEventType
from crypto_core.execution.models import ExecutionMode, OrderIntent
from crypto_core.execution.state_machine import (
    IllegalOrderTransitionError,
    Order,
    OrderState,
)

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1"
_RECORD_TYPE = "order_event"

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExecutionStoreCorruptError(RuntimeError):
    """Raised when a persisted execution record is malformed or inconsistent.

    Fail-closed: any corruption → STOP restore, do not silently skip.
    """


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _fill_event_to_dict(fe: FillEvent) -> dict:
    return {
        "order_id": fe.order_id,
        "symbol": fe.symbol,
        "exchange": fe.exchange,
        "intent": str(fe.intent),
        "filled_quantity": fe.filled_quantity,
        "fill_price": fe.fill_price,
        "timestamp_ns": fe.timestamp_ns,
        "slippage_bps": fe.slippage_bps,
        "spread_bps": fe.spread_bps,
        "participation_pct": fe.participation_pct,
        "evidence": fe.evidence,
    }


def _fill_event_from_dict(d: dict) -> FillEvent:
    try:
        return FillEvent(
            order_id=d["order_id"],
            symbol=d["symbol"],
            exchange=d["exchange"],
            intent=OrderIntent(d["intent"]),
            filled_quantity=float(d["filled_quantity"]),
            fill_price=float(d["fill_price"]),
            timestamp_ns=int(d["timestamp_ns"]),
            slippage_bps=d.get("slippage_bps"),
            spread_bps=d.get("spread_bps"),
            participation_pct=d.get("participation_pct"),
            evidence=d.get("evidence", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExecutionStoreCorruptError(f"Malformed fill_event record: {d!r}") from exc


def _order_event_to_dict(ev: OrderEvent, order_meta: dict | None = None) -> dict:
    """Serialize one OrderEvent to a JSONL-compatible dict.

    order_meta must be supplied only for CREATED events.  It carries the
    Order-level metadata (symbol, exchange, intent, mode, requested_quantity,
    created_at_ns) needed to rebuild the Order on restore.
    """
    d: dict = {
        "schema_version": _SCHEMA_VERSION,
        "record_type": _RECORD_TYPE,
        "order_id": ev.order_id,
        "event_type": str(ev.event_type),
        "from_state": ev.from_state,
        "to_state": ev.to_state,
        "timestamp_ns": ev.timestamp_ns,
        "reason": ev.reason,
        "fill_event": _fill_event_to_dict(ev.fill_event) if ev.fill_event is not None else None,
        "evidence": ev.evidence,
    }
    if order_meta is not None:
        d["order_meta"] = order_meta
    return d


def _order_event_from_dict(d: dict) -> OrderEvent:
    try:
        fill_event_raw = d.get("fill_event")
        fill_event = _fill_event_from_dict(fill_event_raw) if fill_event_raw is not None else None
        return OrderEvent(
            order_id=d["order_id"],
            event_type=OrderEventType(d["event_type"]),
            from_state=d["from_state"],
            to_state=d["to_state"],
            timestamp_ns=int(d["timestamp_ns"]),
            reason=d.get("reason"),
            fill_event=fill_event,
            evidence=d.get("evidence", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExecutionStoreCorruptError(f"Malformed order_event record: {d!r}") from exc


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class RestoredExecutionState:
    """Result of loading persisted execution state.

    orders:           all fully-replayed Order objects (terminal + non-terminal).
    orphan_order_ids: order IDs that were non-terminal at restore time.
                      These must be explicitly resolved before resuming.
    total_records:    total JSONL lines read (for audit).
    """

    orders: list[Order] = field(default_factory=list)
    orphan_order_ids: list[str] = field(default_factory=list)
    total_records: int = 0


# ---------------------------------------------------------------------------
# ExecutionStateStore
# ---------------------------------------------------------------------------


class ExecutionStateStore:
    """Append-only JSONL store for order lifecycle events.

    Usage::

        store = ExecutionStateStore(path=Path("runtime/execution_state.jsonl"))
        # On CREATED event — include order_meta so Order can be restored:
        meta = _build_order_meta(order)
        store.append_event(created_event, order_meta=meta)
        # All subsequent events — no order_meta needed:
        store.append_event(fill_event)
        # On startup:
        state = store.load()
        for orphan_id in state.orphan_order_ids:
            # handle unresolved orders ...

    Invariants:
      - One JSONL record per line.
      - Append-only; never mutates existing lines.
      - load() fails closed on any malformed line.
      - Not thread-safe — use from single pipeline thread only.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append_event(
        self,
        event: OrderEvent,
        order_meta: dict | None = None,
    ) -> None:
        """Append one order event to the JSONL log.

        Args:
            event:      the OrderEvent to persist.
            order_meta: must be supplied for CREATED events only.  Must include:
                        symbol, exchange, intent, mode, requested_quantity,
                        created_at_ns.  All other event types: pass None.
        """
        record = _order_event_to_dict(event, order_meta=order_meta)
        line = json.dumps(record, separators=(",", ":"), default=str)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def load(self) -> RestoredExecutionState:
        """Load and replay all persisted events.

        Returns:
            RestoredExecutionState with fully-replayed Order objects and
            a list of orphan (non-terminal) order IDs.

        Raises:
            ExecutionStoreCorruptError: on any malformed line (fail-closed).
        """
        if not self._path.exists():
            return RestoredExecutionState()

        raw_records: list[dict] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ExecutionStoreCorruptError(f"JSON decode error at line {lineno}: {exc}") from exc
                if not isinstance(record, dict):
                    raise ExecutionStoreCorruptError(f"Non-dict record at line {lineno}: {line!r}")
                _validate_schema(record, lineno)
                raw_records.append(record)

        return _replay_records(raw_records)


# ---------------------------------------------------------------------------
# Order meta builder (used by lifecycle engine)
# ---------------------------------------------------------------------------


def build_order_meta(order: Order) -> dict:
    """Build the order_meta dict required for CREATED event persistence."""
    return {
        "symbol": order.symbol,
        "exchange": order.exchange,
        "intent": str(order.intent),
        "mode": str(order.mode),
        "requested_quantity": order.requested_quantity,
        "created_at_ns": order.created_at_ns,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_schema(record: dict, lineno: int) -> None:
    """Fail-closed schema validation for one record."""
    version = record.get("schema_version")
    if version != _SCHEMA_VERSION:
        raise ExecutionStoreCorruptError(
            f"Unknown schema_version={version!r} at line {lineno} (expected {_SCHEMA_VERSION!r})"
        )
    rtype = record.get("record_type")
    if rtype != _RECORD_TYPE:
        raise ExecutionStoreCorruptError(f"Unknown record_type={rtype!r} at line {lineno} (expected {_RECORD_TYPE!r})")
    required = {"order_id", "event_type", "from_state", "to_state", "timestamp_ns"}
    missing = required - set(record)
    if missing:
        raise ExecutionStoreCorruptError(f"Missing required fields {sorted(missing)!r} at line {lineno}")


def _replay_records(raw_records: list[dict]) -> RestoredExecutionState:
    """Replay serialized records to reconstruct Order objects.

    Groups records by order_id, then replays each group in timestamp order.
    Detects and surfaces non-terminal (orphan) orders.
    """
    # Group records by order_id (preserving insertion order)
    by_order: dict[str, list[dict]] = {}
    for rec in raw_records:
        oid = rec["order_id"]
        by_order.setdefault(oid, []).append(rec)

    orders: list[Order] = []
    orphan_ids: list[str] = []

    for oid, records in by_order.items():
        # Sort by timestamp_ns for deterministic replay
        records.sort(key=lambda r: int(r["timestamp_ns"]))

        # First record must be the CREATED event with order_meta
        first = records[0]
        if first.get("event_type") != "CREATED":
            raise ExecutionStoreCorruptError(
                f"Order {oid!r}: first event is {first.get('event_type')!r}, expected CREATED"
            )
        order_meta = first.get("order_meta")
        if order_meta is None:
            raise ExecutionStoreCorruptError(f"Order {oid!r}: CREATED event missing order_meta")

        # Construct Order from meta
        try:
            order = Order(
                order_id=oid,
                symbol=order_meta["symbol"],
                exchange=order_meta["exchange"],
                intent=OrderIntent(order_meta["intent"]),
                mode=ExecutionMode(order_meta["mode"]),
                requested_quantity=float(order_meta["requested_quantity"]),
                created_at_ns=int(order_meta["created_at_ns"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExecutionStoreCorruptError(
                f"Order {oid!r}: cannot reconstruct from order_meta {order_meta!r}: {exc}"
            ) from exc

        # Replay all events
        for rec in records:
            event = _order_event_from_dict(rec)

            if event.event_type == OrderEventType.CREATED:
                # Replace the auto-generated CREATED event with the persisted one
                order._event_history.clear()
                order._event_history.append(event)
                continue

            # Apply fill data before transition
            if event.fill_event is not None:
                order.apply_fill(event.fill_event)

            # Apply state transition
            try:
                to_state = OrderState(event.to_state)
                order.transition(to_state, event)
            except (IllegalOrderTransitionError, ValueError) as exc:
                raise ExecutionStoreCorruptError(
                    f"Order {oid!r}: illegal transition during replay {event.from_state!r} → {event.to_state!r}: {exc}"
                ) from exc

        orders.append(order)
        if not order.is_terminal:
            orphan_ids.append(oid)

    return RestoredExecutionState(
        orders=orders,
        orphan_order_ids=orphan_ids,
        total_records=len(raw_records),
    )
