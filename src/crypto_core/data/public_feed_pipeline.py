from __future__ import annotations

from dataclasses import dataclass, replace

from crypto_core.data.public_data_readiness import (
    PublicDataReadinessSnapshot,
    public_data_readiness_snapshot_from_dict,
    public_data_readiness_snapshot_to_dict,
    public_data_ready_for_paper,
)
from crypto_core.data.public_feed_ingest import (
    PublicFeedIngestPlan,
    PublicFeedIngestResult,
    ingest_public_feed_events,
    public_feed_ingest_result_from_dict,
    public_feed_ingest_result_ready,
    public_feed_ingest_result_to_dict,
)
from crypto_core.data.public_feed_ingress import (
    PublicFeedIngressDecision,
    PublicFeedIngressPacket,
    evaluate_public_feed_ingress_packet,
    public_feed_ingress_decision_from_dict,
    public_feed_ingress_decision_ready,
    public_feed_ingress_decision_to_dict,
    public_feed_ingress_packet_from_dict,
    public_feed_ingress_packet_to_dict,
)
from crypto_core.data.public_feed_run_plan import (
    PublicFeedConnectorRunDecision,
    PublicFeedConnectorRunPlan,
    evaluate_public_feed_run_plan,
    public_feed_run_decision_from_dict,
    public_feed_run_decision_ready,
    public_feed_run_decision_to_dict,
    public_feed_run_plan_from_dict,
    public_feed_run_plan_to_dict,
)
from crypto_core.data.public_feed_source import (
    PublicFeedBatch,
    RawPublicFeedEnvelope,
    public_feed_batch_from_dict,
    public_feed_batch_to_dict,
)
from crypto_core.venue.contracts import (
    PublicMarketDataEvent,
    public_market_data_event_from_dict,
    public_market_data_event_to_dict,
)


class PublicFeedPipelineError(ValueError):
    """Raised when offline public-feed pipeline payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedPipelineInput:
    pipeline_id: str
    run_plan: PublicFeedConnectorRunPlan
    ingress_packets: tuple[PublicFeedIngressPacket, ...]
    batch: PublicFeedBatch
    events: tuple[PublicMarketDataEvent, ...]
    now_ns: int
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedPipelineResult:
    accepted: bool
    pipeline_id: str | None
    run_decision: PublicFeedConnectorRunDecision
    ingress_decisions: tuple[PublicFeedIngressDecision, ...]
    ingest_result: PublicFeedIngestResult | None
    readiness_snapshot: PublicDataReadinessSnapshot | None
    accepted_for_paper: bool
    rejection_reasons: tuple[str, ...]


def run_offline_public_feed_pipeline(pipeline_input: object) -> PublicFeedPipelineResult:
    if pipeline_input is None:
        run_decision = evaluate_public_feed_run_plan(None)
        return _result(
            pipeline_id=None,
            run_decision=run_decision,
            ingress_decisions=(),
            ingest_result=None,
            readiness_snapshot=None,
            reasons=("public_pipeline:input_missing", *run_decision.rejection_reasons),
        )
    if not isinstance(pipeline_input, PublicFeedPipelineInput):
        run_decision = evaluate_public_feed_run_plan(None)
        return _result(
            pipeline_id=None,
            run_decision=run_decision,
            ingress_decisions=(),
            ingest_result=None,
            readiness_snapshot=None,
            reasons=("public_pipeline:input_malformed", *run_decision.rejection_reasons),
        )

    run_decision = evaluate_public_feed_run_plan(pipeline_input.run_plan)
    reasons: list[str] = list(_input_rejection_reasons(pipeline_input))
    if not public_feed_run_decision_ready(run_decision):
        reasons.append("public_pipeline:run_rejected")
        reasons.extend(run_decision.rejection_reasons)

    ingress_decisions = _evaluate_ingress_packets(pipeline_input, run_decision)
    if any(not public_feed_ingress_decision_ready(decision) for decision in ingress_decisions):
        reasons.append("public_pipeline:ingress_rejected")
        for decision in ingress_decisions:
            reasons.extend(decision.rejection_reasons)

    reasons.extend(_packet_batch_rejection_reasons(pipeline_input))
    if reasons:
        return _result(
            pipeline_id=pipeline_input.pipeline_id,
            run_decision=run_decision,
            ingress_decisions=ingress_decisions,
            ingest_result=None,
            readiness_snapshot=None,
            reasons=reasons,
        )

    ingest_plan = PublicFeedIngestPlan(
        plan_id=f"{pipeline_input.pipeline_id}:ingest",
        policy=pipeline_input.run_plan.policy,
        subscription=pipeline_input.run_plan.subscription,
        max_receive_lag_ns=pipeline_input.run_plan.policy.max_receive_lag_ns,
        require_batch_ready=True,
        require_replay_ready=True,
        require_public_data_ready=True,
    )
    ingest_result = ingest_public_feed_events(
        ingest_plan,
        pipeline_input.batch,
        pipeline_input.events,
        now_ns=pipeline_input.now_ns,
    )
    readiness_snapshot = ingest_result.readiness_snapshot

    if not public_feed_ingest_result_ready(ingest_result):
        reasons.append("public_pipeline:ingest_rejected")
        reasons.extend(ingest_result.rejection_reasons)
    if not public_data_ready_for_paper(readiness_snapshot):
        reasons.append("public_pipeline:readiness_rejected")
        reasons.extend(readiness_snapshot.rejection_reasons)

    return _result(
        pipeline_id=pipeline_input.pipeline_id,
        run_decision=run_decision,
        ingress_decisions=ingress_decisions,
        ingest_result=ingest_result,
        readiness_snapshot=readiness_snapshot,
        reasons=reasons,
    )


def public_feed_pipeline_ready(result: PublicFeedPipelineResult | None) -> bool:
    return (
        isinstance(result, PublicFeedPipelineResult)
        and result.accepted is True
        and result.accepted_for_paper is True
        and result.rejection_reasons == ()
        and public_feed_run_decision_ready(result.run_decision)
        and all(public_feed_ingress_decision_ready(decision) for decision in result.ingress_decisions)
        and public_feed_ingest_result_ready(result.ingest_result)
        and public_data_ready_for_paper(result.readiness_snapshot)
    )


def public_feed_pipeline_input_to_dict(pipeline_input: PublicFeedPipelineInput) -> dict[str, object]:
    return {
        "pipeline_id": pipeline_input.pipeline_id,
        "run_plan": public_feed_run_plan_to_dict(pipeline_input.run_plan),
        "ingress_packets": [public_feed_ingress_packet_to_dict(packet) for packet in pipeline_input.ingress_packets],
        "batch": public_feed_batch_to_dict(pipeline_input.batch),
        "events": [public_market_data_event_to_dict(event) for event in pipeline_input.events],
        "now_ns": pipeline_input.now_ns,
        "rejection_reasons": list(pipeline_input.rejection_reasons),
    }


def public_feed_pipeline_input_from_dict(data: object) -> PublicFeedPipelineInput:
    payload = _mapping(data, "public feed pipeline input payload")
    return PublicFeedPipelineInput(
        pipeline_id=_non_empty_string(payload.get("pipeline_id"), "pipeline_id"),
        run_plan=public_feed_run_plan_from_dict(payload.get("run_plan")),
        ingress_packets=tuple(
            public_feed_ingress_packet_from_dict(item) for item in _sequence(payload.get("ingress_packets"))
        ),
        batch=public_feed_batch_from_dict(payload.get("batch")),
        events=tuple(public_market_data_event_from_dict(item) for item in _sequence(payload.get("events"))),
        now_ns=_positive_int_field(payload.get("now_ns"), "now_ns"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_pipeline_result_to_dict(result: PublicFeedPipelineResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "pipeline_id": result.pipeline_id,
        "run_decision": public_feed_run_decision_to_dict(result.run_decision),
        "ingress_decisions": [public_feed_ingress_decision_to_dict(decision) for decision in result.ingress_decisions],
        "ingest_result": None
        if result.ingest_result is None
        else public_feed_ingest_result_to_dict(result.ingest_result),
        "readiness_snapshot": None
        if result.readiness_snapshot is None
        else public_data_readiness_snapshot_to_dict(result.readiness_snapshot),
        "accepted_for_paper": result.accepted_for_paper,
        "rejection_reasons": list(result.rejection_reasons),
    }


def public_feed_pipeline_result_from_dict(data: object) -> PublicFeedPipelineResult:
    payload = _mapping(data, "public feed pipeline result payload")
    ingest_payload = payload.get("ingest_result")
    readiness_payload = payload.get("readiness_snapshot")
    return PublicFeedPipelineResult(
        accepted=_bool(payload.get("accepted"), "accepted"),
        pipeline_id=_optional_non_empty_string(payload.get("pipeline_id"), "pipeline_id"),
        run_decision=public_feed_run_decision_from_dict(payload.get("run_decision")),
        ingress_decisions=tuple(
            public_feed_ingress_decision_from_dict(item) for item in _sequence(payload.get("ingress_decisions"))
        ),
        ingest_result=None if ingest_payload is None else public_feed_ingest_result_from_dict(ingest_payload),
        readiness_snapshot=None
        if readiness_payload is None
        else public_data_readiness_snapshot_from_dict(readiness_payload),
        accepted_for_paper=_bool(payload.get("accepted_for_paper"), "accepted_for_paper"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _input_rejection_reasons(pipeline_input: PublicFeedPipelineInput) -> tuple[str, ...]:
    reasons: list[str] = []
    if not _non_empty(pipeline_input.pipeline_id):
        reasons.append("public_pipeline:input_malformed")
    if not isinstance(pipeline_input.run_plan, PublicFeedConnectorRunPlan):
        reasons.append("public_pipeline:input_malformed")
    if not isinstance(pipeline_input.ingress_packets, tuple):
        reasons.append("public_pipeline:input_malformed")
    if not isinstance(pipeline_input.batch, PublicFeedBatch):
        reasons.append("public_pipeline:input_malformed")
    if not isinstance(pipeline_input.events, tuple):
        reasons.append("public_pipeline:input_malformed")
    if not _positive_int(pipeline_input.now_ns):
        reasons.append("public_pipeline:input_malformed")
    if pipeline_input.rejection_reasons:
        reasons.append("public_pipeline:input_rejected")
        reasons.extend(_string_reasons(pipeline_input.rejection_reasons, "public_pipeline:input_malformed"))
    return tuple(dict.fromkeys(reasons))


def _evaluate_ingress_packets(
    pipeline_input: PublicFeedPipelineInput,
    run_decision: PublicFeedConnectorRunDecision,
) -> tuple[PublicFeedIngressDecision, ...]:
    if not isinstance(pipeline_input.ingress_packets, tuple):
        return ()
    decisions: list[PublicFeedIngressDecision] = []
    for packet in pipeline_input.ingress_packets:
        packet_for_eval = (
            replace(packet, run_decision=run_decision) if isinstance(packet, PublicFeedIngressPacket) else packet
        )
        decisions.append(evaluate_public_feed_ingress_packet(packet_for_eval))
    return tuple(decisions)


def _packet_batch_rejection_reasons(pipeline_input: PublicFeedPipelineInput) -> tuple[str, ...]:
    if not isinstance(pipeline_input.ingress_packets, tuple) or not isinstance(pipeline_input.batch, PublicFeedBatch):
        return ()
    reasons: list[str] = []
    if len(pipeline_input.ingress_packets) != len(pipeline_input.batch.envelopes):
        reasons.append("public_pipeline:packet_batch_mismatch")
    for index, packet in enumerate(pipeline_input.ingress_packets):
        if not isinstance(packet, PublicFeedIngressPacket):
            reasons.append("public_pipeline:packet_batch_mismatch")
            continue
        if not isinstance(packet.envelope, RawPublicFeedEnvelope):
            reasons.append("public_pipeline:packet_batch_mismatch")
            continue
        if index >= len(pipeline_input.batch.envelopes):
            continue
        batch_envelope = pipeline_input.batch.envelopes[index]
        if packet.envelope.envelope_id != batch_envelope.envelope_id:
            reasons.append("public_pipeline:packet_batch_mismatch")
        if packet.envelope.sequence_id != batch_envelope.sequence_id:
            reasons.append("public_pipeline:packet_batch_mismatch")
        if packet.envelope.payload_hash != batch_envelope.payload_hash:
            reasons.append("public_pipeline:packet_batch_mismatch")
        if packet.envelope.raw_payload_ref != batch_envelope.raw_payload_ref:
            reasons.append("public_pipeline:packet_batch_mismatch")
    return tuple(dict.fromkeys(reasons))


def _result(
    *,
    pipeline_id: str | None,
    run_decision: PublicFeedConnectorRunDecision,
    ingress_decisions: tuple[PublicFeedIngressDecision, ...],
    ingest_result: PublicFeedIngestResult | None,
    readiness_snapshot: PublicDataReadinessSnapshot | None,
    reasons: tuple[str, ...] | list[str],
) -> PublicFeedPipelineResult:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    accepted_for_paper = public_data_ready_for_paper(readiness_snapshot)
    return PublicFeedPipelineResult(
        accepted=normalized_reasons == ()
        and public_feed_run_decision_ready(run_decision)
        and all(public_feed_ingress_decision_ready(decision) for decision in ingress_decisions)
        and public_feed_ingest_result_ready(ingest_result)
        and accepted_for_paper,
        pipeline_id=pipeline_id,
        run_decision=run_decision,
        ingress_decisions=ingress_decisions,
        ingest_result=ingest_result,
        readiness_snapshot=readiness_snapshot,
        accepted_for_paper=accepted_for_paper,
        rejection_reasons=normalized_reasons,
    )


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedPipelineError(f"{name} must be a mapping")
    return data


def _sequence(data: object) -> tuple[object, ...]:
    if not isinstance(data, tuple | list):
        raise PublicFeedPipelineError("payload field must be a sequence")
    return tuple(data)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedPipelineError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedPipelineError(f"{field_name} must be a positive integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedPipelineError(f"{field_name} must be a boolean")
    return value


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    reasons = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        return (fallback,)
    return reasons


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedPipelineError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedPipelineError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "PublicFeedPipelineError",
    "PublicFeedPipelineInput",
    "PublicFeedPipelineResult",
    "public_feed_pipeline_input_from_dict",
    "public_feed_pipeline_input_to_dict",
    "public_feed_pipeline_ready",
    "public_feed_pipeline_result_from_dict",
    "public_feed_pipeline_result_to_dict",
    "run_offline_public_feed_pipeline",
]
