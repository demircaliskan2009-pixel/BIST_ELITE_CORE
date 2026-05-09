from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_network_authorization import (
    PUBLIC_NETWORK_AUTHORIZATION_SCHEMA_VERSION,
    PublicNetworkAuthorization,
    PublicNetworkAuthorizationStatus,
    evaluate_public_network_authorization,
    public_network_authorization_decision_from_dict,
    public_network_authorization_decision_to_dict,
    public_network_authorization_from_dict,
    public_network_authorization_ready,
    public_network_authorization_to_dict,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import PublicFeedType, VenueId


def test_valid_authorization_accepted():
    decision = evaluate_public_network_authorization(_auth(), now_ns=1_500)

    assert decision.accepted is True
    assert public_network_authorization_ready(decision) is True
    assert decision.rejection_reasons == ()


def test_missing_auth_rejected():
    decision = evaluate_public_network_authorization(None)

    assert decision.accepted is False
    assert decision.rejection_reasons == ("public_network:authorization_missing",)


def test_network_allowed_false_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), network_allowed=False))

    assert decision.accepted is False
    assert "public_network:not_allowed" in decision.rejection_reasons


def test_private_api_forbidden_false_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), private_api_forbidden=False))

    assert decision.accepted is False
    assert "public_network:private_api_not_forbidden" in decision.rejection_reasons


def test_credentials_forbidden_false_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), credentials_forbidden=False))

    assert decision.accepted is False
    assert "public_network:credentials_not_forbidden" in decision.rejection_reasons


def test_live_trading_forbidden_false_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), live_trading_forbidden=False))

    assert decision.accepted is False
    assert "public_network:live_trading_not_forbidden" in decision.rejection_reasons


def test_empty_symbols_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), allowed_symbols=()))

    assert decision.accepted is False
    assert "public_network:symbols_missing" in decision.rejection_reasons


def test_empty_feeds_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), allowed_feed_types=()))

    assert decision.accepted is False
    assert "public_network:feeds_missing" in decision.rejection_reasons


def test_empty_dialects_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), allowed_dialect_ids=()))

    assert decision.accepted is False
    assert "public_network:dialects_missing" in decision.rejection_reasons


def test_invalid_budgets_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), max_connections=0))

    assert decision.accepted is False
    assert "public_network:invalid_budget" in decision.rejection_reasons


def test_missing_approval_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), approved_by=""))

    assert decision.accepted is False
    assert "public_network:approval_missing" in decision.rejection_reasons


def test_missing_docs_rejected():
    decision = evaluate_public_network_authorization(replace(_auth(), official_doc_bundle_id=""))

    assert decision.accepted is False
    assert "public_network:official_docs_missing" in decision.rejection_reasons


def test_missing_region_or_tos_review_rejected():
    region_decision = evaluate_public_network_authorization(replace(_auth(), region_review_reference=""))
    tos_decision = evaluate_public_network_authorization(replace(_auth(), data_tos_review_reference=""))

    assert "public_network:region_review_missing" in region_decision.rejection_reasons
    assert "public_network:data_tos_review_missing" in tos_decision.rejection_reasons


def test_expired_auth_rejected():
    decision = evaluate_public_network_authorization(_auth(), now_ns=10_001)

    assert decision.accepted is False
    assert "public_network:expired" in decision.rejection_reasons


def test_auth_rejection_reasons_propagate():
    decision = evaluate_public_network_authorization(replace(_auth(), rejection_reasons=("public_network:manual",)))

    assert decision.accepted is False
    assert "public_network:manual" in decision.rejection_reasons


def test_serializer_roundtrip_json_safe():
    payload = public_network_authorization_to_dict(_auth())
    decision_payload = public_network_authorization_decision_to_dict(evaluate_public_network_authorization(_auth()))

    restored = public_network_authorization_from_dict(json.loads(json.dumps(payload)))
    restored_decision = public_network_authorization_decision_from_dict(json.loads(json.dumps(decision_payload)))

    assert public_network_authorization_to_dict(restored) == payload
    assert public_network_authorization_decision_to_dict(restored_decision) == decision_payload


def test_authorization_decision_is_deterministic():
    first = public_network_authorization_decision_to_dict(evaluate_public_network_authorization(_auth(), now_ns=1_500))
    second = public_network_authorization_decision_to_dict(evaluate_public_network_authorization(_auth(), now_ns=1_500))

    assert first == second


def test_new_public_network_authorization_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_network_authorization.py")
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


def _auth(**overrides: object) -> PublicNetworkAuthorization:
    values = {
        "authorization_id": "public-net-auth-21p",
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
        "approved_by": "operator-21p",
        "approved_at_ns": 1_000,
        "expires_at_ns": 10_000,
        "official_doc_bundle_id": "bundle-21p",
        "verification_result_ids": ("verification-21p",),
        "region_review_reference": "region-review-21p",
        "data_tos_review_reference": "data-tos-21p",
        "network_allowed": True,
        "private_api_forbidden": True,
        "credentials_forbidden": True,
        "live_trading_forbidden": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicNetworkAuthorization(**values)  # type: ignore[arg-type]


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
