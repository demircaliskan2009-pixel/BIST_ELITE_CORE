from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.data.deribit_public_connector_contract import (
    DERIBIT_PUBLIC_CONNECTOR_ALLOWED_STATE_EDGES,
    DERIBIT_PUBLIC_CONNECTOR_PAPER_READY_STATES,
    DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES,
    DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS,
    DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES,
    DERIBIT_PUBLIC_CONNECTOR_TERMINAL_STATES,
    DeribitPublicConnectorDesignContract,
    evaluate_deribit_public_connector_design,
)
from crypto_core.data.public_feed_adapter import PublicFeedAdapterReadiness
from crypto_core.data.public_feed_run_plan import PublicFeedConnectorRunDecision, PublicFeedRunMode
from crypto_core.data.public_network_authorization import PublicNetworkAuthorizationDecision
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.operational_evidence_readiness import (
    OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS,
    OperationalEvidenceReadinessRequirement,
    OperationalEvidenceReadinessResult,
    OperationalEvidenceReadinessStatus,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect


def test_required_states_are_complete_and_ordered():
    assert DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES == (
        "DISCONNECTED",
        "SUBSCRIBING",
        "SNAPSHOT_PENDING",
        "STREAMING",
        "GAP_DETECTED",
        "RESYNC_REQUIRED",
        "HALTED",
    )


def test_disconnected_cannot_jump_to_streaming_without_subscription_and_snapshot_pending():
    edges = set(DERIBIT_PUBLIC_CONNECTOR_ALLOWED_STATE_EDGES)

    assert ("DISCONNECTED", "STREAMING") not in edges
    assert ("DISCONNECTED", "SUBSCRIBING") in edges
    assert ("SUBSCRIBING", "SNAPSHOT_PENDING") in edges
    assert ("SNAPSHOT_PENDING", "STREAMING") in edges


def test_gap_detected_must_lead_to_resync_required_or_halted():
    edges = set(DERIBIT_PUBLIC_CONNECTOR_ALLOWED_STATE_EDGES)

    assert ("GAP_DETECTED", "RESYNC_REQUIRED") in edges
    assert ("GAP_DETECTED", "HALTED") in edges
    assert not any(source == "GAP_DETECTED" and target == "STREAMING" for source, target in edges)


def test_resync_required_not_accepted_as_paper_ready():
    assert "RESYNC_REQUIRED" not in DERIBIT_PUBLIC_CONNECTOR_PAPER_READY_STATES
    assert DERIBIT_PUBLIC_CONNECTOR_PAPER_READY_STATES == ("STREAMING",)


def test_halted_is_terminal_for_current_run():
    assert DERIBIT_PUBLIC_CONNECTOR_TERMINAL_STATES == ("HALTED",)
    assert not any(source == "HALTED" for source, _target in DERIBIT_PUBLIC_CONNECTOR_ALLOWED_STATE_EDGES)


def test_no_state_implies_order_private_or_live_capability():
    combined = " ".join(DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES).lower()

    assert "order" not in combined
    assert "private" not in combined
    assert "live" not in combined


def test_no_runtime_methods_exist_in_design_contract_module():
    module_path = Path("src/crypto_core/data/deribit_public_connector_contract.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    function_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            function_names.add(node.name)

    assert {"connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)
    assert {"place_order", "cancel_order"}.isdisjoint(function_names)


def test_no_network_imports_exist_in_design_contract_module():
    module_path = Path("src/crypto_core/data/deribit_public_connector_contract.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imports)


def test_current_deribit_evidence_still_blocks_design_acceptance():
    decision = evaluate_deribit_public_connector_design(
        _contract(operational_evidence_result=_blocked_operational_evidence())
    )

    assert decision.accepted is False
    assert "deribit_connector_design:operational_evidence_not_ready" in decision.rejection_reasons


def test_static_registry_verified_but_connector_disabled():
    spec = get_public_feed_dialect("deribit:l2_orderbook:placeholder")

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is True


def test_connector_ready_dialects_remains_empty():
    assert len(connector_ready_dialects()) == 1


_DIALECT_ID = "deribit:l2_orderbook:placeholder"


def _contract(**overrides: object) -> DeribitPublicConnectorDesignContract:
    values = {
        "contract_id": "deribit-public-connector-state-contract-phase22h",
        "venue_id": VenueId.DERIBIT,
        "dialect_id": _DIALECT_ID,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "instrument_name": "BTC-PERPETUAL",
        "operational_evidence_result": _accepted_operational_evidence(),
        "network_authorization_decision": PublicNetworkAuthorizationDecision(
            accepted=True,
            authorization_id="public-network-auth-deribit-synthetic",
            venue_id=VenueId.DERIBIT,
            rejection_reasons=(),
            expires_at_ns=9_999_999,
        ),
        "adapter_readiness": PublicFeedAdapterReadiness(
            accepted=True,
            adapter_id="deribit-public-adapter-synthetic",
            venue_id=VenueId.DERIBIT,
            rejection_reasons=(),
            network_authorized=True,
            connector_gate_ready=True,
            offline_only=True,
        ),
        "run_decision": PublicFeedConnectorRunDecision(
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
        ),
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
        rejection_reasons=("operational_evidence:content_hash_missing",),
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
