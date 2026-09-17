"""Tests for the StrategySpec → executable profile binding (DETERMINISTIC_HISTORICAL_SIGNAL_SPINE_V1, contract C)."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields, replace

import pytest

import crypto_core.validation.strategy_executable_binding as binding_module
import crypto_core.validation.strategy_executable_profiles as profiles_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
)
from crypto_core.validation.strategy_executable_binding import (
    STRATEGY_EXECUTABLE_BINDING_NON_CLAIM_FLAGS,
    StrategyExecutableBinding,
    StrategyExecutableBindingApproval,
    StrategyExecutableBindingError,
    StrategyExecutableCoverageEntry,
    build_strategy_executable_binding,
    strategy_executable_binding_digest,
    strategy_executable_binding_from_payload,
    strategy_executable_binding_payload_is_well_formed,
    strategy_executable_binding_to_dict,
    strategy_executable_coverage_digest,
    verify_strategy_executable_binding,
)
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    get_strategy_executable_profile,
    strategy_executable_profile_semantics_digest,
)
from tests.crypto_core.validation import test_historical_pit_dataset as support

_PREFIX = "strategy_executable_binding"

COVERAGE = (
    StrategyExecutableCoverageEntry(
        "entry_condition", "short_when_mean_final_funding_above_entry_threshold", ("entry_short_on_positive_mean",)
    ),
    StrategyExecutableCoverageEntry(
        "entry_condition",
        "long_when_mean_final_funding_below_negative_entry_threshold",
        ("entry_long_on_negative_mean",),
    ),
    StrategyExecutableCoverageEntry("exit_condition", "exit_on_mean_final_funding_sign_flip", ("exit_on_sign_flip",)),
    StrategyExecutableCoverageEntry(
        "exit_condition", "exit_when_abs_mean_final_funding_below_exit_threshold", ("exit_below_exit_threshold",)
    ),
    StrategyExecutableCoverageEntry(
        "invalidation_condition",
        "no_action_without_n_final_funding_settlements",
        ("invalidation_insufficient_final_history",),
    ),
    StrategyExecutableCoverageEntry(
        "feature_requirement", "final_funding_mean", ("feature_mean_last_n_final_funding_rates",)
    ),
    StrategyExecutableCoverageEntry("data_requirement", "funding_rate", ("data_final_funding_settlements",)),
    StrategyExecutableCoverageEntry(
        "kill_switch_trigger", "funding_flip_persistence", ("kill_triggers_not_evaluated_by_profile",)
    ),
    StrategyExecutableCoverageEntry(
        "kill_switch_trigger", "max_drawdown_breach", ("kill_triggers_not_evaluated_by_profile",)
    ),
    StrategyExecutableCoverageEntry("risk_cap", "max_leverage", ("sizing_fixed_unit_size",)),
)


def approval_for(admission, coverage=COVERAGE, **overrides: str) -> StrategyExecutableBindingApproval:
    arguments = {
        "approval_reference": "governance-binding-1",
        "approval_digest": "e" * 64,
        "approved_strategy_spec_digest": admission.strategy_spec_digest,
        "approved_profile_semantics_digest": get_strategy_executable_profile(
            PASSIVE_FUNDING_CARRY_V1
        ).profile_semantics_digest,
        "approved_coverage_digest": strategy_executable_coverage_digest(coverage),
    }
    arguments.update(overrides)
    return StrategyExecutableBindingApproval(**arguments)


def executable_binding(admission, coverage=COVERAGE, *, approve: bool = True, **overrides) -> StrategyExecutableBinding:
    arguments: dict[str, object] = {
        "expected_admission_digest": admission.admission_digest,
        "binding_id": "binding-1",
        "correlation_id": admission.correlation_id,
        "profile_id": PASSIVE_FUNDING_CARRY_V1,
        "profile_version": "1",
        "expected_profile_semantics_digest": get_strategy_executable_profile(
            PASSIVE_FUNDING_CARRY_V1
        ).profile_semantics_digest,
        "coverage": coverage,
        "approval": approval_for(admission, coverage) if approve else None,
    }
    arguments.update(overrides)
    return build_strategy_executable_binding(admission, **arguments)  # type: ignore[arg-type]


def _admission(**chain_kwargs: object):
    return support.chain(**chain_kwargs)[2]  # type: ignore[arg-type]


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(binding: StrategyExecutableBinding, **changes: object) -> StrategyExecutableBinding:
    changed = replace(binding, **changes)
    return replace(changed, binding_digest=strategy_executable_binding_digest(changed))


def _assert_receipt_invariants(binding: StrategyExecutableBinding) -> None:
    verification = verify_strategy_executable_binding(binding)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == binding.binding_digest
    assert strategy_executable_binding_from_payload(json.loads(verification.canonical_json)) == binding
    assert strategy_executable_binding_payload_is_well_formed(strategy_executable_binding_to_dict(binding)) is True
    assert binding.advances is (
        binding.status is EdgeEvidenceStatus.READY and binding.gate_verdict is EdgeGateVerdict.PASS
    )
    assert binding.semantic_equivalence_machine_proven is False
    if binding.status is EdgeEvidenceStatus.REJECTED:
        assert binding.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert binding.integrity_reason_codes
        assert binding.verdict_reason_codes == ()
    else:
        assert binding.integrity_reason_codes == ()


# --- outcomes -----------------------------------------------------------------------------------------------------------


def test_complete_approved_binding_is_ready_pass_and_binds_authenticated_identities() -> None:
    _, manifest, admission, _ = support.chain()
    binding = executable_binding(admission)
    _assert_receipt_invariants(binding)
    assert (binding.status, binding.gate_verdict, binding.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    profile = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    assert binding.admission_digest == admission.admission_digest
    assert binding.source_manifest_digest == manifest.source_packet_evidence_digest
    assert binding.strategy_spec_digest == admission.strategy_spec_digest
    assert (binding.strategy_id, binding.strategy_version) == ("passive-funding-carry", "1.0.0")
    assert binding.instrument_universe == (support.BTC,)
    assert binding.registered_profile_semantics_digest == profile.profile_semantics_digest
    assert binding.coverage_digest == strategy_executable_coverage_digest(COVERAGE)
    assert binding.approval == approval_for(admission)


def test_binding_is_deterministic_and_coverage_order_insensitive() -> None:
    admission = _admission()
    first = executable_binding(admission)
    second = executable_binding(admission, tuple(reversed(COVERAGE)))
    assert strategy_executable_binding_to_dict(first) == strategy_executable_binding_to_dict(second)


def test_missing_approval_needs_governance() -> None:
    binding = executable_binding(_admission(), approve=False)
    _assert_receipt_invariants(binding)
    assert binding.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert binding.verdict_reason_codes == (_code("approval_missing"),)


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"approved_strategy_spec_digest": "a" * 64}, "approval_strategy_spec_digest_mismatch"),
        ({"approved_profile_semantics_digest": "a" * 64}, "approval_profile_semantics_digest_mismatch"),
        ({"approved_coverage_digest": "a" * 64}, "approval_coverage_digest_mismatch"),
    ],
)
def test_approval_must_commit_to_exact_spec_profile_and_coverage(override: dict[str, str], code: str) -> None:
    admission = _admission()
    binding = executable_binding(admission, approval=approval_for(admission, **override))
    _assert_receipt_invariants(binding)
    assert binding.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert binding.verdict_reason_codes == (_code(code),)


def test_coverage_gap_is_ready_fail_and_dominates_missing_approval() -> None:
    admission = _admission()
    binding = executable_binding(admission, COVERAGE[:-1], approve=False)
    _assert_receipt_invariants(binding)
    assert (binding.status, binding.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.FAIL)
    assert set(binding.verdict_reason_codes) == {
        _code("spec_element_uncovered:risk_cap:max_leverage"),
        _code("profile_element_uncovered:sizing_fixed_unit_size"),
        _code("approval_missing"),
    }


def test_rejected_authorities_are_truthful_receipts() -> None:
    _, manifest, admission, _ = support.chain()
    unknown = executable_binding(admission, profile_id="passive_funding_carry.v2")
    wrong_version = executable_binding(admission, profile_version="2")
    wrong_digest = executable_binding(admission, expected_profile_semantics_digest="b" * 64)
    wrong_anchor = executable_binding(admission, expected_admission_digest=manifest.source_packet_evidence_digest)
    wrong_correlation = executable_binding(admission, correlation_id="corr-2")
    for binding, code in (
        (unknown, "profile_unknown"),
        (wrong_version, "profile_version_mismatch"),
        (wrong_digest, "profile_semantics_digest_mismatch"),
        (wrong_anchor, "admission_digest_mismatch"),
        (wrong_correlation, "admission_correlation_mismatch"),
    ):
        _assert_receipt_invariants(binding)
        assert binding.status is EdgeEvidenceStatus.REJECTED
        assert binding.integrity_reason_codes == (_code(code),)
    forged = executable_binding(replace(admission, admission_id="admission-forged"))
    assert forged.status is EdgeEvidenceStatus.REJECTED
    assert all(code.startswith(_code("admission_integrity_failure:")) for code in forged.integrity_reason_codes)


# --- attack matrix ------------------------------------------------------------------------------------------------------


def test_attack_same_strategy_id_with_changed_spec_digest_cannot_reuse_approval() -> None:
    original = _admission()
    changed = _admission(spec_changes={"latency_sensitivity": "medium"})
    assert (changed.strategy_id, changed.strategy_spec_digest != original.strategy_spec_digest) == (
        original.strategy_id,
        True,
    )
    binding = executable_binding(changed, approval=approval_for(original))
    assert binding.advances is False
    assert binding.verdict_reason_codes == (_code("approval_strategy_spec_digest_mismatch"),)


@pytest.mark.parametrize(
    ("spec_changes", "expected_codes"),
    [
        (
            {"feature_requirements": {"final_funding_mean": "last_n_final_settlements_v2"}},
            {"approval_strategy_spec_digest_mismatch"},
        ),
        (
            {
                "entry_conditions": [
                    "short_when_mean_final_funding_above_double_entry_threshold",
                    "long_when_mean_final_funding_below_negative_entry_threshold",
                ]
            },
            {
                "approval_strategy_spec_digest_mismatch",
                "coverage_spec_element_unknown:entry_condition:short_when_mean_final_funding_above_entry_threshold",
                "spec_element_uncovered:entry_condition:short_when_mean_final_funding_above_double_entry_threshold",
            },
        ),
        (
            {"exit_conditions": ["exit_on_mean_final_funding_sign_flip"]},
            {
                "approval_strategy_spec_digest_mismatch",
                "coverage_spec_element_unknown:exit_condition:exit_when_abs_mean_final_funding_below_exit_threshold",
            },
        ),
        ({"data_requirements": {"funding_rate": "1h"}}, {"approval_strategy_spec_digest_mismatch"}),
        (
            {"kill_switch_triggers": ["max_drawdown_breach"]},
            {
                "admission_not_advanced:FAIL",
                "approval_strategy_spec_digest_mismatch",
                "coverage_spec_element_unknown:kill_switch_trigger:funding_flip_persistence",
            },
        ),
    ],
)
def test_attack_changed_spec_semantics_never_advance_under_the_old_mapping_and_approval(
    spec_changes: dict[str, object], expected_codes: set[str]
) -> None:
    original = _admission()
    changed = _admission(spec_changes=spec_changes)
    binding = executable_binding(changed, approval=approval_for(original))
    _assert_receipt_invariants(binding)
    assert binding.status is EdgeEvidenceStatus.READY
    assert binding.advances is False
    assert {_code(code) for code in expected_codes} <= set(binding.verdict_reason_codes)


def test_attack_profile_constant_change_invalidates_existing_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    admission = _admission()
    binding = executable_binding(admission)
    profile = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    changed = replace(
        profile,
        semantic_elements=(replace(profile.semantic_elements[1], definition="Enter LONG at any negative mean."),)
        + profile.semantic_elements[2:]
        + profile.semantic_elements[:1],
    )
    sealed = replace(changed, profile_semantics_digest=strategy_executable_profile_semantics_digest(changed))
    monkeypatch.setitem(profiles_module._REGISTRY, PASSIVE_FUNDING_CARRY_V1, sealed)
    verification = verify_strategy_executable_binding(binding)
    assert verification.intact is False
    assert _code("field_mismatch:integrity_reason_codes") in verification.reason_codes
    rebuilt = executable_binding(admission, expected_profile_semantics_digest=profile.profile_semantics_digest)
    assert rebuilt.integrity_reason_codes == (_code("profile_semantics_digest_mismatch"),)


def test_attack_profile_id_substitution_is_rejected() -> None:
    binding = executable_binding(_admission())
    substituted = _reseal(binding, profile_id="funding_momentum.v1")
    verification = verify_strategy_executable_binding(substituted)
    assert verification.intact is False
    assert _code("field_mismatch:integrity_reason_codes") in verification.reason_codes
    assert _code("field_mismatch:status") in verification.reason_codes


def test_attack_missing_coverage_entry_and_omitted_executable_element_fail() -> None:
    admission = _admission()
    without_invalidation = tuple(entry for entry in COVERAGE if entry.spec_element_kind != "invalidation_condition")
    missing = executable_binding(admission, without_invalidation)
    assert missing.gate_verdict is EdgeGateVerdict.FAIL
    assert {
        _code("spec_element_uncovered:invalidation_condition:no_action_without_n_final_funding_settlements"),
        _code("profile_element_uncovered:invalidation_insufficient_final_history"),
    } <= set(missing.verdict_reason_codes)
    rerouted = tuple(
        replace(entry, profile_element_ids=("exit_below_exit_threshold",))
        if entry.spec_element_ref == "exit_on_mean_final_funding_sign_flip"
        else entry
        for entry in COVERAGE
    )
    omitted = executable_binding(admission, rerouted)
    assert omitted.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("profile_element_uncovered:exit_on_sign_flip") in omitted.verdict_reason_codes


def test_attack_kind_mismatch_and_unknown_elements_fail() -> None:
    admission = _admission()
    mismatched = tuple(
        replace(entry, profile_element_ids=("entry_long_on_negative_mean", "exit_on_sign_flip"))
        if entry.spec_element_ref == "exit_on_mean_final_funding_sign_flip"
        else entry
        for entry in COVERAGE
    )
    binding = executable_binding(admission, mismatched)
    assert (
        _code("coverage_kind_mismatch:exit_condition:exit_on_mean_final_funding_sign_flip:entry_long_on_negative_mean")
        in binding.verdict_reason_codes
    )
    invented = COVERAGE + (
        StrategyExecutableCoverageEntry("entry_condition", "buy_the_dip", ("entry_long_with_leverage",)),
    )
    binding = executable_binding(admission, invented)
    assert {
        _code("coverage_spec_element_unknown:entry_condition:buy_the_dip"),
        _code("coverage_profile_element_unknown:entry_long_with_leverage"),
    } <= set(binding.verdict_reason_codes)


def test_attack_arbitrary_caller_profile_or_callable_is_impossible() -> None:
    admission = _admission()
    profile = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    for candidate in (profile, lambda *args: None, len, None, PASSIVE_FUNDING_CARRY_V1.upper()):
        with pytest.raises(StrategyExecutableBindingError, match="profile_id_invalid"):
            executable_binding(admission, profile_id=candidate)
    parameters = set(inspect.signature(build_strategy_executable_binding).parameters)
    assert not parameters & {"profile", "implementation", "callable", "decide", "rule"}


# --- malformed input ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"coverage": ()}, "coverage_empty"),
        ({"coverage": None}, "coverage_malformed"),
        ({"coverage": ({"spec_element_kind": "entry_condition"},)}, "coverage_entry_malformed"),
        ({"coverage": COVERAGE + COVERAGE[:1]}, "coverage_entry_duplicate"),
        (
            {"coverage": (StrategyExecutableCoverageEntry("strategy_family", "carry", ("sizing_fixed_unit_size",)),)},
            "coverage_spec_element_kind_invalid",
        ),
        (
            {"coverage": (StrategyExecutableCoverageEntry("risk_cap", "max_leverage", ()),)},
            "coverage_profile_element_ids_invalid",
        ),
        ({"approval": "approved"}, "approval_malformed"),
        ({"binding_id": "binding live"}, "binding_id"),
        ({"expected_profile_semantics_digest": "A" * 64}, "expected_profile_semantics_digest_invalid"),
        ({"expected_admission_digest": None}, "admission_expected_digest_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(StrategyExecutableBindingError, match=code):
        executable_binding(_admission(), **overrides)


def test_foreign_admission_object_is_a_construction_error() -> None:
    _, manifest, admission, _ = support.chain()
    for foreign in (manifest, None, strategy_executable_binding_to_dict(executable_binding(admission))):
        with pytest.raises(StrategyExecutableBindingError, match="admission_malformed"):
            build_strategy_executable_binding(
                foreign,  # type: ignore[arg-type]
                expected_admission_digest=admission.admission_digest,
                binding_id="binding-1",
                correlation_id="corr-1",
                profile_id=PASSIVE_FUNDING_CARRY_V1,
                profile_version="1",
                expected_profile_semantics_digest="a" * 64,
                coverage=COVERAGE,
            )


# --- totality and parity ------------------------------------------------------------------------------------------------


def _corrupted(**changes: object) -> StrategyExecutableBinding:
    copy = replace(executable_binding(_admission()))
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    3,
    "binding",
    b"binding",
    {},
    object(),
    object.__new__(StrategyExecutableBinding),
    _corrupted(coverage=None),
    _corrupted(coverage=({"spec_element_kind": "entry_condition"},)),
    _corrupted(approval="approved"),
    _corrupted(admission_binding=None),
    _corrupted(instrument_universe="BTC-PERPETUAL"),
    _corrupted(gate_verdict="ACCEPTED"),
    _corrupted(semantic_equivalence_machine_proven=True),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify_strategy_executable_binding(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


def test_foreign_dataclasses_are_not_bindings() -> None:
    _, manifest, admission, registry = support.chain()
    for foreign in (admission, manifest, support.pit_dataset(manifest, registry), approval_for(admission)):
        assert verify_strategy_executable_binding(foreign).intact is False


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), "ACCEPTED"),
        (("coverage",), {}),
        (("coverage", 0, "spec_element_kind"), "strategy_family"),
        (("coverage", 0, "profile_element_ids"), "entry_short_on_positive_mean"),
        (("approval",), {"approval_reference": "governance-binding-1"}),
        (("admission_binding",), None),
        (("instrument_universe",), "BTC-PERPETUAL"),
        (("semantic_equivalence_machine_proven",), "false"),
    ],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = strategy_executable_binding_to_dict(executable_binding(_admission()))
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert strategy_executable_binding_payload_is_well_formed(payload) is False


def test_every_builder_state_round_trips_through_the_verifier() -> None:
    admission = _admission()
    for binding in (
        executable_binding(admission),
        executable_binding(admission, approve=False),
        executable_binding(admission, COVERAGE[:3]),
        executable_binding(admission, profile_id="passive_funding_carry.v2"),
        executable_binding(_admission(spec_changes={"kill_switch_triggers": ["max_drawdown_breach"]})),
    ):
        _assert_receipt_invariants(binding)


# --- non-claims and purity ----------------------------------------------------------------------------------------------


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(STRATEGY_EXECUTABLE_BINDING_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    assert flags["semantic_equivalence_machine_proven"] is False
    defaults = {field.name: field.default for field in fields(StrategyExecutableBinding) if field.name in flags}
    assert defaults == flags
    assert not set(flags) & set(inspect.signature(build_strategy_executable_binding).parameters)


@pytest.mark.parametrize("flag", ["semantic_equivalence_machine_proven", "edge_proven", "orders_created"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify_strategy_executable_binding(_reseal(executable_binding(_admission()), **{flag: True}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_module_is_pure_and_consumes_only_public_substrate() -> None:
    support.assert_module_is_pure(
        binding_module,
        {
            "crypto_core.strategy.spec",
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.edge_strategy_spec_admission",
            "crypto_core.validation.strategy_executable_profiles",
        },
    )


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    support.assert_single_assembly_path(
        binding_module,
        "StrategyExecutableBinding",
        "_assemble_binding",
        "build_strategy_executable_binding",
        "_reassemble_binding",
    )
