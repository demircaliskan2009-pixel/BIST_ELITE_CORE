from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.deribit_public_connector_contract import (
    DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES,
    DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS,
    DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES,
    DeribitPublicConnectorDesignContract,
    deribit_public_connector_design_contract_from_dict,
    deribit_public_connector_design_contract_to_dict,
    deribit_public_connector_design_decision_from_dict,
    deribit_public_connector_design_decision_to_dict,
    deribit_public_connector_design_ready,
    evaluate_deribit_public_connector_design,
)
from crypto_core.data.public_feed_adapter import PublicFeedAdapterReadiness
from crypto_core.data.public_feed_run_plan import PublicFeedConnectorRunDecision, PublicFeedRunMode
from crypto_core.data.public_network_authorization import PublicNetworkAuthorizationDecision
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.operational_evidence_readiness import (
    OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS,
    OperationalEvidenceReadinessRequirement,
    OperationalEvidenceReadinessResult,
    OperationalEvidenceReadinessStatus,
)


def test_current_deribit_operational_evidence_blocked_rejects_design():
    decision = evaluate_deribit_public_connector_design(
        _contract(operational_evidence_result=_blocked_operational_evidence())
    )

    assert decision.accepted is False
    assert "deribit_connector_design:operational_evidence_not_ready" in decision.rejection_reasons
    assert "operational_evidence:content_hash_missing" in decision.rejection_reasons


def test_missing_contract_rejected():
    decision = evaluate_deribit_public_connector_design(None)

    assert decision.accepted is False
    assert decision.rejection_reasons == ("deribit_connector_design:contract_missing",)


def test_wrong_venue_rejected():
    decision = evaluate_deribit_public_connector_design(_contract(venue_id=VenueId.BINANCE_USDM))

    assert decision.accepted is False
    assert "deribit_connector_design:wrong_venue" in decision.rejection_reasons


def test_rejected_network_authorization_rejected():
    decision = evaluate_deribit_public_connector_design(
        _contract(network_authorization_decision=replace(_network_decision(), accepted=False))
    )

    assert decision.accepted is False
    assert "deribit_connector_design:network_not_authorized" in decision.rejection_reasons


def test_rejected_adapter_readiness_rejected():
    readiness = replace(_adapter_readiness(), accepted=False, rejection_reasons=("public_feed_adapter:disabled",))
    decision = evaluate_deribit_public_connector_design(_contract(adapter_readiness=readiness))

    assert decision.accepted is False
    assert "deribit_connector_design:adapter_not_ready" in decision.rejection_reasons
    assert "public_feed_adapter:disabled" in decision.rejection_reasons


def test_rejected_run_decision_rejected():
    run_decision = replace(_run_decision(), accepted=False, rejection_reasons=("public_run:disabled",))
    decision = evaluate_deribit_public_connector_design(_contract(run_decision=run_decision))

    assert decision.accepted is False
    assert "deribit_connector_design:run_not_ready" in decision.rejection_reasons
    assert "public_run:disabled" in decision.rejection_reasons


def test_missing_snapshot_event_rejected():
    decision = evaluate_deribit_public_connector_design(
        _contract(required_event_types=_without(DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES, "snapshot"))
    )

    assert decision.accepted is False
    assert "deribit_connector_design:required_event_missing" in decision.rejection_reasons


def test_missing_delta_event_rejected():
    decision = evaluate_deribit_public_connector_design(
        _contract(required_event_types=_without(DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES, "delta"))
    )

    assert decision.accepted is False
    assert "deribit_connector_design:required_event_missing" in decision.rejection_reasons


def test_missing_gap_or_resync_event_rejected():
    missing_gap = evaluate_deribit_public_connector_design(
        _contract(required_event_types=_without(DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES, "gap"))
    )
    missing_resync = evaluate_deribit_public_connector_design(
        _contract(required_event_types=_without(DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES, "resync_requested"))
    )

    assert missing_gap.accepted is False
    assert "deribit_connector_design:required_event_missing" in missing_gap.rejection_reasons
    assert missing_resync.accepted is False
    assert "deribit_connector_design:required_event_missing" in missing_resync.rejection_reasons


def test_missing_required_state_rejected():
    decision = evaluate_deribit_public_connector_design(
        _contract(required_state_transitions=_without(DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES, "SNAPSHOT_PENDING"))
    )

    assert decision.accepted is False
    assert "deribit_connector_design:state_transition_missing" in decision.rejection_reasons


def test_forbidden_runtime_method_rejected():
    decision = evaluate_deribit_public_connector_design(
        _contract(forbidden_methods=_without(DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS, "connect"))
    )

    assert decision.accepted is False
    assert "deribit_connector_design:forbidden_runtime_method" in decision.rejection_reasons


def test_unsafe_allowed_method_rejected():
    decision = evaluate_deribit_public_connector_design(_contract(allowed_methods=("descriptor", "connect")))

    assert decision.accepted is False
    assert "deribit_connector_design:unsafe_allowed_method" in decision.rejection_reasons


def test_all_safe_inert_conditions_accepted_with_synthetic_accepted_evidence_only():
    decision = evaluate_deribit_public_connector_design(_contract())

    assert decision.accepted is True
    assert deribit_public_connector_design_ready(decision) is True
    assert decision.rejection_reasons == ()


def test_serializer_roundtrip_json_safe():
    contract_payload = deribit_public_connector_design_contract_to_dict(_contract())
    restored_contract = deribit_public_connector_design_contract_from_dict(json.loads(json.dumps(contract_payload)))
    decision = evaluate_deribit_public_connector_design(restored_contract)
    decision_payload = deribit_public_connector_design_decision_to_dict(decision)

    restored_decision = deribit_public_connector_design_decision_from_dict(json.loads(json.dumps(decision_payload)))

    assert deribit_public_connector_design_contract_to_dict(restored_contract) == contract_payload
    assert deribit_public_connector_design_decision_to_dict(restored_decision) == decision_payload


def test_deterministic_same_contract_same_decision():
    first = deribit_public_connector_design_decision_to_dict(evaluate_deribit_public_connector_design(_contract()))
    second = deribit_public_connector_design_decision_to_dict(evaluate_deribit_public_connector_design(_contract()))

    assert first == second


def test_deribit_contract_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/data/deribit_public_connector_contract.py")
    source = module_path.read_text(encoding="utf-8").lower()
    tree = ast.parse(source)
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}
    imports: set[str] = set()
    function_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            function_names.add(node.name)

    assert forbidden_import_roots.isdisjoint(imports)
    assert {"connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)


def test_deribit_contract_source_has_no_connector_endpoint_or_secret_strings():
    source = Path("src/crypto_core/data/deribit_public_connector_contract.py").read_text(encoding="utf-8").lower()

    assert "endpoint" not in source
    assert "api_key" not in source
    assert "api_secret" not in source
    assert "private_key" not in source
    assert "websocket" not in source
    assert "requests" not in source


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


_DIALECT_ID = "deribit:l2_orderbook:placeholder"


def _contract(**overrides: object) -> DeribitPublicConnectorDesignContract:
    values = {
        "contract_id": "deribit-public-connector-design-phase22g",
        "venue_id": VenueId.DERIBIT,
        "dialect_id": _DIALECT_ID,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "instrument_name": "BTC-PERPETUAL",
        "operational_evidence_result": _accepted_operational_evidence(),
        "network_authorization_decision": _network_decision(),
        "adapter_readiness": _adapter_readiness(),
        "run_decision": _run_decision(),
        "required_event_types": DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES,
        "required_state_transitions": DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES,
        "required_fail_closed_conditions": (
            "gap_requires_resync",
            "resync_not_paper_ready",
            "halted_terminal",
        ),
        "allowed_methods": ("descriptor", "readiness", "to_dict", "from_dict"),
        "forbidden_methods": DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return DeribitPublicConnectorDesignContract(**values)  # type: ignore[arg-type]


def _accepted_operational_evidence() -> OperationalEvidenceReadinessResult:
    return OperationalEvidenceReadinessResult(
        accepted=True,
        venue_id=VenueId.DERIBIT,
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        status=OperationalEvidenceReadinessStatus.READY,
        requirements=_requirements(satisfied=True),
        rejection_reasons=(),
    )


def _blocked_operational_evidence() -> OperationalEvidenceReadinessResult:
    return OperationalEvidenceReadinessResult(
        accepted=False,
        venue_id=VenueId.DERIBIT,
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        status=OperationalEvidenceReadinessStatus.BLOCKED,
        requirements=_requirements(satisfied=False),
        rejection_reasons=(
            "operational_evidence:content_hash_missing",
            "operational_evidence:staleness_unknown",
        ),
    )


def _requirements(*, satisfied: bool) -> tuple[OperationalEvidenceReadinessRequirement, ...]:
    return tuple(
        OperationalEvidenceReadinessRequirement(
            requirement_id=f"req:{field}",
            field_name=field,
            satisfied=satisfied,
            evidence_refs=(f"evidence:{field}",) if satisfied else (),
            rejection_reasons=(),
        )
        for field in OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS
    )


def _network_decision() -> PublicNetworkAuthorizationDecision:
    return PublicNetworkAuthorizationDecision(
        accepted=True,
        authorization_id="public-network-auth-deribit-synthetic",
        venue_id=VenueId.DERIBIT,
        rejection_reasons=(),
        expires_at_ns=9_999_999,
    )


def _adapter_readiness() -> PublicFeedAdapterReadiness:
    return PublicFeedAdapterReadiness(
        accepted=True,
        adapter_id="deribit-public-adapter-synthetic",
        venue_id=VenueId.DERIBIT,
        rejection_reasons=(),
        network_authorized=True,
        connector_gate_ready=True,
        offline_only=True,
    )


def _run_decision() -> PublicFeedConnectorRunDecision:
    return PublicFeedConnectorRunDecision(
        accepted=True,
        run_id="deribit-public-run-synthetic",
        mode=PublicFeedRunMode.OFFLINE_REPLAY,
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERPETUAL",
        feed_type=PublicFeedType.L2_ORDERBOOK,
        offline_only=True,
        network_start_forbidden=True,
        rejection_reasons=(),
    )


def _without(values: tuple[str, ...], item: str) -> tuple[str, ...]:
    return tuple(value for value in values if value != item)


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
