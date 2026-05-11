from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_ingress import (
    PublicFeedIngressPacket,
    evaluate_public_feed_ingress_packet,
    public_feed_ingress_decision_from_dict,
    public_feed_ingress_decision_ready,
    public_feed_ingress_decision_to_dict,
    public_feed_ingress_packet_from_dict,
    public_feed_ingress_packet_to_dict,
)
from crypto_core.data.public_feed_run_plan import PublicFeedConnectorRunDecision, PublicFeedRunMode
from crypto_core.data.public_feed_source import PublicFeedSubscription, RawPublicFeedEnvelope
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import PublicFeedType, VenueId


def test_valid_ingress_packet_accepted():
    decision = evaluate_public_feed_ingress_packet(_packet())

    assert decision.accepted is True
    assert public_feed_ingress_decision_ready(decision) is True
    assert decision.rejection_reasons == ()


def test_missing_packet_rejected():
    decision = evaluate_public_feed_ingress_packet(None)

    assert decision.accepted is False
    assert decision.rejection_reasons == ("public_ingress:packet_missing",)


def test_run_not_ready_rejected():
    run_decision = replace(_run_decision(), accepted=False, rejection_reasons=("public_run:disabled",))
    decision = evaluate_public_feed_ingress_packet(_packet(run_decision=run_decision))

    assert decision.accepted is False
    assert "public_ingress:run_not_ready" in decision.rejection_reasons
    assert "public_run:disabled" in decision.rejection_reasons


def test_subscription_missing_rejected():
    decision = evaluate_public_feed_ingress_packet(_packet(subscription=None))  # type: ignore[arg-type]

    assert decision.accepted is False
    assert "public_ingress:subscription_missing" in decision.rejection_reasons


def test_envelope_missing_rejected():
    decision = evaluate_public_feed_ingress_packet(_packet(envelope=None))  # type: ignore[arg-type]

    assert decision.accepted is False
    assert "public_ingress:envelope_missing" in decision.rejection_reasons


def test_venue_mismatch_rejected():
    decision = evaluate_public_feed_ingress_packet(_packet(envelope=_envelope(venue_id=VenueId.OKX_SWAP)))

    assert decision.accepted is False
    assert "public_ingress:venue_mismatch" in decision.rejection_reasons


def test_symbol_mismatch_rejected():
    decision = evaluate_public_feed_ingress_packet(_packet(envelope=_envelope(symbol="ETHUSDT")))

    assert decision.accepted is False
    assert "public_ingress:symbol_mismatch" in decision.rejection_reasons


def test_feed_mismatch_rejected():
    decision = evaluate_public_feed_ingress_packet(_packet(envelope=_envelope(feed_type=PublicFeedType.TRADES)))

    assert decision.accepted is False
    assert "public_ingress:feed_type_mismatch" in decision.rejection_reasons


def test_invalid_received_at_rejected():
    decision = evaluate_public_feed_ingress_packet(_packet(received_at_ns=999))

    assert decision.accepted is False
    assert "public_ingress:invalid_received_at" in decision.rejection_reasons


def test_envelope_rejection_propagates():
    decision = evaluate_public_feed_ingress_packet(
        _packet(envelope=_envelope(normalized=False, rejection_reasons=("public_feed_source:manual",)))
    )

    assert decision.accepted is False
    assert "public_ingress:envelope_rejected" in decision.rejection_reasons
    assert "public_feed_source:not_normalized" in decision.rejection_reasons
    assert "public_feed_source:manual" in decision.rejection_reasons


def test_packet_rejection_propagates():
    decision = evaluate_public_feed_ingress_packet(_packet(rejection_reasons=("public_ingress:manual",)))

    assert decision.accepted is False
    assert "public_ingress:manual" in decision.rejection_reasons


def test_ingress_serializer_roundtrip_json_safe():
    payload = public_feed_ingress_packet_to_dict(_packet())
    decision_payload = public_feed_ingress_decision_to_dict(evaluate_public_feed_ingress_packet(_packet()))

    restored = public_feed_ingress_packet_from_dict(json.loads(json.dumps(payload)))
    restored_decision = public_feed_ingress_decision_from_dict(json.loads(json.dumps(decision_payload)))

    assert public_feed_ingress_packet_to_dict(restored) == payload
    assert public_feed_ingress_decision_to_dict(restored_decision) == decision_payload


def test_ingress_decision_is_deterministic():
    first = public_feed_ingress_decision_to_dict(evaluate_public_feed_ingress_packet(_packet()))
    second = public_feed_ingress_decision_to_dict(evaluate_public_feed_ingress_packet(_packet()))

    assert first == second


def test_new_public_feed_ingress_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_ingress.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets", "asyncio"}

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imports)


def test_new_public_feed_ingress_module_has_no_network_client_or_endpoint_strings():
    module_text = Path("src/crypto_core/data/public_feed_ingress.py").read_text(encoding="utf-8").lower()

    assert "http" not in module_text
    assert "websocket" not in module_text
    assert "endpoint" not in module_text
    assert "client" not in module_text


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _packet(**overrides: object) -> PublicFeedIngressPacket:
    values = {
        "packet_id": "packet-21s",
        "run_decision": _run_decision(),
        "subscription": _subscription(),
        "envelope": _envelope(),
        "received_at_ns": 1_020,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedIngressPacket(**values)  # type: ignore[arg-type]


def _run_decision(**overrides: object) -> PublicFeedConnectorRunDecision:
    values = {
        "accepted": True,
        "run_id": "run-21s",
        "mode": PublicFeedRunMode.OFFLINE_REPLAY,
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "offline_only": True,
        "network_start_forbidden": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedConnectorRunDecision(**values)  # type: ignore[arg-type]


def _subscription(**overrides: object) -> PublicFeedSubscription:
    values = {
        "subscription_id": "sub-21s",
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


def _envelope(**overrides: object) -> RawPublicFeedEnvelope:
    values = {
        "envelope_id": "envelope-21s",
        "subscription_id": "sub-21s",
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "event_time_ns": 1_000,
        "receive_time_ns": 1_010,
        "sequence_id": 10,
        "payload_hash": "hash-21s",
        "raw_payload_ref": "raw-ref-21s",
        "normalized": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return RawPublicFeedEnvelope(**values)  # type: ignore[arg-type]


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
