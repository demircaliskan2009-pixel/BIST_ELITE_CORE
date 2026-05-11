from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from crypto_core.data.market_data_journal import PublicMarketDataReplayCursor, PublicMarketDataReplayResult
from crypto_core.data.order_book import OrderBookApplyResult, build_order_book_state_from_snapshot
from crypto_core.data.public_feed_policy import (
    PublicFeedPolicy,
    PublicFeedPolicyError,
    evaluate_public_feed_gate,
    public_feed_gate_decision_from_dict,
    public_feed_gate_decision_to_dict,
    public_feed_gate_ready,
    public_feed_policy_from_dict,
    public_feed_policy_rejection_reasons,
    public_feed_policy_to_dict,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import OrderBookLevel, OrderBookSnapshot, PublicFeedHealth, PublicFeedType, VenueId


def test_valid_public_feed_gate_is_accepted():
    decision = evaluate_public_feed_gate(
        _policy(),
        health=_health(),
        replay_cursor=_cursor(),
        order_book_state=_book_state(),
        now_ns=1_010,
    )

    assert public_feed_gate_ready(decision) is True
    assert decision.accepted is True
    assert decision.rejection_reasons == ()


def test_missing_and_malformed_policy_reject_fail_closed():
    missing = evaluate_public_feed_gate(None)
    malformed = evaluate_public_feed_gate(object())

    assert missing.accepted is False
    assert missing.rejection_reasons == ("public_feed:policy_missing",)
    assert malformed.accepted is False
    assert malformed.rejection_reasons == ("public_feed:policy_malformed",)


def test_policy_invalid_staleness_or_lag_rejects():
    policy = _unsafe_policy(max_staleness_ns=0, max_receive_lag_ns=0)

    reasons = public_feed_policy_rejection_reasons(policy)

    assert "public_feed:invalid_staleness" in reasons
    assert "public_feed:invalid_receive_lag" in reasons


def test_unhealthy_stale_and_receive_lag_reject():
    decision = evaluate_public_feed_gate(
        _policy(max_receive_lag_ns=2),
        health=_health(healthy=False, stale=True, last_receive_time_ns=1_000),
        replay_cursor=_cursor(),
        order_book_state=_book_state(),
        now_ns=1_010,
    )

    assert decision.accepted is False
    assert "public_feed:unhealthy" in decision.rejection_reasons
    assert "public_feed:stale" in decision.rejection_reasons
    assert "public_feed:receive_lag_exceeded" in decision.rejection_reasons


def test_gap_and_resync_propagate_from_health_and_replay_result():
    decision = evaluate_public_feed_gate(
        _policy(),
        health=_health(gap_detected=True, resync_required=True),
        replay_result=PublicMarketDataReplayResult(
            applied=False,
            cursor=None,
            rejection_reasons=("market_data_journal:sequence_not_monotonic",),
            gap_detected=True,
            stale_detected=False,
            resync_required=True,
        ),
        order_book_state=_book_state(),
        now_ns=1_010,
    )

    assert decision.accepted is False
    assert "public_feed:gap_detected" in decision.rejection_reasons
    assert "public_feed:resync_required" in decision.rejection_reasons
    assert "public_feed:replay_rejected" in decision.rejection_reasons
    assert decision.gap_detected is True
    assert decision.resync_required is True


def test_replay_cursor_missing_or_not_ready_rejects():
    missing = evaluate_public_feed_gate(_policy(), health=_health(), order_book_state=_book_state(), now_ns=1_010)
    not_ready = evaluate_public_feed_gate(
        _policy(),
        health=_health(),
        replay_cursor=_cursor(healthy=False, rejection_reasons=("market_data_journal:cursor_rejected",)),
        order_book_state=_book_state(),
        now_ns=1_010,
    )

    assert "public_feed:replay_cursor_missing" in missing.rejection_reasons
    assert "public_feed:replay_cursor_not_ready" in not_ready.rejection_reasons


def test_order_book_missing_not_ready_and_rejected_paths_reject():
    missing = evaluate_public_feed_gate(_policy(), health=_health(), replay_cursor=_cursor(), now_ns=1_010)
    not_ready = evaluate_public_feed_gate(
        _policy(),
        health=_health(),
        replay_cursor=_cursor(),
        order_book_state=_book_state(healthy=False, rejection_reasons=("order_book:unhealthy",)),
        now_ns=1_010,
    )
    rejected_result = evaluate_public_feed_gate(
        _policy(),
        health=_health(),
        replay_cursor=_cursor(),
        order_book_result=OrderBookApplyResult(
            applied=False,
            state=_book_state(),
            rejection_reasons=("order_book:sequence_gap",),
            resync_required=True,
            gap_detected=True,
        ),
        now_ns=1_010,
    )

    assert "public_feed:order_book_missing" in missing.rejection_reasons
    assert "public_feed:order_book_not_ready" in not_ready.rejection_reasons
    assert "public_feed:order_book_rejected" in rejected_result.rejection_reasons
    assert "public_feed:gap_detected" in rejected_result.rejection_reasons


def test_venue_symbol_and_feed_mismatch_rejects():
    decision = evaluate_public_feed_gate(
        _policy(),
        health=_health(venue_id=VenueId.DERIBIT, symbol="ETH-PERPETUAL", feed_type=PublicFeedType.TRADES),
        replay_cursor=_cursor(venue_id=VenueId.DERIBIT, symbol="ETH-PERPETUAL", canonical_symbol="ETH-PERP"),
        order_book_state=_book_state(venue_id=VenueId.DERIBIT, symbol="ETH-PERPETUAL", canonical_symbol="ETH-PERP"),
        now_ns=1_010,
    )

    assert "public_feed:venue_mismatch" in decision.rejection_reasons
    assert "public_feed:symbol_mismatch" in decision.rejection_reasons
    assert "public_feed:feed_type_mismatch" in decision.rejection_reasons


def test_public_feed_gate_ready_false_for_none_or_rejected():
    decision = evaluate_public_feed_gate(None)

    assert public_feed_gate_ready(None) is False
    assert public_feed_gate_ready(decision) is False


def test_policy_and_decision_roundtrip_json_safe():
    policy_payload = public_feed_policy_to_dict(_policy())
    policy = public_feed_policy_from_dict(json.loads(json.dumps(policy_payload)))
    decision = evaluate_public_feed_gate(
        policy,
        health=_health(),
        replay_cursor=_cursor(),
        order_book_state=_book_state(),
        now_ns=1_010,
    )

    decision_payload = public_feed_gate_decision_to_dict(decision)
    restored = public_feed_gate_decision_from_dict(json.loads(json.dumps(decision_payload)))

    assert public_feed_policy_to_dict(policy) == policy_payload
    assert public_feed_gate_decision_to_dict(restored) == decision_payload


def test_policy_from_dict_rejects_malformed_payload():
    payload = public_feed_policy_to_dict(_policy())
    payload["venue_id"] = "unknown"

    with pytest.raises(PublicFeedPolicyError, match="venue_id"):
        public_feed_policy_from_dict(payload)


def test_public_feed_gate_is_deterministic():
    kwargs = {
        "health": _health(),
        "replay_cursor": _cursor(),
        "order_book_state": _book_state(),
        "now_ns": 1_010,
    }

    first = public_feed_gate_decision_to_dict(evaluate_public_feed_gate(_policy(), **kwargs))
    second = public_feed_gate_decision_to_dict(evaluate_public_feed_gate(_policy(), **kwargs))

    assert first == second


def test_new_public_feed_policy_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_policy.py")
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


def _policy(
    *,
    max_staleness_ns: int = 100,
    max_receive_lag_ns: int = 100,
    require_order_book: bool = True,
) -> PublicFeedPolicy:
    return PublicFeedPolicy(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        feed_type=PublicFeedType.L2_ORDERBOOK,
        max_staleness_ns=max_staleness_ns,
        max_receive_lag_ns=max_receive_lag_ns,
        require_replay_cursor=True,
        require_order_book=require_order_book,
    )


def _unsafe_policy(**overrides: object) -> PublicFeedPolicy:
    policy = _policy()
    for name, value in overrides.items():
        object.__setattr__(policy, name, value)
    return policy


def _health(
    *,
    venue_id: VenueId = VenueId.BINANCE_USDM,
    symbol: str = "BTCUSDT",
    feed_type: PublicFeedType = PublicFeedType.L2_ORDERBOOK,
    healthy: bool = True,
    stale: bool = False,
    last_event_time_ns: int = 1_000,
    last_receive_time_ns: int = 1_001,
    gap_detected: bool = False,
    resync_required: bool = False,
    rejection_reasons: tuple[str, ...] = (),
) -> PublicFeedHealth:
    return PublicFeedHealth(
        venue_id=venue_id,
        feed_type=feed_type,
        symbol=symbol,
        healthy=healthy,
        stale=stale,
        last_event_time_ns=last_event_time_ns,
        last_receive_time_ns=last_receive_time_ns,
        gap_detected=gap_detected,
        resync_required=resync_required,
        rejection_reasons=rejection_reasons,
    )


def _cursor(
    *,
    venue_id: VenueId = VenueId.BINANCE_USDM,
    symbol: str = "BTCUSDT",
    canonical_symbol: str = "BTC-USDT-PERP",
    healthy: bool = True,
    rejection_reasons: tuple[str, ...] = (),
) -> PublicMarketDataReplayCursor:
    return PublicMarketDataReplayCursor(
        journal_id="journal-1",
        venue_id=venue_id,
        symbol=symbol,
        canonical_symbol=canonical_symbol,
        last_sequence_id=10,
        last_event_time_ns=1_000,
        entry_count=1,
        healthy=healthy,
        rejection_reasons=rejection_reasons,
    )


def _book_state(
    *,
    venue_id: VenueId = VenueId.BINANCE_USDM,
    symbol: str = "BTCUSDT",
    canonical_symbol: str = "BTC-USDT-PERP",
    healthy: bool = True,
    rejection_reasons: tuple[str, ...] = (),
):
    result = build_order_book_state_from_snapshot(
        OrderBookSnapshot(
            venue_id=venue_id,
            symbol=symbol,
            canonical_symbol=canonical_symbol,
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
