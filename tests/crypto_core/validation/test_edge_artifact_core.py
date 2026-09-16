"""Tests for the Edge Factory trust kernel ``crypto_core.validation.edge_artifact_core``."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import crypto_core.validation.edge_artifact_core as core_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_MILESTONE_CLAIM_FLAG_NAMES,
    EDGE_PERMANENT_NON_CLAIM_FLAGS,
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_canonical_json,
    edge_gate_claim_profile,
    edge_gate_milestone_claims,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)

_DIGEST = "a" * 64
_CODE = "kernel_test:authority"


class _KernelTestError(EdgeArtifactError):
    pass


def _shape(snapshot: dict) -> bool:
    return set(snapshot) == {"name", "value"} and type(snapshot["name"]) is str and type(snapshot["value"]) is int


def _build(snapshot: object, digest: object = _DIGEST) -> EdgeAuthorityBinding:
    return build_edge_authority_binding(
        snapshot_payload=snapshot, expected_digest=digest, shape=_shape, error=_KernelTestError, code=_CODE
    )


def _require(binding: object, *, optional: bool = False) -> EdgeAuthorityBinding | None:
    return require_edge_authority_binding(binding, shape=_shape, error=_KernelTestError, code=_CODE, optional=optional)


def _parse(value: object, *, optional: bool = False) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(value, shape=_shape, error=_KernelTestError, code=_CODE, optional=optional)


# --- primitives -----------------------------------------------------------------------------------------------------


def test_verdict_precedence_is_fail_then_external_then_governance_then_pass() -> None:
    assert resolve_edge_gate_verdict(["f"], ["e"], ["g"]) is EdgeGateVerdict.FAIL
    assert resolve_edge_gate_verdict([], ["e"], ["g"]) is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert resolve_edge_gate_verdict([], [], ["g"]) is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert resolve_edge_gate_verdict([], [], []) is EdgeGateVerdict.PASS


def test_status_and_verdict_vocabularies_are_separate() -> None:
    assert {member.value for member in EdgeEvidenceStatus} == {"READY", "REJECTED"}
    assert {member.value for member in EdgeGateVerdict} == {
        "PASS",
        "FAIL",
        "NEEDS_EXTERNAL_FACTS",
        "NEEDS_GOVERNANCE_APPROVAL",
        "NOT_EVALUATED",
    }


def test_canonical_json_is_sorted_compact_ascii_and_rejects_non_finite_numbers() -> None:
    assert edge_canonical_json({"b": 1, "a": "ç"}) == '{"a":"\\u00e7","b":1}'
    with pytest.raises(ValueError):
        edge_canonical_json({"x": float("nan")})
    with pytest.raises(ValueError):
        edge_canonical_json({"x": float("inf")})


def test_payload_digest_excludes_only_the_self_digest_field() -> None:
    payload = {"a": 1, "self": "anything"}
    assert edge_payload_digest(payload, "self") == edge_sha256_text('{"a":1}')
    assert edge_payload_digest({**payload, "self": "other"}, "self") == edge_payload_digest(payload, "self")
    assert edge_payload_digest({**payload, "a": 2}, "self") != edge_payload_digest(payload, "self")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("a" * 64, True), ("0123456789abcdef" * 4, True), ("A" * 64, False), ("a" * 63, False), ("g" * 64, False)],
)
def test_hex64_accepts_only_lowercase_sha256_hex(value: str, expected: bool) -> None:
    assert edge_is_hex64(value) is expected


def test_hex64_rejects_non_strings() -> None:
    assert edge_is_hex64(None) is False
    assert edge_is_hex64(b"a" * 64) is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BIST30 funding", "bist_scope_leakage"),
        ("funding_bist30", "bist_scope_leakage"),
        ("borsa_istanbul", "bist_scope_leakage"),
        ("matriks feed", "bist_scope_leakage"),
        ("kap disclosure", "bist_scope_leakage"),
        ("kap_disclosure", "bist_scope_leakage"),
        ("carry_scheduler_loop", "forbidden_scope_token"),
        ("live trading", "forbidden_scope_token"),
        ("live_execution", "forbidden_scope_token"),
        ("no private_api use", "forbidden_scope_token"),
        ("api_key rotation", "forbidden_scope_token"),
        ("order_id mapping", "forbidden_scope_token"),
        ("credentials vault", "forbidden_scope_token"),
        ("auto_loop_v3", "forbidden_scope_token"),
        ("kappa decay", None),
        ("delivery basis", None),
        ("liveness of funding", None),
        ("funding_basis_carry", None),
        ("crypto_perpetuals", None),
    ],
)
def test_single_scope_policy_is_delimited(text: str, expected: str | None) -> None:
    assert edge_scope_violation(text) == expected


def test_structural_non_claim_flags_are_unique_and_only_paper_only_is_true() -> None:
    names = [name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS]
    assert len(names) == len(set(names))
    assert dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)["paper_only"] is True
    assert [name for name, value in EDGE_STRUCTURAL_NON_CLAIM_FLAGS if value] == ["paper_only"]
    for required in ("edge_proven", "profitability_proven", "live_ready", "real_orders_enabled", "scheduler_enabled"):
        assert dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)[required] is False


def test_regime_pending_pattern_constants() -> None:
    assert EDGE_REGIME_LABEL_BINDING_PENDING == "PENDING_RF_LABEL_ENUM_UNAVAILABLE"
    assert EDGE_REGIME_EVIDENCE_UNAVAILABLE == "regime_evidence_unavailable"


# --- gate-aware milestone claim profiles ----------------------------------------------------------------------------

_BASELINE_EXPECTED = (
    ("paper_only", True),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("candidate_admitted_to_paper", False),
    ("preregistration_sealed", False),
    ("kill_criteria_sealed", False),
    ("performance_data_consumed", False),
    ("oos_evidence_consumed", False),
    ("regime_evidence_available", False),
    ("current_venue_facts_consumed", False),
    ("operational_readiness", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("deribit_ready", False),
    ("private_api_ready", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
)


def test_pre_ef5_baseline_tuple_is_unchanged() -> None:
    assert EDGE_STRUCTURAL_NON_CLAIM_FLAGS == _BASELINE_EXPECTED


@pytest.mark.parametrize("gate_id", ["EF-2", "EF-3", "EF-4"])
def test_accepted_gates_keep_the_baseline_profile(gate_id: str) -> None:
    assert edge_gate_claim_profile(gate_id) == EDGE_STRUCTURAL_NON_CLAIM_FLAGS


@pytest.mark.parametrize(
    ("gate_id", "sealed", "consumed"),
    [
        ("EF-2", False, False),
        ("EF-3", False, False),
        ("EF-4", False, False),
        ("EF-5", True, False),
        ("EF-6", True, True),
    ],
)
def test_gate_profiles_raise_only_their_milestone_claims(gate_id: str, sealed: bool, consumed: bool) -> None:
    profile = dict(edge_gate_claim_profile(gate_id))
    assert profile["preregistration_sealed"] is sealed
    assert profile["performance_data_consumed"] is consumed
    assert {name: profile[name] for name, _ in EDGE_PERMANENT_NON_CLAIM_FLAGS} == dict(EDGE_PERMANENT_NON_CLAIM_FLAGS)
    assert [name for name, _ in edge_gate_claim_profile(gate_id)] == [name for name, _ in _BASELINE_EXPECTED]


def test_permanent_non_claims_exclude_only_the_milestone_flags() -> None:
    assert EDGE_MILESTONE_CLAIM_FLAG_NAMES == ("preregistration_sealed", "performance_data_consumed")
    assert dict(EDGE_PERMANENT_NON_CLAIM_FLAGS) == {
        name: value for name, value in _BASELINE_EXPECTED if name not in EDGE_MILESTONE_CLAIM_FLAG_NAMES
    }
    for name in ("edge_proven", "oos_evidence_consumed", "kill_criteria_sealed", "regime_evidence_available"):
        assert dict(EDGE_PERMANENT_NON_CLAIM_FLAGS)[name] is False


@pytest.mark.parametrize("gate_id", ["EF-1", "EF-7", "EF-8", "", "ef-5"])
def test_unknown_or_unimplemented_gates_have_no_profile(gate_id: str) -> None:
    with pytest.raises(EdgeArtifactError, match="edge_milestone_claim_gate_unknown"):
        edge_gate_claim_profile(gate_id)


@pytest.mark.parametrize(
    ("gate_id", "sealed", "consumed"),
    [
        ("EF-2", False, False),
        ("EF-5", False, False),
        ("EF-5", True, False),
        ("EF-6", False, False),
        ("EF-6", True, False),
        ("EF-6", True, True),
    ],
)
def test_milestone_claims_within_the_gate_ceiling_are_returned(gate_id: str, sealed: bool, consumed: bool) -> None:
    assert edge_gate_milestone_claims(gate_id, preregistration_sealed=sealed, performance_data_consumed=consumed) == {
        "preregistration_sealed": sealed,
        "performance_data_consumed": consumed,
    }


@pytest.mark.parametrize(
    ("gate_id", "sealed", "consumed", "code"),
    [
        ("EF-4", True, False, "edge_milestone_claim_exceeds_gate:EF-4:preregistration_sealed"),
        ("EF-5", True, True, "edge_milestone_claim_exceeds_gate:EF-5:performance_data_consumed"),
        ("EF-3", False, True, "edge_milestone_claim_exceeds_gate:EF-3:performance_data_consumed"),
        ("EF-6", False, True, "edge_milestone_claim_performance_without_sealed_preregistration"),
        ("EF-6", 1, False, "edge_milestone_claim_invalid:preregistration_sealed"),
        ("EF-6", True, None, "edge_milestone_claim_invalid:performance_data_consumed"),
    ],
)
def test_milestone_claims_above_the_ceiling_or_without_a_seal_raise(
    gate_id: str, sealed: object, consumed: object, code: str
) -> None:
    with pytest.raises(EdgeArtifactError, match=f"^{code}$"):
        edge_gate_milestone_claims(gate_id, preregistration_sealed=sealed, performance_data_consumed=consumed)  # type: ignore[arg-type]


# --- authority bindings ---------------------------------------------------------------------------------------------


def test_builder_produces_a_canonical_present_binding() -> None:
    binding = _build({"value": 1, "name": "x"})
    assert binding == EdgeAuthorityBinding(snapshot_json='{"name":"x","value":1}', expected_digest=_DIGEST)
    assert _require(binding) is binding
    assert edge_authority_binding_snapshot(binding) == {"name": "x", "value": 1}
    payload = edge_authority_binding_to_payload(binding)
    assert payload == {"expected_digest": _DIGEST, "snapshot": {"name": "x", "value": 1}}
    assert _parse(payload) == binding


@pytest.mark.parametrize("digest", [None, "", "A" * 64, "a" * 63, 7, "z" * 64])
def test_builder_rejects_a_non_hex64_anchor(digest: object) -> None:
    with pytest.raises(_KernelTestError, match=f"^{_CODE}_expected_digest_invalid$"):
        _build({"name": "x", "value": 1}, digest)


@pytest.mark.parametrize(
    "snapshot",
    [
        {},
        [],
        "text",
        None,
        {"name": "x"},
        {"name": "x", "value": "1"},
        {"name": "x", "value": True},
        {"name": "x", "value": float("nan")},
        {"name": "x", "value": {1, 2}},
        {"name": object(), "value": 1},
    ],
)
def test_builder_refuses_malformed_or_non_serializable_snapshots(snapshot: object) -> None:
    with pytest.raises(_KernelTestError, match=f"^{_CODE}_not_serializable$"):
        _build(snapshot)


def test_builder_treats_a_raising_or_non_true_shape_as_a_rejection() -> None:
    def raising(snapshot: dict) -> bool:
        raise KeyError("boom")

    def truthy(snapshot: dict) -> bool:
        return 1  # type: ignore[return-value]

    for shape in (raising, truthy):
        with pytest.raises(_KernelTestError, match="_not_serializable$"):
            build_edge_authority_binding(
                snapshot_payload={"name": "x", "value": 1},
                expected_digest=_DIGEST,
                shape=shape,
                error=_KernelTestError,
                code=_CODE,
            )


def test_require_handles_absent_optional_and_missing_required_authority() -> None:
    assert _require(None, optional=True) is None
    with pytest.raises(_KernelTestError, match=f"^{_CODE}_binding_missing$"):
        _require(None)


@pytest.mark.parametrize(
    "binding",
    [
        {"snapshot_json": '{"name":"x","value":1}', "expected_digest": _DIGEST},
        EdgeAuthorityBinding(snapshot_json="", expected_digest=""),
        EdgeAuthorityBinding(snapshot_json="", expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json="{}", expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json='{"name":"x","value":1}', expected_digest=""),
        EdgeAuthorityBinding(snapshot_json='{"name":"x","value":1}', expected_digest="A" * 64),
        EdgeAuthorityBinding(snapshot_json='{"value": 1, "name": "x"}', expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json='{"name":"x","value":NaN}', expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json='{"name":"x"}', expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json="[1]", expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json=b'{"name":"x","value":1}', expected_digest=_DIGEST),  # type: ignore[arg-type]
    ],
)
def test_require_rejects_every_partial_or_noncanonical_binding_state(binding: object) -> None:
    with pytest.raises(_KernelTestError, match=f"^{_CODE}_binding_malformed$"):
        _require(binding)


def test_require_rejects_a_hollow_binding_object() -> None:
    with pytest.raises(_KernelTestError, match=f"^{_CODE}_binding_malformed$"):
        _require(object.__new__(EdgeAuthorityBinding))


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"expected_digest": _DIGEST},
        {"expected_digest": _DIGEST, "snapshot": {"name": "x", "value": 1}, "extra": 1},
        {"expected_digest": "", "snapshot": {"name": "x", "value": 1}},
        {"expected_digest": _DIGEST, "snapshot": {}},
        {"expected_digest": _DIGEST, "snapshot": '{"name":"x","value":1}'},
        {"expected_digest": _DIGEST, "snapshot": {"name": "x", "value": "1"}},
        ["expected_digest", "snapshot"],
    ],
)
def test_parser_rejects_malformed_serialized_bindings(value: object) -> None:
    with pytest.raises(_KernelTestError, match=f"^{_CODE}_binding_malformed$"):
        _parse(value)


def test_parser_handles_absent_optional_and_missing_required_authority() -> None:
    assert _parse(None, optional=True) is None
    with pytest.raises(_KernelTestError, match=f"^{_CODE}_binding_missing$"):
        _parse(None)


_PARITY_CANDIDATES: list[tuple[object, object]] = [
    ({"name": "x", "value": 1}, _DIGEST),
    ({"value": 2, "name": "y"}, "b" * 64),
    ({}, _DIGEST),
    ({"name": "x"}, _DIGEST),
    ({"name": "x", "value": 1, "extra": None}, _DIGEST),
    ({"name": "x", "value": 1.5}, _DIGEST),
    ({"name": "x", "value": 1}, "A" * 64),
    ({"name": "x", "value": 1}, ""),
    ([{"name": "x", "value": 1}], _DIGEST),
    ("snapshot", _DIGEST),
]


@pytest.mark.parametrize(("snapshot", "digest"), _PARITY_CANDIDATES)
def test_builder_domain_equals_parser_domain(snapshot: object, digest: object) -> None:
    """RC1: BUILDER_DOMAIN_EQ_VERIFIER_REASSEMBLY_DOMAIN for authority bindings."""

    try:
        built: EdgeAuthorityBinding | None = _build(snapshot, digest)
    except _KernelTestError:
        built = None
    try:
        parsed = _parse({"expected_digest": digest, "snapshot": snapshot})
    except _KernelTestError:
        parsed = None
    assert (built is None) == (parsed is None)
    if built is not None:
        assert parsed == built
        assert _require(built) is built
        assert _parse(edge_authority_binding_to_payload(built)) == built


def test_binding_serializer_refuses_non_canonical_in_memory_states() -> None:
    """RC4: only a canonical binding serializes; a corrupted binding is never silently canonicalized."""

    assert edge_authority_binding_to_payload(None) is None
    for corrupted in (
        EdgeAuthorityBinding(snapshot_json='{"value": 1, "name": "x"}', expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json="{}", expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json="", expected_digest=_DIGEST),
        EdgeAuthorityBinding(snapshot_json='{"name":"x","value":1}', expected_digest=""),
        EdgeAuthorityBinding(snapshot_json=None, expected_digest=_DIGEST),  # type: ignore[arg-type]
    ):
        with pytest.raises(ValueError):
            edge_authority_binding_to_payload(corrupted)


# --- total verifier boundary ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Toy:
    name: str
    value: int
    toy_digest: str


def _toy_payload(toy: object) -> dict:
    return {"name": toy.name, "value": toy.value, "toy_digest": toy.toy_digest}  # type: ignore[attr-defined]


def _toy_parse(payload: dict) -> _Toy:
    if set(payload) != {"name", "value", "toy_digest"} or type(payload["value"]) is not int:
        raise ValueError("malformed")
    return _Toy(**payload)


def _toy_assemble(toy: object) -> _Toy:
    if toy.name == "boom":  # type: ignore[attr-defined]
        raise _KernelTestError("reassembly refused")
    seed = _Toy(name=toy.name, value=abs(toy.value), toy_digest="")  # type: ignore[attr-defined]
    return replace(seed, toy_digest=edge_payload_digest(_toy_payload(seed), "toy_digest"))


def _toy_verify(artifact: object, *, to_payload=_toy_payload, parse_payload=_toy_parse) -> EdgeEvidenceVerification:
    return verify_edge_artifact_total(
        artifact,
        cls=_Toy,
        to_payload=to_payload,
        parse_payload=parse_payload,
        reassemble=_toy_assemble,
        self_digest_field="toy_digest",
        reason=lambda code: f"toy:{code}",
    )


def test_total_verifier_accepts_an_assembled_artifact() -> None:
    toy = _toy_assemble(_Toy(name="ok", value=3, toy_digest=""))
    verification = _toy_verify(toy)
    assert verification.intact is True
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == toy.toy_digest
    assert json.loads(verification.canonical_json) == _toy_payload(toy)


def test_total_verifier_reports_self_digest_and_field_mismatches() -> None:
    toy = _toy_assemble(_Toy(name="ok", value=3, toy_digest=""))
    assert _toy_verify(replace(toy, toy_digest="b" * 64)).reason_codes == (
        "toy:field_mismatch:toy_digest",
        "toy:self_digest_mismatch",
    )
    tampered = replace(toy, value=-3)
    tampered = replace(tampered, toy_digest=edge_payload_digest(_toy_payload(tampered), "toy_digest"))
    assert _toy_verify(tampered).reason_codes == ("toy:field_mismatch:toy_digest", "toy:field_mismatch:value")


def test_total_verifier_reports_fields_missing_on_either_side() -> None:
    toy = _Toy(name="ok", value=-3, toy_digest="")

    def extra_when_negative(artifact: object) -> dict:
        payload = _toy_payload(artifact)
        return {**payload, "extra": 1} if payload["value"] < 0 else payload

    def parse_ignoring_extra(payload: dict) -> _Toy:
        return _toy_parse({key: value for key, value in payload.items() if key != "extra"})

    verification = _toy_verify(toy, to_payload=extra_when_negative, parse_payload=parse_ignoring_extra)
    assert "toy:field_mismatch:extra" in verification.reason_codes
    assert "toy:field_mismatch:value" in verification.reason_codes
    assert verification.intact is False


@pytest.mark.parametrize(
    ("artifact", "code"),
    [
        (None, "toy:evidence_type_invalid"),
        (1, "toy:evidence_type_invalid"),
        (object(), "toy:evidence_type_invalid"),
        ({"name": "ok", "value": 1, "toy_digest": ""}, "toy:evidence_type_invalid"),
        (object.__new__(_Toy), "toy:evidence_serialization_failed"),
        (_Toy(name="ok", value=float("nan"), toy_digest=""), "toy:evidence_serialization_failed"),  # type: ignore[arg-type]
        (_Toy(name="ok", value="1", toy_digest=""), "toy:evidence_parse_failed"),  # type: ignore[arg-type]
        (_Toy(name="boom", value=1, toy_digest=""), "toy:evidence_reassembly_failed"),
    ],
)
def test_total_verifier_never_raises_for_any_object(artifact: object, code: str) -> None:
    """RC2: VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT at the kernel boundary."""

    verification = _toy_verify(artifact)
    assert verification == EdgeEvidenceVerification(False, (code,), "", "")


# --- structural purity ----------------------------------------------------------------------------------------------

_FORBIDDEN_MODULES = (
    "math",
    "numpy",
    "pandas",
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
    "duckdb",
    "logging",
    "crypto_core",
)
_FORBIDDEN_CALLS = frozenset(
    {"open", "Path", "float", "now", "utcnow", "time", "time_ns", "perf_counter", "monotonic", "getenv", "print"}
)


def test_kernel_has_no_io_clock_randomness_float_or_repository_dependency() -> None:
    tree = ast.parse(Path(core_module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
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


def test_kernel_public_surface_is_exactly_all() -> None:
    public = {name for name in vars(core_module) if not name.startswith("_") and name not in {"annotations"}}
    imported = {"hashlib", "json", "re", "Callable", "Mapping", "Sequence", "dataclass", "Enum"}
    assert public - imported == set(core_module.__all__)
