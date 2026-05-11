from __future__ import annotations

import json
from dataclasses import dataclass, replace

from crypto_core.data.public_feed_adapter import (
    evaluate_public_feed_adapter_readiness,
    public_feed_adapter_ready,
)
from crypto_core.data.public_feed_connector import (
    PublicFeedConnectorPlan,
    evaluate_public_feed_connector_gate,
)
from crypto_core.data.public_feed_pipeline import (
    PublicFeedPipelineInput,
    public_feed_pipeline_ready,
    public_feed_pipeline_result_from_dict,
    public_feed_pipeline_result_to_dict,
    run_offline_public_feed_pipeline,
)
from crypto_core.data.public_feed_run_plan import PublicFeedRunMode
from crypto_core.data.public_feed_source import RawPublicFeedEnvelope
from crypto_core.data.public_network_authorization import (
    evaluate_public_network_authorization,
)
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, RejectionReason
from crypto_core.venue.contracts import PublicMarketDataEvent
from crypto_core.venue.dialect_evidence import (
    OfficialDocEvidence,
    OfficialDocEvidenceStatus,
    PublicFeedDialectEvidenceBundle,
    verify_public_feed_dialect_evidence_bundle,
)
from crypto_core.venue.dialect_verification import (
    apply_public_feed_dialect_verification,
)
from crypto_core.venue.public_feed_dialects import get_public_feed_dialect
from tests.crypto_core.data import test_phase21t_public_feed_pipeline as phase21t


@dataclass(frozen=True)
class _Stack:
    pipeline_input: PublicFeedPipelineInput
    dialect_id: str


def test_full_valid_offline_stack_reaches_accepted_pipeline_result():
    stack = _stack()
    result = run_offline_public_feed_pipeline(stack.pipeline_input)

    assert result.accepted is True
    assert result.accepted_for_paper is True
    assert public_feed_pipeline_ready(result) is True
    assert result.rejection_reasons == ()


def test_unverified_dialect_prevents_connector_ready_path():
    unverified = get_public_feed_dialect("binance_usdm:l2_orderbook:placeholder")
    stack = _stack(dialect=unverified)
    result = run_offline_public_feed_pipeline(stack.pipeline_input)

    assert result.accepted is False
    assert "public_pipeline:run_rejected" in result.rejection_reasons
    assert "public_connector:dialect_not_ready" in result.rejection_reasons
    assert "public_feed_dialect:unverified" in result.rejection_reasons


def test_rejected_official_doc_evidence_prevents_verified_dialect_overlay():
    spec = _overlay_candidate_from_registry()
    rejected_evidence = _official_doc_evidence(status=OfficialDocEvidenceStatus.REJECTED)
    verification = verify_public_feed_dialect_evidence_bundle(
        _evidence_bundle(spec.dialect_id, evidence_items=(rejected_evidence,))
    )
    overlay = apply_public_feed_dialect_verification(spec, verification)

    assert verification.accepted is False
    assert overlay.accepted is False
    assert overlay.verified_spec is None
    assert "official_doc:status_not_verified" in overlay.rejection_reasons


def test_rejected_network_authorization_prevents_adapter_readiness():
    dialect = _verified_dialect_from_evidence()
    stack = _stack(
        dialect=dialect,
        auth=phase21t._auth(
            allowed_dialect_ids=(dialect.dialect_id,),
            network_allowed=False,
        ),
    )

    assert public_feed_adapter_ready(stack.pipeline_input.run_plan.adapter_readiness) is False
    assert run_offline_public_feed_pipeline(stack.pipeline_input).accepted is False
    assert "public_network:not_allowed" in stack.pipeline_input.run_plan.adapter_readiness.rejection_reasons


def test_rejected_connector_gate_prevents_run_decision():
    dialect = _verified_dialect_from_evidence()
    connector_plan = phase21t._connector_plan(
        dialect=dialect,
        network_enabled=True,
    )
    result = run_offline_public_feed_pipeline(_stack(dialect=dialect, connector_plan=connector_plan).pipeline_input)

    assert result.accepted is False
    assert "public_run:connector_gate_not_ready" in result.rejection_reasons
    assert "public_connector:network_forbidden" in result.rejection_reasons


def test_rejected_run_decision_prevents_ingress():
    stack = _stack()
    disabled_run_plan = replace(
        stack.pipeline_input.run_plan,
        mode=PublicFeedRunMode.DISABLED,
    )
    result = run_offline_public_feed_pipeline(replace(stack.pipeline_input, run_plan=disabled_run_plan))

    assert result.accepted is False
    assert "public_pipeline:run_rejected" in result.rejection_reasons
    assert "public_pipeline:ingress_rejected" in result.rejection_reasons
    assert "public_ingress:run_not_ready" in result.rejection_reasons


def test_rejected_ingress_prevents_pipeline():
    bad_envelope = phase21t._envelope(normalized=False)
    result = run_offline_public_feed_pipeline(_stack(envelopes=(bad_envelope,)).pipeline_input)

    assert result.accepted is False
    assert result.ingest_result is None
    assert "public_pipeline:ingress_rejected" in result.rejection_reasons
    assert "public_ingress:envelope_rejected" in result.rejection_reasons


def test_event_hash_mismatch_prevents_ingest_and_pipeline():
    result = run_offline_public_feed_pipeline(
        _stack(events=(phase21t._event(payload_hash="different-hash"),)).pipeline_input
    )

    assert result.accepted is False
    assert result.ingest_result is not None
    assert "public_pipeline:ingest_rejected" in result.rejection_reasons
    assert "public_feed_ingest:event_hash_mismatch" in result.rejection_reasons


def test_duplicate_sequence_prevents_replay_and_pipeline():
    envelopes = (
        phase21t._envelope(
            envelope_id="envelope-21v-1",
            sequence_id=10,
            event_time_ns=1_000,
            receive_time_ns=1_010,
            payload_hash="hash-21v-1",
            raw_payload_ref="raw-ref-21v-1",
        ),
        phase21t._envelope(
            envelope_id="envelope-21v-2",
            sequence_id=10,
            event_time_ns=1_020,
            receive_time_ns=1_030,
            payload_hash="hash-21v-2",
            raw_payload_ref="raw-ref-21v-2",
        ),
    )
    events = _events_from_envelopes(envelopes)
    result = run_offline_public_feed_pipeline(_stack(envelopes=envelopes, events=events, now_ns=1_040).pipeline_input)

    assert result.accepted is False
    assert result.ingest_result is not None
    assert "public_pipeline:ingest_rejected" in result.rejection_reasons
    assert "public_feed_source:duplicate_sequence_id" in result.rejection_reasons


def test_stale_feed_policy_prevents_readiness_and_pipeline():
    policy = phase21t._policy(max_receive_lag_ns=1, max_staleness_ns=1)
    result = run_offline_public_feed_pipeline(_stack(policy=policy, now_ns=5_000).pipeline_input)

    assert result.accepted is False
    assert "public_pipeline:ingest_rejected" in result.rejection_reasons
    assert "public_feed_source:receive_lag_exceeded" in result.rejection_reasons


def test_order_book_not_ready_prevents_readiness_when_required():
    policy = phase21t._policy(require_order_book=True)
    result = run_offline_public_feed_pipeline(_stack(policy=policy).pipeline_input)

    assert result.accepted is False
    assert result.readiness_snapshot is not None
    assert "public_pipeline:readiness_rejected" in result.rejection_reasons
    assert "public_data:order_book_not_ready" in result.rejection_reasons


def test_same_full_stack_input_gives_identical_result():
    stack = _stack()

    first = public_feed_pipeline_result_to_dict(run_offline_public_feed_pipeline(stack.pipeline_input))
    second = public_feed_pipeline_result_to_dict(run_offline_public_feed_pipeline(stack.pipeline_input))

    assert first == second


def test_pipeline_result_json_roundtrip_preserves_blockers():
    result = run_offline_public_feed_pipeline(
        _stack(events=(phase21t._event(payload_hash="different-hash"),)).pipeline_input
    )
    payload = public_feed_pipeline_result_to_dict(result)
    restored = public_feed_pipeline_result_from_dict(json.loads(json.dumps(payload)))

    assert restored.rejection_reasons == result.rejection_reasons
    assert restored.run_decision.rejection_reasons == result.run_decision.rejection_reasons
    assert public_feed_pipeline_result_to_dict(restored) == payload


def test_live_execution_remains_disabled():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(
        phase21t._execution_request()
    )

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _stack(
    *,
    dialect: object | None = None,
    auth: object | None = None,
    connector_plan: PublicFeedConnectorPlan | None = None,
    policy: object | None = None,
    envelopes: tuple[RawPublicFeedEnvelope, ...] | None = None,
    events: tuple[PublicMarketDataEvent, ...] | None = None,
    now_ns: int = 1_020,
) -> _Stack:
    verified_dialect = dialect if dialect is not None else _verified_dialect_from_evidence()
    dialect_id = getattr(verified_dialect, "dialect_id", "unknown-dialect")
    subscription = phase21t._subscription()
    policy = policy if policy is not None else phase21t._policy()
    connector_plan = connector_plan or phase21t._connector_plan(
        dialect=verified_dialect,
        subscription=subscription,
        policy=policy,
    )
    auth = auth or phase21t._auth(
        allowed_dialect_ids=(dialect_id,),
        official_doc_bundle_id="bundle-21v",
        verification_result_ids=("verification-21v",),
    )
    descriptor = phase21t._descriptor(
        dialect_ids=(dialect_id,),
        network_authorization=auth,
        connector_plan=connector_plan,
    )
    run_plan = phase21t._run_plan(
        adapter_descriptor=descriptor,
        adapter_readiness=evaluate_public_feed_adapter_readiness(descriptor, now_ns=1_500),
        network_authorization_decision=evaluate_public_network_authorization(auth, now_ns=1_500),
        connector_gate=evaluate_public_feed_connector_gate(connector_plan),
        subscription=subscription,
        policy=policy,
    )
    run_decision = phase21t.evaluate_public_feed_run_plan(run_plan)
    envelopes = envelopes or (phase21t._envelope(),)
    events = events or _events_from_envelopes(envelopes)
    packets = tuple(
        phase21t._packet(
            packet_id=f"packet-21v-{index}",
            run_decision=run_decision,
            subscription=subscription,
            envelope=envelope,
            received_at_ns=envelope.receive_time_ns + 10,
        )
        for index, envelope in enumerate(envelopes, start=1)
    )
    batch = phase21t._batch(envelopes=envelopes, subscription=subscription)
    pipeline_input = phase21t._pipeline_input(
        run_plan=run_plan,
        ingress_packets=packets,
        batch=batch,
        events=events,
        now_ns=now_ns,
    )
    return _Stack(pipeline_input=pipeline_input, dialect_id=dialect_id)


def _verified_dialect_from_evidence():
    spec = _overlay_candidate_from_registry()
    verification = verify_public_feed_dialect_evidence_bundle(
        _evidence_bundle(
            spec.dialect_id,
            evidence_items=(_official_doc_evidence(),),
        )
    )
    overlay = apply_public_feed_dialect_verification(spec, verification)
    assert overlay.accepted is True
    assert overlay.verified_spec is not None
    return overlay.verified_spec


def _overlay_candidate_from_registry():
    base = get_public_feed_dialect("binance_usdm:l2_orderbook:placeholder")
    return replace(
        base,
        dialect_id="binance_usdm:l2_orderbook:phase21v",
        supports_delta_stream=True,
        supports_resync=True,
        sequence_model=phase21t.FeedSequenceModel.PREV_FINAL_RANGE,
        checksum_model=phase21t.FeedChecksumModel.NONE,
        max_gap_tolerance=0,
        max_staleness_ns=1_000,
        max_receive_lag_ns=1_000,
        rejection_reasons=(),
    )


def _official_doc_evidence(
    *,
    status: OfficialDocEvidenceStatus = OfficialDocEvidenceStatus.VERIFIED,
) -> OfficialDocEvidence:
    return OfficialDocEvidence(
        evidence_id="binance_usdm:l2_orderbook:phase21v::official-doc",
        venue_id=phase21t.VenueId.BINANCE_USDM,
        doc_type=phase21t.PublicFeedType.L2_ORDERBOOK.value,
        doc_url="https://docs.example.test/binance-usdm/l2",
        retrieved_at_ns=1_000,
        content_hash="doc-hash-21v",
        source_name="unit-test-official-doc-snapshot",
        status=status,
        rejection_reasons=(),
    )


def _evidence_bundle(
    dialect_id: str,
    *,
    evidence_items: tuple[OfficialDocEvidence, ...],
) -> PublicFeedDialectEvidenceBundle:
    return PublicFeedDialectEvidenceBundle(
        bundle_id="bundle-21v",
        dialect_id=dialect_id,
        venue_id=phase21t.VenueId.BINANCE_USDM,
        feed_type=phase21t.PublicFeedType.L2_ORDERBOOK,
        evidence_items=evidence_items,
        verified_at_ns=1_100,
        verifier_id="verifier-21v",
        rejection_reasons=(),
    )


def _events_from_envelopes(
    envelopes: tuple[RawPublicFeedEnvelope, ...],
) -> tuple[PublicMarketDataEvent, ...]:
    return tuple(
        phase21t._event(
            event_time_ns=envelope.event_time_ns,
            receive_time_ns=envelope.receive_time_ns,
            sequence_id=envelope.sequence_id,
            payload_hash=envelope.payload_hash,
            raw_payload_ref=envelope.raw_payload_ref,
            normalized=envelope.normalized,
        )
        for envelope in envelopes
    )
