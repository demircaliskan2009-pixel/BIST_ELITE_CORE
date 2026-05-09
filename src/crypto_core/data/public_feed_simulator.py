from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.public_data_readiness import (
    PublicDataReadinessSnapshot,
    public_data_readiness_snapshot_from_dict,
    public_data_readiness_snapshot_to_dict,
    public_data_ready_for_paper,
)
from crypto_core.data.public_feed_connector import (
    PublicFeedConnectorGateDecision,
    PublicFeedConnectorPlan,
    evaluate_public_feed_connector_gate,
    public_feed_connector_gate_decision_from_dict,
    public_feed_connector_gate_decision_to_dict,
    public_feed_connector_plan_from_dict,
    public_feed_connector_plan_to_dict,
    public_feed_connector_ready,
)
from crypto_core.data.public_feed_ingest import (
    PublicFeedIngestPlan,
    PublicFeedIngestResult,
    ingest_public_feed_events,
    public_feed_ingest_result_from_dict,
    public_feed_ingest_result_ready,
    public_feed_ingest_result_to_dict,
)
from crypto_core.data.public_feed_source import (
    PublicFeedBatch,
    public_feed_batch_from_dict,
    public_feed_batch_to_dict,
)
from crypto_core.venue.contracts import (
    PublicMarketDataEvent,
    public_market_data_event_from_dict,
    public_market_data_event_to_dict,
)


class PublicFeedSimulatorError(ValueError):
    """Raised when offline public-feed simulation payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedSimulationInput:
    simulation_id: str
    connector_plan: PublicFeedConnectorPlan
    batch: PublicFeedBatch
    events: tuple[PublicMarketDataEvent, ...]
    now_ns: int


@dataclass(frozen=True)
class PublicFeedSimulationResult:
    accepted: bool
    simulation_id: str | None
    connector_gate: PublicFeedConnectorGateDecision
    ingest_result: PublicFeedIngestResult | None
    readiness_snapshot: PublicDataReadinessSnapshot | None
    rejection_reasons: tuple[str, ...]


def run_offline_public_feed_simulation(
    simulation_input: object,
) -> PublicFeedSimulationResult:
    if not isinstance(simulation_input, PublicFeedSimulationInput):
        gate = evaluate_public_feed_connector_gate(None)
        return PublicFeedSimulationResult(
            accepted=False,
            simulation_id=None,
            connector_gate=gate,
            ingest_result=None,
            readiness_snapshot=None,
            rejection_reasons=(
                "public_feed_simulator:input_malformed",
                *gate.rejection_reasons,
            ),
        )

    input_reasons = list(_input_rejection_reasons(simulation_input))
    gate = evaluate_public_feed_connector_gate(simulation_input.connector_plan)
    if not public_feed_connector_ready(gate):
        input_reasons.append("public_feed_simulator:connector_not_ready")
        input_reasons.extend(gate.rejection_reasons)
        return _result(
            simulation_id=simulation_input.simulation_id,
            gate=gate,
            ingest_result=None,
            readiness_snapshot=None,
            reasons=input_reasons,
        )
    if input_reasons:
        return _result(
            simulation_id=simulation_input.simulation_id,
            gate=gate,
            ingest_result=None,
            readiness_snapshot=None,
            reasons=input_reasons,
        )

    ingest_plan = PublicFeedIngestPlan(
        plan_id=f"{simulation_input.simulation_id}:ingest",
        policy=simulation_input.connector_plan.policy,
        subscription=simulation_input.connector_plan.subscription,
        max_receive_lag_ns=simulation_input.connector_plan.policy.max_receive_lag_ns,
        require_batch_ready=True,
        require_replay_ready=True,
        require_public_data_ready=True,
    )
    ingest_result = ingest_public_feed_events(
        ingest_plan,
        simulation_input.batch,
        simulation_input.events,
        now_ns=simulation_input.now_ns,
    )
    readiness_snapshot = ingest_result.readiness_snapshot
    reasons: list[str] = []
    if not public_feed_ingest_result_ready(ingest_result):
        reasons.append("public_feed_simulator:ingest_not_ready")
        reasons.extend(ingest_result.rejection_reasons)
    if not public_data_ready_for_paper(readiness_snapshot):
        reasons.append("public_feed_simulator:readiness_not_ready")
        reasons.extend(readiness_snapshot.rejection_reasons)

    return _result(
        simulation_id=simulation_input.simulation_id,
        gate=gate,
        ingest_result=ingest_result,
        readiness_snapshot=readiness_snapshot,
        reasons=reasons,
    )


def public_feed_simulation_ready(result: PublicFeedSimulationResult | None) -> bool:
    return (
        isinstance(result, PublicFeedSimulationResult)
        and result.accepted is True
        and result.rejection_reasons == ()
        and public_feed_connector_ready(result.connector_gate)
        and public_feed_ingest_result_ready(result.ingest_result)
        and public_data_ready_for_paper(result.readiness_snapshot)
    )


def public_feed_simulation_input_to_dict(
    simulation_input: PublicFeedSimulationInput,
) -> dict[str, object]:
    return {
        "simulation_id": simulation_input.simulation_id,
        "connector_plan": public_feed_connector_plan_to_dict(simulation_input.connector_plan),
        "batch": public_feed_batch_to_dict(simulation_input.batch),
        "events": [public_market_data_event_to_dict(event) for event in simulation_input.events],
        "now_ns": simulation_input.now_ns,
    }


def public_feed_simulation_input_from_dict(data: object) -> PublicFeedSimulationInput:
    payload = _mapping(data, "public feed simulation input payload")
    return PublicFeedSimulationInput(
        simulation_id=_non_empty_string(payload.get("simulation_id"), "simulation_id"),
        connector_plan=public_feed_connector_plan_from_dict(payload.get("connector_plan")),
        batch=public_feed_batch_from_dict(payload.get("batch")),
        events=tuple(public_market_data_event_from_dict(item) for item in _sequence(payload.get("events"))),
        now_ns=_positive_int_field(payload.get("now_ns"), "now_ns"),
    )


def public_feed_simulation_result_to_dict(result: PublicFeedSimulationResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "simulation_id": result.simulation_id,
        "connector_gate": public_feed_connector_gate_decision_to_dict(result.connector_gate),
        "ingest_result": None
        if result.ingest_result is None
        else public_feed_ingest_result_to_dict(result.ingest_result),
        "readiness_snapshot": None
        if result.readiness_snapshot is None
        else public_data_readiness_snapshot_to_dict(result.readiness_snapshot),
        "rejection_reasons": list(result.rejection_reasons),
    }


def public_feed_simulation_result_from_dict(data: object) -> PublicFeedSimulationResult:
    payload = _mapping(data, "public feed simulation result payload")
    ingest_payload = payload.get("ingest_result")
    readiness_payload = payload.get("readiness_snapshot")
    return PublicFeedSimulationResult(
        accepted=_bool(payload.get("accepted"), "accepted"),
        simulation_id=_optional_non_empty_string(payload.get("simulation_id"), "simulation_id"),
        connector_gate=public_feed_connector_gate_decision_from_dict(payload.get("connector_gate")),
        ingest_result=None if ingest_payload is None else public_feed_ingest_result_from_dict(ingest_payload),
        readiness_snapshot=None
        if readiness_payload is None
        else public_data_readiness_snapshot_from_dict(readiness_payload),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _input_rejection_reasons(simulation_input: PublicFeedSimulationInput) -> tuple[str, ...]:
    reasons: list[str] = []
    if not _non_empty(simulation_input.simulation_id):
        reasons.append("public_feed_simulator:input_malformed")
    if not isinstance(simulation_input.connector_plan, PublicFeedConnectorPlan):
        reasons.append("public_feed_simulator:input_malformed")
    if not isinstance(simulation_input.batch, PublicFeedBatch):
        reasons.append("public_feed_simulator:input_malformed")
    if not isinstance(simulation_input.events, tuple):
        reasons.append("public_feed_simulator:input_malformed")
    if not _positive_int(simulation_input.now_ns):
        reasons.append("public_feed_simulator:input_malformed")
    return tuple(dict.fromkeys(reasons))


def _result(
    *,
    simulation_id: str | None,
    gate: PublicFeedConnectorGateDecision,
    ingest_result: PublicFeedIngestResult | None,
    readiness_snapshot: PublicDataReadinessSnapshot | None,
    reasons: tuple[str, ...] | list[str],
) -> PublicFeedSimulationResult:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return PublicFeedSimulationResult(
        accepted=normalized_reasons == ()
        and public_feed_connector_ready(gate)
        and public_feed_ingest_result_ready(ingest_result)
        and public_data_ready_for_paper(readiness_snapshot),
        simulation_id=simulation_id,
        connector_gate=gate,
        ingest_result=ingest_result,
        readiness_snapshot=readiness_snapshot,
        rejection_reasons=normalized_reasons,
    )


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedSimulatorError(f"{name} must be a mapping")
    return data


def _sequence(data: object) -> tuple[object, ...]:
    if not isinstance(data, tuple | list):
        raise PublicFeedSimulatorError("payload field must be a sequence")
    return tuple(data)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedSimulatorError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedSimulatorError(f"{field_name} must be a positive integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedSimulatorError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedSimulatorError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedSimulatorError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "PublicFeedSimulationInput",
    "PublicFeedSimulationResult",
    "PublicFeedSimulatorError",
    "public_feed_simulation_input_from_dict",
    "public_feed_simulation_input_to_dict",
    "public_feed_simulation_ready",
    "public_feed_simulation_result_from_dict",
    "public_feed_simulation_result_to_dict",
    "run_offline_public_feed_simulation",
]
