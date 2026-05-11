from __future__ import annotations

import ast
import json
from pathlib import Path

from crypto_core.data.public_feed_adapter import (
    PublicFeedAdapterDescriptor,
    PublicFeedAdapterProtocol,
    PublicFeedAdapterReadiness,
    evaluate_public_feed_adapter_readiness,
)
from crypto_core.data.public_feed_connector import (
    PublicFeedConnectorMode,
    PublicFeedConnectorPlan,
    evaluate_public_feed_connector_gate,
)
from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    PublicFeedDialectSpec,
)
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.data.public_feed_run_plan import (
    PublicFeedConnectorRunPlan,
    PublicFeedRunMode,
    evaluate_public_feed_run_plan,
    public_feed_run_decision_from_dict,
    public_feed_run_decision_ready,
    public_feed_run_decision_to_dict,
    public_feed_run_plan_from_dict,
    public_feed_run_plan_to_dict,
)
from crypto_core.data.public_feed_source import PublicFeedSubscription
from crypto_core.data.public_network_authorization import (
    PUBLIC_NETWORK_AUTHORIZATION_SCHEMA_VERSION,
    PublicNetworkAuthorization,
    PublicNetworkAuthorizationStatus,
    evaluate_public_network_authorization,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, VenueId


def test_valid_offline_replay_run_plan_accepted():
    decision = evaluate_public_feed_run_plan(_run_plan())

    assert decision.accepted is True
    assert public_feed_run_decision_ready(decision) is True
    assert decision.offline_only is True
    assert decision.network_start_forbidden is True
    assert decision.rejection_reasons == ()


def test_disabled_mode_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(mode=PublicFeedRunMode.DISABLED))

    assert decision.accepted is False
    assert "public_run:disabled" in decision.rejection_reasons


def test_network_mode_without_network_start_forbidden_rejected():
    decision = evaluate_public_feed_run_plan(
        _run_plan(
            mode=PublicFeedRunMode.PUBLIC_NETWORK_AUTHORIZED_BUT_NOT_STARTED,
            network_start_forbidden=False,
        )
    )

    assert decision.accepted is False
    assert "public_run:network_start_forbidden_required" in decision.rejection_reasons


def test_dry_run_only_false_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(dry_run_only=False))

    assert decision.accepted is False
    assert "public_run:dry_run_required" in decision.rejection_reasons


def test_adapter_not_ready_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(adapter_readiness=_adapter_readiness(enabled=False)))

    assert decision.accepted is False
    assert "public_run:adapter_not_ready" in decision.rejection_reasons


def test_network_auth_not_accepted_rejected():
    decision = evaluate_public_feed_run_plan(
        _run_plan(network_authorization_decision=evaluate_public_network_authorization(_auth(network_allowed=False)))
    )

    assert decision.accepted is False
    assert "public_run:network_not_authorized" in decision.rejection_reasons


def test_connector_gate_not_accepted_rejected():
    decision = evaluate_public_feed_run_plan(
        _run_plan(connector_gate=evaluate_public_feed_connector_gate(_connector_plan(network_enabled=True)))
    )

    assert decision.accepted is False
    assert "public_run:connector_gate_not_ready" in decision.rejection_reasons


def test_subscription_missing_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(subscription=None))  # type: ignore[arg-type]

    assert decision.accepted is False
    assert "public_run:subscription_missing" in decision.rejection_reasons


def test_policy_missing_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(policy=None))  # type: ignore[arg-type]

    assert decision.accepted is False
    assert "public_run:policy_missing" in decision.rejection_reasons


def test_venue_mismatch_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(subscription=_subscription(venue_id=VenueId.OKX_SWAP)))

    assert decision.accepted is False
    assert "public_run:venue_mismatch" in decision.rejection_reasons


def test_symbol_mismatch_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(subscription=_subscription(symbol="ETHUSDT")))

    assert decision.accepted is False
    assert "public_run:symbol_mismatch" in decision.rejection_reasons


def test_feed_mismatch_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(subscription=_subscription(feed_type=PublicFeedType.TRADES)))

    assert decision.accepted is False
    assert "public_run:feed_type_mismatch" in decision.rejection_reasons


def test_invalid_budgets_rejected():
    decision = evaluate_public_feed_run_plan(_run_plan(max_runtime_ns=0))

    assert decision.accepted is False
    assert "public_run:invalid_budget" in decision.rejection_reasons


def test_plan_rejection_reasons_propagate():
    decision = evaluate_public_feed_run_plan(_run_plan(rejection_reasons=("public_run:manual",)))

    assert decision.accepted is False
    assert "public_run:manual" in decision.rejection_reasons


def test_decision_ready_false_for_none_or_rejected():
    assert public_feed_run_decision_ready(None) is False
    assert (
        public_feed_run_decision_ready(evaluate_public_feed_run_plan(_run_plan(mode=PublicFeedRunMode.DISABLED)))
        is False
    )


def test_run_plan_serializer_roundtrip_json_safe():
    payload = public_feed_run_plan_to_dict(_run_plan())
    decision_payload = public_feed_run_decision_to_dict(evaluate_public_feed_run_plan(_run_plan()))

    restored = public_feed_run_plan_from_dict(json.loads(json.dumps(payload)))
    restored_decision = public_feed_run_decision_from_dict(json.loads(json.dumps(decision_payload)))

    assert public_feed_run_plan_to_dict(restored) == payload
    assert public_feed_run_decision_to_dict(restored_decision) == decision_payload


def test_run_plan_decision_is_deterministic():
    first = public_feed_run_decision_to_dict(evaluate_public_feed_run_plan(_run_plan()))
    second = public_feed_run_decision_to_dict(evaluate_public_feed_run_plan(_run_plan()))

    assert first == second


def test_new_public_feed_run_plan_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_run_plan.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets", "asyncio"}

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imports)


def test_no_connect_start_recv_or_stop_methods_exist_on_adapter_protocol():
    protocol_names = set(PublicFeedAdapterProtocol.__dict__)

    assert {"connect", "start", "stop", "recv", "receive", "send"}.isdisjoint(protocol_names)
    assert {"descriptor", "readiness"}.issubset(protocol_names)


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _run_plan(**overrides: object) -> PublicFeedConnectorRunPlan:
    descriptor = _descriptor()
    values = {
        "run_id": "run-21r",
        "mode": PublicFeedRunMode.OFFLINE_REPLAY,
        "adapter_descriptor": descriptor,
        "adapter_readiness": evaluate_public_feed_adapter_readiness(descriptor, now_ns=1_500),
        "network_authorization_decision": evaluate_public_network_authorization(descriptor.network_authorization),
        "connector_gate": evaluate_public_feed_connector_gate(descriptor.connector_plan),
        "subscription": _subscription(),
        "policy": _policy(),
        "max_runtime_ns": 1_000_000,
        "max_envelopes": 100,
        "max_reconnects": 0,
        "created_at_ns": 1_000,
        "dry_run_only": True,
        "network_start_forbidden": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedConnectorRunPlan(**values)  # type: ignore[arg-type]


def _adapter_readiness(**descriptor_overrides: object) -> PublicFeedAdapterReadiness:
    return evaluate_public_feed_adapter_readiness(_descriptor(**descriptor_overrides), now_ns=1_500)


def _descriptor(**overrides: object) -> PublicFeedAdapterDescriptor:
    values = {
        "adapter_id": "adapter-21r",
        "venue_id": VenueId.BINANCE_USDM,
        "supported_feed_types": (PublicFeedType.L2_ORDERBOOK,),
        "supported_symbols": ("BTCUSDT",),
        "dialect_ids": ("unit-binance-l2",),
        "network_authorization": _auth(),
        "connector_plan": _connector_plan(),
        "enabled": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedAdapterDescriptor(**values)  # type: ignore[arg-type]


def _auth(**overrides: object) -> PublicNetworkAuthorization:
    values = {
        "authorization_id": "public-net-auth-21r",
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
        "approved_by": "operator-21r",
        "approved_at_ns": 1_000,
        "expires_at_ns": 10_000,
        "official_doc_bundle_id": "bundle-21r",
        "verification_result_ids": ("verification-21r",),
        "region_review_reference": "region-review-21r",
        "data_tos_review_reference": "data-tos-21r",
        "network_allowed": True,
        "private_api_forbidden": True,
        "credentials_forbidden": True,
        "live_trading_forbidden": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicNetworkAuthorization(**values)  # type: ignore[arg-type]


def _connector_plan(**overrides: object) -> PublicFeedConnectorPlan:
    values = {
        "connector_id": "connector-21r",
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
        "subscription_id": "sub-21r",
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
