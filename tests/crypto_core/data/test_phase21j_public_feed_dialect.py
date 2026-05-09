from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    build_public_feed_resync_plan,
    evaluate_public_feed_dialect_gate,
    public_feed_dialect_connector_ready,
    public_feed_dialect_gate_decision_to_dict,
    public_feed_dialect_rejection_reasons,
    public_feed_dialect_spec_from_dict,
    public_feed_dialect_spec_to_dict,
    public_feed_resync_plan_from_dict,
    public_feed_resync_plan_to_dict,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, VenueId


def test_unverified_dialect_not_connector_ready():
    spec = _spec(verification_status=FeedDialectVerificationStatus.UNVERIFIED, enabled_for_connector=False)

    decision = evaluate_public_feed_dialect_gate(spec)

    assert public_feed_dialect_connector_ready(spec) is False
    assert decision.accepted is False
    assert "public_feed_dialect:unverified" in decision.rejection_reasons


def test_verified_dialect_with_official_docs_can_be_connector_ready():
    spec = _spec()

    decision = evaluate_public_feed_dialect_gate(spec)

    assert public_feed_dialect_connector_ready(spec) is True
    assert decision.accepted is True
    assert decision.rejection_reasons == ()


def test_verified_status_without_doc_refs_rejected():
    spec = _spec(official_doc_refs=())

    reasons = public_feed_dialect_rejection_reasons(spec)

    assert "public_feed_dialect:official_docs_missing" in reasons


def test_enabled_connector_while_unverified_rejected():
    spec = _spec(verification_status=FeedDialectVerificationStatus.UNVERIFIED, enabled_for_connector=True)

    reasons = public_feed_dialect_rejection_reasons(spec)

    assert "public_feed_dialect:connector_unverified" in reasons


def test_unknown_sequence_model_rejected_for_delta_stream():
    spec = _spec(sequence_model=FeedSequenceModel.UNKNOWN)

    reasons = public_feed_dialect_rejection_reasons(spec)

    assert "public_feed_dialect:sequence_model_unknown" in reasons


def test_invalid_stale_or_lag_rejected():
    spec = replace(_spec(), max_staleness_ns=0, max_receive_lag_ns=0)

    reasons = public_feed_dialect_rejection_reasons(spec)

    assert "public_feed_dialect:invalid_staleness" in reasons
    assert "public_feed_dialect:invalid_receive_lag" in reasons


def test_gap_builds_resync_plan():
    plan = build_public_feed_resync_plan(_spec(), symbol="BTCUSDT", gap_detected=True)

    assert plan.accepted is True
    assert plan.resync_required is True
    assert plan.reason == "public_feed_dialect:gap_detected"
    assert plan.discard_buffer is True
    assert plan.reset_sequence is True


def test_stale_builds_resync_plan():
    plan = build_public_feed_resync_plan(_spec(), symbol="BTCUSDT", stale_detected=True)

    assert plan.accepted is True
    assert plan.resync_required is True
    assert plan.reason == "public_feed_dialect:stale_detected"


def test_checksum_failure_builds_resync_plan_when_supported():
    plan = build_public_feed_resync_plan(_spec(supports_checksum=True), symbol="BTCUSDT", checksum_failed=True)

    assert plan.accepted is True
    assert plan.resync_required is True
    assert plan.reason == "public_feed_dialect:checksum_failed"


def test_no_resync_support_rejects_plan():
    plan = build_public_feed_resync_plan(_spec(supports_resync=False), symbol="BTCUSDT", gap_detected=True)

    assert plan.accepted is False
    assert "public_feed_dialect:resync_unsupported" in plan.rejection_reasons


def test_public_feed_dialect_spec_roundtrip_json_safe():
    payload = public_feed_dialect_spec_to_dict(_spec())

    restored = public_feed_dialect_spec_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_dialect_spec_to_dict(restored) == payload


def test_public_feed_resync_plan_roundtrip_json_safe():
    payload = public_feed_resync_plan_to_dict(
        build_public_feed_resync_plan(_spec(), symbol="BTCUSDT", gap_detected=True)
    )

    restored = public_feed_resync_plan_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_resync_plan_to_dict(restored) == payload


def test_public_feed_dialect_gate_is_deterministic():
    first = public_feed_dialect_gate_decision_to_dict(evaluate_public_feed_dialect_gate(_spec()))
    second = public_feed_dialect_gate_decision_to_dict(evaluate_public_feed_dialect_gate(_spec()))

    assert first == second


def test_new_public_feed_dialect_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_dialect.py")
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


def _spec(**overrides: object):
    from crypto_core.data.public_feed_dialect import PublicFeedDialectSpec

    values = {
        "dialect_id": "unit-binance-l2",
        "venue_id": VenueId.BINANCE_USDM,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "instrument_type": InstrumentType.USDT_PERP,
        "verification_status": FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS,
        "official_doc_refs": ("doc:unit-public-feed",),
        "requires_rest_snapshot": True,
        "supports_delta_stream": True,
        "supports_checksum": True,
        "sequence_model": FeedSequenceModel.PREV_FINAL_RANGE,
        "checksum_model": FeedChecksumModel.VENUE_SPECIFIC,
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
