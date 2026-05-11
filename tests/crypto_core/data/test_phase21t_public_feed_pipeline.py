from __future__ import annotations

import ast
import json
from pathlib import Path

from crypto_core.data.public_feed_adapter import (
    PublicFeedAdapterDescriptor,
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
from crypto_core.data.public_feed_ingress import PublicFeedIngressPacket
from crypto_core.data.public_feed_pipeline import (
    PublicFeedPipelineInput,
    public_feed_pipeline_input_from_dict,
    public_feed_pipeline_input_to_dict,
    public_feed_pipeline_ready,
    public_feed_pipeline_result_from_dict,
    public_feed_pipeline_result_to_dict,
    run_offline_public_feed_pipeline,
)
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.data.public_feed_run_plan import (
    PublicFeedConnectorRunPlan,
    PublicFeedRunMode,
    evaluate_public_feed_run_plan,
)
from crypto_core.data.public_feed_source import (
    PublicFeedBatch,
    PublicFeedSubscription,
    RawPublicFeedEnvelope,
)
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
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, PublicMarketDataEvent, VenueId


def test_valid_end_to_end_offline_pipeline_accepted():
    result = run_offline_public_feed_pipeline(_pipeline_input())

    assert result.accepted is True
    assert result.accepted_for_paper is True
    assert public_feed_pipeline_ready(result) is True
    assert result.rejection_reasons == ()
    assert result.ingest_result is not None
    assert result.readiness_snapshot is not None


def test_missing_input_rejected():
    result = run_offline_public_feed_pipeline(None)

    assert result.accepted is False
    assert result.rejection_reasons[0] == "public_pipeline:input_missing"


def test_input_rejection_reasons_propagate():
    result = run_offline_public_feed_pipeline(_pipeline_input(rejection_reasons=("public_pipeline:manual_reject",)))

    assert result.accepted is False
    assert "public_pipeline:input_rejected" in result.rejection_reasons
    assert "public_pipeline:manual_reject" in result.rejection_reasons


def test_rejected_run_blocks_pipeline_before_readiness_accepted():
    result = run_offline_public_feed_pipeline(_pipeline_input(run_plan=_run_plan(mode=PublicFeedRunMode.DISABLED)))

    assert result.accepted is False
    assert result.accepted_for_paper is False
    assert result.ingest_result is None
    assert result.readiness_snapshot is None
    assert "public_pipeline:run_rejected" in result.rejection_reasons


def test_rejected_ingress_blocks_pipeline():
    bad_envelope = _envelope(normalized=False)
    result = run_offline_public_feed_pipeline(_pipeline_input(ingress_packets=(_packet(envelope=bad_envelope),)))

    assert result.accepted is False
    assert result.ingest_result is None
    assert "public_pipeline:ingress_rejected" in result.rejection_reasons
    assert "public_ingress:envelope_rejected" in result.rejection_reasons


def test_packet_batch_envelope_mismatch_rejected():
    packet = _packet(envelope=_envelope(envelope_id="other-envelope"))
    result = run_offline_public_feed_pipeline(_pipeline_input(ingress_packets=(packet,)))

    assert result.accepted is False
    assert result.ingest_result is None
    assert "public_pipeline:packet_batch_mismatch" in result.rejection_reasons


def test_event_batch_mismatch_rejected_through_ingest():
    result = run_offline_public_feed_pipeline(_pipeline_input(events=(_event(payload_hash="different-hash"),)))

    assert result.accepted is False
    assert result.ingest_result is not None
    assert "public_pipeline:ingest_rejected" in result.rejection_reasons
    assert "public_feed_ingest:event_hash_mismatch" in result.rejection_reasons


def test_ingest_rejection_blocks_pipeline():
    batch = _batch(rejection_reasons=("public_feed_source:batch_manual",))
    result = run_offline_public_feed_pipeline(_pipeline_input(batch=batch))

    assert result.accepted is False
    assert result.ingest_result is not None
    assert "public_pipeline:ingest_rejected" in result.rejection_reasons
    assert "public_feed_source:batch_manual" in result.rejection_reasons


def test_readiness_rejection_blocks_pipeline():
    policy = _policy(require_order_book=True)
    result = run_offline_public_feed_pipeline(_pipeline_input(run_plan=_run_plan(policy=policy)))

    assert result.accepted is False
    assert result.readiness_snapshot is not None
    assert "public_pipeline:readiness_rejected" in result.rejection_reasons
    assert "public_data:order_book_not_ready" in result.rejection_reasons


def test_aggregate_rejection_reasons_are_deterministic():
    bad_input = _pipeline_input(
        run_plan=_run_plan(mode=PublicFeedRunMode.DISABLED),
        ingress_packets=(_packet(envelope=_envelope(normalized=False)),),
        rejection_reasons=("public_pipeline:manual_reject",),
    )

    first = public_feed_pipeline_result_to_dict(run_offline_public_feed_pipeline(bad_input))
    second = public_feed_pipeline_result_to_dict(run_offline_public_feed_pipeline(bad_input))

    assert first == second


def test_pipeline_ready_false_for_none_or_rejected():
    assert public_feed_pipeline_ready(None) is False
    assert public_feed_pipeline_ready(run_offline_public_feed_pipeline(None)) is False


def test_pipeline_result_serializer_roundtrip_json_safe():
    input_payload = public_feed_pipeline_input_to_dict(_pipeline_input())
    result_payload = public_feed_pipeline_result_to_dict(run_offline_public_feed_pipeline(_pipeline_input()))

    restored_input = public_feed_pipeline_input_from_dict(json.loads(json.dumps(input_payload)))
    restored_result = public_feed_pipeline_result_from_dict(json.loads(json.dumps(result_payload)))

    assert public_feed_pipeline_input_to_dict(restored_input) == input_payload
    assert public_feed_pipeline_result_to_dict(restored_result) == result_payload


def test_pipeline_is_deterministic_for_same_input():
    first = public_feed_pipeline_result_to_dict(run_offline_public_feed_pipeline(_pipeline_input()))
    second = public_feed_pipeline_result_to_dict(run_offline_public_feed_pipeline(_pipeline_input()))

    assert first == second


def test_new_public_feed_pipeline_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_pipeline.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets", "asyncio"}

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imports)


def test_new_public_feed_pipeline_module_has_no_runtime_network_verbs():
    module_path = Path("src/crypto_core/data/public_feed_pipeline.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    module_text = module_path.read_text(encoding="utf-8").lower()

    assert {"connect", "start", "stop", "recv", "receive", "send", "subscribe"}.isdisjoint(function_names)
    assert "websocket" not in module_text
    assert "endpoint" not in module_text
    assert "network" not in module_text


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _pipeline_input(**overrides: object) -> PublicFeedPipelineInput:
    run_plan = _run_plan()
    run_decision = evaluate_public_feed_run_plan(run_plan)
    envelope = _envelope()
    values = {
        "pipeline_id": "pipeline-21t",
        "run_plan": run_plan,
        "ingress_packets": (_packet(run_decision=run_decision, envelope=envelope),),
        "batch": _batch(envelopes=(envelope,)),
        "events": (_event(),),
        "now_ns": 1_020,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedPipelineInput(**values)  # type: ignore[arg-type]


def _packet(**overrides: object) -> PublicFeedIngressPacket:
    values = {
        "packet_id": "packet-21t",
        "run_decision": evaluate_public_feed_run_plan(_run_plan()),
        "subscription": _subscription(),
        "envelope": _envelope(),
        "received_at_ns": 1_020,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedIngressPacket(**values)  # type: ignore[arg-type]


def _batch(**overrides: object) -> PublicFeedBatch:
    values = {
        "batch_id": "batch-21t",
        "subscription": _subscription(),
        "envelopes": (_envelope(),),
        "created_at_ns": 1_000,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedBatch(**values)  # type: ignore[arg-type]


def _event(**overrides: object) -> PublicMarketDataEvent:
    values = {
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "event_time_ns": 1_000,
        "receive_time_ns": 1_010,
        "sequence_id": 10,
        "payload_hash": "hash-21t",
        "raw_payload_ref": "raw-ref-21t",
        "normalized": True,
    }
    values.update(overrides)
    return PublicMarketDataEvent(**values)  # type: ignore[arg-type]


def _envelope(**overrides: object) -> RawPublicFeedEnvelope:
    values = {
        "envelope_id": "envelope-21t",
        "subscription_id": "sub-21t",
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "event_time_ns": 1_000,
        "receive_time_ns": 1_010,
        "sequence_id": 10,
        "payload_hash": "hash-21t",
        "raw_payload_ref": "raw-ref-21t",
        "normalized": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return RawPublicFeedEnvelope(**values)  # type: ignore[arg-type]


def _run_plan(**overrides: object) -> PublicFeedConnectorRunPlan:
    descriptor = _descriptor()
    values = {
        "run_id": "run-21t",
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


def _descriptor(**overrides: object) -> PublicFeedAdapterDescriptor:
    values = {
        "adapter_id": "adapter-21t",
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
        "authorization_id": "public-net-auth-21t",
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
        "approved_by": "operator-21t",
        "approved_at_ns": 1_000,
        "expires_at_ns": 10_000,
        "official_doc_bundle_id": "bundle-21t",
        "verification_result_ids": ("verification-21t",),
        "region_review_reference": "region-review-21t",
        "data_tos_review_reference": "data-tos-21t",
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
        "connector_id": "connector-21t",
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
        "subscription_id": "sub-21t",
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
