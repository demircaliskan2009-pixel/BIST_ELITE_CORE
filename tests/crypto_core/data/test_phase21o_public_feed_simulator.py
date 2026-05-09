from __future__ import annotations

import ast
import json
from pathlib import Path

from crypto_core.data.public_feed_connector import PublicFeedConnectorMode, PublicFeedConnectorPlan
from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    PublicFeedDialectSpec,
)
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.data.public_feed_simulator import (
    PublicFeedSimulationInput,
    public_feed_simulation_input_from_dict,
    public_feed_simulation_input_to_dict,
    public_feed_simulation_ready,
    public_feed_simulation_result_from_dict,
    public_feed_simulation_result_to_dict,
    run_offline_public_feed_simulation,
)
from crypto_core.data.public_feed_source import PublicFeedBatch, PublicFeedSubscription, RawPublicFeedEnvelope
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, PublicMarketDataEvent, VenueId


def test_valid_offline_simulation_accepted():
    result = run_offline_public_feed_simulation(_simulation_input())

    assert result.accepted is True
    assert public_feed_simulation_ready(result) is True
    assert result.ingest_result is not None
    assert result.readiness_snapshot is not None
    assert result.readiness_snapshot.accepted_for_paper is True
    assert result.rejection_reasons == ()


def test_rejected_connector_blocks_before_ingest():
    result = run_offline_public_feed_simulation(_simulation_input(connector_plan=_plan(network_enabled=True)))

    assert result.accepted is False
    assert result.ingest_result is None
    assert "public_feed_simulator:connector_not_ready" in result.rejection_reasons
    assert "public_connector:network_forbidden" in result.rejection_reasons


def test_invalid_batch_rejected():
    envelopes = (_envelope(sequence_id=1), _envelope(envelope_id="env-2", sequence_id=1))
    result = run_offline_public_feed_simulation(_simulation_input(batch=_batch(envelopes=envelopes)))

    assert result.accepted is False
    assert "public_feed_ingest:batch_not_ready" in result.rejection_reasons
    assert "public_feed_source:duplicate_sequence_id" in result.rejection_reasons


def test_event_batch_mismatch_rejected():
    events = (_event(sequence_id=1, payload_hash="different-hash"), _event(sequence_id=2, payload_hash="hash-2"))

    result = run_offline_public_feed_simulation(_simulation_input(events=events))

    assert result.accepted is False
    assert "public_feed_ingest:event_hash_mismatch" in result.rejection_reasons


def test_ingest_readiness_failure_rejected():
    plan = _plan(policy=_policy(require_order_book=True))

    result = run_offline_public_feed_simulation(_simulation_input(connector_plan=plan))

    assert result.accepted is False
    assert "public_feed_simulator:ingest_not_ready" in result.rejection_reasons
    assert "public_data:order_book_not_ready" in result.rejection_reasons


def test_rejection_reasons_aggregate_deterministically():
    simulation_input = _simulation_input(connector_plan=_plan(network_enabled=True))

    first = run_offline_public_feed_simulation(simulation_input)
    second = run_offline_public_feed_simulation(simulation_input)

    assert first.rejection_reasons == second.rejection_reasons
    assert public_feed_simulation_result_to_dict(first) == public_feed_simulation_result_to_dict(second)


def test_simulation_ready_false_for_none_or_rejected():
    assert public_feed_simulation_ready(None) is False
    assert public_feed_simulation_ready(run_offline_public_feed_simulation(_simulation_input(events=()))) is False


def test_input_serializer_roundtrip_json_safe():
    payload = public_feed_simulation_input_to_dict(_simulation_input())

    restored = public_feed_simulation_input_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_simulation_input_to_dict(restored) == payload


def test_result_serializer_roundtrip_json_safe():
    payload = public_feed_simulation_result_to_dict(run_offline_public_feed_simulation(_simulation_input()))

    restored = public_feed_simulation_result_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_simulation_result_to_dict(restored) == payload


def test_simulation_is_deterministic():
    first = public_feed_simulation_result_to_dict(run_offline_public_feed_simulation(_simulation_input()))
    second = public_feed_simulation_result_to_dict(run_offline_public_feed_simulation(_simulation_input()))

    assert first == second


def test_new_public_feed_simulator_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/public_feed_simulator.py")
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


def _simulation_input(**overrides: object) -> PublicFeedSimulationInput:
    values = {
        "simulation_id": "sim-21o",
        "connector_plan": _plan(),
        "batch": _batch(),
        "events": (_event(sequence_id=1, payload_hash="hash-1"), _event(sequence_id=2, payload_hash="hash-2")),
        "now_ns": 250,
    }
    values.update(overrides)
    return PublicFeedSimulationInput(**values)  # type: ignore[arg-type]


def _plan(**overrides: object) -> PublicFeedConnectorPlan:
    values = {
        "connector_id": "connector-21o",
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
        "subscription_id": "sub-21o",
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


def _batch(**overrides: object) -> PublicFeedBatch:
    values = {
        "batch_id": "batch-21o",
        "subscription": _subscription(),
        "envelopes": (
            _envelope(envelope_id="env-1", sequence_id=1, event_time_ns=100, payload_hash="hash-1"),
            _envelope(
                envelope_id="env-2",
                sequence_id=2,
                event_time_ns=200,
                payload_hash="hash-2",
                raw_payload_ref="raw-ref-2",
            ),
        ),
        "created_at_ns": 90,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedBatch(**values)  # type: ignore[arg-type]


def _envelope(**overrides: object) -> RawPublicFeedEnvelope:
    event_time_ns = overrides.get("event_time_ns", 100)
    values = {
        "envelope_id": "env-1",
        "subscription_id": "sub-21o",
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "event_time_ns": event_time_ns,
        "receive_time_ns": int(event_time_ns) + 10,
        "sequence_id": 1,
        "payload_hash": "hash-1",
        "raw_payload_ref": "raw-ref-1",
        "normalized": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return RawPublicFeedEnvelope(**values)  # type: ignore[arg-type]


def _event(**overrides: object) -> PublicMarketDataEvent:
    sequence_id = overrides.get("sequence_id", 1)
    event_time_ns = 100 if sequence_id == 1 else 200
    values = {
        "venue_id": VenueId.BINANCE_USDM,
        "symbol": "BTCUSDT",
        "canonical_symbol": "BTC-USDT-PERP",
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "event_time_ns": event_time_ns,
        "receive_time_ns": event_time_ns + 10,
        "sequence_id": sequence_id,
        "payload_hash": "hash-1",
        "raw_payload_ref": "raw-ref-1" if sequence_id == 1 else "raw-ref-2",
        "normalized": True,
    }
    values.update(overrides)
    return PublicMarketDataEvent(**values)  # type: ignore[arg-type]


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
