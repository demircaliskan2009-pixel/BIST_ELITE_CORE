from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_adapter import (
    PublicFeedAdapterDescriptor,
    PublicFeedAdapterProtocol,
    evaluate_public_feed_adapter_readiness,
    public_feed_adapter_descriptor_from_dict,
    public_feed_adapter_descriptor_to_dict,
    public_feed_adapter_readiness_from_dict,
    public_feed_adapter_readiness_to_dict,
    public_feed_adapter_ready,
)
from crypto_core.data.public_feed_connector import PublicFeedConnectorMode, PublicFeedConnectorPlan
from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    PublicFeedDialectSpec,
)
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.data.public_feed_source import PublicFeedSubscription
from crypto_core.data.public_network_authorization import (
    PUBLIC_NETWORK_AUTHORIZATION_SCHEMA_VERSION,
    PublicNetworkAuthorization,
    PublicNetworkAuthorizationStatus,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, VenueId


def test_valid_descriptor_readiness_accepted():
    readiness = evaluate_public_feed_adapter_readiness(_descriptor(), now_ns=1_500)

    assert readiness.accepted is True
    assert public_feed_adapter_ready(readiness) is True
    assert readiness.network_authorized is True
    assert readiness.connector_gate_ready is True
    assert readiness.offline_only is True
    assert readiness.rejection_reasons == ()


def test_disabled_descriptor_rejected():
    readiness = evaluate_public_feed_adapter_readiness(_descriptor(enabled=False))

    assert readiness.accepted is False
    assert "public_feed_adapter:disabled" in readiness.rejection_reasons


def test_missing_or_failed_network_auth_rejected():
    missing = evaluate_public_feed_adapter_readiness(_descriptor(network_authorization=None))  # type: ignore[arg-type]
    failed = evaluate_public_feed_adapter_readiness(
        _descriptor(network_authorization=replace(_auth(), network_allowed=False))
    )

    assert "public_feed_adapter:network_not_authorized" in missing.rejection_reasons
    assert "public_network:not_allowed" in failed.rejection_reasons


def test_missing_or_failed_connector_gate_rejected():
    missing = evaluate_public_feed_adapter_readiness(_descriptor(connector_plan=None))  # type: ignore[arg-type]
    failed = evaluate_public_feed_adapter_readiness(_descriptor(connector_plan=_plan(network_enabled=True)))

    assert "public_feed_adapter:connector_gate_not_ready" in missing.rejection_reasons
    assert "public_connector:network_forbidden" in failed.rejection_reasons


def test_symbol_mismatch_rejected():
    readiness = evaluate_public_feed_adapter_readiness(_descriptor(connector_plan=_plan(symbol="ETHUSDT")))

    assert readiness.accepted is False
    assert "public_feed_adapter:symbol_mismatch" in readiness.rejection_reasons


def test_feed_mismatch_rejected():
    readiness = evaluate_public_feed_adapter_readiness(
        _descriptor(
            connector_plan=_plan(feed_type=PublicFeedType.TRADES, dialect=_dialect(feed_type=PublicFeedType.TRADES))
        )
    )

    assert readiness.accepted is False
    assert "public_feed_adapter:feed_type_mismatch" in readiness.rejection_reasons


def test_dialect_mismatch_rejected():
    readiness = evaluate_public_feed_adapter_readiness(_descriptor(dialect_ids=("other-dialect",)))

    assert readiness.accepted is False
    assert "public_feed_adapter:dialect_mismatch" in readiness.rejection_reasons


def test_descriptor_rejection_reasons_propagate():
    readiness = evaluate_public_feed_adapter_readiness(_descriptor(rejection_reasons=("public_feed_adapter:manual",)))

    assert readiness.accepted is False
    assert "public_feed_adapter:manual" in readiness.rejection_reasons


def test_adapter_readiness_false_for_none_or_rejected():
    assert public_feed_adapter_ready(None) is False
    assert public_feed_adapter_ready(evaluate_public_feed_adapter_readiness(_descriptor(enabled=False))) is False


def test_descriptor_serializer_roundtrip_json_safe():
    payload = public_feed_adapter_descriptor_to_dict(_descriptor())

    restored = public_feed_adapter_descriptor_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_adapter_descriptor_to_dict(restored) == payload


def test_readiness_serializer_roundtrip_json_safe():
    payload = public_feed_adapter_readiness_to_dict(evaluate_public_feed_adapter_readiness(_descriptor()))

    restored = public_feed_adapter_readiness_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_adapter_readiness_to_dict(restored) == payload


def test_adapter_readiness_is_deterministic():
    first = public_feed_adapter_readiness_to_dict(evaluate_public_feed_adapter_readiness(_descriptor(), now_ns=1_500))
    second = public_feed_adapter_readiness_to_dict(evaluate_public_feed_adapter_readiness(_descriptor(), now_ns=1_500))

    assert first == second


def test_protocol_has_no_connect_start_or_recv_methods():
    protocol_names = set(PublicFeedAdapterProtocol.__dict__)

    assert {"connect", "start", "stop", "recv", "receive", "send"}.isdisjoint(protocol_names)
    assert {"descriptor", "readiness"}.issubset(protocol_names)


def test_new_public_feed_adapter_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_adapter.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets", "asyncio"}

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


def _descriptor(**overrides: object) -> PublicFeedAdapterDescriptor:
    values = {
        "adapter_id": "adapter-21q",
        "venue_id": VenueId.BINANCE_USDM,
        "supported_feed_types": (PublicFeedType.L2_ORDERBOOK,),
        "supported_symbols": ("BTCUSDT",),
        "dialect_ids": ("unit-binance-l2",),
        "network_authorization": _auth(),
        "connector_plan": _plan(),
        "enabled": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedAdapterDescriptor(**values)  # type: ignore[arg-type]


def _auth(**overrides: object) -> PublicNetworkAuthorization:
    values = {
        "authorization_id": "public-net-auth-21q",
        "schema_version": PUBLIC_NETWORK_AUTHORIZATION_SCHEMA_VERSION,
        "status": PublicNetworkAuthorizationStatus.AUTHORIZED,
        "venue_id": VenueId.BINANCE_USDM,
        "allowed_symbols": ("BTCUSDT",),
        "allowed_feed_types": (PublicFeedType.L2_ORDERBOOK,),
        "allowed_dialect_ids": ("unit-binance-l2",),
        "max_connections": 1,
        "max_subscriptions": 4,
        "max_messages_per_second": 10.0,
        "max_snapshot_requests_per_minute": 2,
        "approved_by": "operator-21q",
        "approved_at_ns": 1_000,
        "expires_at_ns": 10_000,
        "official_doc_bundle_id": "bundle-21q",
        "verification_result_ids": ("verification-21q",),
        "region_review_reference": "region-review-21q",
        "data_tos_review_reference": "data-tos-21q",
        "network_allowed": True,
        "private_api_forbidden": True,
        "credentials_forbidden": True,
        "live_trading_forbidden": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicNetworkAuthorization(**values)  # type: ignore[arg-type]


def _plan(**overrides: object) -> PublicFeedConnectorPlan:
    values = {
        "connector_id": "connector-21q",
        "mode": PublicFeedConnectorMode.OFFLINE_SIMULATED,
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "dialect": _dialect(),
        "subscription": _subscription(),
        "policy": _policy(),
        "created_at_ns": 1_000,
        "require_verified_dialect": True,
        "require_subscription_enabled": True,
        "require_policy_valid": True,
        "network_enabled": False,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedConnectorPlan(**values)  # type: ignore[arg-type]


def _dialect(**overrides: object) -> PublicFeedDialectSpec:
    values = {
        "dialect_id": "unit-binance-l2",
        "venue_id": VenueId.BINANCE_USDM,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "instrument_type": InstrumentType.USDT_PERP,
        "verification_status": FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS,
        "official_doc_refs": ("https://docs.example.test/binance-usdm/l2",),
        "requires_rest_snapshot": True,
        "supports_delta_stream": True,
        "supports_checksum": False,
        "sequence_model": FeedSequenceModel.PREV_FINAL_RANGE,
        "checksum_model": FeedChecksumModel.NONE,
        "requires_heartbeat": True,
        "requires_ping_pong": False,
        "supports_resync": True,
        "max_gap_tolerance": 0,
        "max_staleness_ns": 1_000,
        "max_receive_lag_ns": 1_000,
        "enabled_for_connector": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedDialectSpec(**values)  # type: ignore[arg-type]


def _subscription(**overrides: object) -> PublicFeedSubscription:
    values = {
        "subscription_id": "sub-21q",
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "depth": 20,
        "enabled": True,
        "created_at_ns": 1_000,
    }
    values.update(overrides)
    return PublicFeedSubscription(**values)  # type: ignore[arg-type]


def _policy(**overrides: object) -> PublicFeedPolicy:
    values = {
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "max_staleness_ns": 1_000,
        "max_receive_lag_ns": 1_000,
        "require_replay_cursor": True,
        "require_order_book": False,
        "reject_on_gap": True,
        "reject_on_resync": True,
        "reject_on_stale": True,
    }
    values.update(overrides)
    return PublicFeedPolicy(**values)  # type: ignore[arg-type]


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
