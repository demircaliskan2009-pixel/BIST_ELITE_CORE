"""Tests for Edge Factory EF-5 preregistration and leakage/bias firewall (EF5_EDGE_LEAKAGE_BIAS_PREREGISTRATION_V1)."""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from dataclasses import fields, replace
from functools import cache
from pathlib import Path

import pytest

import crypto_core.validation.edge_leakage_bias_evidence as ef5_module
import crypto_core.validation.strategy_executable_profiles as profiles_module
from crypto_core.data.requirements import data_requirement_registry_digest, default_perp_data_requirement_registry
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.strategy.spec import strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS,
    EdgeBiasProofKind,
    EdgeBiasProofOutcome,
    EdgeInputVariant,
    EdgeLeakageBiasEvidence,
    EdgeLeakageBiasEvidenceError,
    EdgeParameterSearchBound,
    EdgeParameterSearchTreatment,
    EdgePreregistrationApproval,
    EdgeRegisteredVariant,
    EdgeSurvivorshipClaimScope,
    build_edge_leakage_bias_evidence,
    edge_leakage_bias_evidence_digest,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_payload_is_well_formed,
    edge_leakage_bias_evidence_to_dict,
    verify_edge_leakage_bias_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import EdgeInputSeries, build_edge_source_packet_evidence
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmissionEvidence,
    build_edge_strategy_spec_admission,
    edge_strategy_spec_admission_digest,
)
from crypto_core.validation.historical_walk_forward_metrics import HistoricalWalkForwardMetricsResult
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableBinding,
    StrategyExecutableCoverageEntry,
    strategy_executable_binding_digest,
)
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    ProfileAction,
    ProfileParameterAssignment,
    canonical_profile_parameter_assignment,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
)
from tests.crypto_core.validation import test_historical_pit_dataset as support
from tests.crypto_core.validation import test_strategy_executable_binding as bind

_PREFIX = "edge_leakage_bias_evidence"
_PROFILE_PREFIX = "strategy_executable_profile"
_UNSET = object()

# Synthetic test values only: EF-5 holds no production parameter values and never chooses one.
ENTRY_LOW = "0.000100000000000000"
ENTRY_HIGH = "0.000200000000000000"
EXIT = "0.000050000000000000"
UNIT = "1.000000000000000000"
FEATURE = "final_funding_mean"
GRID = ((ENTRY_LOW, "2"), (ENTRY_LOW, "3"), (ENTRY_HIGH, "2"), (ENTRY_HIGH, "3"))
COMMITMENTS = (
    "root_intake_digest",
    "predecessor_digest",
    "strategy_spec_digest",
    "executable_binding_digest",
    "profile_semantics_digest",
    "feature_set_digest",
    "parameter_bounds_digest",
    "variant_ledger_digest",
    "decision_structure_digest",
    "bias_proof_set_digest",
)


def assignment(
    *, entry: str = ENTRY_LOW, exit_: str = EXIT, lookback: str = "2", unit: str = UNIT, **extra: str
) -> tuple[ProfileParameterAssignment, ...]:
    return (
        ProfileParameterAssignment("entry_threshold", entry),
        ProfileParameterAssignment("exit_threshold", exit_),
        ProfileParameterAssignment("final_funding_lookback_count", lookback),
        ProfileParameterAssignment("unit_size", unit),
        *(ProfileParameterAssignment(name, value) for name, value in extra.items()),
    )


def variants() -> tuple[EdgeInputVariant, ...]:
    return tuple(
        EdgeInputVariant(f"variant-{index}", assignment(entry=entry, lookback=lookback))
        for index, (entry, lookback) in enumerate(GRID, start=1)
    )


def bounds() -> tuple[EdgeParameterSearchBound, ...]:
    return (
        EdgeParameterSearchBound("entry_threshold", "searched", (ENTRY_LOW, ENTRY_HIGH)),
        EdgeParameterSearchBound("exit_threshold", "fixed", (EXIT,)),
        EdgeParameterSearchBound("final_funding_lookback_count", "searched", ("2", "3")),
        EdgeParameterSearchBound("unit_size", "fixed", (UNIT,)),
    )


def single_variant(**overrides: str) -> dict[str, object]:
    """One variant plus FIXED bounds exercising exactly its values."""

    values = assignment(**overrides)
    return {
        "parameter_bounds": tuple(
            EdgeParameterSearchBound(item.parameter_id, "fixed", (item.value,)) for item in values
        ),
        "variants": (EdgeInputVariant("variant-1", values),),
    }


@cache
def _base() -> tuple[object, object, EdgeStrategySpecAdmissionEvidence, StrategyExecutableBinding]:
    intake, manifest, admission, _ = support.chain()
    return intake, manifest, admission, bind.executable_binding(admission)


def approval_for(evidence: EdgeLeakageBiasEvidence, **overrides: str) -> EdgePreregistrationApproval:
    arguments = {
        "approval_reference": "governance-preregistration-1",
        "approval_digest": "a" * 64,
        **{f"approved_{name}": getattr(evidence, name) or "0" * 64 for name in COMMITMENTS},
    }
    arguments.update(overrides)
    return EdgePreregistrationApproval(**arguments)


def arguments_for(admission, binding, intake, **overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "expected_predecessor_digest": admission.admission_digest,
        "expected_root_intake_digest": intake.intake_digest,
        "executable_binding": binding,
        "expected_executable_binding_digest": binding.binding_digest,
        "preregistration_id": "prereg-1",
        "correlation_id": admission.correlation_id,
        "feature_ids": (FEATURE,),
        "parameter_bounds": bounds(),
        "variants": variants(),
        "survivorship_claim_scope": EdgeSurvivorshipClaimScope.PINNED_INSTRUMENT_UNIVERSE,
    }
    arguments.update(overrides)
    return arguments


def prereg(*, admission=None, binding=None, intake=None, approve: bool = True, **overrides) -> EdgeLeakageBiasEvidence:
    """EF-5 over the base chain; with ``approve`` the approval commits to the exact draft being built."""

    base_intake, _, base_admission, base_binding = _base()
    admission = base_admission if admission is None else admission
    binding = base_binding if binding is None else binding
    intake = base_intake if intake is None else intake
    arguments = arguments_for(admission, binding, intake, **overrides)
    if approve and "approval" not in overrides:
        draft = build_edge_leakage_bias_evidence(admission, **arguments)  # type: ignore[arg-type]
        arguments["approval"] = approval_for(draft)
    return build_edge_leakage_bias_evidence(admission, **arguments)  # type: ignore[arg-type]


@cache
def _sealed() -> EdgeLeakageBiasEvidence:
    return prereg()


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _rejected_variant(variant_id: str, code: str) -> str:
    return _code(f"variant_assignment_rejected:{variant_id}:{_PROFILE_PREFIX}:{code}")


def _reseal(evidence: EdgeLeakageBiasEvidence, **changes: object) -> EdgeLeakageBiasEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, leakage_bias_evidence_digest=edge_leakage_bias_evidence_digest(changed))


def _payload(evidence: EdgeLeakageBiasEvidence) -> dict:
    return json.loads(edge_canonical_json(edge_leakage_bias_evidence_to_dict(evidence)))


def _resealed_payload(payload: dict) -> EdgeLeakageBiasEvidence:
    payload["leakage_bias_evidence_digest"] = edge_payload_digest(payload, "leakage_bias_evidence_digest")
    return edge_leakage_bias_evidence_from_payload(payload)


def _assert_not_intact(evidence: object, *codes: str) -> EdgeEvidenceVerification:
    verification = verify_edge_leakage_bias_evidence(evidence)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes
    assert {_code(code) for code in codes} <= set(verification.reason_codes)
    return verification


def _assert_receipt_invariants(evidence: EdgeLeakageBiasEvidence) -> None:
    verification = verify_edge_leakage_bias_evidence(evidence)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.leakage_bias_evidence_digest
    assert edge_leakage_bias_evidence_from_payload(json.loads(verification.canonical_json)) == evidence
    assert edge_leakage_bias_evidence_payload_is_well_formed(edge_leakage_bias_evidence_to_dict(evidence)) is True
    assert evidence.advances is (
        evidence.status is EdgeEvidenceStatus.READY and evidence.gate_verdict is EdgeGateVerdict.PASS
    )
    assert evidence.preregistration_sealed is evidence.advances
    assert {name: getattr(evidence, name) for name, _ in EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS} == dict(
        EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS
    )
    assert evidence.multiple_testing_count == len(evidence.registered_variants)
    assert evidence.registered_parameter_assignment_digests == tuple(
        sorted(item.parameter_assignment_digest for item in evidence.registered_variants)
    )
    for item in evidence.registered_variants:
        assert item.parameter_assignment_digest == profile_parameter_assignment_digest(item.parameter_assignment)
    if evidence.status is EdgeEvidenceStatus.REJECTED:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes
        assert evidence.verdict_reason_codes == ()
        assert evidence.bias_proofs == ()
    else:
        assert evidence.integrity_reason_codes == ()
        assert [proof.proof_kind for proof in evidence.bias_proofs] == list(EdgeBiasProofKind)


# --- chains used as authentic upstream authority ----------------------------------------------------------------------


def _kill_policy(correlation_id: str = "corr-1"):
    return build_edge_kill_criteria_policy(
        policy_id="kp-1",
        correlation_id=correlation_id,
        kill_criteria=support.CRITERIA,
        thresholds_approved=True,
        approval_reference="gov-1",
        approval_digest="d" * 64,
    )


def _admission_from(intake, manifest, *, spec_changes=None, policy: bool = True, **overrides):
    spec = validate_strategy_spec({**support.SPEC, **(spec_changes or {})}).spec
    kill_policy = _kill_policy(manifest.correlation_id) if policy else None
    arguments = {
        "expected_predecessor_digest": manifest.source_packet_evidence_digest,
        "expected_root_intake_digest": intake.intake_digest,
        "strategy_spec": spec,
        "expected_strategy_spec_digest": strategy_spec_digest(spec),
        "admission_id": "admission-1",
        "correlation_id": manifest.correlation_id,
        "admitted_kill_criteria": support.CRITERIA,
        "kill_criteria_policy": kill_policy,
        "expected_kill_criteria_policy_digest": None if kill_policy is None else kill_policy.policy_digest,
    }
    arguments.update(overrides)
    return build_edge_strategy_spec_admission(manifest, **arguments)


def _series(series_id: str, key: str) -> EdgeInputSeries:
    return EdgeInputSeries(
        series_id,
        key,
        f"archive:{series_id}",
        "own_research",
        "note-1",
        "finalized_only",
        "immutable_after_finalization",
        (support.BTC, support.ETH),
    )


def _chain_with_series(series: tuple[EdgeInputSeries, ...], spec_keys: tuple[str, ...]):
    """Authentic EF-2 → EF-4 chain over ``series`` whose spec declares ``spec_keys``, plus an approved binding.

    The intake and manifest carry every series key; the binding maps each spec data element onto the profile's funding
    data element — a governance text mapping the binding cannot machine-check.
    """

    keys = tuple(sorted({item.data_requirement_key for item in series}))

    packet = build_source_packet(
        packet_id="pkt-1",
        source_type="academic_paper",
        source_reference="doi:10.0/carry",
        source_title="Perpetual funding carry",
        rights_status="own_research",
        edge_hypothesis="Funding pays passive carry.",
        content_digest="c" * 64,
        market_scope_tags=("crypto_perpetuals",),
    )
    policy = _kill_policy()
    intake = build_edge_idea_intake_evidence(
        packet,
        expected_source_packet_digest=packet.packet_digest,
        intake_id="intake-1",
        correlation_id="corr-1",
        candidate_strategy_id="passive-funding-carry",
        edge_family="funding_basis_carry",
        economic_rationale="Funding pays carry.",
        data_requirement_keys=keys,
        declared_regime_dependence="positive_funding_regime",
        kill_criteria_draft=support.CRITERIA,
        kill_criteria_policy=policy,
        expected_kill_criteria_policy_digest=policy.policy_digest,
    )
    registry = default_perp_data_requirement_registry()
    manifest = build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id="corr-1",
        input_series=series,
    )
    assert manifest.advances is True
    admission = _admission_from(intake, manifest, spec_changes={"data_requirements": dict.fromkeys(spec_keys, "8h")})
    data_entry = next(entry for entry in bind.COVERAGE if entry.spec_element_kind == "data_requirement")
    coverage = (
        *(entry for entry in bind.COVERAGE if entry.spec_element_kind != "data_requirement"),
        *(replace(data_entry, spec_element_ref=key) for key in spec_keys),
    )
    binding = bind.executable_binding(admission, coverage)
    assert (admission.advances, binding.advances) == (True, True)
    return intake, admission, binding


@cache
def _mark_price_chain():
    """Only mark prices exist and are declared; the binding maps them onto the funding profile's data element."""

    return _chain_with_series((_series("mark-final", "mark_price"),), ("mark_price",))


@cache
def _undeclared_funding_chain():
    """The manifest carries funding AND mark prices, but the admitted spec declares only mark prices."""

    return _chain_with_series(
        (_series("funding-final", "funding_rate"), _series("mark-final", "mark_price")), ("mark_price",)
    )


@cache
def _two_source_chain():
    """Two eligible final funding series cover the same instrument: the feature's input source is not pinned."""

    return _chain_with_series(
        (_series("funding-final", "funding_rate"), _series("funding-final-mirror", "funding_rate")), ("funding_rate",)
    )


@cache
def _other_chain():
    """A second authentic chain with the same correlation and spec but a different root."""

    intake, manifest, admission, _ = support.chain(intake_id="intake-2")
    return intake, manifest, admission, bind.executable_binding(admission)


# --- outcomes ----------------------------------------------------------------------------------------------------------


def test_sealed_preregistration_is_ready_pass_and_binds_the_authenticated_chain() -> None:
    intake, manifest, admission, binding = _base()
    evidence = _sealed()
    _assert_receipt_invariants(evidence)
    assert (evidence.status, evidence.gate_verdict, evidence.advances, evidence.preregistration_sealed) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
        True,
    )
    profile = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    assert (evidence.gate_id, evidence.predecessor_gate_id) == ("EF-5", "EF-4")
    assert evidence.root_intake_digest == intake.intake_digest
    assert evidence.predecessor_digest == admission.admission_digest
    assert evidence.source_manifest_digest == manifest.source_packet_evidence_digest
    assert evidence.strategy_spec_digest == admission.strategy_spec_digest
    assert evidence.executable_binding_digest == binding.binding_digest
    assert (evidence.profile_id, evidence.profile_version) == (PASSIVE_FUNDING_CARRY_V1, "1")
    assert evidence.profile_semantics_digest == profile.profile_semantics_digest
    assert (evidence.candidate_strategy_id, evidence.edge_family) == ("passive-funding-carry", "funding_basis_carry")
    assert (evidence.strategy_id, evidence.strategy_version) == ("passive-funding-carry", "1.0.0")
    assert evidence.pinned_instrument_universe == (support.BTC,)
    assert evidence.feature_ids == evidence.strategy_feature_ids == (FEATURE,)
    assert evidence.profile_feature_element_ids == ("feature_mean_last_n_final_funding_rates",)
    assert evidence.multiple_testing_count == 4
    assert evidence.survivorship_claim_scope is EdgeSurvivorshipClaimScope.PINNED_INSTRUMENT_UNIVERSE
    assert all(proof.outcome is EdgeBiasProofOutcome.PROVEN for proof in evidence.bias_proofs)
    assert evidence.approval == approval_for(evidence)
    assert evidence.verdict_reason_codes == ()


def test_registered_digests_are_the_profile_assignment_digests_a_later_gate_checks() -> None:
    evidence = _sealed()
    profile = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    expected = {
        profile_parameter_assignment_digest(
            canonical_profile_parameter_assignment(profile, assignment(entry=entry, lookback=lookback))
        )
        for entry, lookback in GRID
    }
    assert set(evidence.registered_parameter_assignment_digests) == expected
    unregistered = canonical_profile_parameter_assignment(profile, assignment(entry=ENTRY_HIGH, lookback="4"))
    assert profile_parameter_assignment_digest(unregistered) not in evidence.registered_parameter_assignment_digests
    for item in evidence.registered_variants:
        assert item.parameter_assignment == canonical_profile_parameter_assignment(profile, item.parameter_assignment)


def test_preregistration_is_deterministic_and_declaration_order_insensitive() -> None:
    first = _sealed()
    reordered = prereg(
        parameter_bounds=tuple(replace(bound, values=tuple(reversed(bound.values))) for bound in reversed(bounds())),
        variants=tuple(
            replace(item, parameter_assignment=tuple(reversed(item.parameter_assignment)))
            for item in reversed(variants())
        ),
        survivorship_claim_scope="pinned_instrument_universe",
        approval=first.approval,
    )
    assert edge_leakage_bias_evidence_to_dict(reordered) == edge_leakage_bias_evidence_to_dict(first)
    assert prereg(approval=first.approval) == first


def test_decision_structure_is_derived_from_the_registered_profile_and_binding() -> None:
    evidence = _sealed()
    profile = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    _, _, _, binding = _base()
    assert evidence.decision_labels == tuple(sorted(action.value for action in ProfileAction))
    assert evidence.decision_schedule_id == profile.decision_schedule_id
    assert evidence.state_rule_id == profile.state_rule_id
    assert evidence.parameter_constraints == ("exit_threshold_lte_entry_threshold",)
    assert evidence.parameter_schema_refs == (
        "entry_threshold:positive_decimal",
        "exit_threshold:nonnegative_decimal",
        "final_funding_lookback_count:positive_integer",
        "unit_size:positive_decimal",
    )
    assert "entry:entry_short_on_positive_mean" in evidence.decision_element_refs
    assert not any(ref.startswith(("feature:", "data_requirement:")) for ref in evidence.decision_element_refs)
    assert evidence.binding_coverage_digest == binding.coverage_digest
    structure_text = edge_canonical_json(
        [evidence.decision_labels, evidence.decision_element_refs, evidence.parameter_schema_refs]
    )
    assert ENTRY_LOW not in structure_text
    assert EXIT not in structure_text


def test_bias_proofs_are_structured_and_bound_to_the_exact_authorities() -> None:
    _, manifest, admission, _ = _base()
    evidence = _sealed()
    lookahead, repaint, survivorship = evidence.bias_proofs
    profile_digest = evidence.profile_semantics_digest
    authorities = (
        admission.strategy_spec_digest,
        manifest.source_packet_evidence_digest,
        manifest.data_requirement_registry_digest,
        profile_digest,
    )
    assert lookahead.authority_digests == authorities
    assert repaint.authority_digests == authorities
    assert survivorship.authority_digests == (admission.strategy_spec_digest, manifest.source_packet_evidence_digest)
    assert {(item.check_id, item.subject) for item in lookahead.checks} == {
        ("decision_schedule_point_in_time_visible", "final_funding_record_max_available_finalized.v1"),
        ("required_input_declared_by_admitted_strategy_spec", "funding_rate"),
        ("input_series_finalized_only", support.SERIES),
        ("input_series_time_policies_registry_bound", support.SERIES),
        ("required_input_served_for_instrument", f"funding_rate:{support.BTC}"),
        ("required_input_source_unambiguous_for_instrument", f"funding_rate:{support.BTC}"),
    }
    assert {(item.check_id, item.subject) for item in repaint.checks} == {
        ("decision_schedule_point_in_time_visible", "final_funding_record_max_available_finalized.v1"),
        ("required_input_declared_by_admitted_strategy_spec", "funding_rate"),
        ("input_series_finalized_only", support.SERIES),
        ("input_series_point_in_time_revision_safe", support.SERIES),
    }
    assert {(item.check_id, item.subject) for item in survivorship.checks} == {
        ("claim_scope_restricted_to_pinned_admitted_universe", "pinned_instrument_universe"),
        ("universe_instrument_in_point_in_time_manifest_coverage", support.BTC),
    }
    assert survivorship.limitations == (
        "cross_sectional_generalization_not_claimed",
        "instrument_listing_lifecycle_not_evaluated",
    )


# --- EF-4 predecessor and chain authority ------------------------------------------------------------------------------


def test_root_anchor_transplant_is_a_chain_splice_rejection() -> None:
    other_intake, _, _, _ = _other_chain()
    evidence = prereg(approve=False, expected_root_intake_digest=other_intake.intake_digest)
    _assert_receipt_invariants(evidence)
    assert evidence.integrity_reason_codes == (_code("chain_splice_root_intake_mismatch"),)
    assert evidence.preregistration_sealed is False


def test_predecessor_anchor_transplant_is_rejected() -> None:
    _, _, other_admission, _ = _other_chain()
    evidence = prereg(approve=False, expected_predecessor_digest=other_admission.admission_digest)
    _assert_receipt_invariants(evidence)
    assert evidence.integrity_reason_codes == (
        _code("executable_binding_admission_mismatch"),
        _code("predecessor_digest_mismatch"),
    )


def test_correlation_splice_is_rejected() -> None:
    evidence = prereg(approve=False, correlation_id="corr-2")
    _assert_receipt_invariants(evidence)
    assert evidence.integrity_reason_codes == (
        _code("executable_binding_correlation_mismatch"),
        _code("predecessor_correlation_mismatch"),
    )


def test_forged_resealed_ef4_is_rejected() -> None:
    _, _, admission, _ = _base()
    forged = replace(admission, candidate_strategy_id="other-carry")
    forged = replace(forged, admission_digest=edge_strategy_spec_admission_digest(forged))
    evidence = prereg(admission=forged, approve=False)
    _assert_receipt_invariants(evidence)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("predecessor_integrity_failure:")) for code in evidence.integrity_reason_codes)


def test_authentic_rejected_ef4_receipt_is_never_evaluated() -> None:
    intake, manifest, _, _ = _base()
    rejected = _admission_from(intake, manifest, expected_strategy_spec_digest="e" * 64)
    assert rejected.status is EdgeEvidenceStatus.REJECTED
    evidence = prereg(admission=rejected, approve=False)
    _assert_receipt_invariants(evidence)
    assert evidence.integrity_reason_codes == (
        _code("executable_binding_admission_mismatch"),
        _code("predecessor_rejected"),
    )


def test_nested_ef4_promotion_with_every_digest_recomputed_never_verifies() -> None:
    intake, manifest, _, _ = _base()
    failing = _admission_from(intake, manifest, spec_changes={"strategy_id": "beta-funding-carry"})
    evidence = prereg(admission=failing, binding=bind.executable_binding(failing))
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    payload = _payload(evidence)
    snapshot = payload["predecessor_binding"]["snapshot"]
    snapshot.update(gate_verdict="PASS", advances=True, verdict_reason_codes=[])
    snapshot["admission_digest"] = edge_payload_digest(snapshot, "admission_digest")
    payload["predecessor_binding"]["expected_digest"] = snapshot["admission_digest"]
    payload["predecessor_digest"] = snapshot["admission_digest"]
    payload.update(gate_verdict="PASS", advances=True, preregistration_sealed=True, verdict_reason_codes=[])
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:status", "field_mismatch:preregistration_sealed")


def test_nested_ef3_coverage_forgery_with_every_digest_recomputed_never_verifies() -> None:
    payload = _payload(_sealed())
    admission = payload["predecessor_binding"]["snapshot"]
    manifest = admission["predecessor_binding"]["snapshot"]
    manifest["instrument_coverage"] = sorted([*manifest["instrument_coverage"], "SOL-PERPETUAL"])
    manifest["source_packet_evidence_digest"] = edge_payload_digest(manifest, "source_packet_evidence_digest")
    admission["predecessor_binding"]["expected_digest"] = manifest["source_packet_evidence_digest"]
    admission["predecessor_digest"] = manifest["source_packet_evidence_digest"]
    admission["packet_instrument_coverage"] = manifest["instrument_coverage"]
    admission["admission_digest"] = edge_payload_digest(admission, "admission_digest")
    payload["predecessor_binding"]["expected_digest"] = admission["admission_digest"]
    payload["predecessor_digest"] = admission["admission_digest"]
    payload["source_manifest_digest"] = manifest["source_packet_evidence_digest"]
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:status")


def test_nested_binding_promotion_with_every_digest_recomputed_never_verifies() -> None:
    _, _, admission, _ = _base()
    evidence = prereg(binding=bind.executable_binding(admission, approve=False))
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    payload = _payload(evidence)
    snapshot = payload["executable_binding"]["snapshot"]
    snapshot.update(gate_verdict="PASS", advances=True, verdict_reason_codes=[])
    snapshot["binding_digest"] = edge_payload_digest(snapshot, "binding_digest")
    payload["executable_binding"]["expected_digest"] = snapshot["binding_digest"]
    payload["executable_binding_digest"] = snapshot["binding_digest"]
    payload.update(gate_verdict="PASS", advances=True, preregistration_sealed=True, verdict_reason_codes=[])
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:status")


@pytest.mark.parametrize(
    ("policy", "spec_changes", "expected"),
    [
        (
            True,
            {"strategy_id": "beta-funding-carry"},
            {"predecessor_not_advanced:FAIL", "executable_binding_not_advanced:FAIL"},
        ),
        (
            False,
            None,
            {
                "predecessor_not_advanced:NEEDS_GOVERNANCE_APPROVAL",
                "executable_binding_not_advanced:NEEDS_GOVERNANCE_APPROVAL",
            },
        ),
    ],
)
def test_non_advancing_ef4_never_seals(policy: bool, spec_changes, expected: set[str]) -> None:
    intake, manifest, _, _ = _base()
    admission = _admission_from(intake, manifest, spec_changes=spec_changes, policy=policy)
    assert admission.status is EdgeEvidenceStatus.READY
    assert admission.advances is False
    evidence = prereg(admission=admission, binding=bind.executable_binding(admission))
    _assert_receipt_invariants(evidence)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.preregistration_sealed is False
    assert set(evidence.verdict_reason_codes) == {_code(code) for code in expected}


# --- auxiliary executable authority ------------------------------------------------------------------------------------


def test_executable_binding_of_a_different_ef4_is_rejected() -> None:
    _, _, _, other_binding = _other_chain()
    evidence = prereg(binding=other_binding, approve=False)
    _assert_receipt_invariants(evidence)
    assert evidence.integrity_reason_codes == (_code("executable_binding_admission_mismatch"),)


def test_executable_binding_anchor_transplant_is_rejected() -> None:
    _, _, _, other_binding = _other_chain()
    evidence = prereg(approve=False, expected_executable_binding_digest=other_binding.binding_digest)
    _assert_receipt_invariants(evidence)
    assert evidence.integrity_reason_codes == (_code("executable_binding_digest_mismatch"),)


def test_forged_resealed_executable_binding_is_rejected() -> None:
    _, _, _, binding = _base()
    forged = replace(binding, profile_version="2")
    forged = replace(forged, binding_digest=strategy_executable_binding_digest(forged))
    evidence = prereg(binding=forged, approve=False)
    _assert_receipt_invariants(evidence)
    assert any(
        code.startswith(_code("executable_binding_integrity_failure:")) for code in evidence.integrity_reason_codes
    )


def test_unknown_profile_binding_receipt_is_rejected() -> None:
    _, _, admission, _ = _base()
    unknown = bind.executable_binding(admission, profile_id="funding_momentum.v1")
    assert unknown.status is EdgeEvidenceStatus.REJECTED
    evidence = prereg(binding=unknown, approve=False)
    _assert_receipt_invariants(evidence)
    assert evidence.integrity_reason_codes == (_code("executable_binding_rejected"),)


def test_profile_semantics_drift_invalidates_the_preregistration(monkeypatch: pytest.MonkeyPatch) -> None:
    sealed = _sealed()
    drifted = bind.drifted_registry_profile(max_decimal_text_length=59)
    monkeypatch.setitem(profiles_module._REGISTRY, PASSIVE_FUNDING_CARRY_V1, drifted)
    _assert_not_intact(sealed, "field_mismatch:status")
    rebuilt = prereg(approve=False)
    assert rebuilt.status is EdgeEvidenceStatus.REJECTED
    assert any(
        code.startswith(_code("executable_binding_integrity_failure:")) for code in rebuilt.integrity_reason_codes
    )


@pytest.mark.parametrize(
    ("approve", "coverage", "expected"),
    [
        (False, bind.COVERAGE, "executable_binding_not_advanced:NEEDS_GOVERNANCE_APPROVAL"),
        (
            True,
            tuple(entry for entry in bind.COVERAGE if entry.spec_element_kind != "invalidation_condition"),
            "executable_binding_not_advanced:FAIL",
        ),
    ],
)
def test_non_advancing_executable_binding_never_seals(approve: bool, coverage, expected: str) -> None:
    _, _, admission, _ = _base()
    binding = bind.executable_binding(admission, coverage, approve=approve)
    evidence = prereg(binding=binding)
    _assert_receipt_invariants(evidence)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.verdict_reason_codes == (_code(expected),)
    assert evidence.preregistration_sealed is False


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"executable_binding": "binding-1"}, "executable_binding_malformed"),
        ({"executable_binding": object.__new__(StrategyExecutableBinding)}, "executable_binding_not_serializable"),
        ({"expected_executable_binding_digest": "B" * 64}, "executable_binding_expected_digest_invalid"),
        ({"expected_predecessor_digest": None}, "predecessor_expected_digest_invalid"),
    ],
)
def test_malformed_authority_objects_are_construction_errors(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeLeakageBiasEvidenceError) as excinfo:
        prereg(approve=False, **overrides)
    assert str(excinfo.value) == _code(code)


@pytest.mark.parametrize(
    ("predecessor", "code"),
    [
        ("admission-1", "predecessor_malformed"),
        (object.__new__(EdgeStrategySpecAdmissionEvidence), "predecessor_not_serializable"),
    ],
)
def test_malformed_predecessor_is_a_construction_error(predecessor: object, code: str) -> None:
    intake, _, admission, binding = _base()
    with pytest.raises(EdgeLeakageBiasEvidenceError) as excinfo:
        build_edge_leakage_bias_evidence(predecessor, **arguments_for(admission, binding, intake))  # type: ignore[arg-type]
    assert str(excinfo.value) == _code(code)


# --- feature set -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("feature_ids", "expected"),
    [
        ((FEATURE, "open_interest_trend"), {"feature_not_admitted_by_strategy_spec:open_interest_trend"}),
        (
            ("open_interest_trend",),
            {
                "feature_not_admitted_by_strategy_spec:open_interest_trend",
                f"feature_omitted_from_preregistration:{FEATURE}",
            },
        ),
        ((), {f"feature_omitted_from_preregistration:{FEATURE}"}),
    ],
)
def test_feature_set_must_equal_the_admitted_strategy_features(
    feature_ids: tuple[str, ...], expected: set[str]
) -> None:
    evidence = prereg(feature_ids=feature_ids)
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert set(evidence.verdict_reason_codes) == {_code(code) for code in expected}
    assert evidence.strategy_feature_ids == (FEATURE,)


@cache
def _two_feature_chain():
    features = {FEATURE: "last_n_final_settlements", "funding_mean_dispersion": "last_n_final_settlements"}
    intake, _, admission, _ = support.chain(spec_changes={"feature_requirements": features})
    coverage = (
        *bind.COVERAGE,
        StrategyExecutableCoverageEntry(
            "feature_requirement", "funding_mean_dispersion", ("feature_mean_last_n_final_funding_rates",)
        ),
    )
    return intake, admission, bind.executable_binding(admission, coverage)


def test_multi_feature_set_is_canonical_and_a_partial_declaration_fails() -> None:
    intake, admission, binding = _two_feature_chain()
    forward = prereg(
        admission=admission, binding=binding, intake=intake, feature_ids=(FEATURE, "funding_mean_dispersion")
    )
    _assert_receipt_invariants(forward)
    assert forward.preregistration_sealed is True
    assert forward.feature_ids == (FEATURE, "funding_mean_dispersion")
    backward = prereg(
        admission=admission,
        binding=binding,
        intake=intake,
        feature_ids=("funding_mean_dispersion", FEATURE),
        approval=forward.approval,
    )
    assert backward == forward
    partial = prereg(admission=admission, binding=binding, intake=intake, feature_ids=(FEATURE,))
    assert partial.verdict_reason_codes == (_code("feature_omitted_from_preregistration:funding_mean_dispersion"),)
    payload = _payload(forward)
    payload["feature_ids"] = list(reversed(payload["feature_ids"]))
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:feature_ids")


def test_post_hoc_feature_change_cannot_reuse_the_approval() -> None:
    evidence = prereg(feature_ids=(FEATURE, "open_interest_trend"), approval=_sealed().approval)
    assert _code("preregistration_approval_feature_set_digest_mismatch") in evidence.verdict_reason_codes
    assert evidence.preregistration_sealed is False


# --- parameter search space --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"entry": "5"}, "parameter_value_invalid:entry_threshold"),
        ({"lookback": "2.000000000000000000"}, "parameter_value_invalid:final_funding_lookback_count"),
        ({"entry": "0.0001"}, "parameter_value_invalid:entry_threshold"),
        ({"entry": "1e-4"}, "parameter_value_invalid:entry_threshold"),
        ({"entry": "-0.000100000000000000"}, "parameter_value_invalid:entry_threshold"),
        ({"unit": "0.000000000000000000"}, "parameter_value_invalid:unit_size"),
        ({"exit_": "-0.000000000000000000"}, "parameter_value_invalid:exit_threshold"),
        ({"lookback": "02"}, "parameter_value_invalid:final_funding_lookback_count"),
        ({"lookback": "0"}, "parameter_value_invalid:final_funding_lookback_count"),
        ({"lookback": "-2"}, "parameter_value_invalid:final_funding_lookback_count"),
        ({"entry": "1" * 42 + "." + "0" * 18}, "parameter_value_invalid:entry_threshold"),
        ({"lookback": "9223372036854775808"}, "parameter_value_invalid:final_funding_lookback_count"),
        ({"exit_": "0.000200000000000000"}, "parameter_constraint_violated:exit_threshold_lte_entry_threshold"),
    ],
)
def test_registry_owned_kind_grammar_representation_and_constraints_fail(overrides: dict[str, str], code: str) -> None:
    evidence = prereg(**single_variant(**overrides))
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert evidence.verdict_reason_codes == (_rejected_variant("variant-1", code),)
    assert evidence.preregistration_sealed is False


def test_largest_representable_values_are_accepted_by_the_registry() -> None:
    largest_decimal = "9" * 41 + "." + "9" * 18
    evidence = prereg(**single_variant(entry=largest_decimal, unit=largest_decimal, lookback="9223372036854775807"))
    _assert_receipt_invariants(evidence)
    assert evidence.preregistration_sealed is True
    assert evidence.multiple_testing_count == 1


def test_unknown_parameter_bound_and_hidden_variant_parameter_fail() -> None:
    evidence = prereg(**single_variant(leverage_cap="1"))
    _assert_receipt_invariants(evidence)
    assert set(evidence.verdict_reason_codes) == {
        _code("parameter_bound_unknown:leverage_cap"),
        _rejected_variant("variant-1", "parameter_unknown:leverage_cap"),
    }


def test_hidden_parameter_without_a_bound_still_fails() -> None:
    case = single_variant()
    case["variants"] = (EdgeInputVariant("variant-1", assignment(leverage_cap="1")),)
    evidence = prereg(**case)
    assert evidence.verdict_reason_codes == (_rejected_variant("variant-1", "parameter_unknown:leverage_cap"),)


def test_missing_parameter_bound_is_pending_governance_input() -> None:
    evidence = prereg(parameter_bounds=bounds()[:3])
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == (_code("parameter_bound_pending_governance:unit_size"),)


def test_incomplete_variant_assignment_fails() -> None:
    case = single_variant()
    case["variants"] = (EdgeInputVariant("variant-1", assignment()[:3]),)
    evidence = prereg(**case)
    _assert_receipt_invariants(evidence)
    assert set(evidence.verdict_reason_codes) == {
        _rejected_variant("variant-1", "parameter_missing:unit_size"),
        _code(f"parameter_bound_value_unregistered:unit_size:{UNIT}"),
    }


def test_variant_outside_the_preregistered_bounds_fails() -> None:
    outside = EdgeInputVariant("variant-5", assignment(entry="0.000300000000000000"))
    evidence = prereg(variants=(*variants(), outside))
    _assert_receipt_invariants(evidence)
    assert evidence.verdict_reason_codes == (_code("variant_value_outside_bounds:variant-5:entry_threshold"),)


def test_every_bound_value_must_be_exercised_by_a_registered_variant() -> None:
    widened = (
        EdgeParameterSearchBound("entry_threshold", "searched", (ENTRY_LOW, ENTRY_HIGH, "0.000300000000000000")),
        *bounds()[1:],
    )
    evidence = prereg(parameter_bounds=widened)
    _assert_receipt_invariants(evidence)
    assert evidence.verdict_reason_codes == (
        _code("parameter_bound_value_unregistered:entry_threshold:0.000300000000000000"),
    )


def test_malformed_but_unexercised_bound_value_can_never_seal() -> None:
    widened = (EdgeParameterSearchBound("entry_threshold", "searched", (ENTRY_LOW, ENTRY_HIGH, "0.1")), *bounds()[1:])
    evidence = prereg(parameter_bounds=widened)
    assert evidence.verdict_reason_codes == (_code("parameter_bound_value_unregistered:entry_threshold:0.1"),)
    assert evidence.preregistration_sealed is False


def test_parameter_bounds_carry_no_caller_kind_and_variants_no_caller_digest() -> None:
    assert [field.name for field in fields(EdgeParameterSearchBound)] == ["parameter_id", "treatment", "values"]
    assert [field.name for field in fields(EdgeInputVariant)] == ["variant_id", "parameter_assignment"]
    assert _sealed().parameter_bounds[0].treatment is EdgeParameterSearchTreatment.SEARCHED


# --- variant ledger and multiple-testing count -------------------------------------------------------------------------


def test_empty_ledger_is_pending_governance_and_counts_zero() -> None:
    evidence = prereg(variants=())
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == (_code("variant_ledger_pending_governance"),)
    assert evidence.multiple_testing_count == 0
    assert evidence.preregistration_sealed is False


def test_real_candidate_without_governance_input_is_buildable_and_never_invents_values() -> None:
    evidence = prereg(parameter_bounds=(), variants=(), approve=False)
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert set(evidence.verdict_reason_codes) == {
        _code("parameter_bound_pending_governance:entry_threshold"),
        _code("parameter_bound_pending_governance:exit_threshold"),
        _code("parameter_bound_pending_governance:final_funding_lookback_count"),
        _code("parameter_bound_pending_governance:unit_size"),
        _code("variant_ledger_pending_governance"),
        _code("preregistration_approval_missing"),
    }
    assert evidence.parameter_bounds == ()
    assert evidence.registered_variants == ()


def test_multiple_testing_count_is_the_ledger_cardinality() -> None:
    three = prereg(variants=variants()[:3])
    assert three.multiple_testing_count == 3
    assert three.preregistration_sealed is True
    assert three.variant_ledger_digest != _sealed().variant_ledger_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("multiple_testing_count", 1),
        ("multiple_testing_count", 5),
        ("registered_parameter_assignment_digests", ("0" * 64,)),
        ("variant_ledger_digest", "0" * 64),
    ],
)
def test_ledger_count_and_digest_tamper_never_verifies(field: str, value: object) -> None:
    _assert_not_intact(_reseal(_sealed(), **{field: value}), f"field_mismatch:{field}")


def test_caller_forged_assignment_digest_never_verifies() -> None:
    evidence = _sealed()
    forged = replace(evidence.registered_variants[0], parameter_assignment_digest="f" * 64)
    _assert_not_intact(
        _reseal(evidence, registered_variants=(forged, *evidence.registered_variants[1:])),
        "field_mismatch:registered_variants",
    )


def test_ledger_reorder_in_the_payload_never_verifies() -> None:
    payload = _payload(_sealed())
    payload["registered_variants"] = list(reversed(payload["registered_variants"]))
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:registered_variants")


def test_injected_ledger_entry_never_verifies() -> None:
    evidence = _sealed()
    extra = EdgeRegisteredVariant("variant-5", assignment(entry=ENTRY_HIGH, lookback="4"), "0" * 64)
    tampered = _reseal(evidence, registered_variants=(*evidence.registered_variants, extra))
    _assert_not_intact(tampered, "field_mismatch:registered_variants", "field_mismatch:multiple_testing_count")


def test_changed_ledger_cannot_reuse_a_copied_approval() -> None:
    evidence = prereg(variants=variants()[:3], approval=_sealed().approval)
    assert evidence.verdict_reason_codes == (_code("preregistration_approval_variant_ledger_digest_mismatch"),)


# --- digest tamper -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "feature_set_digest",
        "parameter_bounds_digest",
        "decision_structure_digest",
        "bias_proof_set_digest",
        "strategy_feature_ids",
        "profile_feature_element_ids",
        "decision_labels",
        "decision_element_refs",
        "parameter_schema_refs",
        "parameter_constraints",
        "decision_schedule_id",
        "binding_coverage_digest",
        "pinned_instrument_universe",
        "source_manifest_digest",
        "strategy_spec_digest",
        "profile_semantics_digest",
    ],
)
def test_derived_field_tamper_never_verifies(field: str) -> None:
    evidence = _sealed()
    current = getattr(evidence, field)
    value = ("forged",) if type(current) is tuple else "0" * 64
    _assert_not_intact(_reseal(evidence, **{field: value}), f"field_mismatch:{field}")


def test_bound_tamper_never_verifies() -> None:
    evidence = _sealed()
    widened = replace(evidence.parameter_bounds[0], values=(ENTRY_LOW, ENTRY_HIGH, "0.000300000000000000"))
    _assert_not_intact(
        _reseal(evidence, parameter_bounds=(widened, *evidence.parameter_bounds[1:])),
        "field_mismatch:parameter_bounds_digest",
    )


# --- bias proofs -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(EdgeBiasProofKind))
def test_missing_bias_proof_never_verifies(kind: EdgeBiasProofKind) -> None:
    evidence = _sealed()
    remaining = tuple(proof for proof in evidence.bias_proofs if proof.proof_kind is not kind)
    _assert_not_intact(_reseal(evidence, bias_proofs=remaining), "field_mismatch:bias_proofs")
    _assert_not_intact(replace(evidence, bias_proofs=remaining), "self_digest_mismatch", "field_mismatch:bias_proofs")


def test_forged_proof_outcome_or_limitation_never_verifies() -> None:
    evidence = prereg(survivorship_claim_scope="edge_family_cross_section")
    lookahead, repaint, survivorship = evidence.bias_proofs
    promoted = replace(
        survivorship,
        outcome=EdgeBiasProofOutcome.PROVEN,
        checks=tuple(replace(item, outcome=EdgeBiasProofOutcome.PROVEN) for item in survivorship.checks),
    )
    _assert_not_intact(_reseal(evidence, bias_proofs=(lookahead, repaint, promoted)), "field_mismatch:bias_proofs")
    unlimited = replace(_sealed().bias_proofs[2], limitations=())
    sealed = _sealed()
    _assert_not_intact(_reseal(sealed, bias_proofs=(*sealed.bias_proofs[:2], unlimited)), "field_mismatch:bias_proofs")


def test_unproven_external_fact_is_needs_external_facts_and_governance_cannot_discharge_it() -> None:
    evidence = prereg(survivorship_claim_scope=EdgeSurvivorshipClaimScope.EDGE_FAMILY_CROSS_SECTION)
    _assert_receipt_invariants(evidence)
    assert evidence.approval == approval_for(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert evidence.verdict_reason_codes == (
        _code(
            "bias_proof_needs_external_facts:survivorship:point_in_time_universe_membership_authority:"
            "edge_family:funding_basis_carry"
        ),
    )
    survivorship = evidence.bias_proofs[2]
    assert survivorship.outcome is EdgeBiasProofOutcome.NEEDS_EXTERNAL_FACTS
    assert survivorship.limitations == ("point_in_time_universe_membership_authority_unavailable",)
    assert evidence.preregistration_sealed is False


_UNDECLARED_FUNDING_CODES = {
    _code("bias_proof_failed:lookahead:required_input_declared_by_admitted_strategy_spec:funding_rate"),
    _code("bias_proof_failed:repaint:required_input_declared_by_admitted_strategy_spec:funding_rate"),
}


@pytest.mark.parametrize("chain", [_mark_price_chain, _undeclared_funding_chain])
def test_profile_input_not_declared_by_the_admitted_spec_never_seals(chain) -> None:
    """Regression: manifest data the admitted spec never declared is not admissible profile input.

    ``_undeclared_funding_chain`` is the dual-series case: the manifest carries a valid final funding series, but the
    spec declares only mark prices and the approved binding maps that element onto the funding profile.
    """

    intake, admission, binding = chain()
    evidence = prereg(admission=admission, binding=binding, intake=intake)
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert set(evidence.verdict_reason_codes) == _UNDECLARED_FUNDING_CODES
    assert evidence.preregistration_sealed is False
    assert [proof.outcome for proof in evidence.bias_proofs] == [
        EdgeBiasProofOutcome.FAILED,
        EdgeBiasProofOutcome.FAILED,
        EdgeBiasProofOutcome.PROVEN,
    ]
    lookahead, repaint, _ = evidence.bias_proofs
    cited = {item.subject for proof in (lookahead, repaint) for item in proof.checks}
    assert "funding-final" not in cited


def test_profile_input_declared_by_the_spec_seals_even_with_extra_declared_data() -> None:
    intake, admission, binding = _chain_with_series(
        (_series("funding-final", "funding_rate"), _series("mark-final", "mark_price")), ("funding_rate", "mark_price")
    )
    evidence = prereg(admission=admission, binding=binding, intake=intake)
    _assert_receipt_invariants(evidence)
    assert evidence.preregistration_sealed is True
    lookahead = evidence.bias_proofs[0]
    assert ("input_series_finalized_only", "funding-final") in {
        (item.check_id, item.subject) for item in lookahead.checks
    }
    assert "mark-final" not in {item.subject for item in lookahead.checks}


def test_ambiguous_input_source_fails_so_no_source_can_be_chosen_after_results() -> None:
    intake, admission, binding = _two_source_chain()
    assert (admission.advances, binding.advances) == (True, True)
    evidence = prereg(admission=admission, binding=binding, intake=intake)
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert evidence.verdict_reason_codes == (
        _code(
            f"bias_proof_failed:lookahead:required_input_source_unambiguous_for_instrument:funding_rate:{support.BTC}"
        ),
    )
    single_intake, single_admission, single_binding = _chain_with_series(
        (_series("funding-final", "funding_rate"),), ("funding_rate",)
    )
    single = prereg(admission=single_admission, binding=single_binding, intake=single_intake)
    assert single.preregistration_sealed is True


def test_unrecognized_decision_schedule_cannot_be_proven_point_in_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ef5_module, "_POINT_IN_TIME_VISIBLE_DECISION_SCHEDULES", frozenset())
    evidence = prereg()
    subject = "final_funding_record_max_available_finalized.v1"
    assert set(evidence.verdict_reason_codes) == {
        _code(f"bias_proof_failed:lookahead:decision_schedule_point_in_time_visible:{subject}"),
        _code(f"bias_proof_failed:repaint:decision_schedule_point_in_time_visible:{subject}"),
    }
    assert evidence.preregistration_sealed is False


def test_verdict_precedence_fail_then_external_then_governance() -> None:
    both = prereg(
        survivorship_claim_scope="edge_family_cross_section",
        feature_ids=(FEATURE, "open_interest_trend"),
        approve=False,
    )
    assert both.gate_verdict is EdgeGateVerdict.FAIL
    external = prereg(survivorship_claim_scope="edge_family_cross_section", approve=False)
    assert external.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert _code("preregistration_approval_missing") in external.verdict_reason_codes


# --- governance approval -----------------------------------------------------------------------------------------------


def test_missing_approval_needs_governance() -> None:
    evidence = prereg(approve=False)
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == (_code("preregistration_approval_missing"),)
    assert evidence.preregistration_sealed is False


@pytest.mark.parametrize("name", COMMITMENTS)
def test_copied_approval_with_any_changed_commitment_needs_governance(name: str) -> None:
    evidence = prereg(approval=approval_for(_sealed(), **{f"approved_{name}": "0" * 64}))
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == (_code(f"preregistration_approval_{name}_mismatch"),)


def test_approval_commits_to_every_reuse_sensitive_authority() -> None:
    approved = {field.name for field in fields(EdgePreregistrationApproval) if field.name.startswith("approved_")}
    assert approved == {f"approved_{name}" for name in COMMITMENTS}


@pytest.mark.parametrize(
    ("approval", "code"),
    [
        ("approved", "approval_malformed"),
        (object.__new__(EdgePreregistrationApproval), "approval_reference_invalid"),
        (lambda evidence: approval_for(evidence, approval_reference=""), "approval_reference_invalid"),
        (
            lambda evidence: approval_for(evidence, approval_reference="borsa-committee"),
            "bist_scope_leakage:approval_reference",
        ),
        (lambda evidence: approval_for(evidence, approval_digest="A" * 64), "approval_digest_invalid"),
        (
            lambda evidence: approval_for(evidence, approved_feature_set_digest="xyz"),
            "approved_feature_set_digest_invalid",
        ),
    ],
)
def test_malformed_approval_is_a_construction_error(approval: object, code: str) -> None:
    candidate = approval(_sealed()) if callable(approval) else approval
    with pytest.raises(EdgeLeakageBiasEvidenceError) as excinfo:
        prereg(approval=candidate)
    assert str(excinfo.value) == _code(code)


# --- seal and structural non-claims ------------------------------------------------------------------------------------


def test_preregistration_seal_and_verdict_cannot_be_caller_forced() -> None:
    signature = set(inspect.signature(build_edge_leakage_bias_evidence).parameters)
    assert not signature & {
        "status",
        "gate_verdict",
        "advances",
        "preregistration_sealed",
        "multiple_testing_count",
        "registered_parameter_assignment_digests",
        "bias_proofs",
        *COMMITMENTS[5:],
    }
    pending = prereg(approve=False)
    _assert_not_intact(_reseal(pending, preregistration_sealed=True), "field_mismatch:preregistration_sealed")
    forced = _reseal(
        pending,
        preregistration_sealed=True,
        advances=True,
        gate_verdict=EdgeGateVerdict.PASS,
        verdict_reason_codes=(),
    )
    _assert_not_intact(forced, "field_mismatch:gate_verdict", "field_mismatch:advances")


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    names = {name for name, _ in EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS}
    defaults = {field.name: field.default for field in fields(EdgeLeakageBiasEvidence) if field.name in names}
    assert defaults == dict(EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS)
    assert names == ({name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS} - {"preregistration_sealed"}) | {
        "pbo_passed",
        "stress_passed",
        "walk_forward_evaluated",
        "performance_metrics_computed",
    }
    assert not names & set(inspect.signature(build_edge_leakage_bias_evidence).parameters)


@pytest.mark.parametrize("flag", [name for name, _ in EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    default = dict(EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS)[flag]
    _assert_not_intact(_reseal(_sealed(), **{flag: not default}), f"field_mismatch:{flag}")


def test_no_field_or_verdict_implies_admission_ranking_or_selection() -> None:
    names = [field.name for field in fields(EdgeLeakageBiasEvidence)]
    assert [name for name in names if "admit" in name] == ["candidate_admitted_to_paper"]
    assert not [name for name in names if any(token in name for token in ("rank", "select", "best", "winner"))]
    evidence = _sealed()
    assert evidence.candidate_admitted_to_paper is False
    assert (evidence.pbo_passed, evidence.stress_passed, evidence.walk_forward_evaluated) == (False, False, False)
    assert (evidence.performance_data_consumed, evidence.oos_evidence_consumed) == (False, False)


def test_performance_artifacts_cannot_enter_the_preregistration() -> None:
    intake, _, admission, binding = _base()
    foreign = object.__new__(HistoricalWalkForwardMetricsResult)
    base = arguments_for(admission, binding, intake)
    cases = [
        ({"executable_binding": foreign}, "executable_binding_malformed"),
        ({"variants": (foreign,)}, "variant_malformed"),
        ({"parameter_bounds": (foreign,)}, "parameter_bound_malformed"),
        ({"approval": foreign}, "approval_malformed"),
    ]
    for overrides, code in cases:
        with pytest.raises(EdgeLeakageBiasEvidenceError) as excinfo:
            build_edge_leakage_bias_evidence(admission, **{**base, **overrides})  # type: ignore[arg-type]
        assert str(excinfo.value) == _code(code)
    with pytest.raises(EdgeLeakageBiasEvidenceError):
        build_edge_leakage_bias_evidence(foreign, **base)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_edge_leakage_bias_evidence(admission, **base, walk_forward_metrics=foreign)  # type: ignore[call-arg]


# --- construction errors -----------------------------------------------------------------------------------------------


def _bound(**changes: object) -> tuple[EdgeParameterSearchBound, ...]:
    return (replace(bounds()[0], **changes), *bounds()[1:])


def _variant(**changes: object) -> tuple[EdgeInputVariant, ...]:
    return (replace(variants()[0], **changes), *variants()[1:])


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"preregistration_id": ""}, "preregistration_id_invalid"),
        ({"preregistration_id": "live-prereg"}, "forbidden_scope_token:preregistration_id"),
        ({"preregistration_id": "bist-prereg"}, "bist_scope_leakage:preregistration_id"),
        ({"preregistration_id": "scheduler_run"}, "forbidden_scope_token:preregistration_id"),
        ({"correlation_id": " corr-1"}, "correlation_id_invalid"),
        ({"expected_root_intake_digest": "A" * 64}, "root_intake_digest_invalid"),
        ({"feature_ids": FEATURE}, "feature_ids_malformed"),
        ({"feature_ids": (FEATURE, FEATURE)}, "feature_id_duplicate"),
        ({"feature_ids": ("",)}, "feature_id_invalid"),
        ({"feature_ids": ("bist30_basis",)}, "bist_scope_leakage:feature_id"),
        ({"parameter_bounds": None}, "parameter_bounds_malformed"),
        ({"parameter_bounds": ("entry_threshold",)}, "parameter_bound_malformed"),
        ({"parameter_bounds": (*bounds(), bounds()[0])}, "parameter_bound_duplicate"),
        ({"parameter_bounds": _bound(parameter_id="Entry_Threshold")}, "parameter_bound_id_invalid"),
        ({"parameter_bounds": _bound(treatment="grid")}, "parameter_bound_treatment_invalid"),
        ({"parameter_bounds": _bound(values=ENTRY_LOW)}, "parameter_bound_values_malformed"),
        ({"parameter_bounds": _bound(values=())}, "parameter_bound_values_empty"),
        ({"parameter_bounds": _bound(values=(ENTRY_LOW, ENTRY_LOW))}, "parameter_bound_value_duplicate"),
        ({"parameter_bounds": _bound(treatment="fixed")}, "parameter_bound_treatment_inconsistent"),
        ({"parameter_bounds": _bound(values=(ENTRY_LOW,))}, "parameter_bound_treatment_inconsistent"),
        ({"parameter_bounds": _bound(values=(ENTRY_LOW, 1))}, "parameter_value_invalid"),
        ({"parameter_bounds": _bound(values=(ENTRY_LOW, " 0.1"))}, "parameter_value_invalid"),
        ({"parameter_bounds": _bound(values=(ENTRY_LOW, "9" * 129))}, "parameter_value_invalid"),
        ({"parameter_bounds": _bound(values=(ENTRY_LOW, "live"))}, "forbidden_scope_token:parameter_value"),
        ({"variants": None}, "variants_malformed"),
        ({"variants": (assignment(),)}, "variant_malformed"),
        ({"variants": _variant(variant_id="Variant-1")}, "variant_id_invalid"),
        ({"variants": _variant(variant_id="kap")}, "bist_scope_leakage:variant_id"),
        ({"variants": _variant(variant_id="variant-2")}, "variant_id_duplicate"),
        (
            {"variants": (*variants(), EdgeInputVariant("variant-9", tuple(reversed(assignment()))))},
            "variant_assignment_duplicate",
        ),
        (
            {"variants": _variant(parameter_assignment={"entry_threshold": ENTRY_LOW})},
            "variant_parameter_assignment_malformed",
        ),
        (
            {"variants": _variant(parameter_assignment=(("entry_threshold", ENTRY_LOW),))},
            "variant_parameter_assignment_entry_malformed",
        ),
        (
            {"variants": _variant(parameter_assignment=(*assignment(), ProfileParameterAssignment("unit_size", UNIT)))},
            "variant_parameter_duplicate",
        ),
        ({"variants": _variant(parameter_assignment=())}, "variant_parameter_assignment_empty"),
        (
            {"variants": _variant(parameter_assignment=(object.__new__(ProfileParameterAssignment),))},
            "variant_parameter_id_invalid",
        ),
        ({"survivorship_claim_scope": "global"}, "survivorship_claim_scope_invalid"),
        ({"survivorship_claim_scope": None}, "survivorship_claim_scope_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeLeakageBiasEvidenceError) as excinfo:
        prereg(approve=False, **overrides)
    assert str(excinfo.value) == _code(code)


# --- verifier totality, parser strictness and round trips --------------------------------------------------------------


def _corrupted(**changes: object) -> EdgeLeakageBiasEvidence:
    copy = replace(_sealed())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    -1,
    "evidence",
    object(),
    {},
    [],
    b"\x00",
    edge_leakage_bias_evidence_to_dict(_sealed()),
    _base()[2],
    _base()[3],
    object.__new__(EdgeLeakageBiasEvidence),
    _corrupted(bias_proofs=None),
    _corrupted(bias_proofs=("lookahead",)),
    _corrupted(registered_variants=None),
    _corrupted(registered_variants=(object(),)),
    _corrupted(parameter_bounds=("entry_threshold",)),
    _corrupted(feature_ids=None),
    _corrupted(multiple_testing_count="4"),
    _corrupted(multiple_testing_count=2**70),
    _corrupted(survivorship_claim_scope="global"),
    _corrupted(approval=object()),
    _corrupted(predecessor_binding=object.__new__(EdgeAuthorityBinding)),
    _corrupted(executable_binding=EdgeAuthorityBinding(snapshot_json="{", expected_digest="a" * 64)),
    _corrupted(root_intake_digest=None),
    _corrupted(preregistration_id="prereg scheduler"),
    _corrupted(status="READY"),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    _assert_not_intact(artifact)


def _str_alias_cases() -> list[dict[str, object]]:
    evidence = _sealed()
    lookahead, repaint, survivorship = evidence.bias_proofs
    return [
        {"status": "READY"},
        {"gate_verdict": "PASS"},
        {"survivorship_claim_scope": "pinned_instrument_universe"},
        {"bias_proofs": (replace(lookahead, proof_kind="lookahead"), repaint, survivorship)},
        {"bias_proofs": (replace(lookahead, outcome="PROVEN"), repaint, survivorship)},
        {
            "bias_proofs": (
                replace(lookahead, checks=(replace(lookahead.checks[0], outcome="PROVEN"), *lookahead.checks[1:])),
                repaint,
                survivorship,
            )
        },
        {
            "parameter_bounds": (
                replace(evidence.parameter_bounds[0], treatment="searched"),
                *evidence.parameter_bounds[1:],
            )
        },
    ]


@pytest.mark.parametrize("index", range(7))
def test_equal_comparing_str_enum_aliases_never_verify(index: int) -> None:
    alias = _corrupted(**_str_alias_cases()[index])
    assert alias == _sealed()
    verification = _assert_not_intact(alias)
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)
    with pytest.raises(EdgeLeakageBiasEvidenceError):
        edge_leakage_bias_evidence_to_dict(alias)


def _mutated_payload(path: tuple[object, ...], value: object) -> dict:
    payload = _payload(_sealed())
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
        (("status",), None),
        (("preregistration_sealed",), "true"),
        (("multiple_testing_count",), True),
        (("multiple_testing_count",), -1),
        (("multiple_testing_count",), "4"),
        (("multiple_testing_count",), 4.0),
        (("multiple_testing_count",), 2**63),
        (("bias_proofs", 0, "outcome"), "MAYBE"),
        (("bias_proofs", 0, "checks", 0, "subject"), 7),
        (("bias_proofs", 0, "extra"), "x"),
        (("bias_proofs", 0, "limitations"), _UNSET),
        (("registered_variants", 0, "parameter_assignment"), {}),
        (("registered_variants", 0, "parameter_assignment", 0, "value"), 1),
        (("parameter_bounds", 0, "treatment"), "grid"),
        (("parameter_bounds", 0, "values"), ENTRY_LOW),
        (("approval",), {}),
        (("approval", "approval_digest"), None),
        (("survivorship_claim_scope",), "global"),
        (("predecessor_binding", "snapshot"), {}),
        (("executable_binding", "snapshot", "coverage"), None),
        (("feature_ids",), FEATURE),
        (("pbo_passed",), 0),
        (("walk_forward_evaluated",), _UNSET),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    assert edge_leakage_bias_evidence_payload_is_well_formed(_mutated_payload(path, value)) is False


def _state_builders() -> dict[str, object]:
    return {
        "pass": _sealed,
        "fail_feature": lambda: prereg(feature_ids=(FEATURE, "open_interest_trend")),
        "fail_lookahead": lambda: prereg(
            admission=_mark_price_chain()[1], binding=_mark_price_chain()[2], intake=_mark_price_chain()[0]
        ),
        "needs_external_facts": lambda: prereg(survivorship_claim_scope="edge_family_cross_section"),
        "needs_governance_approval": lambda: prereg(approve=False),
        "pending_governance_input": lambda: prereg(parameter_bounds=(), variants=()),
        "rejected_root_splice": lambda: prereg(expected_root_intake_digest=_other_chain()[0].intake_digest),
        "rejected_binding_admission": lambda: prereg(binding=_other_chain()[3]),
        "rejected_binding_receipt": lambda: prereg(
            binding=bind.executable_binding(_base()[2], profile_id="funding_momentum.v1")
        ),
    }


@pytest.mark.parametrize("state", sorted(_state_builders()))
def test_every_builder_state_round_trips_through_the_verifier(state: str) -> None:
    evidence = _state_builders()[state]()  # type: ignore[operator]
    _assert_receipt_invariants(evidence)
    expected = EdgeEvidenceStatus.REJECTED if state.startswith("rejected") else EdgeEvidenceStatus.READY
    assert evidence.status is expected
    assert evidence.preregistration_sealed is (state == "pass")


def test_bindings_are_canonical_and_noncanonical_in_memory_bindings_never_verify() -> None:
    evidence = _sealed()
    for binding in (evidence.predecessor_binding, evidence.executable_binding):
        assert binding.snapshot_json == edge_canonical_json(json.loads(binding.snapshot_json))
    pretty = replace(
        evidence.executable_binding,
        snapshot_json=json.dumps(json.loads(evidence.executable_binding.snapshot_json), sort_keys=True, indent=1),
    )
    verification = verify_edge_leakage_bias_evidence(replace(evidence, executable_binding=pretty))
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- structural purity, performance firewall and single assembly path --------------------------------------------------

_FORBIDDEN_MODULES = (
    "math",
    "decimal",
    "fractions",
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
    "importlib",
    "pickle",
    "bist_core",
)
_FORBIDDEN_CALLS = frozenset(
    {
        "open",
        "Path",
        "float",
        "eval",
        "exec",
        "compile",
        "__import__",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
        "getenv",
        "print",
        "evaluate_strategy_executable_profile",
    }
)
_PERFORMANCE_TOKENS = (
    "sharpe",
    "expectancy",
    "profit_factor",
    "drawdown",
    "hit_rate",
    "pnl",
    "walk_forward",
    "pbo",
    "stress",
    "oos",
    "performance",
    "metric",
    "returns",
    "rank",
    "best_variant",
    "winner",
    "selected",
)


def _module_tree() -> ast.Module:
    return ast.parse(Path(ef5_module.__file__).read_text(encoding="utf-8"))


def _docstring_nodes(tree: ast.Module) -> set[int]:
    nodes = {id(tree.body[0].value)} if isinstance(tree.body[0], ast.Expr) else set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.body and isinstance(node.body[0], ast.Expr):
            nodes.add(id(node.body[0].value))
    return nodes


def _module_words(tree: ast.Module) -> list[str]:
    docstrings = _docstring_nodes(tree)
    words: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            words.append(node.id)
        elif isinstance(node, ast.Attribute):
            words.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            words.append(node.name)
        elif isinstance(node, ast.arg):
            words.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            words.append(node.arg)
        elif isinstance(node, ast.alias):
            words.append(node.name)
        elif isinstance(node, ast.Constant) and type(node.value) is str and id(node) not in docstrings:
            words.append(node.value)
    return words


def test_module_has_no_io_clock_randomness_float_or_dynamic_execution() -> None:
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
            assert node.attr not in {"environ", "system", "popen"}


def test_module_consumes_only_public_pre_performance_substrate() -> None:
    crypto_imports: dict[str, set[str]] = {}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core"):
            crypto_imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
    assert set(crypto_imports) == {
        "crypto_core.strategy.spec",
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_idea_intake_evidence",
        "crypto_core.validation.edge_source_packet_evidence",
        "crypto_core.validation.edge_strategy_spec_admission",
        "crypto_core.validation.strategy_executable_binding",
        "crypto_core.validation.strategy_executable_profiles",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}


def test_performance_firewall_module_names_no_performance_concept() -> None:
    allowed = {name for name, _ in EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS} | {"preregistration_sealed"}
    offending = sorted(
        {
            word
            for word in _module_words(_module_tree())
            if word not in allowed and any(token in word.lower() for token in _PERFORMANCE_TOKENS)
        }
    )
    assert offending == []


def _crypto_core_imports(module_name: str) -> set[str]:
    source = Path(importlib.import_module(module_name).__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
    return {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None and node.module.startswith("crypto_core")
    }


def test_performance_firewall_holds_for_the_whole_transitive_import_closure() -> None:
    closure: set[str] = set()
    pending = {ef5_module.__name__}
    while pending:
        name = pending.pop()
        closure.add(name)
        pending |= _crypto_core_imports(name) - closure
    closure.discard(ef5_module.__name__)
    offending = sorted(
        name
        for name in closure
        if any(
            token in name
            for token in ("historical_", "walk_forward", "pbo", "stress", "paper_", "stage4", "sharpe", "execution")
        )
    )
    assert offending == []
    assert "crypto_core.validation.edge_strategy_spec_admission" in closure


def test_builder_parameters_name_no_performance_or_authority_flag() -> None:
    parameters = set(inspect.signature(build_edge_leakage_bias_evidence).parameters)
    assert not [name for name in parameters if any(token in name for token in _PERFORMANCE_TOKENS)]
    assert "survivorship_claim_scope" in parameters
    assert inspect.signature(build_edge_leakage_bias_evidence).parameters["survivorship_claim_scope"].default is (
        inspect.Parameter.empty
    )


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    tree = _module_tree()
    constructor_calls = 0
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        constructor_calls += names.count("EdgeLeakageBiasEvidence")
    assert constructor_calls == 1
    assert "EdgeLeakageBiasEvidence" in calls_by_function["_assemble_evidence"]
    assert "_assemble_evidence" in calls_by_function["build_edge_leakage_bias_evidence"]
    assert "_assemble_evidence" in calls_by_function["_reassemble_evidence"]
