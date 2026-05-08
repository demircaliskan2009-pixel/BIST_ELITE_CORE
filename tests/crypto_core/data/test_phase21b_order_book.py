from __future__ import annotations

import ast
import json
from pathlib import Path

from crypto_core.data.order_book import (
    OrderBookState,
    apply_order_book_delta,
    build_order_book_state_from_snapshot,
    order_book_state_from_dict,
    order_book_state_ready,
    order_book_state_to_dict,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot, VenueId


def test_valid_snapshot_builds_ready_state():
    result = build_order_book_state_from_snapshot(_snapshot())

    assert result.applied is True
    assert result.state is not None
    assert order_book_state_ready(result.state) is True
    assert result.state.last_sequence_id == 10
    assert tuple(level.price for level in result.state.bids) == (100.0, 99.0)
    assert tuple(level.price for level in result.state.asks) == (101.0, 102.0)


def test_crossed_snapshot_rejected():
    result = build_order_book_state_from_snapshot(
        _unsafe_snapshot(
            bids=(OrderBookLevel(100.0, 1.0),),
            asks=(OrderBookLevel(99.0, 1.0),),
        )
    )

    assert result.applied is False
    assert result.state is None
    assert "order_book:crossed" in result.rejection_reasons


def test_empty_side_rejected():
    result = build_order_book_state_from_snapshot(_unsafe_snapshot(bids=()))

    assert result.applied is False
    assert result.state is None
    assert "order_book:bids_empty" in result.rejection_reasons


def test_non_positive_level_rejected():
    result = build_order_book_state_from_snapshot(
        _unsafe_snapshot(bids=(OrderBookLevel(100.0, 0.0), OrderBookLevel(99.0, 1.0)))
    )

    assert result.applied is False
    assert "order_book:bids_invalid_quantity" in result.rejection_reasons


def test_duplicate_price_levels_rejected():
    result = build_order_book_state_from_snapshot(
        _unsafe_snapshot(bids=(OrderBookLevel(100.0, 1.0), OrderBookLevel(100.0, 2.0)))
    )

    assert result.applied is False
    assert "order_book:bids_duplicate_price" in result.rejection_reasons


def test_bid_ordering_is_rejected_fail_closed():
    result = build_order_book_state_from_snapshot(
        _unsafe_snapshot(bids=(OrderBookLevel(99.0, 1.0), OrderBookLevel(100.0, 1.0)))
    )

    assert result.applied is False
    assert "order_book:bids_not_descending" in result.rejection_reasons


def test_ask_ordering_is_rejected_fail_closed():
    result = build_order_book_state_from_snapshot(
        _unsafe_snapshot(asks=(OrderBookLevel(102.0, 1.0), OrderBookLevel(101.0, 1.0)))
    )

    assert result.applied is False
    assert "order_book:asks_not_ascending" in result.rejection_reasons


def test_valid_delta_updates_existing_level():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(100.0, 2.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is True
    assert result.state is not None
    assert result.state.bids[0] == OrderBookLevel(100.0, 2.0)
    assert result.state.last_sequence_id == 11


def test_valid_delta_inserts_new_level():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(98.5, 3.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is True
    assert result.state is not None
    assert tuple(level.price for level in result.state.bids) == (100.0, 99.0, 98.5)


def test_valid_delta_deletes_level_with_size_zero():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(99.0, 0.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is True
    assert result.state is not None
    assert tuple(level.price for level in result.state.bids) == (100.0,)


def test_delta_venue_mismatch_rejected():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            venue_id=VenueId.DERIBIT,
            bid_updates=(OrderBookLevel(100.0, 2.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is False
    assert result.state == state
    assert "order_book:venue_mismatch" in result.rejection_reasons


def test_delta_symbol_mismatch_rejected():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            symbol="ETHUSDT",
            canonical_symbol="ETH-USDT-PERP",
            bid_updates=(OrderBookLevel(100.0, 2.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is False
    assert result.state == state
    assert "order_book:symbol_mismatch" in result.rejection_reasons


def test_delta_prev_update_id_mismatch_rejected():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(100.0, 2.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=9,
        ),
    )

    assert result.applied is False
    assert result.state == state
    assert result.resync_required is True
    assert result.gap_detected is True
    assert "order_book:prev_update_id_mismatch" in result.rejection_reasons


def test_delta_sequence_gap_rejected():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(100.0, 2.0),),
            first_update_id=12,
            final_update_id=12,
            prev_update_id=10,
        ),
    )

    assert result.applied is False
    assert result.resync_required is True
    assert result.gap_detected is True
    assert "order_book:sequence_gap" in result.rejection_reasons


def test_delta_no_updates_rejected():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _unsafe_delta(bid_updates=(), ask_updates=(), first_update_id=11, final_update_id=11, prev_update_id=10),
    )

    assert result.applied is False
    assert result.state == state
    assert "order_book:no_updates" in result.rejection_reasons


def test_delta_causing_crossed_book_rejected():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(101.5, 1.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is False
    assert result.state == state
    assert result.resync_required is True
    assert "order_book:crossed" in result.rejection_reasons


def test_delta_causing_empty_side_rejected():
    state = build_order_book_state_from_snapshot(
        _snapshot(bids=(OrderBookLevel(100.0, 1.0),), asks=(OrderBookLevel(101.0, 1.0),), depth=1)
    ).state
    assert state is not None

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(100.0, 0.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is False
    assert result.state == state
    assert result.resync_required is True
    assert "order_book:empty_side" in result.rejection_reasons


def test_duplicate_updates_in_delta_rejected():
    state = _ready_state()

    result = apply_order_book_delta(
        state,
        _delta(
            bid_updates=(OrderBookLevel(100.0, 2.0), OrderBookLevel(100.0, 3.0)),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is False
    assert result.state == state
    assert "order_book:bid_updates_duplicate_price" in result.rejection_reasons


def test_input_state_immutable_unchanged_after_failed_delta():
    state = _ready_state()
    before_payload = order_book_state_to_dict(state)

    result = apply_order_book_delta(
        state,
        _delta(
            ask_updates=(OrderBookLevel(99.5, 1.0),),
            first_update_id=11,
            final_update_id=11,
            prev_update_id=10,
        ),
    )

    assert result.applied is False
    assert result.state == state
    assert order_book_state_to_dict(state) == before_payload


def test_deterministic_replay_same_snapshot_and_deltas_gives_identical_state():
    snapshot = _snapshot()
    deltas = (
        _delta(bid_updates=(OrderBookLevel(100.0, 2.0),), first_update_id=11, final_update_id=11, prev_update_id=10),
        _delta(ask_updates=(OrderBookLevel(102.5, 1.0),), first_update_id=12, final_update_id=12, prev_update_id=11),
    )

    first = _replay(snapshot, deltas)
    second = _replay(snapshot, deltas)

    assert first is not None
    assert second is not None
    assert order_book_state_to_dict(first) == order_book_state_to_dict(second)


def test_order_book_state_serializer_roundtrip_json_safe():
    state = _ready_state()

    payload = order_book_state_to_dict(state)

    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert order_book_state_from_dict(payload) == state


def test_new_order_book_module_has_no_network_env_or_credential_imports():
    path = Path("src/crypto_core/data/order_book.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint(forbidden_import_roots)


def test_lifecycle_live_still_rejected():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _ready_state() -> OrderBookState:
    result = build_order_book_state_from_snapshot(_snapshot())
    assert result.state is not None
    return result.state


def _replay(snapshot: OrderBookSnapshot, deltas: tuple[OrderBookDelta, ...]) -> OrderBookState | None:
    result = build_order_book_state_from_snapshot(snapshot)
    state = result.state
    for delta in deltas:
        assert state is not None
        result = apply_order_book_delta(state, delta)
        state = result.state
    return state


def _snapshot(
    *,
    bids: tuple[OrderBookLevel, ...] = (OrderBookLevel(100.0, 1.0), OrderBookLevel(99.0, 1.0)),
    asks: tuple[OrderBookLevel, ...] = (OrderBookLevel(101.0, 1.0), OrderBookLevel(102.0, 1.0)),
    depth: int = 2,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        event_time_ns=1_000,
        receive_time_ns=1_001,
        sequence_id=10,
        bids=bids,
        asks=asks,
        checksum=None,
        depth=depth,
        source="unit",
    )


def _delta(
    *,
    venue_id: VenueId = VenueId.BINANCE_USDM,
    symbol: str = "BTCUSDT",
    canonical_symbol: str = "BTC-USDT-PERP",
    first_update_id: int,
    final_update_id: int,
    prev_update_id: int,
    bid_updates: tuple[OrderBookLevel, ...] = (),
    ask_updates: tuple[OrderBookLevel, ...] = (),
) -> OrderBookDelta:
    return OrderBookDelta(
        venue_id=venue_id,
        symbol=symbol,
        canonical_symbol=canonical_symbol,
        event_time_ns=1_002,
        receive_time_ns=1_003,
        first_update_id=first_update_id,
        final_update_id=final_update_id,
        prev_update_id=prev_update_id,
        bid_updates=bid_updates,
        ask_updates=ask_updates,
        checksum=None,
        source="unit",
    )


def _unsafe_snapshot(
    *,
    bids: tuple[OrderBookLevel, ...] = (OrderBookLevel(100.0, 1.0), OrderBookLevel(99.0, 1.0)),
    asks: tuple[OrderBookLevel, ...] = (OrderBookLevel(101.0, 1.0), OrderBookLevel(102.0, 1.0)),
) -> OrderBookSnapshot:
    snapshot = object.__new__(OrderBookSnapshot)
    object.__setattr__(snapshot, "venue_id", VenueId.BINANCE_USDM)
    object.__setattr__(snapshot, "symbol", "BTCUSDT")
    object.__setattr__(snapshot, "canonical_symbol", "BTC-USDT-PERP")
    object.__setattr__(snapshot, "event_time_ns", 1_000)
    object.__setattr__(snapshot, "receive_time_ns", 1_001)
    object.__setattr__(snapshot, "sequence_id", 10)
    object.__setattr__(snapshot, "bids", bids)
    object.__setattr__(snapshot, "asks", asks)
    object.__setattr__(snapshot, "checksum", None)
    object.__setattr__(snapshot, "depth", max(1, min(len(bids), len(asks))))
    object.__setattr__(snapshot, "source", "unit")
    return snapshot


def _unsafe_delta(
    *,
    first_update_id: int,
    final_update_id: int,
    prev_update_id: int,
    bid_updates: tuple[OrderBookLevel, ...],
    ask_updates: tuple[OrderBookLevel, ...],
) -> OrderBookDelta:
    delta = object.__new__(OrderBookDelta)
    object.__setattr__(delta, "venue_id", VenueId.BINANCE_USDM)
    object.__setattr__(delta, "symbol", "BTCUSDT")
    object.__setattr__(delta, "canonical_symbol", "BTC-USDT-PERP")
    object.__setattr__(delta, "event_time_ns", 1_002)
    object.__setattr__(delta, "receive_time_ns", 1_003)
    object.__setattr__(delta, "first_update_id", first_update_id)
    object.__setattr__(delta, "final_update_id", final_update_id)
    object.__setattr__(delta, "prev_update_id", prev_update_id)
    object.__setattr__(delta, "bid_updates", bid_updates)
    object.__setattr__(delta, "ask_updates", ask_updates)
    object.__setattr__(delta, "checksum", None)
    object.__setattr__(delta, "source", "unit")
    return delta


def _execution_request() -> ExecutionRequest:
    edge_signal = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=100,
        is_valid=True,
        block_reason=None,
    )
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        size=0.01,
        price_hint=50_000.0,
        risk_evaluation=RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=edge_signal,
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )
