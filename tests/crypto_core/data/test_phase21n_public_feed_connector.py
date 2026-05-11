from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_connector import (
    PublicFeedConnectorMode,
    PublicFeedConnectorPlan,
    evaluate_public_feed_connector_gate,
    public_feed_connector_gate_decision_from_dict,
    public_feed_connector_gate_decision_to_dict,
    public_feed_connector_plan_from_dict,
    public_feed_connector_plan_to_dict,
    public_feed_connector_ready,
)
from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    PublicFeedDialectSpec,
)
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.data.public_feed_source import PublicFeedSubscription
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, VenueId


def test_valid_offline_simulated_connector_plan_accepted():
    decision = evaluate_public_feed_connector_gate(_plan())

    assert decision.accepted is True
    assert public_feed_connector_ready(decision) is True
    assert decision.offline_only is True
    assert decision.rejection_reasons == ()


def test_missing_plan_rejected():
    decision = evaluate_public_feed_connector_gate(None)

    assert decision.accepted is False
    assert decision.rejection_reasons == ("public_connector:plan_missing",)


def test_disabled_mode_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(mode=PublicFeedConnectorMode.DISABLED))

    assert decision.accepted is False
    assert "public_connector:disabled" in decision.rejection_reasons


def test_realtime_mode_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(mode=PublicFeedConnectorMode.REALTIME_DISABLED))

    assert decision.accepted is False
    assert "public_connector:realtime_disabled" in decision.rejection_reasons


def test_network_enabled_true_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(network_enabled=True))

    assert decision.accepted is False
    assert "public_connector:network_forbidden" in decision.rejection_reasons


def test_unverified_dialect_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(dialect=_dialect_unverified()))

    assert decision.accepted is False
    assert "public_connector:dialect_not_ready" in decision.rejection_reasons
    assert "public_feed_dialect:unverified" in decision.rejection_reasons


def test_non_connector_ready_dialect_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(dialect=_dialect(supports_delta_stream=False)))

    assert decision.accepted is False
    assert "public_connector:dialect_not_ready" in decision.rejection_reasons
    assert "public_feed_dialect:delta_stream_unsupported" in decision.rejection_reasons


def test_disabled_subscription_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(subscription=_subscription(enabled=False)))

    assert decision.accepted is False
    assert "public_connector:subscription_disabled" in decision.rejection_reasons
    assert "public_connector:subscription_rejected" in decision.rejection_reasons


def test_malformed_policy_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(policy=_policy(max_staleness_ns=0)))

    assert decision.accepted is False
    assert "public_connector:policy_rejected" in decision.rejection_reasons
    assert "public_feed:invalid_staleness" in decision.rejection_reasons


def test_venue_mismatch_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(subscription=_subscription(venue_id=VenueId.DERIBIT)))

    assert decision.accepted is False
    assert "public_connector:venue_mismatch" in decision.rejection_reasons


def test_symbol_mismatch_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(policy=_policy(symbol="ETHUSDT")))

    assert decision.accepted is False
    assert "public_connector:symbol_mismatch" in decision.rejection_reasons


def test_feed_type_mismatch_rejected():
    decision = evaluate_public_feed_connector_gate(_plan(dialect=_dialect(feed_type=PublicFeedType.TRADES)))

    assert decision.accepted is False
    assert "public_connector:feed_type_mismatch" in decision.rejection_reasons


def test_plan_rejection_reasons_propagate():
    decision = evaluate_public_feed_connector_gate(_plan(rejection_reasons=("public_connector:manual_block",)))

    assert decision.accepted is False
    assert "public_connector:manual_block" in decision.rejection_reasons


def test_gate_ready_false_for_none_or_rejected():
    assert public_feed_connector_ready(None) is False
    assert public_feed_connector_ready(evaluate_public_feed_connector_gate(_plan(network_enabled=True))) is False


def test_plan_serializer_roundtrip_json_safe():
    payload = public_feed_connector_plan_to_dict(_plan())

    restored = public_feed_connector_plan_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_connector_plan_to_dict(restored) == payload


def test_decision_serializer_roundtrip_json_safe():
    payload = public_feed_connector_gate_decision_to_dict(evaluate_public_feed_connector_gate(_plan()))

    restored = public_feed_connector_gate_decision_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_connector_gate_decision_to_dict(restored) == payload


def test_connector_gate_is_deterministic():
    first = public_feed_connector_gate_decision_to_dict(evaluate_public_feed_connector_gate(_plan()))
    second = public_feed_connector_gate_decision_to_dict(evaluate_public_feed_connector_gate(_plan()))

    assert first == second


def test_new_public_feed_connector_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_connector.py")
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


def _plan(**overrides: object) -> PublicFeedConnectorPlan:
    values = {
        "connector_id": "connector-21n",
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


def _dialect_unverified() -> PublicFeedDialectSpec:
    return replace(
        _dialect(),
        verification_status=FeedDialectVerificationStatus.UNVERIFIED,
        official_doc_refs=(),
        enabled_for_connector=False,
    )


def _subscription(**overrides: object) -> PublicFeedSubscription:
    values = {
        "subscription_id": "sub-21n",
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
