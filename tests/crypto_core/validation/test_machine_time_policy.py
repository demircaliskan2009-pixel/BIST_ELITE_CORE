"""Tests for the MT-2 abstract machine-time policy artifact (pre-Deep-Research-safe)."""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import FrozenInstanceError, fields, replace
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
    "digest_commitment_policy",
    "proof_encoding_policy",
    "spacing_policy",
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
    "reason_codes",
    "metadata",
    "policy_digest",
    "paper_only",
    "policy_only",
    "abstract_pre_deep_research",
    "deep_research_facts_bound",
    "concrete_sources_bound",
    "machine_time_anchor_verified",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "injected_time_accepted_as_proof",
    "attested_time_accepted_as_proof",
    "network_fetch_performed",
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

_ALWAYS_FALSE = (
    "deep_research_facts_bound",
    "concrete_sources_bound",
    "machine_time_anchor_verified",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "injected_time_accepted_as_proof",
    "attested_time_accepted_as_proof",
    "network_fetch_performed",
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


# --------------------------------------------------------------------------------------------------
# Public contract
# --------------------------------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert policy_module.__all__ == [
        "MachineTimePolicy",
        "MachineTimePolicyError",
        "MachineTimePolicyStatus",
        "build_machine_time_policy",
        "machine_time_policy_digest",
        "machine_time_policy_to_dict",
    ]
    assert [status.value for status in MachineTimePolicyStatus] == ["POLICY_READY", "POLICY_REJECTED"]


def test_dataclass_field_order_exact() -> None:
    assert tuple(field.name for field in fields(MachineTimePolicy)) == _EXPECTED_FIELD_ORDER


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
        "not_before_verification_policy",
        "not_after_verification_policy",
        "quorum_model",
        "digest_commitment_policy",
        "proof_encoding_policy",
        "spacing_policy",
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
    assert policy.digest_commitment_policy == "not_after_proof_commits_to_exact_day_self_digest.v1"
    assert policy.proof_encoding_policy == "canonical_deterministic_proof_bytes_no_fetch_at_verify.v1"
    assert policy.spacing_policy == "consecutive_utc_days_monotonic_nonoverlapping_interval_consistent.v1"
    assert policy.min_quorum_per_role == 2
    assert policy.min_machine_proven_day_count == 30
    assert policy.utc_day_ns == _DAY_NS
    assert policy.approved_quorum_per_role == 2
    assert policy.approved_required_machine_proven_day_count == 30
    assert policy.policy_approved is True
    assert policy.paper_only is True
    assert policy.policy_only is True
    assert policy.abstract_pre_deep_research is True


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
    policy = _build()
    forged = replace(policy, machine_time_origin_proven=True)
    assert machine_time_policy_digest(forged) != policy.policy_digest


def test_determinism_same_inputs_same_digest() -> None:
    assert _build().policy_digest == _build().policy_digest


# --------------------------------------------------------------------------------------------------
# Approval / value gates (fail-closed to POLICY_REJECTED)
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
        (_DAY_NS + 1, _DAY_NS * 2),  # window entirely above one day
        (1, _DAY_NS - 1),  # window entirely below one day
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
# Structure identifiers must equal the pinned constants
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    [
        "sandwich_model",
        "not_before_verification_policy",
        "not_after_verification_policy",
        "quorum_model",
        "digest_commitment_policy",
        "proof_encoding_policy",
        "spacing_policy",
    ],
)
def test_structure_identifier_mismatch_rejected(field_name: str) -> None:
    policy = _build(**{field_name: "forged.structure.v1"})
    assert policy.status is MachineTimePolicyStatus.POLICY_REJECTED
    assert _rc("structure_mismatch") in policy.reason_codes


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


def test_ready_and_rejected_keep_all_unsafe_claims_structurally_false() -> None:
    ready = _build()
    rejected = _build(policy_approved=False)
    defaults = {field.name: field.default for field in fields(MachineTimePolicy)}
    for flag in _ALWAYS_FALSE:
        assert getattr(ready, flag) is False, flag
        assert getattr(rejected, flag) is False, flag
        assert defaults[flag] is False, flag
    assert ready.paper_only is rejected.paper_only is True
    assert ready.policy_only is rejected.policy_only is True
    assert ready.abstract_pre_deep_research is rejected.abstract_pre_deep_research is True


def test_machine_time_origin_never_provable_by_this_policy() -> None:
    # The defining safety property: no combination of caller inputs can make MT-2 set time-origin proof.
    for policy in (_build(), _build(policy_approved=False), _build(approved_quorum_per_role=99)):
        assert policy.machine_time_origin_proven is False
        assert policy.timestamp_origin_proven is False
        assert policy.machine_time_anchor_verified is False
        assert policy.deep_research_facts_bound is False
        assert policy.injected_time_accepted_as_proof is False
        assert policy.attested_time_accepted_as_proof is False


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
