"""Tests for Edge Factory EF-2 ``crypto_core.validation.edge_idea_intake_evidence``.

All kill-criterion thresholds below are synthetic test fixtures, never approved production thresholds.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.edge_idea_intake_evidence as intake_module
from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import (
    SourcePacket,
    SourcePacketRightsStatus,
    build_source_packet,
    source_packet_to_dict,
)
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeIdeaIntakeEvidence,
    EdgeIdeaIntakeEvidenceError,
    EdgeKillCriteriaPolicy,
    EdgeKillCriteriaPolicyStatus,
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
    edge_idea_intake_evidence_digest,
    edge_idea_intake_evidence_from_payload,
    edge_idea_intake_evidence_payload_is_well_formed,
    edge_idea_intake_evidence_to_dict,
    edge_kill_criteria_digest,
    edge_kill_criteria_policy_digest,
    edge_kill_criteria_policy_from_payload,
    edge_kill_criteria_policy_to_dict,
    verify_edge_idea_intake_evidence,
    verify_edge_kill_criteria_policy,
)

_PREFIX = "edge_idea_intake_evidence"
_POLICY_PREFIX = "edge_kill_criteria_policy"
_CONTENT_DIGEST = "c" * 64
_APPROVAL_DIGEST = "d" * 64
_UNSET = object()


def _packet(**overrides: object) -> SourcePacket:
    arguments: dict[str, object] = {
        "packet_id": "pkt-funding-carry-001",
        "source_type": "academic_paper",
        "source_reference": "doi:10.0000/funding-carry",
        "source_title": "Perpetual funding carry",
        "rights_status": "own_research",
        "edge_hypothesis": "Persistent positive funding compensates passive carry.",
        "content_digest": _CONTENT_DIGEST,
        "market_scope_tags": ("crypto_perpetuals",),
        "data_requirement_hints": ("funding_rate", "mark_price"),
    }
    arguments.update(overrides)
    return build_source_packet(**arguments)  # type: ignore[arg-type]


def _criteria(
    *, drawdown: str | None = "0.250000000000000000", funding: str | None = "12.000000000000000000"
) -> tuple[EdgeKillCriterion, ...]:
    return (
        EdgeKillCriterion(
            "max_drawdown_breach",
            "max_drawdown",
            EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
            drawdown,
            "rolling_30_utc_days",
        ),
        EdgeKillCriterion(
            "funding_flip_persistence",
            "negative_funding_hours",
            EdgeKillCriterionComparator.KILL_IF_ABOVE,
            funding,
            "rolling_7_utc_days",
        ),
    )


def _policy(criteria: tuple[EdgeKillCriterion, ...] | None = None, **overrides: object) -> EdgeKillCriteriaPolicy:
    arguments: dict[str, object] = {
        "policy_id": "policy-1",
        "correlation_id": "corr-1",
        "kill_criteria": _criteria() if criteria is None else criteria,
        "thresholds_approved": True,
        "approval_reference": "governance-review-1",
        "approval_digest": _APPROVAL_DIGEST,
    }
    arguments.update(overrides)
    return build_edge_kill_criteria_policy(**arguments)  # type: ignore[arg-type]


def _intake(
    *,
    packet: object = _UNSET,
    packet_digest: object = _UNSET,
    policy: object = _UNSET,
    policy_digest: object = _UNSET,
    **overrides: object,
) -> EdgeIdeaIntakeEvidence:
    packet = _packet() if packet is _UNSET else packet
    policy = _policy() if policy is _UNSET else policy
    if packet_digest is _UNSET:
        packet_digest = packet.packet_digest  # type: ignore[attr-defined]
    if policy_digest is _UNSET:
        policy_digest = None if policy is None else policy.policy_digest  # type: ignore[attr-defined]
    arguments: dict[str, object] = {
        "expected_source_packet_digest": packet_digest,
        "intake_id": "intake-1",
        "correlation_id": "corr-1",
        "candidate_strategy_id": "alpha-funding-carry",
        "edge_family": "funding_basis_carry",
        "economic_rationale": "Persistent positive funding pays passive carry holders.",
        "data_requirement_keys": ("funding_rate", "mark_price"),
        "declared_regime_dependence": "positive_funding_regime",
        "kill_criteria_draft": _criteria(),
        "external_fact_needs": (),
        "kill_criteria_policy": policy,
        "expected_kill_criteria_policy_digest": policy_digest,
    }
    arguments.update(overrides)
    return build_edge_idea_intake_evidence(packet, **arguments)  # type: ignore[arg-type]


def _redigest(evidence: EdgeIdeaIntakeEvidence) -> EdgeIdeaIntakeEvidence:
    return replace(evidence, intake_digest=edge_idea_intake_evidence_digest(evidence))


def _packet_redigested(packet: SourcePacket) -> SourcePacket:
    body = source_packet_to_dict(packet)
    del body["packet_digest"]
    return replace(packet, packet_digest=edge_sha256_text(edge_canonical_json(body)))


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _assert_receipt_invariants(evidence: EdgeIdeaIntakeEvidence) -> None:
    verification = verify_edge_idea_intake_evidence(evidence)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.intake_digest == edge_idea_intake_evidence_digest(evidence)
    assert edge_idea_intake_evidence_from_payload(json.loads(verification.canonical_json)) == evidence
    assert evidence.advances is (
        evidence.status is EdgeEvidenceStatus.READY and evidence.gate_verdict is EdgeGateVerdict.PASS
    )
    if evidence.status is EdgeEvidenceStatus.REJECTED:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes
        assert evidence.verdict_reason_codes == ()
    else:
        assert evidence.integrity_reason_codes == ()
        assert evidence.gate_verdict is not EdgeGateVerdict.NOT_EVALUATED


# --- happy path -----------------------------------------------------------------------------------------------------


def test_pass_intake_is_ready_advances_and_re_proves() -> None:
    packet = _packet()
    evidence = _intake(packet=packet)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.advances is True
    assert evidence.gate_id == "EF-2"
    assert evidence.source_packet_binding.expected_digest == packet.packet_digest
    assert json.loads(evidence.source_packet_binding.snapshot_json) == source_packet_to_dict(packet)
    assert evidence.source_packet_id == packet.packet_id
    assert evidence.source_packet_rights_status == "own_research"
    assert evidence.source_packet_usable_for_compilation is True
    assert evidence.data_requirement_keys == ("funding_rate", "mark_price")
    assert evidence.kill_criteria_digest == edge_kill_criteria_digest(_criteria())
    assert evidence.kill_criteria_lifecycle_stage == "DRAFT"
    assert evidence.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert evidence.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert evidence.verdict_reason_codes == ()
    _assert_receipt_invariants(evidence)
    assert edge_idea_intake_evidence_payload_is_well_formed(edge_idea_intake_evidence_to_dict(evidence)) is True


def test_intake_is_deterministic_and_order_insensitive() -> None:
    baseline = _intake()
    reordered = _intake(
        kill_criteria_draft=tuple(reversed(_criteria())),
        data_requirement_keys=[DataRequirementKey.MARK_PRICE, "funding_rate"],
    )
    assert reordered == baseline
    assert _intake() == baseline


@pytest.mark.parametrize(
    "field_name",
    ["regime_label_binding_status", "regime_evidence_status", "kill_criteria_lifecycle_stage", "source_packet_id"],
)
def test_derived_and_pending_fields_are_digest_bound(field_name: str) -> None:
    tampered = _redigest(replace(_intake(), **{field_name: "tampered"}))
    verification = verify_edge_idea_intake_evidence(tampered)
    assert verification.intact is False
    assert _code(f"field_mismatch:{field_name}") in verification.reason_codes


# --- verdict states -------------------------------------------------------------------------------------------------


def test_restricted_source_packet_is_valid_negative_evidence() -> None:
    evidence = _intake(packet=_packet(rights_status="restricted"))
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert evidence.source_packet_usable_for_compilation is False
    assert evidence.verdict_reason_codes == (_code("source_packet_not_usable_for_compilation"),)
    _assert_receipt_invariants(evidence)


def test_declared_external_fact_needs_always_stay_pending() -> None:
    evidence = _intake(external_fact_needs=("venue_funding_interval_confirmation",))
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert evidence.verdict_reason_codes == (
        _code("external_fact_need_unresolved:venue_funding_interval_confirmation"),
    )
    assert evidence.advances is False
    parameters = set(inspect.signature(build_edge_idea_intake_evidence).parameters)
    assert not {name for name in parameters if "resol" in name}
    _assert_receipt_invariants(evidence)


def test_fail_dominates_pending_external_facts_and_governance() -> None:
    evidence = _intake(packet=_packet(rights_status="restricted"), external_fact_needs=("venue_fact",), policy=None)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert set(evidence.verdict_reason_codes) == {
        _code("source_packet_not_usable_for_compilation"),
        _code("external_fact_need_unresolved:venue_fact"),
        _code("kill_criteria_policy_missing"),
    }


@pytest.mark.parametrize(
    ("overrides", "expected_codes"),
    [
        ({"policy": None}, {"kill_criteria_policy_missing"}),
        ({"policy": _policy(thresholds_approved=False)}, {"kill_criteria_policy_not_ready"}),
        ({"policy": _policy(approval_reference=None)}, {"kill_criteria_policy_not_ready"}),
        ({"policy": _policy(correlation_id="corr-other")}, {"kill_criteria_policy_correlation_mismatch"}),
        (
            {"policy": _policy(criteria=_criteria(drawdown="0.200000000000000000"))},
            {"kill_criteria_policy_kill_criteria_mismatch"},
        ),
        (
            {"kill_criteria_draft": _criteria(funding=None), "policy": _policy(criteria=_criteria(funding=None))},
            {"kill_criterion_threshold_pending_governance:funding_flip_persistence", "kill_criteria_policy_not_ready"},
        ),
    ],
)
def test_governance_needs_never_advance(overrides: dict[str, object], expected_codes: set[str]) -> None:
    evidence = _intake(**overrides)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert set(evidence.verdict_reason_codes) == {_code(code) for code in expected_codes}
    _assert_receipt_invariants(evidence)


# --- truthful REJECTED receipts -------------------------------------------------------------------------------------


def test_stale_source_packet_anchor_is_a_truthful_rejected_receipt() -> None:
    evidence = _intake(packet_digest=_packet(packet_id="pkt-other").packet_digest)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes == (_code("source_packet_digest_mismatch"),)
    _assert_receipt_invariants(evidence)


def test_policy_anchor_mismatch_is_a_truthful_rejected_receipt() -> None:
    evidence = _intake(policy_digest=_policy(policy_id="policy-other").policy_digest)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes == (_code("kill_criteria_policy_digest_mismatch"),)
    _assert_receipt_invariants(evidence)


def test_tampered_policy_is_an_integrity_rejection() -> None:
    policy = _policy(thresholds_approved=False)
    forged = replace(policy, status=EdgeKillCriteriaPolicyStatus.POLICY_READY, ready=True, reason_codes=())
    forged = replace(forged, policy_digest=edge_kill_criteria_policy_digest(forged))
    evidence = _intake(policy=forged)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert _code(f"kill_criteria_policy_integrity_failure:{_POLICY_PREFIX}:field_mismatch:status") in (
        evidence.integrity_reason_codes
    )
    _assert_receipt_invariants(evidence)


def test_scope_policy_applies_to_authenticated_source_packet_text() -> None:
    packet = _packet(source_title="order_id reconciliation study")
    evidence = _intake(packet=packet)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes == (_code("source_packet_scope_violation"),)
    _assert_receipt_invariants(evidence)


# --- negative-evidence regression: SourcePacket rights spoof -------------------------------------------------------


def test_restricted_packet_claiming_usable_with_recomputed_digest_is_rejected() -> None:
    spoof = _packet_redigested(replace(_packet(rights_status="restricted"), usable_for_compilation=True))
    evidence = _intake(packet=spoof)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert _code("source_packet_noncanonical") in evidence.integrity_reason_codes
    assert evidence.advances is False
    _assert_receipt_invariants(evidence)


def test_restricted_packet_flipped_to_own_research_with_stale_digest_is_rejected() -> None:
    restricted = _packet(rights_status="restricted")
    spoof = replace(restricted, rights_status=SourcePacketRightsStatus.OWN_RESEARCH, usable_for_compilation=True)
    evidence = _intake(packet=spoof)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert _code("source_packet_digest_mismatch") in evidence.integrity_reason_codes
    _assert_receipt_invariants(evidence)


def test_intake_level_rights_copy_spoof_fails_verification() -> None:
    restricted = _intake(packet=_packet(rights_status="restricted"))
    forged = _redigest(
        replace(
            restricted,
            source_packet_rights_status="own_research",
            source_packet_usable_for_compilation=True,
            gate_verdict=EdgeGateVerdict.PASS,
            advances=True,
            verdict_reason_codes=(),
        )
    )
    verification = verify_edge_idea_intake_evidence(forged)
    assert verification.intact is False
    assert _code("field_mismatch:source_packet_usable_for_compilation") in verification.reason_codes
    assert _code("field_mismatch:source_packet_rights_status") in verification.reason_codes
    assert _code("field_mismatch:advances") in verification.reason_codes


# --- construction errors --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("packet", "code"),
    [
        (None, "source_packet_malformed"),
        ({"packet_id": "pkt"}, "source_packet_malformed"),
        (object.__new__(SourcePacket), "source_packet_not_serializable"),
        (replace(_packet(), market_scope_tags=None), "source_packet_not_serializable"),
        (replace(_packet(), rights_status="own_research"), "source_packet_not_serializable"),
        (replace(_packet(), usable_for_compilation="yes"), "source_packet_not_serializable"),
    ],
)
def test_malformed_or_non_serializable_packets_are_construction_errors(packet: object, code: str) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=f"^{_code(code)}$"):
        _intake(packet=packet, packet_digest=_CONTENT_DIGEST)


@pytest.mark.parametrize("digest", [None, "", "A" * 64, "a" * 63])
def test_invalid_source_packet_anchor_is_a_construction_error(digest: object) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=f"^{_code('source_packet_expected_digest_invalid')}$"):
        _intake(packet_digest=digest)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"intake_id": " intake-1"}, "intake_id_invalid"),
        ({"intake_id": "intake\n1"}, "intake_id_invalid"),
        ({"correlation_id": ""}, "correlation_id_invalid"),
        ({"edge_family": "carry_scheduler_loop"}, "forbidden_scope_token:edge_family"),
        ({"economic_rationale": "BIST30 funding carry"}, "bist_scope_leakage:economic_rationale"),
        ({"candidate_strategy_id": 7}, "candidate_strategy_id_invalid"),
        ({"declared_regime_dependence": "live regime"}, "forbidden_scope_token:declared_regime_dependence"),
        ({"data_requirement_keys": ("open_interest",)}, "data_requirement_key_unknown"),
        ({"data_requirement_keys": ("funding_rate", "funding_rate")}, "data_requirement_key_duplicate"),
        ({"data_requirement_keys": ()}, "data_requirement_keys_empty"),
        ({"data_requirement_keys": "funding_rate"}, "data_requirement_keys_malformed"),
        ({"kill_criteria_draft": ()}, "kill_criteria_empty"),
        ({"kill_criteria_draft": "max_drawdown_breach"}, "kill_criteria_malformed"),
        ({"kill_criteria_draft": ({"criterion_id": "x"},)}, "kill_criterion_malformed"),
        ({"kill_criteria_draft": _criteria() + _criteria()[:1]}, "kill_criterion_duplicate"),
        ({"external_fact_needs": ("Venue_Fact",)}, "external_fact_need_invalid"),
        ({"external_fact_needs": ("venue_fact", "venue_fact")}, "external_fact_need_duplicate"),
        ({"external_fact_needs": ("live_venue_check",)}, "forbidden_scope_token:external_fact_need"),
        ({"external_fact_needs": None}, "external_fact_needs_malformed"),
    ],
)
def test_malformed_caller_fields_are_construction_errors(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=f"^{_code(code)}$"):
        _intake(**overrides)


@pytest.mark.parametrize(
    ("replacement", "code"),
    [
        ({"threshold": "0.25"}, "kill_criterion_threshold_invalid"),
        ({"threshold": "-0.000000000000000000"}, "kill_criterion_threshold_invalid"),
        ({"threshold": "01.000000000000000000"}, "kill_criterion_threshold_invalid"),
        ({"threshold": "1e-18"}, "kill_criterion_threshold_invalid"),
        ({"comparator": "kill_if_above"}, "kill_criterion_comparator_invalid"),
        ({"criterion_id": "Max_Drawdown"}, "kill_criterion_id_invalid"),
        ({"metric_id": ""}, "kill_criterion_metric_id_invalid"),
        ({"evaluation_basis": "rolling live window"}, "kill_criterion_evaluation_basis_invalid"),
    ],
)
def test_malformed_kill_criteria_are_construction_errors(replacement: dict[str, object], code: str) -> None:
    criteria = (replace(_criteria()[0], **replacement), _criteria()[1])
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=f"^{_code(code)}$"):
        _intake(kill_criteria_draft=criteria)


@pytest.mark.parametrize(
    ("policy", "policy_digest", "code"),
    [
        (None, _APPROVAL_DIGEST, "kill_criteria_policy_expected_digest_unexpected"),
        (_policy(), None, "kill_criteria_policy_expected_digest_invalid"),
        ({"policy_id": "policy-1"}, _APPROVAL_DIGEST, "kill_criteria_policy_malformed"),
        (object.__new__(EdgeKillCriteriaPolicy), _APPROVAL_DIGEST, "kill_criteria_policy_not_serializable"),
        (replace(_policy(), kill_criteria=None), _APPROVAL_DIGEST, "kill_criteria_policy_not_serializable"),
    ],
)
def test_malformed_policy_arguments_are_construction_errors(policy: object, policy_digest: object, code: str) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=f"^{_code(code)}$"):
        _intake(policy=policy, policy_digest=policy_digest)


# --- kill-criteria policy -------------------------------------------------------------------------------------------


def test_ready_policy_records_approval_only_and_re_proves() -> None:
    policy = _policy()
    assert policy.status is EdgeKillCriteriaPolicyStatus.POLICY_READY
    assert policy.ready is True
    assert policy.policy_only is True
    assert policy.reason_codes == ()
    assert policy.kill_criteria_digest == edge_kill_criteria_digest(_criteria())
    verification = verify_edge_kill_criteria_policy(policy)
    assert verification.intact is True
    assert verification.recomputed_digest == policy.policy_digest
    assert edge_kill_criteria_policy_from_payload(edge_kill_criteria_policy_to_dict(policy)) == policy


def test_unapproved_policy_is_rejected_with_explicit_reasons_and_nothing_is_defaulted() -> None:
    policy = build_edge_kill_criteria_policy(
        policy_id="policy-1", correlation_id="corr-1", kill_criteria=_criteria(funding=None)
    )
    assert policy.status is EdgeKillCriteriaPolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert policy.reason_codes == tuple(
        sorted(
            f"{_POLICY_PREFIX}:{code}"
            for code in (
                "approval_digest_missing",
                "approval_reference_missing",
                "kill_criterion_threshold_missing:funding_flip_persistence",
                "thresholds_not_approved",
            )
        )
    )
    assert verify_edge_kill_criteria_policy(policy).intact is True


def test_policy_scope_and_type_errors_are_construction_errors() -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="forbidden_scope_token:kill_criteria_policy_approval_ref"):
        _policy(approval_reference="api_key rotation approval")
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="kill_criteria_policy_thresholds_approved_invalid"):
        _policy(thresholds_approved="yes")
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="kill_criteria_policy_approval_digest_invalid"):
        _policy(approval_digest="D" * 64)


def test_forged_policy_fails_verification() -> None:
    policy = _policy(thresholds_approved=False)
    forged = replace(policy, ready=True, status=EdgeKillCriteriaPolicyStatus.POLICY_READY)
    forged = replace(forged, policy_digest=edge_kill_criteria_policy_digest(forged))
    verification = verify_edge_kill_criteria_policy(forged)
    assert verification.intact is False
    assert f"{_POLICY_PREFIX}:field_mismatch:ready" in verification.reason_codes


# --- RC1: builder domain equals verifier reassembly domain ----------------------------------------------------------


@pytest.mark.parametrize(
    "replacement",
    [
        {"source_packet_binding": EdgeAuthorityBinding(snapshot_json="", expected_digest="")},
        {"source_packet_binding": EdgeAuthorityBinding(snapshot_json="{}", expected_digest=_CONTENT_DIGEST)},
        {"source_packet_binding": None},
        {"kill_criteria_policy_binding": EdgeAuthorityBinding(snapshot_json="", expected_digest="")},
        {
            "kill_criteria_policy_binding": EdgeAuthorityBinding(
                snapshot_json='{"a":1}', expected_digest=_CONTENT_DIGEST
            )
        },
    ],
)
def test_partial_binding_states_never_verify(replacement: dict[str, object]) -> None:
    verification = verify_edge_idea_intake_evidence(replace(_intake(), **replacement))
    assert verification.intact is False
    assert len(verification.reason_codes) == 1


def _mutated_payload(path: tuple[str, ...], value: object) -> dict:
    payload = json.loads(edge_canonical_json(edge_idea_intake_evidence_to_dict(_intake())))
    node = payload
    for key in path[:-1]:
        node = node[key]
    if value is _UNSET:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return payload


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("source_packet_binding", "snapshot"), {}),
        (("source_packet_binding", "snapshot", "risk_flags"), _UNSET),
        (("source_packet_binding", "snapshot", "usable_for_compilation"), "true"),
        (("source_packet_binding", "expected_digest"), ""),
        (("kill_criteria_policy_binding", "snapshot"), {"policy_id": "policy-1"}),
        (("kill_criteria_policy_binding", "snapshot", "kill_criteria"), []),
        (("kill_criteria_draft",), []),
        (("status",), "ACCEPTED"),
        (("advances",), 1),
        (("intake_digest",), None),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[str, ...], value: object) -> None:
    assert edge_idea_intake_evidence_payload_is_well_formed(_mutated_payload(path, value)) is False


def test_builder_bindings_are_exactly_the_parsed_bindings() -> None:
    for evidence in (_intake(), _intake(policy=None), _intake(packet=_packet(rights_status="restricted"))):
        parsed = edge_idea_intake_evidence_from_payload(edge_idea_intake_evidence_to_dict(evidence))
        assert parsed.source_packet_binding == evidence.source_packet_binding
        assert parsed.kill_criteria_policy_binding == evidence.kill_criteria_policy_binding


# --- RC2: public verifier totality ----------------------------------------------------------------------------------


def _corrupted(**changes: object) -> EdgeIdeaIntakeEvidence:
    evidence = _intake()
    copy = replace(evidence)
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    0,
    "intake",
    b"intake",
    object(),
    {},
    [],
    edge_idea_intake_evidence_to_dict(_intake()),
    _policy(),
    object.__new__(EdgeIdeaIntakeEvidence),
    object.__new__(EdgeKillCriteriaPolicy),
    _corrupted(source_packet_binding=EdgeAuthorityBinding(snapshot_json="not json", expected_digest="a" * 64)),
    _corrupted(source_packet_binding={"snapshot_json": "{}", "expected_digest": "a" * 64}),
    _corrupted(kill_criteria_draft=None),
    _corrupted(kill_criteria_draft=({"criterion_id": "x"},)),
    _corrupted(data_requirement_keys="funding_rate"),
    _corrupted(status="BOGUS"),
    _corrupted(intake_digest=None),
    _corrupted(economic_rationale=float("nan")),
    _corrupted(edge_family="carry_scheduler_loop"),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifiers_are_total_for_any_object(artifact: object) -> None:
    for verify, cls in (
        (verify_edge_idea_intake_evidence, EdgeIdeaIntakeEvidence),
        (verify_edge_kill_criteria_policy, EdgeKillCriteriaPolicy),
    ):
        verification = verify(artifact)
        assert type(verification) is EdgeEvidenceVerification
        if type(artifact) is not cls:
            assert verification.intact is False
            assert len(verification.reason_codes) == 1
    assert verify_edge_idea_intake_evidence(artifact).intact is False


# --- RC3: builder/verifier round trips for every state --------------------------------------------------------------


_STATE_BUILDERS = {
    "pass": lambda: _intake(),
    "fail": lambda: _intake(packet=_packet(rights_status="restricted")),
    "needs_external_facts": lambda: _intake(external_fact_needs=("venue_fact",)),
    "needs_governance_approval": lambda: _intake(policy=None),
    "rejected_packet": lambda: _intake(packet_digest=_packet(packet_id="pkt-other").packet_digest),
    "rejected_policy": lambda: _intake(policy_digest=_APPROVAL_DIGEST),
    "rejected_scope": lambda: _intake(packet=_packet(source_title="credential rotation")),
}


@pytest.mark.parametrize("state", sorted(_STATE_BUILDERS))
def test_every_builder_state_round_trips_through_the_verifier(state: str) -> None:
    evidence = _STATE_BUILDERS[state]()
    _assert_receipt_invariants(evidence)
    expected_status = EdgeEvidenceStatus.REJECTED if state.startswith("rejected") else EdgeEvidenceStatus.READY
    assert evidence.status is expected_status


# --- RC4: binding canonicality --------------------------------------------------------------------------------------


def test_bindings_are_canonical_and_noncanonical_in_memory_bindings_never_verify() -> None:
    evidence = _intake()
    for binding in (evidence.source_packet_binding, evidence.kill_criteria_policy_binding):
        assert binding is not None
        assert binding.snapshot_json == edge_canonical_json(json.loads(binding.snapshot_json))
    pretty = EdgeAuthorityBinding(
        snapshot_json=json.dumps(json.loads(evidence.source_packet_binding.snapshot_json), indent=2),
        expected_digest=evidence.source_packet_binding.expected_digest,
    )
    verification = verify_edge_idea_intake_evidence(replace(evidence, source_packet_binding=pretty))
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- structural non-claims ------------------------------------------------------------------------------------------


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flag_names = {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
    for cls in (EdgeIdeaIntakeEvidence, EdgeKillCriteriaPolicy):
        defaults = {field.name: field.default for field in fields(cls) if field.name in flag_names}
        assert defaults == dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
    for builder in (build_edge_idea_intake_evidence, build_edge_kill_criteria_policy):
        assert not flag_names & set(inspect.signature(builder).parameters)


@pytest.mark.parametrize("flag", ["edge_proven", "candidate_admitted_to_paper", "kill_criteria_sealed", "live_ready"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify_edge_idea_intake_evidence(_redigest(replace(_intake(), **{flag: True})))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


# --- structural purity ----------------------------------------------------------------------------------------------

_FORBIDDEN_MODULES = (
    "math",
    "time",
    "datetime",
    "random",
    "secrets",
    "uuid",
    "socket",
    "ssl",
    "urllib",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "threading",
    "asyncio",
    "multiprocessing",
    "subprocess",
    "os",
    "sys",
    "pathlib",
    "shutil",
    "tempfile",
    "sqlite3",
    "logging",
)
_FORBIDDEN_CALLS = frozenset(
    {"open", "Path", "float", "now", "utcnow", "time", "time_ns", "perf_counter", "monotonic", "getenv", "print"}
)


def _module_tree() -> ast.Module:
    return ast.parse(Path(intake_module.__file__).read_text(encoding="utf-8"))


def test_module_has_no_io_clock_randomness_or_float() -> None:
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in _FORBIDDEN_CALLS
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr != "environ"


def test_module_consumes_only_public_substrate_names() -> None:
    crypto_imports: dict[str, set[str]] = {}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core"):
            crypto_imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
    assert set(crypto_imports) == {
        "crypto_core.data.requirements",
        "crypto_core.strategy.source_packet",
        "crypto_core.validation.edge_artifact_core",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    tree = _module_tree()
    constructors = {"EdgeIdeaIntakeEvidence": 0, "EdgeKillCriteriaPolicy": 0}
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        names = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        calls_by_function[function.name] = names
        for name in constructors:
            constructors[name] += sum(
                1
                for node in ast.walk(function)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
            )
    assert constructors == {"EdgeIdeaIntakeEvidence": 1, "EdgeKillCriteriaPolicy": 1}
    assert "EdgeIdeaIntakeEvidence" in calls_by_function["_assemble_intake"]
    assert "_assemble_intake" in calls_by_function["build_edge_idea_intake_evidence"]
    assert "_assemble_intake" in calls_by_function["_reassemble_intake"]
    assert "EdgeKillCriteriaPolicy" in calls_by_function["build_edge_kill_criteria_policy"]
    assert "build_edge_kill_criteria_policy" in calls_by_function["_reassemble_policy"]
