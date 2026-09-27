"""Edge Factory EF-5: deterministic preregistration ledger and leakage/bias firewall, sealed BEFORE any performance.

EF-5 pins, over an authenticated EF-4 StrategySpec admission and its EF-2 root, everything a later gate may interpret:
the feature set, the finite parameter search space, the registered variant ledger (the multiple-testing counter), the
decision label/threshold structure, and structured lookahead, repaint and survivorship proofs. It consumes NO
performance data: no metric, return, walk-forward, out-of-sample, PBO or stress artifact is imported, accepted or read,
and no variant is ranked or chosen. A later gate may interpret results only for a parameter assignment whose digest is
in ``registered_parameter_assignment_digests`` of a sealed EF-5 artifact.

Trust model (shared kernel ``edge_artifact_core``):

* Dual anchor. EF-4 is the immediate predecessor: a required ``EdgeAuthorityBinding`` re-proven through
  ``verify_edge_strategy_spec_admission`` against the caller's predecessor anchor. The rest of the chain is re-proven
  through the public verifiers: the EF-3 manifest nested in EF-4 (``verify_edge_source_packet_evidence``) and the EF-2
  root nested in EF-3 (``verify_edge_idea_intake_evidence``), whose digest must equal the explicit root anchor, the
  EF-4 root field and the EF-3 root field. Every link must be READY and share this artifact's correlation.
* Auxiliary executable authority. Parameter legality is owned by the closed profile registry, so a
  ``StrategyExecutableBinding`` is required: re-proven through ``verify_strategy_executable_binding`` against its
  anchor, READY, same correlation, and bound to EXACTLY the authenticated EF-4 admission digest and StrategySpec
  digest. The profile is resolved from the closed registry; its version and recomputed semantics digest must equal the
  binding's. EF-4 remains the Edge Factory predecessor; the binding never replaces it.
* Feature set. The preregistered feature ids must EQUAL the feature requirements of the authenticated StrategySpec (no
  insertion, no omission); the profile FEATURE elements are derived from the binding coverage, never from the caller.
* Parameter search space. Each profile parameter needs one bound, FIXED (exactly one value) or SEARCHED (two or more
  values). Ids, kinds, grammar, representation limits and constraints belong to the registered profile. A parameter
  without a bound, or an empty ledger, is governance input still pending (NEEDS_GOVERNANCE_APPROVAL); nothing is
  defaulted and no parameter value is invented here.
* Variant ledger. Each registered variant is a complete assignment accepted by the registered profile through
  ``canonical_profile_parameter_assignment``; its digest is derived through ``profile_parameter_assignment_digest`` and
  never supplied by the caller. Every variant value lies inside its bound and, for a non-empty ledger, every bound value
  is exercised by a registered variant: a PASS therefore proves every preregistered search value profile-valid through
  the registry's own validator and the declared search space equal to the registered trial space.
  ``multiple_testing_count`` is the ledger cardinality.
* Decision structure. Labels, decision elements, schedule, state rule, parameter schema, constraints and the approved
  coverage mapping are derived from the registered profile and the binding; threshold VALUES live only in the ledger.
* Bias proofs. LOOKAHEAD and REPAINT are proven only from authenticated EF-3 facts (registry-owned time policies,
  finalized-only discipline, point-in-time revision safety, feature-input eligibility, instrument coverage) and the
  registered decision schedule; every profile input needs exactly one eligible source series per pinned instrument,
  so no later gate can choose between candidate sources after seeing results. SURVIVORSHIP is proven only within the
  declared claim scope: a pinned-universe claim rests on the admitted instrument list and manifest coverage and carries
  explicit limitations, while a cross-sectional claim needs point-in-time universe membership that no authenticated
  authority holds (NEEDS_EXTERNAL_FACTS). A check failing on authenticated evidence is FAIL. No proof outcome exceeds
  its evidence.
* Governance. ``EdgePreregistrationApproval`` commits to the root, predecessor, spec, binding, profile semantics,
  feature set, parameter bounds, variant ledger, decision structure and bias-proof set digests; a missing or
  non-matching approval is NEEDS_GOVERNANCE_APPROVAL.
* ``status`` is integrity only and ``gate_verdict`` the outcome; REJECTED implies NOT_EVALUATED; only READY + PASS
  advances, and ``preregistration_sealed`` is True exactly then. One assembly path serves the builder and verifier
  reassembly; ``verify_edge_leakage_bias_evidence`` is total. Paper-only, deterministic, no IO/clock/network/float.
  EF-5 proves preregistration discipline only: never an edge, profitability, results, PBO, stress, walk-forward or
  out-of-sample quality, paper admission, readiness or any live authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
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
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeIdeaIntakeEvidence,
    edge_idea_intake_evidence_from_payload,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    EdgeSourceSeriesRecord,
    edge_source_packet_evidence_from_payload,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmissionEvidence,
    edge_strategy_spec_admission_from_payload,
    edge_strategy_spec_admission_payload_is_well_formed,
    edge_strategy_spec_admission_to_dict,
    verify_edge_strategy_spec_admission,
)
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableBinding,
    StrategySpecElementKind,
    strategy_executable_binding_from_payload,
    strategy_executable_binding_payload_is_well_formed,
    strategy_executable_binding_to_dict,
    verify_strategy_executable_binding,
)
from crypto_core.validation.strategy_executable_profiles import (
    ProfileAction,
    ProfileParameterAssignment,
    ProfileSemanticElementKind,
    StrategyExecutableProfile,
    StrategyExecutableProfileError,
    canonical_profile_parameter_assignment,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
    strategy_executable_profile_semantics_digest,
)

_SCHEMA_VERSION = "edge-leakage-bias-evidence.v1"
_GATE_ID = "EF-5"
_PREDECESSOR_GATE_ID = "EF-4"
_REASON_PREFIX = "edge_leakage_bias_evidence"
_SELF_DIGEST_FIELD = "leakage_bias_evidence_digest"
# Caller-text safety bound for a parameter value (the token length bound of the Edge Factory gates). It never decides
# whether a value is acceptable: the registered profile's numeric policy does, with far tighter representation limits.
_MAX_PARAMETER_VALUE_LENGTH = 128
# Decision schedules whose decision instant is max(available_at_ns, finalized_at_ns) of a triggering record and whose
# visible history holds only records available AND finalized at or before that instant. A registered profile using any
# other schedule cannot be proven lookahead- or repaint-safe here and FAILs until its schedule is recognized.
_POINT_IN_TIME_VISIBLE_DECISION_SCHEDULES = frozenset({"final_funding_record_max_available_finalized.v1"})
_DECISION_STRUCTURE_EXCLUDED_KINDS = (ProfileSemanticElementKind.FEATURE, ProfileSemanticElementKind.DATA_REQUIREMENT)
_LOOKAHEAD_CLAIM_ID = "lookahead.point_in_time_finalized_inputs_and_visible_decision_schedule.v1"
_REPAINT_CLAIM_ID = "repaint.finalized_revision_safe_inputs_and_visible_decision_schedule.v1"
_SURVIVORSHIP_PINNED_CLAIM_ID = "survivorship.pinned_admitted_instrument_universe_fixed_ex_ante.v1"
_SURVIVORSHIP_CROSS_SECTION_CLAIM_ID = "survivorship.edge_family_cross_section_point_in_time_membership.v1"
_LOOKAHEAD_LIMITATIONS = ("record_level_visibility_enforced_by_downstream_point_in_time_views",)
_REPAINT_LIMITATIONS = ("record_level_vintage_selection_enforced_by_downstream_point_in_time_views",)
_SURVIVORSHIP_PINNED_LIMITATIONS = (
    "cross_sectional_generalization_not_claimed",
    "instrument_listing_lifecycle_not_evaluated",
)
_SURVIVORSHIP_CROSS_SECTION_LIMITATIONS = ("point_in_time_universe_membership_authority_unavailable",)

# Structural non-claims of EF-5: the shared Edge Factory flags except ``preregistration_sealed`` (the one milestone EF-5
# computes) plus the performance-evaluation flags a preregistration can never raise. Defaults no builder can set.
EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *(flag for flag in EDGE_STRUCTURAL_NON_CLAIM_FLAGS if flag[0] != "preregistration_sealed"),
    ("pbo_passed", False),
    ("stress_passed", False),
    ("walk_forward_evaluated", False),
    ("performance_metrics_computed", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS)
_INT64_BIT_LENGTH = 63


class EdgeLeakageBiasEvidenceError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class EdgeParameterSearchTreatment(str, Enum):
    """Preregistration treatment of one profile parameter."""

    FIXED = "fixed"
    SEARCHED = "searched"


class EdgeSurvivorshipClaimScope(str, Enum):
    """The population a later performance claim may speak about; it decides what survivorship evidence is needed."""

    PINNED_INSTRUMENT_UNIVERSE = "pinned_instrument_universe"
    EDGE_FAMILY_CROSS_SECTION = "edge_family_cross_section"


class EdgeBiasProofKind(str, Enum):
    LOOKAHEAD = "lookahead"
    REPAINT = "repaint"
    SURVIVORSHIP = "survivorship"


class EdgeBiasProofOutcome(str, Enum):
    """Outcome of one structured check or proof. PROVEN never exceeds what the named authority proves."""

    PROVEN = "PROVEN"
    FAILED = "FAILED"
    NEEDS_EXTERNAL_FACTS = "NEEDS_EXTERNAL_FACTS"


@dataclass(frozen=True)
class EdgeParameterSearchBound:
    """Preregistered finite search set of one profile parameter, as canonical profile value texts."""

    parameter_id: str
    treatment: EdgeParameterSearchTreatment | str
    values: tuple[str, ...]


@dataclass(frozen=True)
class EdgeInputVariant:
    """Caller declaration of one variant to be tried: an id and a complete parameter assignment, and no digest."""

    variant_id: str
    parameter_assignment: tuple[ProfileParameterAssignment, ...]


@dataclass(frozen=True)
class EdgeRegisteredVariant:
    """One ledger entry: the assignment ordered by parameter id and its derived ``profile_parameter_assignment_digest``."""

    variant_id: str
    parameter_assignment: tuple[ProfileParameterAssignment, ...]
    parameter_assignment_digest: str


@dataclass(frozen=True)
class EdgeBiasCheck:
    """One machine-evaluated predicate over one authenticated subject (series id, instrument, schedule or scope)."""

    check_id: str
    subject: str
    outcome: EdgeBiasProofOutcome


@dataclass(frozen=True)
class EdgeBiasProof:
    """One structured bias proof: its closed claim, the authority digests it reads, its checks and its limitations."""

    proof_kind: EdgeBiasProofKind
    claim_id: str
    outcome: EdgeBiasProofOutcome
    authority_digests: tuple[str, ...]
    checks: tuple[EdgeBiasCheck, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class EdgePreregistrationApproval:
    """Human governance approval of one exact preregistration; every committed digest must match to advance."""

    approval_reference: str
    approval_digest: str
    approved_root_intake_digest: str
    approved_predecessor_digest: str
    approved_strategy_spec_digest: str
    approved_executable_binding_digest: str
    approved_profile_semantics_digest: str
    approved_feature_set_digest: str
    approved_parameter_bounds_digest: str
    approved_variant_ledger_digest: str
    approved_decision_structure_digest: str
    approved_bias_proof_set_digest: str


_APPROVAL_COMMITMENTS = (
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


@dataclass(frozen=True)
class EdgeLeakageBiasEvidence:
    """Immutable, digest-bound EF-5 preregistration. PAPER ONLY; proves preregistration discipline, never an edge."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    preregistration_sealed: bool
    preregistration_id: str
    correlation_id: str
    root_intake_digest: str
    predecessor_binding: EdgeAuthorityBinding
    predecessor_gate_id: str
    predecessor_digest: str
    source_manifest_digest: str
    candidate_strategy_id: str
    edge_family: str
    strategy_spec_digest: str
    strategy_id: str
    strategy_version: str
    pinned_instrument_universe: tuple[str, ...]
    executable_binding: EdgeAuthorityBinding
    executable_binding_digest: str
    profile_id: str
    profile_version: str
    profile_semantics_digest: str
    feature_ids: tuple[str, ...]
    strategy_feature_ids: tuple[str, ...]
    profile_feature_element_ids: tuple[str, ...]
    feature_set_digest: str
    parameter_bounds: tuple[EdgeParameterSearchBound, ...]
    parameter_bounds_digest: str
    registered_variants: tuple[EdgeRegisteredVariant, ...]
    registered_parameter_assignment_digests: tuple[str, ...]
    multiple_testing_count: int
    variant_ledger_digest: str
    decision_schedule_id: str
    state_rule_id: str
    decision_labels: tuple[str, ...]
    decision_element_refs: tuple[str, ...]
    parameter_schema_refs: tuple[str, ...]
    parameter_constraints: tuple[str, ...]
    binding_coverage_digest: str
    decision_structure_digest: str
    survivorship_claim_scope: EdgeSurvivorshipClaimScope
    bias_proofs: tuple[EdgeBiasProof, ...]
    bias_proof_set_digest: str
    approval: EdgePreregistrationApproval | None
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    leakage_bias_evidence_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
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
    walk_forward_evaluated: bool = False
    performance_metrics_computed: bool = False


@dataclass(frozen=True)
class _DerivedFacts:
    """Everything EF-5 derives from re-proven authority; the defaults are the REJECTED (unevaluated) state."""

    source_manifest_digest: str = ""
    candidate_strategy_id: str = ""
    edge_family: str = ""
    strategy_spec_digest: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    pinned_instrument_universe: tuple[str, ...] = ()
    profile_id: str = ""
    profile_version: str = ""
    profile_semantics_digest: str = ""
    strategy_feature_ids: tuple[str, ...] = ()
    profile_feature_element_ids: tuple[str, ...] = ()
    decision_schedule_id: str = ""
    state_rule_id: str = ""
    decision_labels: tuple[str, ...] = ()
    decision_element_refs: tuple[str, ...] = ()
    parameter_schema_refs: tuple[str, ...] = ()
    parameter_constraints: tuple[str, ...] = ()
    binding_coverage_digest: str = ""
    bias_proofs: tuple[EdgeBiasProof, ...] = ()


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeLeakageBiasEvidenceError:
    return EdgeLeakageBiasEvidenceError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


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


def _require_parameter_value(value: object) -> str:
    """Structural text check only; profile grammar, kind and representation limits are decided by the registry."""

    if type(value) is not str or not value or len(value) > _MAX_PARAMETER_VALUE_LENGTH:
        raise _fail("parameter_value_invalid")
    if any(not ("!" <= char <= "~") for char in value):
        raise _fail("parameter_value_invalid")
    return _require_text(value, "parameter_value")


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str:
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise _fail(f"{field_name}_invalid") from exc
    raise _fail(f"{field_name}_invalid")


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize a record; an enum-typed field must hold the exact enum member, never an equal plain string."""

    for name, enum_cls in _ENUM_FIELDS.get(type(artifact), ()):
        if type(getattr(artifact, name)) is not enum_cls:
            raise _fail("payload_enum_field_not_exact_member")
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


_RECORD_TYPES = frozenset(
    {
        EdgeParameterSearchBound,
        EdgeRegisteredVariant,
        ProfileParameterAssignment,
        EdgeBiasCheck,
        EdgeBiasProof,
        EdgePreregistrationApproval,
    }
)
_ENUM_FIELDS: dict[type, tuple[tuple[str, type[Enum]], ...]] = {
    EdgeLeakageBiasEvidence: (
        ("status", EdgeEvidenceStatus),
        ("gate_verdict", EdgeGateVerdict),
        ("survivorship_claim_scope", EdgeSurvivorshipClaimScope),
    ),
    EdgeParameterSearchBound: (("treatment", EdgeParameterSearchTreatment),),
    EdgeBiasCheck: (("outcome", EdgeBiasProofOutcome),),
    EdgeBiasProof: (("proof_kind", EdgeBiasProofKind), ("outcome", EdgeBiasProofOutcome)),
}


# --- caller declarations -----------------------------------------------------------------------------------------------


def _canonical_feature_ids(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise _fail("feature_ids_malformed")
    ids: set[str] = set()
    for item in values:  # type: ignore[union-attr]
        feature_id = _require_text(item, "feature_id")
        if feature_id in ids:
            raise _fail("feature_id_duplicate")
        ids.add(feature_id)
    return tuple(sorted(ids))


def _canonical_bounds(values: object) -> tuple[EdgeParameterSearchBound, ...]:
    if type(values) not in (tuple, list):
        raise _fail("parameter_bounds_malformed")
    canonical: dict[str, EdgeParameterSearchBound] = {}
    for item in values:  # type: ignore[union-attr]
        if type(item) is not EdgeParameterSearchBound:
            raise _fail("parameter_bound_malformed")
        parameter_id = _require_token(getattr(item, "parameter_id", None), "parameter_bound_id")
        if parameter_id in canonical:
            raise _fail("parameter_bound_duplicate")
        treatment = _require_member(
            getattr(item, "treatment", None), EdgeParameterSearchTreatment, "parameter_bound_treatment"
        )
        raw_values = getattr(item, "values", None)
        if type(raw_values) not in (tuple, list):
            raise _fail("parameter_bound_values_malformed")
        bound_values: set[str] = set()
        for value in raw_values:  # type: ignore[union-attr]
            text = _require_parameter_value(value)
            if text in bound_values:
                raise _fail("parameter_bound_value_duplicate")
            bound_values.add(text)
        if not bound_values:
            raise _fail("parameter_bound_values_empty")
        if treatment is EdgeParameterSearchTreatment.FIXED and len(bound_values) != 1:
            raise _fail("parameter_bound_treatment_inconsistent")
        if treatment is EdgeParameterSearchTreatment.SEARCHED and len(bound_values) < 2:
            raise _fail("parameter_bound_treatment_inconsistent")
        canonical[parameter_id] = EdgeParameterSearchBound(
            parameter_id=parameter_id, treatment=treatment, values=tuple(sorted(bound_values))
        )
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_assignment(values: object) -> tuple[ProfileParameterAssignment, ...]:
    if type(values) not in (tuple, list):
        raise _fail("variant_parameter_assignment_malformed")
    entries: dict[str, ProfileParameterAssignment] = {}
    for item in values:  # type: ignore[union-attr]
        if type(item) is not ProfileParameterAssignment:
            raise _fail("variant_parameter_assignment_entry_malformed")
        parameter_id = _require_token(getattr(item, "parameter_id", None), "variant_parameter_id")
        if parameter_id in entries:
            raise _fail("variant_parameter_duplicate")
        value = _require_parameter_value(getattr(item, "value", None))
        entries[parameter_id] = ProfileParameterAssignment(parameter_id=parameter_id, value=value)
    if not entries:
        raise _fail("variant_parameter_assignment_empty")
    return tuple(entries[key] for key in sorted(entries))


def _canonical_variants(values: object) -> tuple[EdgeRegisteredVariant, ...]:
    """Structural canonical ledger; each digest is ``profile_parameter_assignment_digest`` of the ordered assignment."""

    if type(values) not in (tuple, list):
        raise _fail("variants_malformed")
    canonical: dict[str, EdgeRegisteredVariant] = {}
    digests: set[str] = set()
    for item in values:  # type: ignore[union-attr]
        if type(item) is not EdgeInputVariant:
            raise _fail("variant_malformed")
        variant_id = _require_token(getattr(item, "variant_id", None), "variant_id")
        if variant_id in canonical:
            raise _fail("variant_id_duplicate")
        assignment = _canonical_assignment(getattr(item, "parameter_assignment", None))
        digest = profile_parameter_assignment_digest(assignment)
        if digest in digests:
            raise _fail("variant_assignment_duplicate")
        digests.add(digest)
        canonical[variant_id] = EdgeRegisteredVariant(
            variant_id=variant_id, parameter_assignment=assignment, parameter_assignment_digest=digest
        )
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_approval(approval: object) -> EdgePreregistrationApproval | None:
    if approval is None:
        return None
    if type(approval) is not EdgePreregistrationApproval:
        raise _fail("approval_malformed")
    return EdgePreregistrationApproval(
        approval_reference=_require_text(getattr(approval, "approval_reference", None), "approval_reference"),
        approval_digest=_require_hex64(getattr(approval, "approval_digest", None), "approval_digest"),
        **{
            f"approved_{name}": _require_hex64(getattr(approval, f"approved_{name}", None), f"approved_{name}")
            for name in _APPROVAL_COMMITMENTS
        },
    )


# --- upstream authorities ----------------------------------------------------------------------------------------------


def _chain_authority(
    binding: EdgeAuthorityBinding, *, root_intake_digest: str, correlation_id: str
) -> tuple[
    list[str],
    tuple[EdgeStrategySpecAdmissionEvidence, EdgeSourcePacketEvidence, EdgeIdeaIntakeEvidence, StrategySpec] | None,
]:
    """Re-prove EF-4 → EF-3 → EF-2 through the public verifiers against both anchors and the correlation."""

    admission = edge_strategy_spec_admission_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_strategy_spec_admission(admission)
    if not verification.intact:
        return [_reason(f"predecessor_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("predecessor_digest_mismatch")], None
    if admission.correlation_id != correlation_id:
        return [_reason("predecessor_correlation_mismatch")], None
    if admission.status is not EdgeEvidenceStatus.READY:
        return [_reason("predecessor_rejected")], None
    manifest = edge_source_packet_evidence_from_payload(edge_authority_binding_snapshot(admission.predecessor_binding))
    manifest_verification = verify_edge_source_packet_evidence(manifest)
    if not manifest_verification.intact:
        return [
            _reason(f"source_manifest_integrity_failure:{code}") for code in manifest_verification.reason_codes
        ], None
    if (
        manifest_verification.recomputed_digest != admission.predecessor_digest
        or manifest.correlation_id != correlation_id
        or manifest.status is not EdgeEvidenceStatus.READY
    ):
        return [_reason("source_manifest_chain_mismatch")], None
    root = edge_idea_intake_evidence_from_payload(edge_authority_binding_snapshot(manifest.root_intake_binding))
    root_verification = verify_edge_idea_intake_evidence(root)
    if not root_verification.intact:
        return [_reason(f"root_intake_integrity_failure:{code}") for code in root_verification.reason_codes], None
    if (
        root_verification.recomputed_digest != root_intake_digest
        or admission.root_intake_digest != root_intake_digest
        or manifest.root_intake_digest != root_intake_digest
    ):
        return [_reason("chain_splice_root_intake_mismatch")], None
    if root.correlation_id != correlation_id or root.status is not EdgeEvidenceStatus.READY:
        return [_reason("root_intake_chain_mismatch")], None
    result = validate_strategy_spec(edge_authority_binding_snapshot(admission.strategy_spec_binding))
    if result.accepted is not True or type(result.spec) is not StrategySpec:
        return [_reason("predecessor_strategy_spec_not_accepted")], None
    return [], (admission, manifest, root, result.spec)


def _executable_authority(
    binding: EdgeAuthorityBinding,
    *,
    correlation_id: str,
    predecessor_digest: str,
    admission: EdgeStrategySpecAdmissionEvidence | None,
) -> tuple[list[str], StrategyExecutableBinding | None, StrategyExecutableProfile | None]:
    """Re-prove the auxiliary binding and resolve its profile from the closed registry."""

    executable = strategy_executable_binding_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_strategy_executable_binding(executable)
    if not verification.intact:
        codes = [_reason(f"executable_binding_integrity_failure:{code}") for code in verification.reason_codes]
        return codes, None, None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("executable_binding_digest_mismatch")], None, None
    if executable.correlation_id != correlation_id:
        return [_reason("executable_binding_correlation_mismatch")], None, None
    if executable.status is not EdgeEvidenceStatus.READY:
        return [_reason("executable_binding_rejected")], None, None
    codes: list[str] = []
    if executable.admission_digest != predecessor_digest:
        codes.append(_reason("executable_binding_admission_mismatch"))
    if admission is not None and executable.strategy_spec_digest != admission.strategy_spec_digest:
        codes.append(_reason("executable_binding_strategy_spec_mismatch"))
    try:
        profile = get_strategy_executable_profile(executable.profile_id)
    except StrategyExecutableProfileError:
        return [*codes, _reason("profile_unknown")], None, None
    if profile.profile_version != executable.profile_version:
        codes.append(_reason("profile_version_mismatch"))
    recomputed = strategy_executable_profile_semantics_digest(profile)
    if recomputed != profile.profile_semantics_digest or recomputed != executable.registered_profile_semantics_digest:
        codes.append(_reason("profile_semantics_digest_mismatch"))
    if codes:
        return codes, None, None
    return [], executable, profile


# --- bias proofs -------------------------------------------------------------------------------------------------------


def _check(check_id: str, subject: str, proven: bool) -> EdgeBiasCheck:
    outcome = EdgeBiasProofOutcome.PROVEN if proven else EdgeBiasProofOutcome.FAILED
    return EdgeBiasCheck(check_id=check_id, subject=subject, outcome=outcome)


def _proof(
    kind: EdgeBiasProofKind,
    claim_id: str,
    authority_digests: tuple[str, ...],
    checks: Sequence[EdgeBiasCheck],
    limitations: tuple[str, ...],
) -> EdgeBiasProof:
    ordered = tuple(sorted(checks, key=lambda item: (item.check_id, item.subject)))
    outcomes = {item.outcome for item in ordered}
    if not ordered or EdgeBiasProofOutcome.FAILED in outcomes:
        outcome = EdgeBiasProofOutcome.FAILED
    elif EdgeBiasProofOutcome.NEEDS_EXTERNAL_FACTS in outcomes:
        outcome = EdgeBiasProofOutcome.NEEDS_EXTERNAL_FACTS
    else:
        outcome = EdgeBiasProofOutcome.PROVEN
    return EdgeBiasProof(
        proof_kind=kind,
        claim_id=claim_id,
        outcome=outcome,
        authority_digests=authority_digests,
        checks=ordered,
        limitations=tuple(sorted(limitations)),
    )


def _required_input_series(
    profile: StrategyExecutableProfile, manifest: EdgeSourcePacketEvidence
) -> dict[str, list[EdgeSourceSeriesRecord]]:
    """Per profile-required data key, the EF-3 series of that key carrying the profile's required semantics."""

    return {
        key: [
            record
            for record in manifest.series
            if record.data_requirement_key == key and record.funding_semantics == profile.required_funding_semantics
        ]
        for key in sorted(profile.required_data_requirement_keys)
    }


def _schedule_check(profile: StrategyExecutableProfile) -> EdgeBiasCheck:
    return _check(
        "decision_schedule_point_in_time_visible",
        profile.decision_schedule_id,
        profile.decision_schedule_id in _POINT_IN_TIME_VISIBLE_DECISION_SCHEDULES,
    )


def _lookahead_proof(
    profile: StrategyExecutableProfile, manifest: EdgeSourcePacketEvidence, universe: Sequence[str]
) -> EdgeBiasProof:
    checks = [_schedule_check(profile)]
    for key, series in _required_input_series(profile, manifest).items():
        if not series:
            checks.append(_check("required_input_series_present", key, False))
        for record in series:
            policies_bound = record.registry_requirement_bound and None not in (
                record.event_time_policy,
                record.available_at_policy,
                record.finalized_at_policy,
            )
            checks.append(_check("input_series_time_policies_registry_bound", record.series_id, policies_bound))
            checks.append(_check("input_series_finalized_only", record.series_id, record.finalized_only))
        for instrument in universe:
            sources = [
                record.series_id
                for record in series
                if record.feature_input_eligible and instrument in record.instrument_coverage
            ]
            # Exactly one eligible source per (key, instrument): the proof binds the one series whose point-in-time
            # facts it relies on, and a later gate can never choose between candidate sources after seeing results.
            checks.append(_check("required_input_served_for_instrument", f"{key}:{instrument}", len(sources) >= 1))
            checks.append(
                _check("required_input_source_unambiguous_for_instrument", f"{key}:{instrument}", len(sources) <= 1)
            )
    return _proof(
        EdgeBiasProofKind.LOOKAHEAD,
        _LOOKAHEAD_CLAIM_ID,
        (
            manifest.source_packet_evidence_digest,
            manifest.data_requirement_registry_digest,
            profile.profile_semantics_digest,
        ),
        checks,
        _LOOKAHEAD_LIMITATIONS,
    )


def _repaint_proof(profile: StrategyExecutableProfile, manifest: EdgeSourcePacketEvidence) -> EdgeBiasProof:
    checks = [_schedule_check(profile)]
    for key, series in _required_input_series(profile, manifest).items():
        if not series:
            checks.append(_check("required_input_series_present", key, False))
        for record in series:
            checks.append(_check("input_series_finalized_only", record.series_id, record.finalized_only))
            checks.append(
                _check("input_series_point_in_time_revision_safe", record.series_id, record.point_in_time_revision_safe)
            )
    return _proof(
        EdgeBiasProofKind.REPAINT,
        _REPAINT_CLAIM_ID,
        (
            manifest.source_packet_evidence_digest,
            manifest.data_requirement_registry_digest,
            profile.profile_semantics_digest,
        ),
        checks,
        _REPAINT_LIMITATIONS,
    )


def _survivorship_proof(
    scope: EdgeSurvivorshipClaimScope,
    *,
    spec_digest: str,
    manifest: EdgeSourcePacketEvidence,
    universe: Sequence[str],
    edge_family: str,
) -> EdgeBiasProof:
    checks = [
        _check(
            "universe_instrument_in_point_in_time_manifest_coverage",
            instrument,
            instrument in manifest.instrument_coverage,
        )
        for instrument in universe
    ]
    if scope is EdgeSurvivorshipClaimScope.PINNED_INSTRUMENT_UNIVERSE:
        checks.append(_check("claim_scope_restricted_to_pinned_admitted_universe", scope.value, True))
        claim_id, limitations = _SURVIVORSHIP_PINNED_CLAIM_ID, _SURVIVORSHIP_PINNED_LIMITATIONS
    else:
        checks.append(
            EdgeBiasCheck(
                check_id="point_in_time_universe_membership_authority",
                subject=f"edge_family:{edge_family}",
                outcome=EdgeBiasProofOutcome.NEEDS_EXTERNAL_FACTS,
            )
        )
        claim_id, limitations = _SURVIVORSHIP_CROSS_SECTION_CLAIM_ID, _SURVIVORSHIP_CROSS_SECTION_LIMITATIONS
    return _proof(
        EdgeBiasProofKind.SURVIVORSHIP,
        claim_id,
        (spec_digest, manifest.source_packet_evidence_digest),
        checks,
        limitations,
    )


# --- derivation and verdict --------------------------------------------------------------------------------------------


def _derive_facts(
    *,
    admission: EdgeStrategySpecAdmissionEvidence,
    manifest: EdgeSourcePacketEvidence,
    root: EdgeIdeaIntakeEvidence,
    spec: StrategySpec,
    executable: StrategyExecutableBinding,
    profile: StrategyExecutableProfile,
    scope: EdgeSurvivorshipClaimScope,
) -> _DerivedFacts:
    universe = spec.instrument_universe
    return _DerivedFacts(
        source_manifest_digest=admission.predecessor_digest,
        candidate_strategy_id=root.candidate_strategy_id,
        edge_family=root.edge_family,
        strategy_spec_digest=admission.strategy_spec_digest,
        strategy_id=spec.strategy_id,
        strategy_version=spec.strategy_version,
        pinned_instrument_universe=universe,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_semantics_digest=profile.profile_semantics_digest,
        strategy_feature_ids=tuple(sorted(spec.feature_requirements)),
        profile_feature_element_ids=tuple(
            sorted(
                {
                    element_id
                    for entry in executable.coverage
                    if entry.spec_element_kind is StrategySpecElementKind.FEATURE_REQUIREMENT
                    for element_id in entry.profile_element_ids
                }
            )
        ),
        decision_schedule_id=profile.decision_schedule_id,
        state_rule_id=profile.state_rule_id,
        decision_labels=tuple(sorted(action.value for action in ProfileAction)),
        decision_element_refs=tuple(
            sorted(
                f"{element.kind.value}:{element.element_id}"
                for element in profile.semantic_elements
                if element.kind not in _DECISION_STRUCTURE_EXCLUDED_KINDS
            )
        ),
        parameter_schema_refs=tuple(
            sorted(f"{spec_item.parameter_id}:{spec_item.kind.value}" for spec_item in profile.parameter_schema)
        ),
        parameter_constraints=tuple(sorted(profile.parameter_constraints)),
        binding_coverage_digest=executable.coverage_digest,
        bias_proofs=(
            _lookahead_proof(profile, manifest, universe),
            _repaint_proof(profile, manifest),
            _survivorship_proof(
                scope,
                spec_digest=admission.strategy_spec_digest,
                manifest=manifest,
                universe=universe,
                edge_family=root.edge_family,
            ),
        ),
    )


def _propagate(code_prefix: str, verdict: EdgeGateVerdict, buckets: tuple[list[str], list[str], list[str]]) -> None:
    fail, needs_external, needs_governance = buckets
    code = _reason(f"{code_prefix}_not_advanced:{verdict.value}")
    if verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        needs_external.append(code)
    elif verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        needs_governance.append(code)
    else:
        fail.append(code)


def _feature_reasons(declared: Sequence[str], admitted: Sequence[str]) -> list[str]:
    fail = [_reason(f"feature_not_admitted_by_strategy_spec:{item}") for item in declared if item not in admitted]
    fail.extend(_reason(f"feature_omitted_from_preregistration:{item}") for item in admitted if item not in declared)
    return fail


def _parameter_reasons(
    profile: StrategyExecutableProfile,
    bounds: Sequence[EdgeParameterSearchBound],
    variants: Sequence[EdgeRegisteredVariant],
) -> tuple[list[str], list[str]]:
    """Registry-owned legality of the search space and ledger: ``(fail, needs_governance)``."""

    schema_ids = {item.parameter_id for item in profile.parameter_schema}
    bound_values = {bound.parameter_id: set(bound.values) for bound in bounds}
    fail = [_reason(f"parameter_bound_unknown:{item}") for item in sorted(bound_values) if item not in schema_ids]
    needs_governance = [
        _reason(f"parameter_bound_pending_governance:{item}") for item in sorted(schema_ids - set(bound_values))
    ]
    if not variants:
        needs_governance.append(_reason("variant_ledger_pending_governance"))
        return fail, needs_governance
    exercised: dict[str, set[str]] = {}
    for variant in variants:
        try:
            canonical_profile_parameter_assignment(profile, variant.parameter_assignment)
        except StrategyExecutableProfileError as exc:
            fail.append(_reason(f"variant_assignment_rejected:{variant.variant_id}:{exc}"))
        for item in variant.parameter_assignment:
            allowed = bound_values.get(item.parameter_id)
            if allowed is None:
                continue
            if item.value in allowed:
                exercised.setdefault(item.parameter_id, set()).add(item.value)
            else:
                fail.append(_reason(f"variant_value_outside_bounds:{variant.variant_id}:{item.parameter_id}"))
    for bound in bounds:
        used = exercised.get(bound.parameter_id, set())
        fail.extend(
            _reason(f"parameter_bound_value_unregistered:{bound.parameter_id}:{value}")
            for value in bound.values
            if value not in used
        )
    return fail, needs_governance


def _proof_reasons(proofs: Sequence[EdgeBiasProof]) -> tuple[list[str], list[str]]:
    fail: list[str] = []
    needs_external: list[str] = []
    for proof in proofs:
        for item in proof.checks:
            code = f"{proof.proof_kind.value}:{item.check_id}:{item.subject}"
            if item.outcome is EdgeBiasProofOutcome.FAILED:
                fail.append(_reason(f"bias_proof_failed:{code}"))
            elif item.outcome is EdgeBiasProofOutcome.NEEDS_EXTERNAL_FACTS:
                needs_external.append(_reason(f"bias_proof_needs_external_facts:{code}"))
    return fail, needs_external


def _approval_reasons(approval: EdgePreregistrationApproval | None, committed: Mapping[str, str]) -> list[str]:
    if approval is None:
        return [_reason("preregistration_approval_missing")]
    return [
        _reason(f"preregistration_approval_{name}_mismatch")
        for name in _APPROVAL_COMMITMENTS
        if getattr(approval, f"approved_{name}") != committed[name]
    ]


# --- EF-5 preregistration ----------------------------------------------------------------------------------------------


def _assemble_evidence(
    *,
    predecessor_binding: object,
    root_intake_digest: object,
    executable_binding: object,
    preregistration_id: object,
    correlation_id: object,
    feature_ids: object,
    parameter_bounds: object,
    variants: object,
    survivorship_claim_scope: object,
    approval: object,
) -> EdgeLeakageBiasEvidence:
    """The one EF-5 assembly path, shared by the builder and verifier reassembly."""

    chain_binding = require_edge_authority_binding(
        predecessor_binding,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )
    executable_ref = require_edge_authority_binding(
        executable_binding,
        shape=strategy_executable_binding_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("executable_binding"),
        optional=False,
    )
    root_anchor = _require_hex64(root_intake_digest, "root_intake_digest")
    preregistration_id = _require_text(preregistration_id, "preregistration_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    declared_features = _canonical_feature_ids(feature_ids)
    bounds = _canonical_bounds(parameter_bounds)
    registered = _canonical_variants(variants)
    scope = _require_member(survivorship_claim_scope, EdgeSurvivorshipClaimScope, "survivorship_claim_scope")
    approval_record = _canonical_approval(approval)

    chain_codes, chain = _chain_authority(
        chain_binding,  # type: ignore[arg-type]
        root_intake_digest=root_anchor,
        correlation_id=correlation_id,
    )
    executable_codes, executable, profile = _executable_authority(
        executable_ref,  # type: ignore[arg-type]
        correlation_id=correlation_id,
        predecessor_digest=chain_binding.expected_digest,  # type: ignore[union-attr]
        admission=None if chain is None else chain[0],
    )
    integrity = _sorted_unique([*chain_codes, *executable_codes])

    derived = _DerivedFacts()
    if not integrity and chain is not None and executable is not None and profile is not None:
        admission, manifest, root, spec = chain
        derived = _derive_facts(
            admission=admission,
            manifest=manifest,
            root=root,
            spec=spec,
            executable=executable,
            profile=profile,
            scope=scope,  # type: ignore[arg-type]
        )
    committed = {
        "root_intake_digest": root_anchor,
        "predecessor_digest": chain_binding.expected_digest,  # type: ignore[union-attr]
        "strategy_spec_digest": derived.strategy_spec_digest,
        "executable_binding_digest": executable_ref.expected_digest,  # type: ignore[union-attr]
        "profile_semantics_digest": derived.profile_semantics_digest,
        "feature_set_digest": _digest_of(
            {
                "feature_ids": list(declared_features),
                "profile_feature_element_ids": list(derived.profile_feature_element_ids),
            }
        ),
        "parameter_bounds_digest": _digest_of([_to_payload(bound) for bound in bounds]),
        "variant_ledger_digest": _digest_of([_to_payload(variant) for variant in registered]),
        "decision_structure_digest": _digest_of(
            {
                "profile_id": derived.profile_id,
                "profile_version": derived.profile_version,
                "profile_semantics_digest": derived.profile_semantics_digest,
                "decision_schedule_id": derived.decision_schedule_id,
                "state_rule_id": derived.state_rule_id,
                "decision_labels": list(derived.decision_labels),
                "decision_element_refs": list(derived.decision_element_refs),
                "parameter_schema_refs": list(derived.parameter_schema_refs),
                "parameter_constraints": list(derived.parameter_constraints),
                "binding_coverage_digest": derived.binding_coverage_digest,
            }
        ),
        "bias_proof_set_digest": _digest_of([_to_payload(proof) for proof in derived.bias_proofs]),
    }

    if integrity or chain is None or executable is None or profile is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        admission = chain[0]
        buckets: tuple[list[str], list[str], list[str]] = ([], [], [])
        if admission.advances is not True:
            _propagate("predecessor", admission.gate_verdict, buckets)
        if executable.advances is not True:
            _propagate("executable_binding", executable.gate_verdict, buckets)
        fail, needs_external, needs_governance = buckets
        fail.extend(_feature_reasons(declared_features, derived.strategy_feature_ids))
        parameter_fail, parameter_needs = _parameter_reasons(profile, bounds, registered)
        fail.extend(parameter_fail)
        needs_governance.extend(parameter_needs)
        proof_fail, proof_needs = _proof_reasons(derived.bias_proofs)
        fail.extend(proof_fail)
        needs_external.extend(proof_needs)
        needs_governance.extend(_approval_reasons(approval_record, committed))
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    advances = status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS
    seed = EdgeLeakageBiasEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=advances,
        preregistration_sealed=advances,
        preregistration_id=preregistration_id,
        correlation_id=correlation_id,
        root_intake_digest=root_anchor,
        predecessor_binding=chain_binding,  # type: ignore[arg-type]
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        predecessor_digest=committed["predecessor_digest"],
        source_manifest_digest=derived.source_manifest_digest,
        candidate_strategy_id=derived.candidate_strategy_id,
        edge_family=derived.edge_family,
        strategy_spec_digest=derived.strategy_spec_digest,
        strategy_id=derived.strategy_id,
        strategy_version=derived.strategy_version,
        pinned_instrument_universe=derived.pinned_instrument_universe,
        executable_binding=executable_ref,  # type: ignore[arg-type]
        executable_binding_digest=committed["executable_binding_digest"],
        profile_id=derived.profile_id,
        profile_version=derived.profile_version,
        profile_semantics_digest=derived.profile_semantics_digest,
        feature_ids=declared_features,
        strategy_feature_ids=derived.strategy_feature_ids,
        profile_feature_element_ids=derived.profile_feature_element_ids,
        feature_set_digest=committed["feature_set_digest"],
        parameter_bounds=bounds,
        parameter_bounds_digest=committed["parameter_bounds_digest"],
        registered_variants=registered,
        registered_parameter_assignment_digests=tuple(sorted(item.parameter_assignment_digest for item in registered)),
        multiple_testing_count=len(registered),
        variant_ledger_digest=committed["variant_ledger_digest"],
        decision_schedule_id=derived.decision_schedule_id,
        state_rule_id=derived.state_rule_id,
        decision_labels=derived.decision_labels,
        decision_element_refs=derived.decision_element_refs,
        parameter_schema_refs=derived.parameter_schema_refs,
        parameter_constraints=derived.parameter_constraints,
        binding_coverage_digest=derived.binding_coverage_digest,
        decision_structure_digest=committed["decision_structure_digest"],
        survivorship_claim_scope=scope,  # type: ignore[arg-type]
        bias_proofs=derived.bias_proofs,
        bias_proof_set_digest=committed["bias_proof_set_digest"],
        approval=approval_record,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        leakage_bias_evidence_digest="",
    )
    return replace(seed, leakage_bias_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_leakage_bias_evidence(
    predecessor: EdgeStrategySpecAdmissionEvidence,
    *,
    expected_predecessor_digest: str,
    expected_root_intake_digest: str,
    executable_binding: StrategyExecutableBinding,
    expected_executable_binding_digest: str,
    preregistration_id: str,
    correlation_id: str,
    feature_ids: Sequence[str],
    parameter_bounds: Sequence[EdgeParameterSearchBound],
    variants: Sequence[EdgeInputVariant],
    survivorship_claim_scope: EdgeSurvivorshipClaimScope | str,
    approval: EdgePreregistrationApproval | None = None,
) -> EdgeLeakageBiasEvidence:
    """Build deterministic EF-5 preregistration evidence over an EF-4 admission, its chain and its executable binding.

    Malformed caller input or a non-serializable upstream object raises ``EdgeLeakageBiasEvidenceError``. An authentic
    predecessor, chain link or binding that fails re-proof, a chain splice, a correlation splice or a binding of another
    admission yields ``REJECTED``/``NOT_EVALUATED``. Otherwise the evidence is ``READY`` with ``FAIL``,
    ``NEEDS_EXTERNAL_FACTS``, ``NEEDS_GOVERNANCE_APPROVAL`` or ``PASS``; only PASS seals the preregistration.
    """

    if type(predecessor) is not EdgeStrategySpecAdmissionEvidence:
        raise _fail("predecessor_malformed")
    try:
        predecessor_payload = edge_strategy_spec_admission_to_dict(predecessor)
    except Exception as exc:  # noqa: BLE001 - a hollow predecessor object is a construction error, never a receipt
        raise _fail("predecessor_not_serializable") from exc
    chain_binding = build_edge_authority_binding(
        snapshot_payload=predecessor_payload,
        expected_digest=expected_predecessor_digest,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("predecessor"),
    )
    if type(executable_binding) is not StrategyExecutableBinding:
        raise _fail("executable_binding_malformed")
    try:
        executable_payload = strategy_executable_binding_to_dict(executable_binding)
    except Exception as exc:  # noqa: BLE001 - a hollow binding object is a construction error, never a receipt
        raise _fail("executable_binding_not_serializable") from exc
    executable_ref = build_edge_authority_binding(
        snapshot_payload=executable_payload,
        expected_digest=expected_executable_binding_digest,
        shape=strategy_executable_binding_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("executable_binding"),
    )
    return _assemble_evidence(
        predecessor_binding=chain_binding,
        root_intake_digest=expected_root_intake_digest,
        executable_binding=executable_ref,
        preregistration_id=preregistration_id,
        correlation_id=correlation_id,
        feature_ids=feature_ids,
        parameter_bounds=parameter_bounds,
        variants=variants,
        survivorship_claim_scope=survivorship_claim_scope,
        approval=approval,
    )


def edge_leakage_bias_evidence_to_dict(evidence: EdgeLeakageBiasEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-5 evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_leakage_bias_evidence_digest(evidence: EdgeLeakageBiasEvidence) -> str:
    """Recompute the canonical EF-5 digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_count(value: object) -> int:
    if type(value) is not int or value < 0 or value.bit_length() > _INT64_BIT_LENGTH:
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


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _as_approval(value: object) -> object:
    return None if value is None else _parse_exact(EdgePreregistrationApproval, value, {})


def _parse_predecessor_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )


def _parse_executable_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=strategy_executable_binding_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("executable_binding"),
        optional=False,
    )


_ASSIGNMENT_CONVERTERS: dict[str, Callable[[object], object]] = {}
_BOUND_CONVERTERS: dict[str, Callable[[object], object]] = {
    "treatment": _as_enum(EdgeParameterSearchTreatment),
    "values": _as_str_tuple,
}
_VARIANT_CONVERTERS: dict[str, Callable[[object], object]] = {
    "parameter_assignment": _as_records(ProfileParameterAssignment, _ASSIGNMENT_CONVERTERS),
}
_CHECK_CONVERTERS: dict[str, Callable[[object], object]] = {"outcome": _as_enum(EdgeBiasProofOutcome)}
_PROOF_CONVERTERS: dict[str, Callable[[object], object]] = {
    "proof_kind": _as_enum(EdgeBiasProofKind),
    "outcome": _as_enum(EdgeBiasProofOutcome),
    "authority_digests": _as_str_tuple,
    "checks": _as_records(EdgeBiasCheck, _CHECK_CONVERTERS),
    "limitations": _as_str_tuple,
}
_EVIDENCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "preregistration_sealed": _as_bool,
    "predecessor_binding": _parse_predecessor_binding,
    "pinned_instrument_universe": _as_str_tuple,
    "executable_binding": _parse_executable_binding,
    "feature_ids": _as_str_tuple,
    "strategy_feature_ids": _as_str_tuple,
    "profile_feature_element_ids": _as_str_tuple,
    "parameter_bounds": _as_records(EdgeParameterSearchBound, _BOUND_CONVERTERS),
    "registered_variants": _as_records(EdgeRegisteredVariant, _VARIANT_CONVERTERS),
    "registered_parameter_assignment_digests": _as_str_tuple,
    "multiple_testing_count": _as_count,
    "decision_labels": _as_str_tuple,
    "decision_element_refs": _as_str_tuple,
    "parameter_schema_refs": _as_str_tuple,
    "parameter_constraints": _as_str_tuple,
    "survivorship_claim_scope": _as_enum(EdgeSurvivorshipClaimScope),
    "bias_proofs": _as_records(EdgeBiasProof, _PROOF_CONVERTERS),
    "approval": _as_approval,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_leakage_bias_evidence_from_payload(payload: object) -> EdgeLeakageBiasEvidence:
    """Strictly reconstruct EF-5 evidence from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_leakage_bias_evidence`` on the result.
    """

    return _parse_exact(EdgeLeakageBiasEvidence, payload, _EVIDENCE_CONVERTERS)  # type: ignore[return-value]


def edge_leakage_bias_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-5 snapshot consumed by a later gate."""

    try:
        edge_leakage_bias_evidence_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_evidence(evidence: object) -> EdgeLeakageBiasEvidence:
    return _assemble_evidence(
        predecessor_binding=evidence.predecessor_binding,  # type: ignore[attr-defined]
        root_intake_digest=evidence.root_intake_digest,  # type: ignore[attr-defined]
        executable_binding=evidence.executable_binding,  # type: ignore[attr-defined]
        preregistration_id=evidence.preregistration_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        feature_ids=evidence.feature_ids,  # type: ignore[attr-defined]
        parameter_bounds=evidence.parameter_bounds,  # type: ignore[attr-defined]
        variants=tuple(
            EdgeInputVariant(variant_id=item.variant_id, parameter_assignment=item.parameter_assignment)
            for item in evidence.registered_variants  # type: ignore[attr-defined]
        ),
        survivorship_claim_scope=evidence.survivorship_claim_scope,  # type: ignore[attr-defined]
        approval=evidence.approval,  # type: ignore[attr-defined]
    )


def verify_edge_leakage_bias_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-5 evidence by strict parse and reassembly from its carried bindings, anchors and declarations.

    Every derived field — chain facts, feature set, variant digests, multiple-testing count, decision structure, bias
    proofs, digests, verdict and seal — must equal the reassembled artifact. Total: never raises.
    """

    return verify_edge_artifact_total(
        evidence,
        cls=EdgeLeakageBiasEvidence,
        to_payload=_to_payload,
        parse_payload=edge_leakage_bias_evidence_from_payload,
        reassemble=_reassemble_evidence,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EDGE_LEAKAGE_BIAS_NON_CLAIM_FLAGS",
    "EdgeBiasCheck",
    "EdgeBiasProof",
    "EdgeBiasProofKind",
    "EdgeBiasProofOutcome",
    "EdgeInputVariant",
    "EdgeLeakageBiasEvidence",
    "EdgeLeakageBiasEvidenceError",
    "EdgeParameterSearchBound",
    "EdgeParameterSearchTreatment",
    "EdgePreregistrationApproval",
    "EdgeRegisteredVariant",
    "EdgeSurvivorshipClaimScope",
    "build_edge_leakage_bias_evidence",
    "edge_leakage_bias_evidence_digest",
    "edge_leakage_bias_evidence_from_payload",
    "edge_leakage_bias_evidence_payload_is_well_formed",
    "edge_leakage_bias_evidence_to_dict",
    "verify_edge_leakage_bias_evidence",
]
