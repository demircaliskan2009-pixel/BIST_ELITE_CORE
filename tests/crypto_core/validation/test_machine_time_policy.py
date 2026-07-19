"""Tests for the MT-2 abstract machine-time policy artifact (pre-Deep-Research-safe, trust-boundary hardened)."""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Mapping as _AbcMapping
from dataclasses import FrozenInstanceError, fields, replace
from enum import Enum
from pathlib import Path

import pytest

import crypto_core.validation.machine_time_policy as policy_module
from crypto_core.validation.machine_time_policy import (
    MachineTimePolicy,
    MachineTimePolicyError,
    MachineTimePolicyStatus,
    build_machine_time_policy,
    machine_time_policy_digest,
    machine_time_policy_to_dict,
)

_DAY_NS = 86_400_000_000_000
_HEX_B = "b" * 64

_EXPECTED_FIELD_ORDER = (
    "schema_version",
    "policy_version",
    "status",
    "ready",
    "policy_id",
    "correlation_id",
    "sandwich_model",
    "required_roles",
    "not_before_verification_policy",
    "not_after_verification_policy",
    "quorum_model",
    "independence_policy_id",
    "digest_commitment_policy",
    "proof_encoding_policy",
    "offline_verification_policy_id",
    "utc_day_identity_policy_id",
    "proof_replay_policy_id",
    "spacing_policy",
    "source_registry_policy_id",
    "min_quorum_per_role",
    "min_machine_proven_day_count",
    "utc_day_ns",
    "approved_quorum_per_role",
    "approved_required_machine_proven_day_count",
    "approved_min_inter_day_spacing_ns",
    "approved_max_inter_day_spacing_ns",
    "approval_reference",
    "approval_digest",
    "policy_approved",
    "source_registry_digest",
    "reason_codes",
    "metadata",
    "policy_digest",
    "paper_only",
    "policy_only",
    "abstract_pre_deep_research",
    "independent_source_classes_required",
    "role_separation_required",
    "exact_digest_commitment_required",
    "deterministic_offline_verification_required",
    "network_fetch_in_builder_forbidden",
    "distinct_sandwich_per_utc_day_required",
    "proof_reuse_across_days_forbidden",
    "consecutive_utc_days_required",
    "interval_consistency_required",
    "concrete_source_registry_required",
    "concrete_source_registry_bound",
    "source_registry_consumed",
    "deep_research_facts_bound",
    "concrete_sources_bound",
    "machine_time_anchor_verified",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "injected_time_accepted_as_proof",
    "attested_time_accepted_as_proof",
    "external_proofs_consumed",
    "operational_days_consumed",
    "machine_proven_days_consumed",
    "network_fetch_performed",
    "real_wall_clock_used",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "private_api_ready",
    "live_api_called",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "edge_proven",
    "profitability_proven",
)

_ALWAYS_TRUE = (
    "paper_only",
    "policy_only",
    "abstract_pre_deep_research",
    "independent_source_classes_required",
    "role_separation_required",
    "exact_digest_commitment_required",
    "deterministic_offline_verification_required",
    "network_fetch_in_builder_forbidden",
    "distinct_sandwich_per_utc_day_required",
    "proof_reuse_across_days_forbidden",
    "consecutive_utc_days_required",
    "interval_consistency_required",
    "concrete_source_registry_required",
)

_ALWAYS_FALSE = (
    "concrete_source_registry_bound",
    "source_registry_consumed",
    "deep_research_facts_bound",
    "concrete_sources_bound",
    "machine_time_anchor_verified",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "injected_time_accepted_as_proof",
    "attested_time_accepted_as_proof",
    "external_proofs_consumed",
    "operational_days_consumed",
    "machine_proven_days_consumed",
    "network_fetch_performed",
    "real_wall_clock_used",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "private_api_ready",
    "live_api_called",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "edge_proven",
    "profitability_proven",
)

_PINNED_STRING_MISMATCHES = (
    ("sandwich_model", "sandwich_model_mismatch"),
    ("not_before_verification_policy", "not_before_verification_policy_mismatch"),
    ("not_after_verification_policy", "not_after_verification_policy_mismatch"),
    ("quorum_model", "quorum_model_mismatch"),
    ("independence_policy_id", "independence_policy_mismatch"),
    ("digest_commitment_policy", "digest_commitment_policy_mismatch"),
    ("proof_encoding_policy", "proof_encoding_policy_mismatch"),
    ("offline_verification_policy_id", "offline_verification_policy_mismatch"),
    ("utc_day_identity_policy_id", "utc_day_identity_policy_mismatch"),
    ("proof_replay_policy_id", "proof_replay_policy_mismatch"),
    ("spacing_policy", "spacing_policy_mismatch"),
    ("source_registry_policy_id", "source_registry_policy_mismatch"),
)
_PINNED_STRING_FIELD_NAMES = tuple(name for name, _ in _PINNED_STRING_MISMATCHES)


# --------------------------------------------------------------------------------------------------
# Adversarial value classes
# --------------------------------------------------------------------------------------------------


class _LyingStr(str):
    """JSON-serializable ``str`` subclass whose equality always lies — type-distinct from exact ``str``."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


class _LyingInt(int):
    """JSON-serializable ``int`` subclass whose equality always lies — type-distinct from exact ``int``."""

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = int.__hash__


class _RaisingEq:
    """Equality-raising object: any comparison before the exact-type proof would crash the builder."""

    def __eq__(self, other: object) -> bool:  # pragma: no cover - must never be invoked
        raise AssertionError("custom equality on an unvalidated caller value must never be invoked")

    __hash__ = None  # type: ignore[assignment]


class _EqualityTrue:
    """Equality-true object with a plausible value — only an exact-type gate rejects it."""

    def __eq__(self, other: object) -> bool:
        return True

    __hash__ = None  # type: ignore[assignment]


class _RaisingHash:
    """Hash-raising object: any set/dict construction over it before the type proof would crash."""

    def __hash__(self) -> int:  # pragma: no cover - must never be invoked
        raise AssertionError("hashing an unvalidated caller value must never be invoked")


class _RaisingOrder:
    """Ordering-raising object: any sort over it before the type proof would crash."""

    def __lt__(self, other: object) -> bool:  # pragma: no cover - must never be invoked
        raise AssertionError("ordering an unvalidated caller value must never be invoked")


class _ForeignEnum(str, Enum):
    """A foreign str-enum member — ``type() is str`` is False, so the exact-type gate rejects it."""

    SANDWICH = "not_before_beacon_and_not_after_signed_timestamp_sandwich.v1"


class _RolesTupleSubclass(tuple):
    """A ``tuple`` subclass — type-distinct from an exact ``tuple``, rejected by the exact-type gate."""

    __slots__ = ()


_SAFELY_MALFORMED = (
    None,
    True,
    7,
    2.5,
    ["not", "a", "string"],
    {"not": "a string"},
    _LyingStr("forged.value.v1"),
    _RaisingEq(),
    _EqualityTrue(),
    _RaisingHash(),
    _RaisingOrder(),
    _ForeignEnum.SANDWICH,
)
_SAFELY_MALFORMED_IDS = [
    "none",
    "bool",
    "int",
    "float",
    "list",
    "mapping",
    "lying_str_subclass",
    "equality_raising",
    "equality_true",
    "hash_raising",
    "ordering_raising",
    "foreign_enum",
]


def _rc(code: str) -> str:
    return f"machine_time_policy:{code}"


def _build(**overrides: object) -> MachineTimePolicy:
    payload: dict[str, object] = {
        "policy_id": "mt2-policy-1",
        "correlation_id": "corr-1",
        "approved_quorum_per_role": 2,
        "approved_required_machine_proven_day_count": 30,
        "approved_min_inter_day_spacing_ns": _DAY_NS // 2,
        "approved_max_inter_day_spacing_ns": _DAY_NS * 2,
        "approval_reference": "gov-mt2-1",
        "approval_digest": _HEX_B,
        "policy_approved": True,
        "metadata": {"purpose": "abstract machine-time sandwich policy"},
    }
    payload.update(overrides)
    return build_machine_time_policy(**payload)  # type: ignore[arg-type]


def _assert_serializable_rejected(policy: MachineTimePolicy) -> None:
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert policy.reason_codes
    payload = machine_time_policy_to_dict(policy)
    assert payload["status"] == "POLICY_REJECTED"
    json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert machine_time_policy_digest(policy) == policy.policy_digest
    assert policy.machine_time_origin_proven is False
    assert policy.timestamp_origin_proven is False
    assert policy.concrete_source_registry_bound is False


# --------------------------------------------------------------------------------------------------
# Public contract
# --------------------------------------------------------------------------------------------------


def test_public_api_order_exact() -> None:
    assert policy_module.__all__ == [
        "MachineTimePolicyError",
        "MachineTimePolicyStatus",
        "MachineTimePolicy",
        "build_machine_time_policy",
        "machine_time_policy_to_dict",
        "machine_time_policy_digest",
    ]
    assert [status.value for status in MachineTimePolicyStatus] == ["POLICY_READY", "POLICY_REJECTED"]


def test_dataclass_field_order_exact() -> None:
    assert tuple(field.name for field in fields(MachineTimePolicy)) == _EXPECTED_FIELD_ORDER
    assert len(_EXPECTED_FIELD_ORDER) == 78


def test_builder_signature_exact() -> None:
    parameters = inspect.signature(build_machine_time_policy).parameters
    assert list(parameters) == [
        "policy_id",
        "correlation_id",
        "approved_quorum_per_role",
        "approved_required_machine_proven_day_count",
        "approved_min_inter_day_spacing_ns",
        "approved_max_inter_day_spacing_ns",
        "approval_reference",
        "approval_digest",
        "policy_approved",
        "sandwich_model",
        "required_roles",
        "not_before_verification_policy",
        "not_after_verification_policy",
        "quorum_model",
        "independence_policy_id",
        "digest_commitment_policy",
        "proof_encoding_policy",
        "offline_verification_policy_id",
        "utc_day_identity_policy_id",
        "proof_replay_policy_id",
        "spacing_policy",
        "source_registry_policy_id",
        "metadata",
    ]
    assert all(parameters[name].kind is inspect.Parameter.KEYWORD_ONLY for name in parameters)


# --------------------------------------------------------------------------------------------------
# Happy READY policy
# --------------------------------------------------------------------------------------------------


def test_happy_ready_pins_abstract_sandwich_structure() -> None:
    policy = _build()
    assert policy.status is MachineTimePolicyStatus.POLICY_READY
    assert policy.ready is True
    assert policy.reason_codes == ()
    assert policy.sandwich_model == "not_before_beacon_and_not_after_signed_timestamp_sandwich.v1"
    assert policy.required_roles == ("not_before", "not_after")
    assert policy.not_before_verification_policy == "unpredictable_public_beacon_embedded_pre_seal.v1"
    assert policy.not_after_verification_policy == "external_signed_timestamp_commits_to_day_self_digest.v1"
    assert policy.quorum_model == "independent_source_classes_per_role.v1"
    assert policy.independence_policy_id == "minimum_two_independent_source_classes_per_role.v1"
    assert policy.digest_commitment_policy == "not_after_proof_commits_to_exact_day_self_digest.v1"
    assert policy.proof_encoding_policy == "canonical_deterministic_proof_bytes_no_fetch_at_verify.v1"
    assert policy.offline_verification_policy_id == "deterministic_supplied_proof_verification_no_network.v1"
    assert policy.utc_day_identity_policy_id == "distinct_consecutive_utc_day_identity.v1"
    assert policy.proof_replay_policy_id == "proof_identity_reuse_across_days_forbidden.v1"
    assert policy.spacing_policy == "consecutive_utc_days_monotonic_nonoverlapping_interval_consistent.v1"
    assert policy.source_registry_policy_id == "concrete_source_registry_required_post_deep_research.v1"
    assert policy.min_quorum_per_role == 2
    assert policy.min_machine_proven_day_count == 30
    assert policy.utc_day_ns == _DAY_NS
    assert policy.approved_quorum_per_role == 2
    assert policy.approved_required_machine_proven_day_count == 30
    assert policy.policy_approved is True


def test_output_is_frozen() -> None:
    policy = _build()
    with pytest.raises(FrozenInstanceError):
        policy.ready = False  # type: ignore[misc]


def test_digest_is_deterministic_and_metadata_order_independent() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    changed = _build(metadata={"a": "1", "b": "3"})
    assert first.policy_digest == second.policy_digest
    assert changed.policy_digest != first.policy_digest
    assert first.policy_digest == machine_time_policy_digest(first)


def test_serializer_is_fields_complete_and_excludes_only_self_digest() -> None:
    policy = _build(metadata={"b": "2", "a": "1"})
    payload = machine_time_policy_to_dict(policy)
    resealed = replace(policy, policy_digest="0" * 64)
    assert set(payload) == {field.name for field in fields(policy)}
    assert payload["status"] == policy.status.value
    assert payload["required_roles"] == ["not_before", "not_after"]
    assert payload["metadata"] == [["a", "1"], ["b", "2"]]
    assert payload["reason_codes"] == list(policy.reason_codes)
    assert machine_time_policy_digest(resealed) == policy.policy_digest
    assert payload["policy_digest"] == policy.policy_digest


def test_output_reseal_is_detectable() -> None:
    # A forged structural overclaim OR a canonical-but-invalid READY value is rejected outright (not merely
    # a different digest): the public digest refuses to reseal either.
    policy = _build()
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(replace(policy, machine_time_origin_proven=True))
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(replace(policy, required_roles=("x", "y")))
    # A legitimate identity value change (scope-clean policy_id) still recomputes to a different digest.
    assert machine_time_policy_digest(replace(policy, policy_id="mt2-policy-2")) != policy.policy_digest


def test_determinism_same_inputs_same_digest() -> None:
    assert _build().policy_digest == _build().policy_digest


# --------------------------------------------------------------------------------------------------
# Approval / value gates
# --------------------------------------------------------------------------------------------------


def test_unapproved_policy_rejected() -> None:
    policy = _build(policy_approved=False)
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert _rc("policy_not_approved") in policy.reason_codes


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "approved_quorum_per_role_missing"),
        (1, "approved_quorum_per_role_invalid"),
        (0, "approved_quorum_per_role_invalid"),
        (-2, "approved_quorum_per_role_invalid"),
        (True, "approved_quorum_per_role_invalid"),
        (2.0, "approved_quorum_per_role_invalid"),
    ],
)
def test_quorum_must_be_exact_int_at_least_two(value: object, reason: str) -> None:
    policy = _build(approved_quorum_per_role=value)
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert _rc(reason) in policy.reason_codes


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "approved_required_machine_proven_day_count_missing"),
        (29, "approved_required_machine_proven_day_count_invalid"),
        (0, "approved_required_machine_proven_day_count_invalid"),
        (True, "approved_required_machine_proven_day_count_invalid"),
        (30.0, "approved_required_machine_proven_day_count_invalid"),
    ],
)
def test_day_count_must_be_exact_int_at_least_thirty(value: object, reason: str) -> None:
    policy = _build(approved_required_machine_proven_day_count=value)
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert _rc(reason) in policy.reason_codes


def test_day_count_thirty_boundary_passes() -> None:
    assert _build(approved_required_machine_proven_day_count=30).ready is True
    assert _build(approved_required_machine_proven_day_count=31).ready is True


@pytest.mark.parametrize(
    ("min_ns", "max_ns", "reason"),
    [
        (None, _DAY_NS * 2, "approved_min_inter_day_spacing_ns_missing"),
        (_DAY_NS // 2, None, "approved_max_inter_day_spacing_ns_missing"),
        (0, _DAY_NS * 2, "approved_min_inter_day_spacing_ns_invalid"),
        (-1, _DAY_NS * 2, "approved_min_inter_day_spacing_ns_invalid"),
        (True, _DAY_NS * 2, "approved_min_inter_day_spacing_ns_invalid"),
        (_DAY_NS // 2, "x", "approved_max_inter_day_spacing_ns_invalid"),
        (_DAY_NS, _DAY_NS // 2, "approved_max_inter_day_spacing_ns_invalid"),
    ],
)
def test_spacing_bounds_must_be_ordered_positive_ints(min_ns: object, max_ns: object, reason: str) -> None:
    policy = _build(approved_min_inter_day_spacing_ns=min_ns, approved_max_inter_day_spacing_ns=max_ns)
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert _rc(reason) in policy.reason_codes


@pytest.mark.parametrize(
    ("min_ns", "max_ns"),
    [
        (_DAY_NS + 1, _DAY_NS * 2),
        (1, _DAY_NS - 1),
    ],
)
def test_spacing_window_must_contain_one_utc_day(min_ns: int, max_ns: int) -> None:
    policy = _build(approved_min_inter_day_spacing_ns=min_ns, approved_max_inter_day_spacing_ns=max_ns)
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert _rc("spacing_window_excludes_utc_day") in policy.reason_codes


def test_spacing_window_exact_day_boundaries_pass() -> None:
    assert _build(approved_min_inter_day_spacing_ns=_DAY_NS, approved_max_inter_day_spacing_ns=_DAY_NS).ready is True


def test_missing_approval_metadata_rejected() -> None:
    assert _rc("approval_reference_missing") in _build(approval_reference=None).reason_codes
    assert _rc("approval_reference_missing") in _build(approval_reference="  ").reason_codes
    assert _rc("approval_digest_invalid") in _build(approval_digest=None).reason_codes
    assert _rc("approval_digest_invalid") in _build(approval_digest="not-hex").reason_codes


# --------------------------------------------------------------------------------------------------
# Structure identifiers must equal the pinned constants (precise per-field reasons)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("field_name", "reason"), _PINNED_STRING_MISMATCHES)
def test_structure_identifier_value_mismatch_has_precise_reason(field_name: str, reason: str) -> None:
    policy = _build(**{field_name: "forged.structure.v1"})
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert _rc(reason) in policy.reason_codes
    assert _rc("structure_mismatch") not in policy.reason_codes


def test_required_roles_value_mismatch_has_precise_reason() -> None:
    policy = _build(required_roles=("not_after", "not_before"))
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert _rc("required_roles_mismatch") in policy.reason_codes


# --------------------------------------------------------------------------------------------------
# P1 — exact-type-before-operation: lying subclasses / raising objects
# --------------------------------------------------------------------------------------------------


def test_structure_policy_fields_require_exact_plain_strings_before_equality() -> None:
    for field_name in _PINNED_STRING_FIELD_NAMES:
        policy = _build(**{field_name: _LyingStr("anything")})
        assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED, field_name
        assert _rc("policy_field_type_invalid") in policy.reason_codes, field_name


def test_lie_eq_str_subclass_cannot_forge_policy_ready() -> None:
    # Sanity: the subclass equality genuinely lies, so only the exact-type gate (not ==) can reject it.
    assert _LyingStr("x") == "not_before_beacon_and_not_after_signed_timestamp_sandwich.v1"
    for field_name in _PINNED_STRING_FIELD_NAMES:
        policy = _build(**{field_name: _LyingStr("not-the-pinned-value")})
        assert policy.ready is False, field_name
        assert policy.machine_time_origin_proven is False
        assert _rc("policy_field_type_invalid") in policy.reason_codes


def test_int_subclass_cannot_forge_quorum_or_day_count() -> None:
    assert _LyingInt(1) == 2
    quorum = _build(approved_quorum_per_role=_LyingInt(1))
    assert quorum.ready is False
    assert _rc("approved_quorum_per_role_invalid") in quorum.reason_codes
    days = _build(approved_required_machine_proven_day_count=_LyingInt(1))
    assert days.ready is False
    assert _rc("approved_required_machine_proven_day_count_invalid") in days.reason_codes


def test_structure_equality_raising_objects_never_raise_raw_exception() -> None:
    for field_name in _PINNED_STRING_FIELD_NAMES:
        policy = _build(**{field_name: _RaisingEq()})  # would raise if equality were invoked
        _assert_serializable_rejected(policy)
        assert _rc("policy_field_type_invalid") in policy.reason_codes


@pytest.mark.parametrize("malformed", _SAFELY_MALFORMED, ids=_SAFELY_MALFORMED_IDS)
def test_malformed_rejected_inputs_are_safely_projected(malformed: object) -> None:
    policy = _build(sandwich_model=malformed)
    _assert_serializable_rejected(policy)
    # A valid exact plain string may remain visible; anything else projects to "" — never the custom object.
    assert type(policy.sandwich_model) is str
    if not (type(malformed) is str):
        assert policy.sandwich_model == ""


# Values that are malformed for an exact-int field (excludes valid ints like 7): a lying int subclass, a
# non-int, and non-numeric objects must all reject without invoking a custom operation.
_MALFORMED_FOR_INT_FIELD = (
    None,
    True,
    2.5,
    "2",
    ["x"],
    _RaisingEq(),
    _RaisingHash(),
    _ForeignEnum.SANDWICH,
    _LyingInt(1),
)
_MALFORMED_FOR_REFERENCE_FIELD = (None, True, 7, 2.5, ["x"], _RaisingEq(), _RaisingHash(), _ForeignEnum.SANDWICH)


def test_rejected_custom_values_serialize_and_self_digest() -> None:
    # Exercise field-appropriate malformed values across a string field, an int field, and the reference
    # field; every case must be safely projected, POLICY_REJECTED, serializable, and self-digesting.
    cases: list[tuple[str, object]] = [("not_before_verification_policy", value) for value in _SAFELY_MALFORMED]
    cases += [("approved_quorum_per_role", value) for value in _MALFORMED_FOR_INT_FIELD]
    cases += [("approval_reference", value) for value in _MALFORMED_FOR_REFERENCE_FIELD]
    for field_name, value in cases:
        policy = _build(**{field_name: value})
        _assert_serializable_rejected(policy)
        stored = getattr(policy, field_name)
        assert type(stored) in (str, int, type(None)), (field_name, value)


def test_malformed_int_and_reference_fields_project_to_none() -> None:
    policy = _build(approved_quorum_per_role=_RaisingEq(), approval_reference=_RaisingHash())
    _assert_serializable_rejected(policy)
    assert policy.approved_quorum_per_role is None
    assert policy.approval_reference is None


def test_ordering_raising_required_roles_never_raise_raw_exception() -> None:
    policy = _build(required_roles=_RolesTupleSubclass((_RaisingOrder(),)))
    _assert_serializable_rejected(policy)
    assert _rc("policy_field_type_invalid") in policy.reason_codes
    assert policy.required_roles == ()


# --------------------------------------------------------------------------------------------------
# P2 — public serializer / digest boundary
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, "not-a-policy", 7, {"policy": "dict"}, object()])
def test_public_serializer_rejects_wrong_artifact_type_with_module_error(bad: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, "not-a-policy", 7, {"policy": "dict"}, object()])
def test_public_digest_rejects_wrong_artifact_type_with_module_error(bad: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(bad)  # type: ignore[arg-type]


def test_public_serializer_rejects_malformed_status_without_raw_exception() -> None:
    forged = replace(_build(), status="POLICY_READY")  # type: ignore[arg-type]
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(forged)


def test_public_digest_rejects_malformed_status_without_raw_exception() -> None:
    forged = replace(_build(), status=None)  # type: ignore[arg-type]
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(forged)


def test_public_serializer_requires_populated_hex64_self_digest() -> None:
    forged = replace(_build(), policy_digest="")
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(forged)


# --------------------------------------------------------------------------------------------------
# Patch D — abstract future-binding contract
# --------------------------------------------------------------------------------------------------


def test_required_roles_contract_is_digest_bound_and_fail_closed() -> None:
    policy = _build()
    assert policy.required_roles == ("not_before", "not_after")
    # A forged READY artifact with wrong roles is a canonical-but-invalid READY value → rejected, not resealed.
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(replace(policy, required_roles=("x",)))
    assert _build(required_roles=("only_one",)).ready is False
    assert _rc("policy_field_type_invalid") in _build(required_roles=("ok", 7)).reason_codes  # type: ignore[arg-type]
    assert _rc("policy_field_type_invalid") in _build(required_roles=["not_before", "not_after"]).reason_codes  # type: ignore[arg-type]


def test_source_registry_boundary_is_explicit_and_unbound() -> None:
    for policy in (_build(), _build(policy_approved=False)):
        assert (
            policy.source_registry_policy_id == "concrete_source_registry_required_post_deep_research.v1"
            or not policy.ready
        )
        assert policy.concrete_source_registry_required is True
        assert policy.concrete_source_registry_bound is False
        assert policy.source_registry_digest is None
        assert policy.source_registry_consumed is False


def test_offline_verification_and_replay_invariants_are_digest_bound() -> None:
    policy = _build()
    assert policy.deterministic_offline_verification_required is True
    assert policy.network_fetch_in_builder_forbidden is True
    assert policy.proof_reuse_across_days_forbidden is True
    assert policy.distinct_sandwich_per_utc_day_required is True
    assert policy.consecutive_utc_days_required is True
    assert policy.interval_consistency_required is True
    assert policy.role_separation_required is True
    assert policy.exact_digest_commitment_required is True
    assert policy.independent_source_classes_required is True
    for flag in (
        "deterministic_offline_verification_required",
        "network_fetch_in_builder_forbidden",
        "proof_reuse_across_days_forbidden",
        "exact_digest_commitment_required",
    ):
        # Weakening a structural-required True flag is rejected by the public digest, not resealed.
        with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
            machine_time_policy_digest(replace(policy, **{flag: False}))


def test_no_mt2_input_can_bind_a_concrete_source_registry() -> None:
    variants = (
        _build(),
        _build(policy_approved=False),
        _build(approved_quorum_per_role=99),
        _build(source_registry_policy_id="forged.registry.v1"),
        _build(metadata={"note": "bind a source registry"}),
    )
    for policy in variants:
        assert policy.concrete_source_registry_bound is False
        assert policy.source_registry_digest is None
        assert policy.source_registry_consumed is False
        assert policy.concrete_sources_bound is False
        assert policy.deep_research_facts_bound is False
        assert policy.external_proofs_consumed is False
        assert policy.machine_proven_days_consumed is False


# --------------------------------------------------------------------------------------------------
# Caller-input RAISE contract
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("policy_id", "", "policy_id_invalid"),
        ("policy_id", "  ", "policy_id_invalid"),
        ("policy_id", 7, "policy_id_invalid"),
        ("correlation_id", "", "correlation_id_invalid"),
        ("correlation_id", None, "correlation_id_invalid"),
        ("policy_approved", "yes", "policy_approved_invalid"),
        ("policy_approved", 1, "policy_approved_invalid"),
        ("metadata", {"key": 5}, "metadata_malformed"),
        ("metadata", {" key": "value"}, "metadata_malformed"),
        ("metadata", "not-a-mapping", "metadata_malformed"),
    ],
)
def test_malformed_caller_input_raises(field_name: str, value: object, reason: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc(reason)):
        _build(**{field_name: value})


# --------------------------------------------------------------------------------------------------
# Scope / clock / BIST token rejection
# --------------------------------------------------------------------------------------------------


def test_scope_and_clock_and_bist_tokens_rejected() -> None:
    assert _rc("scope_violation") in _build(metadata={"note": "enable live orders"}).reason_codes
    assert _rc("clock_token_forbidden") in _build(metadata={"note": "read system_time now"}).reason_codes
    assert _rc("bist_token_forbidden") in _build(metadata={"note": "bist matriks feed"}).reason_codes
    assert _rc("scope_violation") in _build(approval_reference="deribit-live-order").reason_codes


# --------------------------------------------------------------------------------------------------
# Non-overclaim: MT-2 proves no machine time and enables no capability
# --------------------------------------------------------------------------------------------------


def test_ready_and_rejected_keep_structural_markers_true_and_unsafe_claims_false() -> None:
    ready = _build()
    rejected = _build(policy_approved=False)
    defaults = {field.name: field.default for field in fields(MachineTimePolicy)}
    for flag in _ALWAYS_TRUE:
        assert getattr(ready, flag) is True, flag
        assert getattr(rejected, flag) is True, flag
        assert defaults[flag] is True, flag
    for flag in _ALWAYS_FALSE:
        assert getattr(ready, flag) is False, flag
        assert getattr(rejected, flag) is False, flag
        assert defaults[flag] is False, flag


def test_machine_time_origin_never_provable_by_this_policy() -> None:
    for policy in (_build(), _build(policy_approved=False), _build(approved_quorum_per_role=99)):
        assert policy.machine_time_origin_proven is False
        assert policy.timestamp_origin_proven is False
        assert policy.machine_time_anchor_verified is False
        assert policy.deep_research_facts_bound is False
        assert policy.injected_time_accepted_as_proof is False
        assert policy.attested_time_accepted_as_proof is False
        assert policy.real_wall_clock_used is False


# --------------------------------------------------------------------------------------------------
# Structural safety (AST forbidden surface)
# --------------------------------------------------------------------------------------------------


def test_ast_forbidden_imports_and_calls() -> None:
    source = Path(policy_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "os",
        "io",
        "pathlib",
        "time",
        "datetime",
        "random",
        "secrets",
        "socket",
        "ssl",
        "requests",
        "urllib",
        "http",
        "threading",
        "asyncio",
        "subprocess",
        "sqlite3",
    )
    forbidden_call_names = {
        "open",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
        "system",
        "getenv",
        "eval",
        "exec",
        "urlopen",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == module or alias.name.startswith(f"{module}.") for module in forbidden_modules
                ), alias.name
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                node.module == module or node.module.startswith(f"{module}.") for module in forbidden_modules
            ), node.module
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names, function.id
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names, function.attr


def test_no_equivalent_builder_exists() -> None:
    validation_dir = Path(policy_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "def build_machine_time_policy(" in path.read_text(encoding="utf-8")
    )
    assert builders == ["machine_time_policy.py"]


def test_reason_codes_are_sorted_unique_and_prefixed() -> None:
    policy = _build(policy_approved=False, approved_quorum_per_role=None, approval_digest=None)
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert list(policy.reason_codes) == sorted(set(policy.reason_codes))
    assert all(code.startswith("machine_time_policy:") for code in policy.reason_codes)


def test_serializer_json_roundtrip_stable() -> None:
    policy = _build()
    payload = machine_time_policy_to_dict(policy)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert json.loads(encoded)["policy_digest"] == policy.policy_digest


# --------------------------------------------------------------------------------------------------
# Public artifact-boundary repair: exact metadata container + complete 78-field validator
# --------------------------------------------------------------------------------------------------


class _HostileMapping(_AbcMapping):
    """A genuine ``Mapping`` (isinstance True) that is NOT an exact ``dict``; every access raises."""

    def __getitem__(self, key: object) -> object:  # pragma: no cover - must never be invoked
        raise AssertionError("hostile mapping __getitem__ must never be invoked")

    def __iter__(self):  # pragma: no cover - must never be invoked
        raise AssertionError("hostile mapping __iter__ must never be invoked")

    def __len__(self) -> int:  # pragma: no cover - must never be invoked
        raise AssertionError("hostile mapping __len__ must never be invoked")

    def items(self):  # pragma: no cover - must never be invoked
        raise AssertionError("hostile mapping items() must never be invoked")


class _EvilDictSubclass(dict):
    """A ``dict`` subclass (type is not exact ``dict``) whose ``.items()`` override must never run."""

    def items(self):  # pragma: no cover - must never be invoked
        raise AssertionError("dict-subclass items() override must never be invoked")


def test_builder_rejects_custom_mapping_without_invoking_items() -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("metadata_malformed")):
        _build(metadata=_HostileMapping())


def test_builder_rejects_dict_subclass_without_invoking_overrides() -> None:
    evil = _EvilDictSubclass()
    evil["purpose"] = "hostile"
    with pytest.raises(MachineTimePolicyError, match=_rc("metadata_malformed")):
        _build(metadata=evil)


def test_valid_exact_dict_metadata_order_independent() -> None:
    assert _build(metadata={"b": "2", "a": "1"}).policy_digest == _build(metadata={"a": "1", "b": "2"}).policy_digest


def _forge(**changes: object) -> MachineTimePolicy:
    return replace(_build(), **changes)  # type: ignore[arg-type]


def test_public_artifact_validator_covers_every_dataclass_field() -> None:
    # An object() is malformed for every field family; the validator must reject a forgery in EACH of the 78
    # fields at both public entry points, never leaking a raw exception.
    for field in fields(MachineTimePolicy):
        forged = _forge(**{field.name: object()})
        with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
            machine_time_policy_digest(forged)
        with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
            machine_time_policy_to_dict(forged)


@pytest.mark.parametrize("field_name", ["schema_version", "policy_version", "policy_id", "correlation_id"])
def test_public_serializer_rejects_malformed_identity_field(field_name: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(_forge(**{field_name: _RaisingEq()}))


@pytest.mark.parametrize("field_name", ["schema_version", "policy_id"])
def test_public_digest_rejects_malformed_identity_field(field_name: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{field_name: 7}))


@pytest.mark.parametrize("roles", [object(), "not_before", ("ok", _RaisingEq()), (_LyingStr("not_before"),), 7])
def test_public_serializer_rejects_malformed_roles_field(roles: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(_forge(required_roles=roles))


@pytest.mark.parametrize(
    "reasons",
    [
        object(),
        ["machine_time_policy:x"],
        ("plain_no_prefix",),
        ("machine_time_policy:b", "machine_time_policy:a"),  # unsorted
        ("machine_time_policy:a", "machine_time_policy:a"),  # duplicate
        (_RaisingEq(),),
    ],
)
def test_public_digest_rejects_malformed_reason_codes(reasons: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(
            _forge(reason_codes=reasons, status=MachineTimePolicyStatus.POLICY_REJECTED, ready=False)
        )


@pytest.mark.parametrize(
    "metadata",
    [
        object(),
        [["a", "1"]],
        (("a", "1", "extra"),),
        (("a", _RaisingEq()),),
        (("b", "2"), ("a", "1")),  # unsorted
        (("a", "1"), ("a", "2")),  # duplicate key
        ((_RaisingHash(), "1"),),
    ],
)
def test_public_serializer_rejects_malformed_metadata_shape(metadata: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(_forge(metadata=metadata))


def test_public_digest_rejects_malformed_metadata_shape() -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(metadata=("not-a-pair-tuple",)))


@pytest.mark.parametrize(
    "field_name",
    [
        "min_quorum_per_role",
        "min_machine_proven_day_count",
        "utc_day_ns",
        "approved_quorum_per_role",
        "approved_required_machine_proven_day_count",
        "approved_min_inter_day_spacing_ns",
        "approved_max_inter_day_spacing_ns",
    ],
)
@pytest.mark.parametrize("bad", [True, _LyingInt(2), 2.0])
def test_public_boundary_rejects_bool_and_int_subclass_in_integer_fields(field_name: str, bad: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{field_name: bad}))


@pytest.mark.parametrize("flag", [*_ALWAYS_TRUE, *_ALWAYS_FALSE])
@pytest.mark.parametrize("bad", [1, 0, "True", None, _EqualityTrue()])
def test_public_boundary_rejects_non_bool_structural_flags(flag: str, bad: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{flag: bad}))


@pytest.mark.parametrize("flag", _ALWAYS_FALSE)
def test_public_digest_rejects_structural_false_flag_overclaim(flag: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{flag: True}))
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(_forge(**{flag: True}))


@pytest.mark.parametrize("flag", _ALWAYS_TRUE)
def test_public_digest_rejects_structural_true_flag_weakening(flag: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{flag: False}))


@pytest.mark.parametrize("bad", [_HEX_B, "", 0, object(), True])
def test_public_boundary_rejects_non_none_source_registry_digest(bad: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(source_registry_digest=bad))


def test_to_dict_is_json_ready_for_every_builder_produced_rejected_artifact() -> None:
    rejected_variants = (
        _build(policy_approved=False),
        _build(approved_quorum_per_role=None),
        _build(approved_quorum_per_role=1),
        _build(approved_required_machine_proven_day_count=5),
        _build(approved_min_inter_day_spacing_ns=None),
        _build(sandwich_model="forged.structure.v1"),
        _build(sandwich_model=_RaisingEq()),
        _build(required_roles=("only_one",)),
        _build(approval_reference=None),
        _build(approval_digest="not-hex"),
        _build(metadata={"note": "enable live orders"}),
    )
    for policy in (_build(), *rejected_variants):
        payload = machine_time_policy_to_dict(policy)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        assert json.loads(encoded)["policy_digest"] == policy.policy_digest
        assert machine_time_policy_digest(policy) == policy.policy_digest


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("policy_id", _RaisingEq()),
        ("status", "POLICY_READY"),
        ("ready", _EqualityTrue()),
        ("required_roles", (_RaisingOrder(),)),
        ("reason_codes", (_RaisingHash(),)),
        ("metadata", (_RaisingEq(),)),
        ("approved_quorum_per_role", _RaisingEq()),
        ("approval_digest", _RaisingHash()),
        ("machine_time_origin_proven", _RaisingEq()),
        ("sandwich_model", _LyingStr("x")),
        ("policy_digest", object()),
    ],
)
def test_digest_never_leaks_raw_exception_for_forged_exact_dataclass(field_name: str, value: object) -> None:
    # pytest.raises(MachineTimePolicyError) fails if any raw AssertionError/TypeError/ValueError/JSON/
    # unpacking/custom-op exception escapes instead, so this proves the boundary never leaks.
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{field_name: value}))


# --------------------------------------------------------------------------------------------------
# Final closeout: full public READY semantic reproof + self-digest exact-type + carried-digest consistency
# --------------------------------------------------------------------------------------------------

# Canonical-but-invalid READY forgeries: each value passes the shape/canonical checks yet violates the
# governance READY contract, so the public digest/serializer must reject (never reseal) it.
_FORGED_READY_SEMANTIC_CASES = [
    ("sandwich_model", "forged.structure.v1"),
    ("sandwich_model", ""),
    ("not_after_verification_policy", "wrong.v1"),
    ("source_registry_policy_id", "wrong.v1"),
    ("required_roles", ("x",)),
    ("required_roles", ("not_after", "not_before")),
    ("required_roles", ("not_before", "not_after", "extra")),
    ("required_roles", ()),
    ("approved_quorum_per_role", None),
    ("approved_quorum_per_role", 1),
    ("approved_required_machine_proven_day_count", None),
    ("approved_required_machine_proven_day_count", 29),
    ("approved_min_inter_day_spacing_ns", None),
    ("approved_min_inter_day_spacing_ns", _DAY_NS + 1),
    ("policy_approved", False),
    ("approval_reference", None),
    ("approval_digest", None),
    ("policy_id", "deribit-live-order"),
    ("correlation_id", "enable-live-orders"),
    ("approval_reference", "scheduler-live"),
    ("metadata", (("note", "enable live orders"),)),
    ("metadata", (("note", "read system_time now"),)),
    ("metadata", (("note", "bist matriks feed"),)),
    # Pre-Deep-Research provider/endpoint scope forgeries (network location or provider vocabulary).
    ("policy_id", "https://provider.example/api"),
    ("policy_id", "provider.name"),
    ("correlation_id", "192.0.2.1:443"),
    ("approval_reference", "tsa.example"),
    ("approval_reference", "wss://time.example/stream"),
    ("metadata", (("provider_name", "x"),)),
    ("metadata", (("endpoint_url", "x"),)),
    ("metadata", (("note", "use provider endpoint"),)),
    ("metadata", (("note", "bind external service hostname"),)),
    ("metadata", (("note", "connect tsa.example"),)),
    ("metadata", (("note", "reach [2001:db8::1] node"),)),
]
_FORGED_READY_SEMANTIC_IDS = [f"{name}-{index}" for index, (name, _) in enumerate(_FORGED_READY_SEMANTIC_CASES)]


@pytest.mark.parametrize(("field_name", "value"), _FORGED_READY_SEMANTIC_CASES, ids=_FORGED_READY_SEMANTIC_IDS)
def test_forged_ready_semantic_matrix_cannot_be_resealed(field_name: str, value: object) -> None:
    forged = _forge(**{field_name: value})
    assert forged.status is MachineTimePolicyStatus.POLICY_READY  # the forgery keeps the READY declaration
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(forged)
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(forged)


@pytest.mark.parametrize("field_name", _PINNED_STRING_FIELD_NAMES)
def test_public_digest_rejects_ready_with_mismatched_pinned_policy(field_name: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{field_name: "forged.pinned.v1"}))


@pytest.mark.parametrize("field_name", _PINNED_STRING_FIELD_NAMES)
def test_public_serializer_rejects_ready_with_mismatched_pinned_policy(field_name: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(_forge(**{field_name: "forged.pinned.v1"}))


@pytest.mark.parametrize("roles", [("x",), ("not_after", "not_before"), ("not_before", "not_after", "z"), ()])
def test_public_digest_rejects_ready_with_wrong_required_roles(roles: tuple) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(required_roles=roles))


@pytest.mark.parametrize("value", [None, 0, 1])
def test_public_digest_rejects_ready_with_quorum_below_minimum(value: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(approved_quorum_per_role=value))


@pytest.mark.parametrize("value", [None, 0, 29])
def test_public_digest_rejects_ready_with_day_count_below_minimum(value: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(approved_required_machine_proven_day_count=value))


@pytest.mark.parametrize(
    ("min_ns", "max_ns"),
    [(None, _DAY_NS * 2), (_DAY_NS // 2, None), (_DAY_NS + 1, _DAY_NS * 2), (1, _DAY_NS - 1), (_DAY_NS, _DAY_NS // 2)],
)
def test_public_digest_rejects_ready_with_invalid_spacing_window(min_ns: object, max_ns: object) -> None:
    forged = _forge(approved_min_inter_day_spacing_ns=min_ns, approved_max_inter_day_spacing_ns=max_ns)
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(forged)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("policy_approved", False), ("approval_reference", None), ("approval_digest", None)],
)
def test_public_digest_rejects_ready_without_approval(field_name: str, value: object) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{field_name: value}))


@pytest.mark.parametrize("field_name", ["policy_id", "correlation_id"])
def test_public_digest_rejects_ready_with_forbidden_identity_scope(field_name: str) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{field_name: "deribit-live-order"}))


@pytest.mark.parametrize(
    "metadata",
    [(("note", "enable live orders"),), (("note", "read system_time now"),), (("note", "bist matriks feed"),)],
)
def test_public_digest_rejects_ready_with_forbidden_metadata_scope(metadata: tuple) -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(metadata=metadata))


def test_public_digest_rejects_ready_with_forbidden_approval_scope() -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(approval_reference="scheduler-live-order"))


@pytest.mark.parametrize("bad", [_RaisingEq(), _LyingStr("x"), 7, True, None, object()])
def test_policy_digest_equality_raising_object_never_invoked(bad: object) -> None:
    # A raw AssertionError from _RaisingEq.__eq__ would surface instead of MachineTimePolicyError if the
    # self-digest field were compared before its exact type was proven.
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(policy_digest=bad))
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(_forge(policy_digest=bad))


def test_to_dict_rejects_stale_carried_self_digest() -> None:
    policy = _build()
    other = _build(policy_id="mt2-policy-stale")
    assert other.policy_digest != policy.policy_digest
    forged = replace(policy, policy_digest=other.policy_digest)  # valid hex64, but not policy's own digest
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(forged)


def test_to_dict_rejects_random_valid_hex64_self_digest() -> None:
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(replace(_build(), policy_digest="a" * 64))


def test_digest_recomputes_despite_stale_valid_hex64_carried_digest() -> None:
    policy = _build()
    # The recomputation API ignores the carried digest and returns the correct canonical digest.
    assert machine_time_policy_digest(replace(policy, policy_digest="a" * 64)) == policy.policy_digest


def test_builder_produced_rejected_artifacts_remain_serializable_after_ready_reproof() -> None:
    rejected_variants = (
        _build(policy_approved=False),
        _build(approved_quorum_per_role=1),
        _build(approved_required_machine_proven_day_count=29),
        _build(approved_min_inter_day_spacing_ns=None),
        _build(sandwich_model="forged.structure.v1"),
        _build(required_roles=("only_one",)),
        _build(approval_reference=None),
        _build(approval_digest="not-hex"),
        _build(metadata={"note": "enable live orders"}),
    )
    for policy in rejected_variants:
        assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
        payload = machine_time_policy_to_dict(policy)
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        assert machine_time_policy_digest(policy) == policy.policy_digest


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("approved_quorum_per_role", 1),
        ("approved_required_machine_proven_day_count", 29),
        ("sandwich_model", "forged.structure.v1"),
        ("policy_approved", False),
        ("approval_reference", None),
        ("approval_digest", None),
    ],
)
def test_public_ready_reproof_matches_builder_ready_contract(field_name: str, value: object) -> None:
    # The exact governance violation that makes the BUILDER reject is exactly what the public READY reproof
    # refuses to reseal on a forged READY artifact.
    assert _build(**{field_name: value}).ready is False
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(**{field_name: value}))
    # A valid READY artifact still serializes and self-digests.
    valid = _build()
    assert valid.ready is True
    assert machine_time_policy_digest(valid) == valid.policy_digest
    assert machine_time_policy_to_dict(valid)["policy_digest"] == valid.policy_digest


# --------------------------------------------------------------------------------------------------
# Pre-Deep-Research provider/endpoint scope closeout: no concrete source binding may reach READY
# --------------------------------------------------------------------------------------------------

# Synthetic network-location material only (no real provider brand). Each must be detected as
# provider-binding.
_NETWORK_LOCATION_SAMPLES = (
    "https://provider.example/api",
    "http://provider.example",
    "ws://time.example/stream",
    "wss://time.example/stream",
    "ftp://archive.example/proofs",
    "scheme://host.example/x",
    "www.provider.example",
    "provider.example",
    "sub.provider.example",
    "tsa.example",
    "192.0.2.1",
    "192.0.2.1:443",
    "[2001:db8::1]",
    "[2001:db8::1]:443",
    "host.example:8080",
)

# Provider/endpoint vocabulary, exercising each supported separator (space, ``_``, ``-``, ``.``, ``:``,
# ``/``). None relies on a real company/service/authority name.
_PROVIDER_VOCABULARY_SAMPLES = (
    "provider",
    "vendor",
    "endpoint",
    "hostname",
    "use provider endpoint",
    "provider_name",
    "endpoint-url",
    "source.hostname",
    "beacon:provider",
    "tsa/endpoint",
    "bind external service hostname",
    "base_url",
    "api_url",
    "domain_name",
)

# Abstract vocabulary + canonical identifiers that must never be flagged (false-positive guard).
_ALLOWED_ABSTRACT_SAMPLES = (
    "external",
    "source",
    "proof",
    "signature",
    "timestamp",
    "public",
    "digest",
    "registry",
    "offline",
    "utc",
    "sandwich",
    "abstract",
    "policy",
    "governance",
    "external source proof signature timestamp registry offline sandwich abstract governance",
    "abstract machine-time sandwich policy",
    "mt2-policy-1",
    "corr-1",
    "gov-mt2-1",
    "bind a source registry",
)


@pytest.mark.parametrize("sample", [*_NETWORK_LOCATION_SAMPLES, *_PROVIDER_VOCABULARY_SAMPLES])
def test_provider_binding_material_detector_flags_concrete_source(sample: str) -> None:
    assert policy_module._has_provider_binding_material(sample) is True


@pytest.mark.parametrize("sample", _ALLOWED_ABSTRACT_SAMPLES)
def test_provider_binding_material_detector_allows_abstract_terms(sample: str) -> None:
    assert policy_module._has_provider_binding_material(sample) is False


def test_provider_binding_material_detector_is_exact_type_guarded() -> None:
    # A non-str / empty text is skipped; no caller-controlled operation is invoked.
    assert policy_module._has_provider_binding_material(None, 7, b"provider", "") is False
    assert policy_module._has_provider_binding_material(_RaisingEq(), _RaisingHash()) is False


@pytest.mark.parametrize(
    "value",
    ["mt2-policy-1", "corr-1", "gov-mt2-1", "a", "x1", "policy_id_1", "note-2"],
)
def test_opaque_identifier_accepts_canonical_ids(value: str) -> None:
    assert policy_module._is_opaque_identifier(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "https://provider.example/api",
        "provider.example",
        "192.0.2.1:443",
        "corr 1",
        "-corr",
        "corr-",
        "Corr-1",
        "corr@1",
        "corr/1",
        "corr:1",
        "corr.1",
        "",
        7,
        None,
        _LyingStr("corr-1"),
    ],
)
def test_opaque_identifier_rejects_network_and_non_exact(value: object) -> None:
    assert policy_module._is_opaque_identifier(value) is False


@pytest.mark.parametrize("field_name", ["policy_id", "correlation_id"])
@pytest.mark.parametrize("value", ["https://provider.example/api", "192.0.2.1:443", "tsa.example"])
def test_builder_rejects_network_location_in_identity_fields(field_name: str, value: str) -> None:
    policy = _build(**{field_name: value})
    _assert_serializable_rejected(policy)
    assert _rc("provider_binding_forbidden") in policy.reason_codes
    assert _rc(f"{field_name}_not_opaque") in policy.reason_codes


@pytest.mark.parametrize("value", ["provider", "endpoint_name"])
def test_builder_rejects_provider_vocabulary_in_identity_fields(value: str) -> None:
    # Grammar-valid opaque ids that nonetheless carry provider vocabulary are still rejected.
    assert policy_module._is_opaque_identifier(value) is True
    policy = _build(policy_id=value)
    _assert_serializable_rejected(policy)
    assert _rc("provider_binding_forbidden") in policy.reason_codes


def test_builder_rejects_canonical_but_forbidden_approval_reference() -> None:
    # A canonical-but-forbidden approval reference returns deterministic POLICY_REJECTED, never a raw raise.
    policy = _build(approval_reference="tsa.example")
    _assert_serializable_rejected(policy)
    assert _rc("provider_binding_forbidden") in policy.reason_codes
    assert _rc("approval_reference_not_opaque") in policy.reason_codes
    assert _rc("approval_reference_missing") not in policy.reason_codes


@pytest.mark.parametrize(
    "key",
    ["provider_name", "endpoint_url", "source_hostname", "beacon_provider", "tsa_endpoint", "exchange_time_host"],
)
def test_builder_rejects_provider_binding_metadata_key(key: str) -> None:
    policy = _build(metadata={key: "x"})
    _assert_serializable_rejected(policy)
    assert _rc("provider_binding_forbidden") in policy.reason_codes


@pytest.mark.parametrize("key", ["provider.name", "endpoint:url", "host/name"])
def test_builder_rejects_non_opaque_metadata_key(key: str) -> None:
    policy = _build(metadata={key: "x"})
    _assert_serializable_rejected(policy)
    assert _rc("metadata_key_not_opaque") in policy.reason_codes


@pytest.mark.parametrize(
    "value",
    [
        "use provider endpoint",
        "bind external service hostname",
        "connect tsa.example",
        "https://provider.example/api",
        "reach [2001:db8::1] node",
        "call 192.0.2.1:443",
    ],
)
def test_builder_rejects_provider_binding_metadata_value(value: str) -> None:
    policy = _build(metadata={"note": value})
    _assert_serializable_rejected(policy)
    assert _rc("provider_binding_forbidden") in policy.reason_codes


def test_abstract_metadata_and_canonical_ids_remain_ready() -> None:
    # The canonical valid metadata stays READY.
    assert _build(metadata={"purpose": "abstract machine-time sandwich policy"}).ready is True
    # Allowed abstract vocabulary (external / source / registry / offline ...) does not false-positive.
    ready = _build(metadata={"purpose": "external source proof signature timestamp registry offline sandwich policy"})
    assert ready.ready is True
    assert ready.status is MachineTimePolicyStatus.POLICY_READY
    assert ready.reason_codes == ()
    # ``source`` / ``registry`` remain allowed even though ``source_provider`` / ``source_hostname`` do not.
    assert _build(metadata={"note": "bind a source registry"}).ready is True


@pytest.mark.parametrize("field_name", ["policy_id", "correlation_id", "approval_reference"])
def test_public_digest_rejects_ready_with_network_location_scope(field_name: str) -> None:
    forged = _forge(**{field_name: "https://provider.example/api"})
    assert forged.status is MachineTimePolicyStatus.POLICY_READY
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(forged)
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(forged)


@pytest.mark.parametrize(
    "metadata",
    [
        (("provider_name", "x"),),
        (("note", "use provider endpoint"),),
        (("note", "connect tsa.example"),),
        (("provider.name", "x"),),
    ],
)
def test_public_digest_rejects_ready_with_provider_binding_metadata(metadata: tuple) -> None:
    forged = _forge(metadata=metadata)
    assert forged.status is MachineTimePolicyStatus.POLICY_READY
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(forged)
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_to_dict(forged)


def test_public_provider_scope_reproof_matches_builder_contract() -> None:
    # The exact scope violation that makes the BUILDER reject is exactly what the public READY reproof
    # refuses to reseal on a forged READY artifact; a scope-clean READY policy still serializes.
    assert _build(policy_id="provider.example").ready is False
    with pytest.raises(MachineTimePolicyError, match=_rc("malformed_artifact")):
        machine_time_policy_digest(_forge(policy_id="provider.example"))
    valid = _build()
    assert valid.ready is True
    assert machine_time_policy_to_dict(valid)["policy_digest"] == valid.policy_digest
