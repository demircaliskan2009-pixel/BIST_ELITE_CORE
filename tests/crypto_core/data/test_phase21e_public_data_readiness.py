from __future__ import annotations

import ast
import json
from pathlib import Path

from crypto_core.data.market_data_journal import PublicMarketDataReplayCursor, PublicMarketDataReplayResult
from crypto_core.data.order_book import OrderBookApplyResult, build_order_book_state_from_snapshot
from crypto_core.data.public_data_readiness import (
    PublicDataReadinessInput,
    build_public_data_readiness_snapshot,
    public_data_readiness_snapshot_from_dict,
    public_data_readiness_snapshot_to_dict,
    public_data_ready_for_paper,
)
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import OrderBookLevel, OrderBookSnapshot, PublicFeedHealth, PublicFeedType, VenueId


def test_valid_public_data_readiness_is_accepted_for_paper():
    snapshot = build_public_data_readiness_snapshot(_input())

    assert public_data_ready_for_paper(snapshot) is True
    assert snapshot.accepted_for_paper is True
    assert snapshot.rejection_reasons == ()


def test_feed_gate_rejection_blocks_readiness():
    snapshot = build_public_data_readiness_snapshot(_input(health=_health(healthy=False)))

    assert public_data_ready_for_paper(snapshot) is False
    assert "public_feed:unhealthy" in snapshot.rejection_reasons


def test_replay_cursor_not_ready_blocks_readiness():
    snapshot = build_public_data_readiness_snapshot(
        _input(
            replay_cursor=_cursor(
                healthy=False,
                rejection_reasons=("market_data_journal:cursor_rejected",),
            )
        )
    )

    assert snapshot.replay_ready is False
    assert "public_feed:replay_cursor_not_ready" in snapshot.rejection_reasons
    assert "market_data_journal:cursor_rejected" in snapshot.rejection_reasons


def test_order_book_not_ready_blocks_readiness():
    snapshot = build_public_data_readiness_snapshot(
        _input(
            order_book_state=_book_state(
                healthy=False,
                rejection_reasons=("order_book:unhealthy",),
            )
        )
    )

    assert snapshot.order_book_ready is False
    assert "public_feed:order_book_not_ready" in snapshot.rejection_reasons
    assert "order_book:unhealthy" in snapshot.rejection_reasons


def test_combined_reasons_are_preserved_in_deterministic_order():
    snapshot = build_public_data_readiness_snapshot(
        _input(
            health=_health(healthy=False),
            replay_result=PublicMarketDataReplayResult(
                applied=False,
                cursor=None,
                rejection_reasons=("market_data_journal:duplicate_sequence_id",),
                gap_detected=True,
                stale_detected=False,
                resync_required=True,
            ),
            order_book_result=OrderBookApplyResult(
                applied=False,
                state=_book_state(),
                rejection_reasons=("order_book:sequence_gap",),
                resync_required=True,
                gap_detected=True,
            ),
        )
    )

    assert snapshot.rejection_reasons == tuple(dict.fromkeys(snapshot.rejection_reasons))
    assert "public_feed:unhealthy" in snapshot.rejection_reasons
    assert "public_feed:replay_rejected" in snapshot.rejection_reasons
    assert "market_data_journal:duplicate_sequence_id" in snapshot.rejection_reasons
    assert "order_book:sequence_gap" in snapshot.rejection_reasons


def test_public_data_ready_for_paper_false_for_none_or_bad_snapshot():
    assert public_data_ready_for_paper(None) is False
    assert public_data_ready_for_paper(object()) is False  # type: ignore[arg-type]


def test_public_data_readiness_snapshot_roundtrip_json_safe():
    snapshot = build_public_data_readiness_snapshot(_input())
    payload = public_data_readiness_snapshot_to_dict(snapshot)

    restored = public_data_readiness_snapshot_from_dict(json.loads(json.dumps(payload)))

    assert public_data_readiness_snapshot_to_dict(restored) == payload


def test_public_data_readiness_is_deterministic():
    first = public_data_readiness_snapshot_to_dict(build_public_data_readiness_snapshot(_input()))
    second = public_data_readiness_snapshot_to_dict(build_public_data_readiness_snapshot(_input()))

    assert first == second


def test_new_public_data_readiness_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_data_readiness.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imports)


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _input(
    *,
    policy: PublicFeedPolicy | None = None,
    health: PublicFeedHealth | None = None,
    replay_cursor: PublicMarketDataReplayCursor | None = None,
    replay_result: PublicMarketDataReplayResult | None = None,
    order_book_state=None,
    order_book_result: OrderBookApplyResult | None = None,
) -> PublicDataReadinessInput:
    return PublicDataReadinessInput(
        policy=policy or _policy(),
        health=health if health is not None else _health(),
        replay_cursor=replay_cursor if replay_cursor is not None else _cursor(),
        replay_result=replay_result,
        order_book_state=order_book_state if order_book_state is not None else _book_state(),
        order_book_result=order_book_result,
        now_ns=1_010,
    )


def _policy() -> PublicFeedPolicy:
    return PublicFeedPolicy(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        feed_type=PublicFeedType.L2_ORDERBOOK,
        max_staleness_ns=100,
        max_receive_lag_ns=100,
        require_replay_cursor=True,
        require_order_book=True,
    )


def _health(*, healthy: bool = True) -> PublicFeedHealth:
    return PublicFeedHealth(
        venue_id=VenueId.BINANCE_USDM,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        symbol="BTCUSDT",
        healthy=healthy,
        stale=False,
        last_event_time_ns=1_000,
        last_receive_time_ns=1_001,
        gap_detected=False,
        resync_required=False,
    )


def _cursor(
    *,
    healthy: bool = True,
    rejection_reasons: tuple[str, ...] = (),
) -> PublicMarketDataReplayCursor:
    return PublicMarketDataReplayCursor(
        journal_id="journal-1",
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        last_sequence_id=10,
        last_event_time_ns=1_000,
        entry_count=1,
        healthy=healthy,
        rejection_reasons=rejection_reasons,
    )


def _book_state(*, healthy: bool = True, rejection_reasons: tuple[str, ...] = ()):
    result = build_order_book_state_from_snapshot(
        OrderBookSnapshot(
            venue_id=VenueId.BINANCE_USDM,
            symbol="BTCUSDT",
            canonical_symbol="BTC-USDT-PERP",
            event_time_ns=1_000,
            receive_time_ns=1_001,
            sequence_id=10,
            bids=(OrderBookLevel(100.0, 1.0),),
            asks=(OrderBookLevel(101.0, 1.0),),
            checksum=None,
            depth=1,
            source="unit",
        )
    )
    assert result.state is not None
    return type(result.state)(
        venue_id=result.state.venue_id,
        symbol=result.state.symbol,
        canonical_symbol=result.state.canonical_symbol,
        last_sequence_id=result.state.last_sequence_id,
        bids=result.state.bids,
        asks=result.state.asks,
        checksum=result.state.checksum,
        depth=result.state.depth,
        source=result.state.source,
        healthy=healthy,
        rejection_reasons=rejection_reasons,
    )


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
