"""Digest-bound, governance-backed binding of an authenticated StrategySpec to one code-defined executable profile.

The StrategySpec is authenticated through an accepted EF-4 ``EdgeStrategySpecAdmissionEvidence`` binding (public
verifier, caller anchor, correlation, READY), and its semantic elements are derived from the authenticated spec only:
entry, exit and invalidation conditions, feature requirements, data requirements, kill-switch triggers and risk caps.
The executable profile is resolved from the closed registry in ``strategy_executable_profiles``; its version and
semantics digest must equal the registry's recomputed constants.

Free-text StrategySpec conditions are NOT machine-equivalent to implementation semantics:
``semantic_equivalence_machine_proven`` is structurally False. The binding is a governance-backed semantic MAPPING:

* bidirectional coverage — every derived spec element maps to at least one profile element of the compatible kind,
  every coverage entry names a real spec element, and every load-bearing profile element is referenced;
* governance approval commits to the exact authenticated ``strategy_spec_digest``, ``profile_semantics_digest`` and
  coverage digest, so a copied approval never advances a different spec, profile or mapping.

Outcomes: a malformed or integrity-invalid binding (EF-4 re-proof, unknown profile, profile version or semantics digest
drift) is ``REJECTED``; a coverage gap is ``READY`` + ``FAIL``; a missing or non-matching approval is
``NEEDS_GOVERNANCE_APPROVAL``; a complete approved binding over an advancing EF-4 admission is ``READY`` + ``PASS``.
The mapping approval never approves variant parameter values: ``StrategyExecutableParameterApproval`` is the separate
exact parameter-governance authority, checked by the historical decision run before any profile execution.
One assembly path serves the builder and verifier reassembly; ``verify_strategy_executable_binding`` is total.
Historical evaluation only; proves no edge, profitability or readiness.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
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
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmissionEvidence,
    edge_strategy_spec_admission_from_payload,
    edge_strategy_spec_admission_payload_is_well_formed,
    edge_strategy_spec_admission_to_dict,
    verify_edge_strategy_spec_admission,
)
from crypto_core.validation.strategy_executable_profiles import (
    ProfileSemanticElementKind,
    StrategyExecutableProfile,
    StrategyExecutableProfileError,
    get_strategy_executable_profile,
    strategy_executable_profile_semantics_digest,
)

_SCHEMA_VERSION = "strategy-executable-binding.v1"
_REASON_PREFIX = "strategy_executable_binding"
_SELF_DIGEST_FIELD = "binding_digest"

STRATEGY_EXECUTABLE_BINDING_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("pbo_passed", False),
    ("stress_passed", False),
    ("semantic_equivalence_machine_proven", False),
    ("orders_created", False),
    ("fills_simulated", False),
    ("pnl_computed", False),
    ("performance_metrics_computed", False),
)
_FLAG_NAMES = frozenset(name for name, _ in STRATEGY_EXECUTABLE_BINDING_NON_CLAIM_FLAGS)


class StrategyExecutableBindingError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class StrategySpecElementKind(str, Enum):
    ENTRY_CONDITION = "entry_condition"
    EXIT_CONDITION = "exit_condition"
    INVALIDATION_CONDITION = "invalidation_condition"
    FEATURE_REQUIREMENT = "feature_requirement"
    DATA_REQUIREMENT = "data_requirement"
    KILL_SWITCH_TRIGGER = "kill_switch_trigger"
    RISK_CAP = "risk_cap"


_COMPATIBLE_PROFILE_KIND: dict[StrategySpecElementKind, ProfileSemanticElementKind] = {
    StrategySpecElementKind.ENTRY_CONDITION: ProfileSemanticElementKind.ENTRY,
    StrategySpecElementKind.EXIT_CONDITION: ProfileSemanticElementKind.EXIT,
    StrategySpecElementKind.INVALIDATION_CONDITION: ProfileSemanticElementKind.INVALIDATION,
    StrategySpecElementKind.FEATURE_REQUIREMENT: ProfileSemanticElementKind.FEATURE,
    StrategySpecElementKind.DATA_REQUIREMENT: ProfileSemanticElementKind.DATA_REQUIREMENT,
    StrategySpecElementKind.KILL_SWITCH_TRIGGER: ProfileSemanticElementKind.KILL_TRIGGER_SURFACE,
    StrategySpecElementKind.RISK_CAP: ProfileSemanticElementKind.SIZING,
}


@dataclass(frozen=True)
class StrategyExecutableCoverageEntry:
    """Governance mapping of one authenticated spec element to profile semantic elements."""

    spec_element_kind: StrategySpecElementKind
    spec_element_ref: str
    profile_element_ids: tuple[str, ...]


@dataclass(frozen=True)
class StrategyExecutableBindingApproval:
    """Human governance approval of one exact spec, profile and coverage mapping."""

    approval_reference: str
    approval_digest: str
    approved_strategy_spec_digest: str
    approved_profile_semantics_digest: str
    approved_coverage_digest: str


@dataclass(frozen=True)
class StrategyExecutableParameterApproval:
    """Human governance approval of one exact parameter assignment for one exact executable binding.

    Deliberately separate from ``StrategyExecutableBindingApproval`` (the semantic mapping approval). It commits to the
    executable binding digest, the authenticated StrategySpec digest, the registered profile semantics digest (which
    includes the numeric policy) and the canonical parameter assignment digest, so a changed variant parameter, spec,
    binding or profile never executes under a previous approval. It is consumed by the historical decision run.
    """

    approval_reference: str
    approval_digest: str
    approved_executable_binding_digest: str
    approved_strategy_spec_digest: str
    approved_profile_semantics_digest: str
    approved_parameter_assignment_digest: str


@dataclass(frozen=True)
class StrategyExecutableBinding:
    """Immutable, digest-bound StrategySpec → executable profile binding. Historical evaluation only."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    binding_id: str
    correlation_id: str
    admission_binding: EdgeAuthorityBinding
    admission_digest: str
    source_manifest_digest: str
    strategy_spec_digest: str
    strategy_id: str
    strategy_version: str
    instrument_universe: tuple[str, ...]
    profile_id: str
    profile_version: str
    expected_profile_semantics_digest: str
    registered_profile_semantics_digest: str
    coverage: tuple[StrategyExecutableCoverageEntry, ...]
    coverage_digest: str
    approval: StrategyExecutableBindingApproval | None
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    binding_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    preregistration_sealed: bool = False
    kill_criteria_sealed: bool = False
    performance_data_consumed: bool = False
    oos_evidence_consumed: bool = False
    regime_evidence_available: bool = False
    current_venue_facts_consumed: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    pbo_passed: bool = False
    stress_passed: bool = False
    semantic_equivalence_machine_proven: bool = False
    orders_created: bool = False
    fills_simulated: bool = False
    pnl_computed: bool = False
    performance_metrics_computed: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> StrategyExecutableBindingError:
    return StrategyExecutableBindingError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_token(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


def _canonical_coverage(values: object) -> tuple[StrategyExecutableCoverageEntry, ...]:
    if type(values) not in (tuple, list):
        raise _fail("coverage_malformed")
    canonical: dict[tuple[str, str], StrategyExecutableCoverageEntry] = {}
    for item in values:  # type: ignore[union-attr]
        if type(item) is not StrategyExecutableCoverageEntry:
            raise _fail("coverage_entry_malformed")
        kind = item.spec_element_kind
        if type(kind) is str and kind in {member.value for member in StrategySpecElementKind}:
            kind = StrategySpecElementKind(kind)
        if type(kind) is not StrategySpecElementKind:
            raise _fail("coverage_spec_element_kind_invalid")
        ref = _require_text(item.spec_element_ref, "coverage_spec_element_ref")
        if type(item.profile_element_ids) not in (tuple, list):
            raise _fail("coverage_profile_element_ids_malformed")
        element_ids = [
            _require_token(element_id, "coverage_profile_element_id") for element_id in item.profile_element_ids
        ]
        if not element_ids or len(set(element_ids)) != len(element_ids):
            raise _fail("coverage_profile_element_ids_invalid")
        key = (kind.value, ref)
        if key in canonical:
            raise _fail("coverage_entry_duplicate")
        canonical[key] = StrategyExecutableCoverageEntry(kind, ref, tuple(sorted(element_ids)))
    if not canonical:
        raise _fail("coverage_empty")
    return tuple(canonical[key] for key in sorted(canonical))


def strategy_executable_coverage_digest(coverage: object) -> str:
    """Canonical digest of a coverage mapping (order-insensitive); raises on malformed coverage."""

    return edge_sha256_text(edge_canonical_json([_to_payload(entry) for entry in _canonical_coverage(coverage)]))


def _canonical_approval(approval: object) -> StrategyExecutableBindingApproval | None:
    if approval is None:
        return None
    if type(approval) is not StrategyExecutableBindingApproval:
        raise _fail("approval_malformed")
    return StrategyExecutableBindingApproval(
        approval_reference=_require_text(approval.approval_reference, "approval_reference"),
        approval_digest=_require_hex64(approval.approval_digest, "approval_digest"),
        approved_strategy_spec_digest=_require_hex64(
            approval.approved_strategy_spec_digest, "approved_strategy_spec_digest"
        ),
        approved_profile_semantics_digest=_require_hex64(
            approval.approved_profile_semantics_digest, "approved_profile_semantics_digest"
        ),
        approved_coverage_digest=_require_hex64(approval.approved_coverage_digest, "approved_coverage_digest"),
    )


def canonical_strategy_executable_parameter_approval(approval: object) -> StrategyExecutableParameterApproval | None:
    """Structurally validate a parameter approval (``None`` stays ``None``); raises on any malformed state.

    Structural only: whether the approval MATCHES a binding, spec, profile and assignment is decided by its consumer.
    """

    if approval is None:
        return None
    if type(approval) is not StrategyExecutableParameterApproval:
        raise _fail("parameter_approval_malformed")
    return StrategyExecutableParameterApproval(
        approval_reference=_require_text(getattr(approval, "approval_reference", None), "parameter_approval_reference"),
        approval_digest=_require_hex64(getattr(approval, "approval_digest", None), "parameter_approval_digest"),
        approved_executable_binding_digest=_require_hex64(
            getattr(approval, "approved_executable_binding_digest", None), "approved_executable_binding_digest"
        ),
        approved_strategy_spec_digest=_require_hex64(
            getattr(approval, "approved_strategy_spec_digest", None), "parameter_approved_strategy_spec_digest"
        ),
        approved_profile_semantics_digest=_require_hex64(
            getattr(approval, "approved_profile_semantics_digest", None), "parameter_approved_profile_semantics_digest"
        ),
        approved_parameter_assignment_digest=_require_hex64(
            getattr(approval, "approved_parameter_assignment_digest", None), "approved_parameter_assignment_digest"
        ),
    )


# --- authorities -------------------------------------------------------------------------------------------------------


def _admission_authority(
    binding: EdgeAuthorityBinding, *, correlation_id: str
) -> tuple[list[str], EdgeStrategySpecAdmissionEvidence | None, StrategySpec | None]:
    admission = edge_strategy_spec_admission_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_strategy_spec_admission(admission)
    if not verification.intact:
        return [_reason(f"admission_integrity_failure:{code}") for code in verification.reason_codes], None, None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("admission_digest_mismatch")], None, None
    if admission.correlation_id != correlation_id:
        return [_reason("admission_correlation_mismatch")], None, None
    if admission.status is not EdgeEvidenceStatus.READY:
        return [_reason("admission_rejected")], None, None
    result = validate_strategy_spec(edge_authority_binding_snapshot(admission.strategy_spec_binding))
    if result.accepted is not True or type(result.spec) is not StrategySpec:
        return [_reason("admission_strategy_spec_not_accepted")], None, None
    return [], admission, result.spec


def _spec_elements(spec: StrategySpec) -> set[tuple[str, str]]:
    elements: set[tuple[str, str]] = set()
    for kind, refs in (
        (StrategySpecElementKind.ENTRY_CONDITION, spec.entry_conditions),
        (StrategySpecElementKind.EXIT_CONDITION, spec.exit_conditions),
        (StrategySpecElementKind.INVALIDATION_CONDITION, spec.invalidation_conditions),
        (StrategySpecElementKind.FEATURE_REQUIREMENT, tuple(spec.feature_requirements)),
        (StrategySpecElementKind.DATA_REQUIREMENT, tuple(spec.data_requirements)),
        (StrategySpecElementKind.KILL_SWITCH_TRIGGER, spec.kill_switch_triggers),
        (StrategySpecElementKind.RISK_CAP, tuple(spec.risk_caps)),
    ):
        elements.update((kind.value, ref) for ref in refs)
    return elements


def _coverage_reasons(
    spec: StrategySpec, profile: StrategyExecutableProfile, coverage: Sequence[StrategyExecutableCoverageEntry]
) -> list[str]:
    fail: list[str] = []
    spec_elements = _spec_elements(spec)
    profile_elements = {element.element_id: element for element in profile.semantic_elements}
    covered_spec: set[tuple[str, str]] = set()
    referenced: set[str] = set()
    for entry in coverage:
        key = (entry.spec_element_kind.value, entry.spec_element_ref)
        if key not in spec_elements:
            fail.append(_reason(f"coverage_spec_element_unknown:{key[0]}:{key[1]}"))
        else:
            covered_spec.add(key)
        for element_id in entry.profile_element_ids:
            element = profile_elements.get(element_id)
            if element is None:
                fail.append(_reason(f"coverage_profile_element_unknown:{element_id}"))
                continue
            referenced.add(element_id)
            if element.kind is not _COMPATIBLE_PROFILE_KIND[entry.spec_element_kind]:
                fail.append(_reason(f"coverage_kind_mismatch:{key[0]}:{key[1]}:{element_id}"))
    fail.extend(_reason(f"spec_element_uncovered:{kind}:{ref}") for kind, ref in sorted(spec_elements - covered_spec))
    fail.extend(
        _reason(f"profile_element_uncovered:{element.element_id}")
        for element in profile.semantic_elements
        if element.load_bearing and element.element_id not in referenced
    )
    return fail


# --- binding -----------------------------------------------------------------------------------------------------------


def _assemble_binding(
    *,
    admission_binding: object,
    binding_id: object,
    correlation_id: object,
    profile_id: object,
    profile_version: object,
    expected_profile_semantics_digest: object,
    coverage: object,
    approval: object,
) -> StrategyExecutableBinding:
    """The one binding assembly path, shared by the builder and verifier reassembly."""

    admission_ref = require_edge_authority_binding(
        admission_binding,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=StrategyExecutableBindingError,
        code=_reason("admission"),
        optional=False,
    )
    binding_id = _require_text(binding_id, "binding_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    profile_id = _require_token(profile_id, "profile_id")
    profile_version = _require_token(profile_version, "profile_version")
    expected_digest = _require_hex64(expected_profile_semantics_digest, "expected_profile_semantics_digest")
    entries = _canonical_coverage(coverage)
    coverage_digest = edge_sha256_text(edge_canonical_json([_to_payload(entry) for entry in entries]))
    approval_record = _canonical_approval(approval)

    admission_codes, admission, spec = _admission_authority(admission_ref, correlation_id=correlation_id)  # type: ignore[arg-type]
    codes = list(admission_codes)
    try:
        profile: StrategyExecutableProfile | None = get_strategy_executable_profile(profile_id)
    except StrategyExecutableProfileError:
        profile = None
        codes.append(_reason("profile_unknown"))
    registered_digest = "" if profile is None else strategy_executable_profile_semantics_digest(profile)
    if profile is not None:
        if profile.profile_version != profile_version:
            codes.append(_reason("profile_version_mismatch"))
        if registered_digest != expected_digest or registered_digest != profile.profile_semantics_digest:
            codes.append(_reason("profile_semantics_digest_mismatch"))
    integrity = _sorted_unique(codes)

    if integrity or admission is None or spec is None or profile is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        fail = _coverage_reasons(spec, profile, entries)
        needs_external: list[str] = []
        needs_governance: list[str] = []
        if admission.advances is not True:
            code = _reason(f"admission_not_advanced:{admission.gate_verdict.value}")
            if admission.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
                needs_external.append(code)
            elif admission.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
                needs_governance.append(code)
            else:
                fail.append(code)
        if approval_record is None:
            needs_governance.append(_reason("approval_missing"))
        else:
            if approval_record.approved_strategy_spec_digest != admission.strategy_spec_digest:
                needs_governance.append(_reason("approval_strategy_spec_digest_mismatch"))
            if approval_record.approved_profile_semantics_digest != registered_digest:
                needs_governance.append(_reason("approval_profile_semantics_digest_mismatch"))
            if approval_record.approved_coverage_digest != coverage_digest:
                needs_governance.append(_reason("approval_coverage_digest_mismatch"))
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    seed = StrategyExecutableBinding(
        schema_version=_SCHEMA_VERSION,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        binding_id=binding_id,
        correlation_id=correlation_id,
        admission_binding=admission_ref,  # type: ignore[arg-type]
        admission_digest=admission_ref.expected_digest,  # type: ignore[union-attr]
        source_manifest_digest="" if admission is None else admission.predecessor_digest,
        strategy_spec_digest="" if admission is None else admission.strategy_spec_digest,
        strategy_id="" if spec is None else spec.strategy_id,
        strategy_version="" if spec is None else spec.strategy_version,
        instrument_universe=() if spec is None else spec.instrument_universe,
        profile_id=profile_id,
        profile_version=profile_version,
        expected_profile_semantics_digest=expected_digest,
        registered_profile_semantics_digest=registered_digest,
        coverage=entries,
        coverage_digest=coverage_digest,
        approval=approval_record,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        binding_digest="",
    )
    return replace(seed, binding_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_strategy_executable_binding(
    admission: EdgeStrategySpecAdmissionEvidence,
    *,
    expected_admission_digest: str,
    binding_id: str,
    correlation_id: str,
    profile_id: str,
    profile_version: str,
    expected_profile_semantics_digest: str,
    coverage: Sequence[StrategyExecutableCoverageEntry],
    approval: StrategyExecutableBindingApproval | None = None,
) -> StrategyExecutableBinding:
    """Build a governance-backed StrategySpec → executable profile binding over an authenticated EF-4 admission.

    Malformed caller input or a non-serializable upstream object raises ``StrategyExecutableBindingError``.
    """

    if type(admission) is not EdgeStrategySpecAdmissionEvidence:
        raise _fail("admission_malformed")
    try:
        admission_payload = edge_strategy_spec_admission_to_dict(admission)
    except Exception as exc:  # noqa: BLE001 - a hollow admission object is a construction error, never a receipt
        raise _fail("admission_not_serializable") from exc
    admission_ref = build_edge_authority_binding(
        snapshot_payload=admission_payload,
        expected_digest=expected_admission_digest,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=StrategyExecutableBindingError,
        code=_reason("admission"),
    )
    return _assemble_binding(
        admission_binding=admission_ref,
        binding_id=binding_id,
        correlation_id=correlation_id,
        profile_id=profile_id,
        profile_version=profile_version,
        expected_profile_semantics_digest=expected_profile_semantics_digest,
        coverage=coverage,
        approval=approval,
    )


def strategy_executable_binding_to_dict(binding: StrategyExecutableBinding) -> dict[str, object]:
    """Canonical JSON-ready mapping for a binding, including its self-digest."""

    return _to_payload(binding)


def strategy_executable_binding_digest(binding: StrategyExecutableBinding) -> str:
    """Recompute the canonical binding digest, excluding only ``binding_digest``."""

    return edge_payload_digest(_to_payload(binding), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_str(item) for item in value)


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_coverage(value: object) -> tuple[object, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    converters = {"spec_element_kind": _as_enum(StrategySpecElementKind), "profile_element_ids": _as_str_tuple}
    return tuple(_parse_exact(StrategyExecutableCoverageEntry, entry, converters) for entry in value)


def _as_approval(value: object) -> object:
    return None if value is None else _parse_exact(StrategyExecutableBindingApproval, value, {})


def _parse_admission_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=StrategyExecutableBindingError,
        code=_reason("admission"),
        optional=False,
    )


_BINDING_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "admission_binding": _parse_admission_binding,
    "instrument_universe": _as_str_tuple,
    "coverage": _as_coverage,
    "approval": _as_approval,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def strategy_executable_binding_from_payload(payload: object) -> StrategyExecutableBinding:
    """Strictly reconstruct a binding from its serialized payload (exact fields and types; no semantic proof)."""

    return _parse_exact(StrategyExecutableBinding, payload, _BINDING_CONVERTERS)  # type: ignore[return-value]


def strategy_executable_binding_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a StrategyExecutableBinding snapshot."""

    try:
        strategy_executable_binding_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_binding(binding: object) -> StrategyExecutableBinding:
    return _assemble_binding(
        admission_binding=binding.admission_binding,  # type: ignore[attr-defined]
        binding_id=binding.binding_id,  # type: ignore[attr-defined]
        correlation_id=binding.correlation_id,  # type: ignore[attr-defined]
        profile_id=binding.profile_id,  # type: ignore[attr-defined]
        profile_version=binding.profile_version,  # type: ignore[attr-defined]
        expected_profile_semantics_digest=binding.expected_profile_semantics_digest,  # type: ignore[attr-defined]
        coverage=binding.coverage,  # type: ignore[attr-defined]
        approval=binding.approval,  # type: ignore[attr-defined]
    )


def verify_strategy_executable_binding(binding: object) -> EdgeEvidenceVerification:
    """Re-prove a binding by strict parse, EF-4 and registry re-proof and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        binding,
        cls=StrategyExecutableBinding,
        to_payload=_to_payload,
        parse_payload=strategy_executable_binding_from_payload,
        reassemble=_reassemble_binding,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "STRATEGY_EXECUTABLE_BINDING_NON_CLAIM_FLAGS",
    "StrategyExecutableBinding",
    "StrategyExecutableBindingApproval",
    "StrategyExecutableBindingError",
    "StrategyExecutableCoverageEntry",
    "StrategyExecutableParameterApproval",
    "StrategySpecElementKind",
    "build_strategy_executable_binding",
    "canonical_strategy_executable_parameter_approval",
    "strategy_executable_binding_digest",
    "strategy_executable_binding_from_payload",
    "strategy_executable_binding_payload_is_well_formed",
    "strategy_executable_binding_to_dict",
    "strategy_executable_coverage_digest",
    "verify_strategy_executable_binding",
]
