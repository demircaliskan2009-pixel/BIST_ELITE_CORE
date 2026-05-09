from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_source import (
    PublicFeedBatch,
    PublicFeedSubscription,
    RawPublicFeedEnvelope,
    public_feed_batch_from_dict,
    public_feed_batch_ready,
    public_feed_batch_to_dict,
    public_feed_batch_validation_result_from_dict,
    public_feed_batch_validation_result_to_dict,
    public_feed_subscription_from_dict,
    public_feed_subscription_to_dict,
    raw_public_feed_envelope_from_dict,
    raw_public_feed_envelope_to_dict,
    validate_public_feed_batch,
    validate_public_feed_subscription,
    validate_raw_public_feed_envelope,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import PublicFeedType, VenueId


def test_valid_subscription_accepted():
    assert validate_public_feed_subscription(_subscription()) == ()


def test_disabled_subscription_rejected():
    reasons = validate_public_feed_subscription(replace(_subscription(), enabled=False))

    assert reasons == ("public_feed_source:subscription_disabled",)


def test_valid_envelope_accepted():
    assert validate_raw_public_feed_envelope(_envelope(), _subscription()) == ()


def test_envelope_venue_mismatch_rejected():
    reasons = validate_raw_public_feed_envelope(
        replace(_envelope(), venue_id=VenueId.DERIBIT),
        _subscription(),
    )

    assert "public_feed_source:venue_mismatch" in reasons


def test_envelope_symbol_mismatch_rejected():
    reasons = validate_raw_public_feed_envelope(
        replace(_envelope(), symbol="ETHUSDT"),
        _subscription(),
    )

    assert "public_feed_source:symbol_mismatch" in reasons


def test_envelope_feed_mismatch_rejected():
    reasons = validate_raw_public_feed_envelope(
        replace(_envelope(), feed_type=PublicFeedType.TRADES),
        _subscription(),
    )

    assert "public_feed_source:feed_type_mismatch" in reasons


def test_envelope_invalid_timestamps_rejected():
    reasons = validate_raw_public_feed_envelope(
        replace(_envelope(), event_time_ns=1_001, receive_time_ns=1_000),
        _subscription(),
    )

    assert "public_feed_source:receive_before_event" in reasons


def test_envelope_empty_payload_hash_or_ref_rejected():
    reasons = validate_raw_public_feed_envelope(
        replace(_envelope(), payload_hash="", raw_payload_ref=""),
        _subscription(),
    )

    assert "public_feed_source:payload_hash_missing" in reasons
    assert "public_feed_source:raw_payload_ref_missing" in reasons


def test_valid_batch_accepted():
    result = validate_public_feed_batch(_batch())

    assert public_feed_batch_ready(result) is True
    assert result.accepted is True
    assert result.envelope_count == 2
    assert result.first_sequence_id == 10
    assert result.last_sequence_id == 11


def test_duplicate_envelope_id_rejected():
    batch = _batch(envelopes=(_envelope(), _envelope(sequence_id=11, event_time_ns=1_010, receive_time_ns=1_011)))

    result = validate_public_feed_batch(batch)

    assert result.accepted is False
    assert "public_feed_source:duplicate_envelope_id" in result.rejection_reasons


def test_duplicate_sequence_id_rejected():
    batch = _batch(
        envelopes=(
            _envelope(envelope_id="env-1", sequence_id=10),
            _envelope(envelope_id="env-2", sequence_id=10, event_time_ns=1_010, receive_time_ns=1_011),
        )
    )

    result = validate_public_feed_batch(batch)

    assert result.gap_detected is True
    assert "public_feed_source:duplicate_sequence_id" in result.rejection_reasons


def test_non_monotonic_sequence_rejected():
    batch = _batch(
        envelopes=(
            _envelope(envelope_id="env-1", sequence_id=11),
            _envelope(envelope_id="env-2", sequence_id=10, event_time_ns=1_010, receive_time_ns=1_011),
        )
    )

    result = validate_public_feed_batch(batch)

    assert result.gap_detected is True
    assert "public_feed_source:sequence_not_monotonic" in result.rejection_reasons


def test_non_monotonic_event_time_rejected():
    batch = _batch(
        envelopes=(
            _envelope(envelope_id="env-1", sequence_id=10, event_time_ns=1_010, receive_time_ns=1_011),
            _envelope(envelope_id="env-2", sequence_id=11, event_time_ns=1_000, receive_time_ns=1_001),
        )
    )

    result = validate_public_feed_batch(batch)

    assert "public_feed_source:event_time_not_monotonic" in result.rejection_reasons


def test_normalized_false_rejected():
    batch = _batch(envelopes=(replace(_envelope(), normalized=False),))

    result = validate_public_feed_batch(batch)

    assert "public_feed_source:not_normalized" in result.rejection_reasons


def test_envelope_rejection_reason_rejects_batch():
    batch = _batch(envelopes=(replace(_envelope(), rejection_reasons=("venue:bad_payload",)),))

    result = validate_public_feed_batch(batch)

    assert "venue:bad_payload" in result.rejection_reasons


def test_receive_lag_exceeded_rejected():
    result = validate_public_feed_batch(_batch(), max_receive_lag_ns=5, now_ns=2_000)

    assert result.stale_detected is True
    assert "public_feed_source:receive_lag_exceeded" in result.rejection_reasons


def test_public_feed_source_serializers_roundtrip_json_safe():
    batch = _batch()
    result = validate_public_feed_batch(batch)

    subscription_payload = public_feed_subscription_to_dict(batch.subscription)
    envelope_payload = raw_public_feed_envelope_to_dict(batch.envelopes[0])
    batch_payload = public_feed_batch_to_dict(batch)
    result_payload = public_feed_batch_validation_result_to_dict(result)

    assert (
        public_feed_subscription_to_dict(
            public_feed_subscription_from_dict(json.loads(json.dumps(subscription_payload)))
        )
        == subscription_payload
    )
    assert (
        raw_public_feed_envelope_to_dict(raw_public_feed_envelope_from_dict(json.loads(json.dumps(envelope_payload))))
        == envelope_payload
    )
    assert (
        public_feed_batch_to_dict(public_feed_batch_from_dict(json.loads(json.dumps(batch_payload)))) == batch_payload
    )
    assert (
        public_feed_batch_validation_result_to_dict(
            public_feed_batch_validation_result_from_dict(json.loads(json.dumps(result_payload)))
        )
        == result_payload
    )


def test_public_feed_batch_validation_is_deterministic():
    first = public_feed_batch_validation_result_to_dict(validate_public_feed_batch(_batch()))
    second = public_feed_batch_validation_result_to_dict(validate_public_feed_batch(_batch()))

    assert first == second


def test_new_public_feed_source_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_source.py")
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


def _subscription(**overrides: object) -> PublicFeedSubscription:
    values = {
        "subscription_id": "sub-21h",
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "depth": 20,
        "enabled": True,
        "created_at_ns": 900,
    }
    values.update(overrides)
    return PublicFeedSubscription(**values)  # type: ignore[arg-type]


def _envelope(**overrides: object) -> RawPublicFeedEnvelope:
    values = {
        "envelope_id": "env-1",
        "subscription_id": "sub-21h",
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
        batch_id="batch-21h",
        subscription=subscription or _subscription(),
        envelopes=envelopes
        if envelopes is not None
        else (
            _envelope(envelope_id="env-1", sequence_id=10, event_time_ns=1_000, receive_time_ns=1_001),
            _envelope(envelope_id="env-2", sequence_id=11, event_time_ns=1_010, receive_time_ns=1_011),
        ),
        created_at_ns=1_012,
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
