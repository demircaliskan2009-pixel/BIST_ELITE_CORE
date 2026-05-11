from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_ingest import (
    PublicFeedIngestPlan,
    ingest_public_feed_events,
    public_feed_ingest_plan_from_dict,
    public_feed_ingest_plan_to_dict,
    public_feed_ingest_result_from_dict,
    public_feed_ingest_result_ready,
    public_feed_ingest_result_to_dict,
)
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.data.public_feed_source import (
    PublicFeedBatch,
    PublicFeedSubscription,
    RawPublicFeedEnvelope,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import PublicFeedType, PublicMarketDataEvent, VenueId


def test_valid_offline_public_feed_ingest_accepted():
    result = ingest_public_feed_events(_plan(), _batch(), _events(), now_ns=1_020)

    assert public_feed_ingest_result_ready(result) is True
    assert result.accepted is True
    assert result.journal_entry_count == 2
    assert result.rejection_reasons == ()
    assert result.readiness_snapshot.accepted_for_paper is True


def test_empty_events_rejected():
    result = ingest_public_feed_events(_plan(), _batch(), (), now_ns=1_020)

    assert result.accepted is False
    assert "public_feed_ingest:events_empty" in result.rejection_reasons


def test_batch_validation_failure_rejected():
    batch = _batch(
        subscription=replace(_subscription(), enabled=False),
        envelopes=(_envelope(),),
    )

    result = ingest_public_feed_events(_plan(), batch, (_event(),), now_ns=1_020)

    assert result.accepted is False
    assert "public_feed_ingest:batch_not_ready" in result.rejection_reasons
    assert "public_feed_source:subscription_disabled" in result.rejection_reasons


def test_event_envelope_count_mismatch_rejected():
    result = ingest_public_feed_events(_plan(), _batch(), (_event(),), now_ns=1_020)

    assert result.accepted is False
    assert "public_feed_ingest:event_envelope_count_mismatch" in result.rejection_reasons


def test_event_hash_mismatch_rejected():
    events = (_event(payload_hash="different-hash"), _event(sequence_id=11, event_time_ns=1_010, receive_time_ns=1_011))

    result = ingest_public_feed_events(_plan(), _batch(), events, now_ns=1_020)

    assert result.accepted is False
    assert "public_feed_ingest:event_hash_mismatch" in result.rejection_reasons


def test_event_sequence_mismatch_rejected():
    events = (
        _event(sequence_id=99),
        _event(sequence_id=11, event_time_ns=1_010, receive_time_ns=1_011),
    )

    result = ingest_public_feed_events(_plan(), _batch(), events, now_ns=1_020)

    assert result.accepted is False
    assert "public_feed_ingest:event_sequence_mismatch" in result.rejection_reasons


def test_replay_failure_rejected():
    batch = _batch(
        envelopes=(
            _envelope(envelope_id="env-1", sequence_id=10),
            _envelope(envelope_id="env-2", sequence_id=10, event_time_ns=1_010, receive_time_ns=1_011),
        )
    )
    events = (
        _event(sequence_id=10),
        _event(sequence_id=10, event_time_ns=1_010, receive_time_ns=1_011),
    )

    result = ingest_public_feed_events(
        _plan(require_batch_ready=False, require_public_data_ready=False),
        batch,
        events,
        now_ns=1_020,
    )

    assert result.accepted is False
    assert "public_feed_ingest:replay_not_ready" in result.rejection_reasons
    assert "market_data_journal:duplicate_sequence_id" in result.rejection_reasons


def test_readiness_failure_rejected():
    result = ingest_public_feed_events(
        _plan(policy=_policy(require_order_book=True)),
        _batch(),
        _events(),
        now_ns=1_020,
    )

    assert result.accepted is False
    assert "public_feed_ingest:public_data_not_ready" in result.rejection_reasons
    assert "public_feed:order_book_missing" in result.rejection_reasons


def test_aggregate_rejection_reasons_are_deterministic():
    result = ingest_public_feed_events(
        _plan(policy=_policy(require_order_book=True)),
        _batch(envelopes=(replace(_envelope(), normalized=False),)),
        (_event(),),
        now_ns=1_020,
    )

    assert result.rejection_reasons == tuple(dict.fromkeys(result.rejection_reasons))
    assert "public_feed_source:not_normalized" in result.rejection_reasons
    assert "public_feed_ingest:public_data_not_ready" in result.rejection_reasons


def test_public_feed_ingest_serializers_roundtrip_json_safe():
    plan = _plan()
    result = ingest_public_feed_events(plan, _batch(), _events(), now_ns=1_020)
    plan_payload = public_feed_ingest_plan_to_dict(plan)
    result_payload = public_feed_ingest_result_to_dict(result)

    assert (
        public_feed_ingest_plan_to_dict(public_feed_ingest_plan_from_dict(json.loads(json.dumps(plan_payload))))
        == plan_payload
    )
    assert (
        public_feed_ingest_result_to_dict(public_feed_ingest_result_from_dict(json.loads(json.dumps(result_payload))))
        == result_payload
    )


def test_public_feed_ingest_is_deterministic():
    first = public_feed_ingest_result_to_dict(ingest_public_feed_events(_plan(), _batch(), _events(), now_ns=1_020))
    second = public_feed_ingest_result_to_dict(ingest_public_feed_events(_plan(), _batch(), _events(), now_ns=1_020))

    assert first == second


def test_new_public_feed_ingest_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_ingest.py")
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


def _plan(
    *,
    policy: PublicFeedPolicy | None = None,
    require_batch_ready: bool = True,
    require_replay_ready: bool = True,
    require_public_data_ready: bool = True,
) -> PublicFeedIngestPlan:
    return PublicFeedIngestPlan(
        plan_id="plan-21i",
        policy=policy or _policy(),
        subscription=_subscription(),
        max_receive_lag_ns=100,
        require_batch_ready=require_batch_ready,
        require_replay_ready=require_replay_ready,
        require_public_data_ready=require_public_data_ready,
    )


def _policy(*, require_order_book: bool = False) -> PublicFeedPolicy:
    return PublicFeedPolicy(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        feed_type=PublicFeedType.L2_ORDERBOOK,
        max_staleness_ns=100,
        max_receive_lag_ns=100,
        require_replay_cursor=True,
        require_order_book=require_order_book,
    )


def _subscription() -> PublicFeedSubscription:
    return PublicFeedSubscription(
        subscription_id="sub-21i",
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        feed_type=PublicFeedType.L2_ORDERBOOK,
        depth=20,
        enabled=True,
        created_at_ns=900,
    )


def _envelope(**overrides: object) -> RawPublicFeedEnvelope:
    values = {
        "envelope_id": "env-1",
        "subscription_id": "sub-21i",
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "event_time_ns": 1_000,
        "receive_time_ns": 1_001,
        "sequence_id": 10,
        "payload_hash": "payload-hash-10",
        "raw_payload_ref": "raw-ref-10",
        "normalized": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return RawPublicFeedEnvelope(**values)  # type: ignore[arg-type]


def _batch(
    *,
    envelopes: tuple[RawPublicFeedEnvelope, ...] | None = None,
    subscription: PublicFeedSubscription | None = None,
) -> PublicFeedBatch:
    return PublicFeedBatch(
        batch_id="batch-21i",
        subscription=subscription or _subscription(),
        envelopes=envelopes
        if envelopes is not None
        else (
            _envelope(envelope_id="env-1", sequence_id=10, event_time_ns=1_000, receive_time_ns=1_001),
            _envelope(
                envelope_id="env-2",
                sequence_id=11,
                event_time_ns=1_010,
                receive_time_ns=1_011,
                payload_hash="payload-hash-11",
                raw_payload_ref="raw-ref-11",
            ),
        ),
        created_at_ns=1_012,
    )


def _event(**overrides: object) -> PublicMarketDataEvent:
    values = {
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "event_time_ns": 1_000,
        "receive_time_ns": 1_001,
        "sequence_id": 10,
        "payload_hash": "payload-hash-10",
        "raw_payload_ref": "raw-ref-10",
        "normalized": True,
    }
    values.update(overrides)
    return PublicMarketDataEvent(**values)  # type: ignore[arg-type]


def _events() -> tuple[PublicMarketDataEvent, ...]:
    return (
        _event(sequence_id=10, event_time_ns=1_000, receive_time_ns=1_001),
        _event(
            sequence_id=11,
            event_time_ns=1_010,
            receive_time_ns=1_011,
            payload_hash="payload-hash-11",
            raw_payload_ref="raw-ref-11",
        ),
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
