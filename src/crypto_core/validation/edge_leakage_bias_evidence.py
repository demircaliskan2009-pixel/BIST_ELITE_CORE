"""Edge Factory EF-5: sealed preregistration ledger and leakage/bias firewall over an authenticated EF-4 admission.

EF-5 pins, BEFORE any performance is visible, everything a later out-of-sample evaluation may interpret: the feature
set (derived from the authenticated StrategySpec), the parameter search bounds, the label/threshold structures, the
evaluation assumption identities (fee, slippage and funding models), the walk-forward window schedule with its
point-in-time universe snapshots, and every candidate variant together with exactly one preregistered primary
variant. The multiple-testing count is derived from the ledger, never supplied.

Trust model (shared kernel ``edge_artifact_core``):

* Dual anchor. The EF-4 admission is a required ``EdgeAuthorityBinding``. ``reprove_edge_admitted_chain``
  independently re-proves EF-4 → EF-3 → EF-2 through their public verifiers, every nested digest and correlation
  edge, and the explicit EF-2 root anchor.
* Governance. ``EdgePreregistrationPolicy`` is the digest-bound human approval, for one candidate and correlation, of
  the exact parameter bound set, the minimum OOS window count and the exact variant ledger (every ledger entry, which
  binds the feature set, label/threshold structures, assumption identities, window schedule and universe membership
  evidence, plus the primary variant). ``None``, a non-READY policy or any mismatch is
  ``NEEDS_GOVERNANCE_APPROVAL``, so a post-hoc change of variants, primary, schedule or assumptions cannot pass
  without a new human approval; a policy that fails its own re-proof or anchor is an integrity rejection. No number is
  chosen or defaulted here.
* Leakage and repaint. A structured ``EdgeLeakageProof`` is re-run through the accepted
  ``evaluate_leakage_bias_repaint`` on every assembly, with the authenticated StrategySpec, a point-in-time policy
  derived from the authenticated EF-3 manifest, and the preregistered assumption identities. PASS passes; REJECT is
  valid negative evidence (FAIL); NEEDS_RESEARCH and INSUFFICIENT_EVIDENCE stay ``NEEDS_EXTERNAL_FACTS``.
* Survivorship. Every window references a canonical universe snapshot of dated memberships, and internal
  point-in-time consistency is machine-evaluated. External historical membership truth is never claimed as
  machine-proven: an unbound membership evidence digest is ``NEEDS_EXTERNAL_FACTS``, and a bound one counts only as
  human-attested through the approved policy.
* Performance firewall. No builder parameter accepts performance: no PnL, returns, Sharpe, hit rate, profit factor,
  drawdown, walk-forward result or selected winner. ``preregistration_sealed`` is True exactly for READY ledgers and
  ``performance_data_consumed`` is always False.
* One assembly path serves the builder and verifier reassembly; every public ``verify_*`` is total. Paper-only,
  deterministic, no IO/clock/network; never an edge, profitability or readiness claim.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_PERMANENT_NON_CLAIM_FLAGS,
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
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeIdeaIntakeEvidence,
    edge_idea_intake_evidence_from_payload,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
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
from crypto_core.validation.leakage_bias_repaint import (
    LeakageBiasRepaintInput,
    LeakageBiasRepaintStatus,
    ValidationFeatureTimestamp,
    ValidationFundingObservation,
    ValidationIndicatorPolicy,
    evaluate_leakage_bias_repaint,
)

_SCHEMA_VERSION = "edge-leakage-bias-evidence.v1"
_GATE_ID = "EF-5"
_PREDECESSOR_GATE_ID = "EF-4"
_REASON_PREFIX = "edge_leakage_bias_evidence"
_SELF_DIGEST_FIELD = "ledger_digest"
_POLICY_SCHEMA_VERSION = "edge-preregistration-policy.v1"
_POLICY_REASON_PREFIX = "edge_preregistration_policy"
_POLICY_SELF_DIGEST_FIELD = "policy_digest"
_SURVIVORSHIP_TRUTH_UNRESOLVED = "external_membership_truth_unresolved"
_SURVIVORSHIP_TRUTH_ATTESTED = "human_governance_attested_membership_evidence_not_machine_proven"
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")
_BASELINE_FLAG_NAMES = frozenset(name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_PERMANENT_FLAG_NAMES = frozenset(name for name, _ in EDGE_PERMANENT_NON_CLAIM_FLAGS)


class EdgeLeakageBiasEvidenceError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class EdgePreregistrationPolicyStatus(str, Enum):
    """Preregistration policy status. READY records human approval only; it never proves an edge or readiness."""

    POLICY_READY = "POLICY_READY"
    POLICY_REJECTED = "POLICY_REJECTED"


class EdgeLabelThresholdKind(str, Enum):
    """Whether a preregistered structure defines an evaluation label or a decision threshold."""

    LABEL = "label"
    THRESHOLD = "threshold"


class EdgeEvaluationAssumptionKind(str, Enum):
    """The cost and carry model identities every later evaluation must use."""

    FEE_MODEL = "fee_model"
    SLIPPAGE_MODEL = "slippage_model"
    FUNDING_MODEL = "funding_model"


@dataclass(frozen=True)
class EdgeParameterBound:
    """One preregistered inclusive search bound; ``lower``/``upper`` are canonical 18-place decimal strings."""

    parameter_id: str
    lower: str
    upper: str


@dataclass(frozen=True)
class EdgeParameterAssignment:
    """One parameter value of a variant, as a canonical 18-place decimal string."""

    parameter_id: str
    value: str


@dataclass(frozen=True)
class EdgeVariantRegistration:
    """One candidate variant registered before any performance is visible."""

    variant_id: str
    parameter_assignment: tuple[EdgeParameterAssignment, ...]


@dataclass(frozen=True)
class EdgeLabelThresholdStructure:
    """A preregistered label or threshold definition and the bound parameters it references."""

    structure_id: str
    kind: EdgeLabelThresholdKind
    definition: str
    parameter_ids: tuple[str, ...]


@dataclass(frozen=True)
class EdgeEvaluationAssumption:
    """A preregistered model identity; ``model_digest`` None means the external model facts are unresolved."""

    kind: EdgeEvaluationAssumptionKind
    model_id: str
    model_digest: str | None


@dataclass(frozen=True)
class EdgeUniverseMember:
    """One dated instrument membership: listed at ``listed_at_ns``, delisted at ``delisted_at_ns`` or still listed."""

    instrument: str
    listed_at_ns: int
    delisted_at_ns: int | None


@dataclass(frozen=True)
class EdgeUniverseSnapshot:
    """A point-in-time universe as of ``as_of_ns``; the evidence digest binds the external membership record."""

    snapshot_id: str
    as_of_ns: int
    members: tuple[EdgeUniverseMember, ...]
    membership_source_reference: str
    membership_evidence_digest: str | None


@dataclass(frozen=True)
class EdgePreregisteredWindow:
    """One preregistered walk-forward window; deterministic evidence times only, never a wall clock."""

    window_id: str
    in_sample_start_ns: int
    in_sample_end_ns: int
    oos_start_ns: int
    oos_end_ns: int
    universe_snapshot_id: str


@dataclass(frozen=True)
class EdgeLeakageProof:
    """Structured leakage/repaint proof input re-run through ``evaluate_leakage_bias_repaint`` on every assembly."""

    decision_timestamp_ns: int
    feature_timestamps: tuple[ValidationFeatureTimestamp, ...]
    funding_observations: tuple[ValidationFundingObservation, ...]
    indicator_policies: tuple[ValidationIndicatorPolicy, ...]
    needs_research_reasons: tuple[str, ...]
    insufficient_evidence_reasons: tuple[str, ...]


@dataclass(frozen=True)
class EdgeVariantLedgerEntry:
    """Derived immutable ledger entry binding a variant to every preregistered evaluation component."""

    variant_id: str
    parameter_assignment: tuple[EdgeParameterAssignment, ...]
    feature_set_digest: str
    label_threshold_structures_digest: str
    evaluation_assumptions_digest: str
    window_schedule_digest: str
    universe_snapshot_set_digest: str
    variant_registration_digest: str


@dataclass(frozen=True)
class EdgeAdmittedChain:
    """The independently re-proven EF-2 → EF-3 → EF-4 chain and the authenticated StrategySpec."""

    intake: EdgeIdeaIntakeEvidence
    source_packet: EdgeSourcePacketEvidence
    admission: EdgeStrategySpecAdmissionEvidence
    strategy_spec: StrategySpec


@dataclass(frozen=True)
class EdgePreregistrationPolicy:
    """Immutable, digest-bound human approval of one candidate's preregistration inputs. PAPER ONLY."""

    schema_version: str
    status: EdgePreregistrationPolicyStatus
    ready: bool
    policy_id: str
    correlation_id: str
    candidate_strategy_id: str
    parameter_bounds: tuple[EdgeParameterBound, ...]
    parameter_bounds_digest: str
    min_oos_window_count: int | None
    approved_variant_ledger_digest: str | None
    approved: bool
    approval_reference: str | None
    approval_digest: str | None
    reason_codes: tuple[str, ...]
    policy_digest: str
    policy_only: bool = True
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


@dataclass(frozen=True)
class EdgeLeakageBiasEvidence:
    """Immutable, digest-bound EF-5 preregistration ledger. PAPER ONLY; seals process inputs, never performance."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    ledger_id: str
    correlation_id: str
    root_intake_digest: str
    predecessor_binding: EdgeAuthorityBinding
    predecessor_gate_id: str
    predecessor_digest: str
    candidate_strategy_id: str
    strategy_id: str
    strategy_spec_digest: str
    admitted_kill_criteria_digest: str
    instrument_universe: tuple[str, ...]
    feature_set: tuple[str, ...]
    feature_set_digest: str
    spec_conditions_digest: str
    pit_policy_digest: str
    parameter_bounds: tuple[EdgeParameterBound, ...]
    parameter_bounds_digest: str
    label_threshold_structures: tuple[EdgeLabelThresholdStructure, ...]
    label_threshold_structures_digest: str
    evaluation_assumptions: tuple[EdgeEvaluationAssumption, ...]
    evaluation_assumptions_digest: str
    universe_snapshots: tuple[EdgeUniverseSnapshot, ...]
    universe_snapshot_set_digest: str
    windows: tuple[EdgePreregisteredWindow, ...]
    window_schedule_digest: str
    variants: tuple[EdgeVariantRegistration, ...]
    ledger_entries: tuple[EdgeVariantLedgerEntry, ...]
    primary_variant_id: str
    variant_ledger_digest: str
    multiple_testing_count: int
    leakage_proof: EdgeLeakageProof
    leakage_repaint_status: str
    leakage_repaint_reason_codes: tuple[str, ...]
    survivorship_internal_consistency_proven: bool
    survivorship_external_truth_basis: str
    preregistration_policy_binding: EdgeAuthorityBinding | None
    approved_min_oos_window_count: int | None
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    ledger_digest: str
    preregistration_sealed: bool
    performance_data_consumed: bool
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    kill_criteria_sealed: bool = False
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


# --- strict caller-input helpers ------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _policy_reason(code: str) -> str:
    return f"{_POLICY_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeLeakageBiasEvidenceError:
    return EdgeLeakageBiasEvidenceError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digest(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _is_plain_text(value: object) -> bool:
    return (
        type(value) is str
        and value != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value  # type: ignore[return-value]


def _require_token(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_instrument(value: object) -> str:
    if type(value) is not str or not value or len(value) > 64 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail("universe_member_instrument_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail("universe_member_instrument_invalid")
    return _require_text(value, "universe_member_instrument")


def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_optional_positive_int(value: object, field_name: str) -> int | None:
    return None if value is None else _require_positive_int(value, field_name)


def _require_optional_hex64(value: object, field_name: str) -> str | None:
    if value is not None and not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str:
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise _fail(f"{field_name}_invalid") from exc
    raise _fail(f"{field_name}_invalid")


def _require_sequence(value: object, field_name: str) -> Sequence[object]:
    if type(value) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    return value  # type: ignore[return-value]


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and value - value == 0  # type: ignore[operator]


def _is_canonical_decimal(value: object) -> bool:
    if type(value) is not str or "." not in value:
        return False
    whole, _, fraction = value.lstrip("-").partition(".")
    if len(fraction) != 18 or not fraction.isdigit() or not whole.isdigit() or (len(whole) > 1 and whole[0] == "0"):
        return False
    if value.startswith("-") and value.count("-") != 1:
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite() and not (value.startswith("-") and parsed == 0)


def _require_decimal(value: object, field_name: str) -> str:
    if not _is_canonical_decimal(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_tokens(values: object, field_name: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for item in _require_sequence(values, f"{field_name}s"):
        token = _require_token(item, field_name)
        if token in tokens:
            raise _fail(f"{field_name}_duplicate")
        tokens.append(token)
    return tuple(sorted(tokens))


# --- canonical preregistration components --------------------------------------------------------------------------


def _canonical_parameter_bounds(values: object) -> tuple[EdgeParameterBound, ...]:
    canonical: dict[str, EdgeParameterBound] = {}
    for item in _require_sequence(values, "parameter_bounds"):
        if type(item) is not EdgeParameterBound:
            raise _fail("parameter_bound_malformed")
        parameter_id = _require_token(item.parameter_id, "parameter_bound_id")
        lower = _require_decimal(item.lower, "parameter_bound_lower")
        upper = _require_decimal(item.upper, "parameter_bound_upper")
        if Decimal(lower) > Decimal(upper):
            raise _fail("parameter_bound_range_invalid")
        if parameter_id in canonical:
            raise _fail("parameter_bound_duplicate")
        canonical[parameter_id] = EdgeParameterBound(parameter_id=parameter_id, lower=lower, upper=upper)
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_assignment(values: object) -> tuple[EdgeParameterAssignment, ...]:
    canonical: dict[str, EdgeParameterAssignment] = {}
    for item in _require_sequence(values, "variant_parameter_assignment"):
        if type(item) is not EdgeParameterAssignment:
            raise _fail("variant_parameter_assignment_malformed")
        parameter_id = _require_token(item.parameter_id, "variant_parameter_id")
        value = _require_decimal(item.value, "variant_parameter_value")
        if parameter_id in canonical:
            raise _fail("variant_parameter_duplicate")
        canonical[parameter_id] = EdgeParameterAssignment(parameter_id=parameter_id, value=value)
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_variants(values: object) -> tuple[EdgeVariantRegistration, ...]:
    canonical: dict[str, EdgeVariantRegistration] = {}
    assignments: set[tuple[EdgeParameterAssignment, ...]] = set()
    for item in _require_sequence(values, "variants"):
        if type(item) is not EdgeVariantRegistration:
            raise _fail("variant_malformed")
        variant_id = _require_token(item.variant_id, "variant_id")
        assignment = _canonical_assignment(item.parameter_assignment)
        if variant_id in canonical:
            raise _fail("variant_id_duplicate")
        if assignment in assignments:
            raise _fail("variant_parameter_assignment_duplicate")
        assignments.add(assignment)
        canonical[variant_id] = EdgeVariantRegistration(variant_id=variant_id, parameter_assignment=assignment)
    if not canonical:
        raise _fail("variants_empty")
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_label_threshold_structures(values: object) -> tuple[EdgeLabelThresholdStructure, ...]:
    canonical: dict[str, EdgeLabelThresholdStructure] = {}
    for item in _require_sequence(values, "label_threshold_structures"):
        if type(item) is not EdgeLabelThresholdStructure:
            raise _fail("label_threshold_structure_malformed")
        structure_id = _require_token(item.structure_id, "label_threshold_structure_id")
        if structure_id in canonical:
            raise _fail("label_threshold_structure_duplicate")
        canonical[structure_id] = EdgeLabelThresholdStructure(
            structure_id=structure_id,
            kind=_require_member(item.kind, EdgeLabelThresholdKind, "label_threshold_structure_kind"),  # type: ignore[arg-type]
            definition=_require_text(item.definition, "label_threshold_structure_definition"),
            parameter_ids=_require_tokens(item.parameter_ids, "label_threshold_structure_parameter_id"),
        )
    if not canonical:
        raise _fail("label_threshold_structures_empty")
    return tuple(canonical[key] for key in sorted(canonical))


def canonical_edge_evaluation_assumptions(assumptions: object) -> tuple[EdgeEvaluationAssumption, ...]:
    """Validate evaluation assumption identities and return them ordered by kind (raises on malformed input)."""

    canonical: dict[str, EdgeEvaluationAssumption] = {}
    for item in _require_sequence(assumptions, "evaluation_assumptions"):
        if type(item) is not EdgeEvaluationAssumption:
            raise _fail("evaluation_assumption_malformed")
        kind = _require_member(item.kind, EdgeEvaluationAssumptionKind, "evaluation_assumption_kind")
        if kind.value in canonical:
            raise _fail("evaluation_assumption_duplicate")
        canonical[kind.value] = EdgeEvaluationAssumption(
            kind=kind,  # type: ignore[arg-type]
            model_id=_require_token(item.model_id, "evaluation_assumption_model_id"),
            model_digest=_require_optional_hex64(item.model_digest, "evaluation_assumption_model_digest"),
        )
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_universe_snapshots(values: object) -> tuple[EdgeUniverseSnapshot, ...]:
    canonical: dict[str, EdgeUniverseSnapshot] = {}
    for item in _require_sequence(values, "universe_snapshots"):
        if type(item) is not EdgeUniverseSnapshot:
            raise _fail("universe_snapshot_malformed")
        snapshot_id = _require_token(item.snapshot_id, "universe_snapshot_id")
        members: dict[str, EdgeUniverseMember] = {}
        for member in _require_sequence(item.members, "universe_snapshot_members"):
            if type(member) is not EdgeUniverseMember:
                raise _fail("universe_member_malformed")
            instrument = _require_instrument(member.instrument)
            listed_at_ns = _require_positive_int(member.listed_at_ns, "universe_member_listed_at_ns")
            delisted_at_ns = _require_optional_positive_int(member.delisted_at_ns, "universe_member_delisted_at_ns")
            if delisted_at_ns is not None and delisted_at_ns <= listed_at_ns:
                raise _fail("universe_member_listing_interval_invalid")
            if instrument in members:
                raise _fail("universe_member_duplicate")
            members[instrument] = EdgeUniverseMember(instrument, listed_at_ns, delisted_at_ns)
        if not members:
            raise _fail("universe_snapshot_members_empty")
        if snapshot_id in canonical:
            raise _fail("universe_snapshot_duplicate")
        canonical[snapshot_id] = EdgeUniverseSnapshot(
            snapshot_id=snapshot_id,
            as_of_ns=_require_positive_int(item.as_of_ns, "universe_snapshot_as_of_ns"),
            members=tuple(members[key] for key in sorted(members)),
            membership_source_reference=_require_text(
                item.membership_source_reference, "universe_snapshot_membership_source_reference"
            ),
            membership_evidence_digest=_require_optional_hex64(
                item.membership_evidence_digest, "universe_snapshot_membership_evidence_digest"
            ),
        )
    if not canonical:
        raise _fail("universe_snapshots_empty")
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_windows(
    values: object, snapshots: Sequence[EdgeUniverseSnapshot]
) -> tuple[EdgePreregisteredWindow, ...]:
    snapshot_ids = {snapshot.snapshot_id for snapshot in snapshots}
    windows: list[EdgePreregisteredWindow] = []
    for item in _require_sequence(values, "windows"):
        if type(item) is not EdgePreregisteredWindow:
            raise _fail("window_malformed")
        window = EdgePreregisteredWindow(
            window_id=_require_token(item.window_id, "window_id"),
            in_sample_start_ns=_require_positive_int(item.in_sample_start_ns, "window_in_sample_start_ns"),
            in_sample_end_ns=_require_positive_int(item.in_sample_end_ns, "window_in_sample_end_ns"),
            oos_start_ns=_require_positive_int(item.oos_start_ns, "window_oos_start_ns"),
            oos_end_ns=_require_positive_int(item.oos_end_ns, "window_oos_end_ns"),
            universe_snapshot_id=_require_token(item.universe_snapshot_id, "window_universe_snapshot_id"),
        )
        if not window.in_sample_start_ns < window.in_sample_end_ns <= window.oos_start_ns < window.oos_end_ns:
            raise _fail("window_interval_invalid")
        if window.universe_snapshot_id not in snapshot_ids:
            raise _fail("window_universe_snapshot_unregistered")
        if any(existing.window_id == window.window_id for existing in windows):
            raise _fail("window_id_duplicate")
        windows.append(window)
    if not windows:
        raise _fail("windows_empty")
    ordered = tuple(sorted(windows, key=lambda window: (window.oos_start_ns, window.window_id)))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.oos_end_ns > current.oos_start_ns:
            raise _fail("window_oos_overlap")
    if {window.universe_snapshot_id for window in ordered} != snapshot_ids:
        raise _fail("universe_snapshot_unreferenced")
    return ordered


def _canonical_leakage_proof(proof: object) -> EdgeLeakageProof:
    if type(proof) is not EdgeLeakageProof:
        raise _fail("leakage_proof_malformed")
    features: dict[str, ValidationFeatureTimestamp] = {}
    for item in _require_sequence(proof.feature_timestamps, "leakage_proof_feature_timestamps"):
        if type(item) is not ValidationFeatureTimestamp:
            raise _fail("leakage_proof_feature_timestamp_malformed")
        name = _require_text(item.feature_name, "leakage_proof_feature_name")
        if name in features:
            raise _fail("leakage_proof_feature_duplicate")
        features[name] = ValidationFeatureTimestamp(
            feature_name=name,
            event_time_ns=_require_positive_int(item.event_time_ns, "leakage_proof_feature_event_time_ns"),
            available_at_ns=_require_positive_int(item.available_at_ns, "leakage_proof_feature_available_at_ns"),
            finalized_at_ns=_require_optional_positive_int(
                item.finalized_at_ns, "leakage_proof_feature_finalized_at_ns"
            ),
            is_candle_or_bar_derived=_require_bool(item.is_candle_or_bar_derived, "leakage_proof_feature_bar_flag"),
            uses_current_bar=_require_bool(item.uses_current_bar, "leakage_proof_feature_current_bar_flag"),
        )
    observations: list[ValidationFundingObservation] = []
    for item in _require_sequence(proof.funding_observations, "leakage_proof_funding_observations"):
        if type(item) is not ValidationFundingObservation:
            raise _fail("leakage_proof_funding_observation_malformed")
        if item.final_rate is not None and not _is_finite_number(item.final_rate):
            raise _fail("leakage_proof_funding_final_rate_invalid")
        observation = ValidationFundingObservation(
            venue=_require_text(item.venue, "leakage_proof_funding_venue"),
            event_time_ns=_require_positive_int(item.event_time_ns, "leakage_proof_funding_event_time_ns"),
            available_at_ns=_require_positive_int(item.available_at_ns, "leakage_proof_funding_available_at_ns"),
            finalized_at_ns=_require_optional_positive_int(
                item.finalized_at_ns, "leakage_proof_funding_finalized_at_ns"
            ),
            final_rate=item.final_rate,
        )
        if any(_digest(_to_payload(existing)) == _digest(_to_payload(observation)) for existing in observations):
            raise _fail("leakage_proof_funding_observation_duplicate")
        observations.append(observation)
    indicators: dict[str, ValidationIndicatorPolicy] = {}
    for item in _require_sequence(proof.indicator_policies, "leakage_proof_indicator_policies"):
        if type(item) is not ValidationIndicatorPolicy:
            raise _fail("leakage_proof_indicator_policy_malformed")
        name = _require_text(item.indicator_name, "leakage_proof_indicator_name")
        rule = item.confirmation_rule
        if name in indicators:
            raise _fail("leakage_proof_indicator_duplicate")
        indicators[name] = ValidationIndicatorPolicy(
            indicator_name=name,
            repaint_risk=_require_bool(item.repaint_risk, "leakage_proof_indicator_repaint_risk"),
            confirmation_rule=None
            if rule is None
            else _require_text(rule, "leakage_proof_indicator_confirmation_rule"),
        )
    return EdgeLeakageProof(
        decision_timestamp_ns=_require_positive_int(proof.decision_timestamp_ns, "leakage_proof_decision_timestamp_ns"),
        feature_timestamps=tuple(features[key] for key in sorted(features)),
        funding_observations=tuple(
            sorted(observations, key=lambda item: (item.venue, item.event_time_ns, item.available_at_ns))
        ),
        indicator_policies=tuple(indicators[key] for key in sorted(indicators)),
        needs_research_reasons=_require_tokens(proof.needs_research_reasons, "leakage_proof_needs_research_reason"),
        insufficient_evidence_reasons=_require_tokens(
            proof.insufficient_evidence_reasons, "leakage_proof_insufficient_evidence_reason"
        ),
    )


# --- serialization and digests --------------------------------------------------------------------------------------


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


def _records_digest(records: Sequence[object]) -> str:
    return _digest([_to_payload(record) for record in records])


def edge_parameter_bounds_digest(parameter_bounds: object) -> str:
    """Canonical SHA-256 digest of a preregistered parameter bound set (order-insensitive)."""

    return _records_digest(_canonical_parameter_bounds(parameter_bounds))


def edge_evaluation_assumptions_digest(assumptions: object) -> str:
    """Canonical SHA-256 digest of an evaluation assumption identity set (order-insensitive)."""

    return _records_digest(canonical_edge_evaluation_assumptions(assumptions))


def edge_universe_snapshot_set_digest(universe_snapshots: object) -> str:
    """Canonical SHA-256 digest of a universe snapshot set, including every membership evidence digest."""

    return _records_digest(_canonical_universe_snapshots(universe_snapshots))


# --- strict payload conversion ---------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_str(value: object) -> str | None:
    return None if value is None else _as_str(value)


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _as_optional_number(value: object) -> object:
    if value is not None and not _is_finite_number(value):
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


def _as_record(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    return lambda value: _parse_exact(cls, value, converters)


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _is_well_formed(parse: Callable[[object], object], payload: object) -> bool:
    try:
        parse(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


_PARAMETER_BOUNDS_CONVERTER = _as_records(EdgeParameterBound, {})
_ASSIGNMENT_CONVERTER = _as_records(EdgeParameterAssignment, {})
_ASSUMPTIONS_CONVERTER = _as_records(
    EdgeEvaluationAssumption,
    {"kind": _as_enum(EdgeEvaluationAssumptionKind), "model_digest": _as_optional_str},
)


# --- EdgePreregistrationPolicy -------------------------------------------------------------------------------------


def build_edge_preregistration_policy(
    *,
    policy_id: str,
    correlation_id: str,
    candidate_strategy_id: str,
    parameter_bounds: Sequence[EdgeParameterBound],
    min_oos_window_count: int | None = None,
    approved_variant_ledger_digest: str | None = None,
    approved: bool = False,
    approval_reference: str | None = None,
    approval_digest: str | None = None,
) -> EdgePreregistrationPolicy:
    """Build a digest-bound human approval record of one candidate's preregistration inputs.

    Malformed input raises. A missing minimum OOS window count, variant ledger approval, approval flag, reference or
    digest yields ``POLICY_REJECTED``; nothing is defaulted and no number is chosen here. The approver reads the exact
    ``variant_ledger_digest`` from an unapproved EF-5 ledger built before any performance is visible.
    """

    policy_id = _require_text(policy_id, "preregistration_policy_id")
    correlation_id = _require_text(correlation_id, "preregistration_policy_correlation_id")
    candidate_strategy_id = _require_text(candidate_strategy_id, "preregistration_policy_candidate_strategy_id")
    bounds = _canonical_parameter_bounds(parameter_bounds)
    min_count = _require_optional_positive_int(min_oos_window_count, "preregistration_policy_min_oos_window_count")
    ledger_digest = _require_optional_hex64(
        approved_variant_ledger_digest, "preregistration_policy_variant_ledger_digest"
    )
    approved = _require_bool(approved, "preregistration_policy_approved")
    if approval_reference is not None:
        approval_reference = _require_text(approval_reference, "preregistration_policy_approval_reference")
    approval_digest = _require_optional_hex64(approval_digest, "preregistration_policy_approval_digest")
    missing = {
        "min_oos_window_count_missing": min_count is None,
        "variant_ledger_approval_missing": ledger_digest is None,
        "not_approved": approved is not True,
        "approval_reference_missing": approval_reference is None,
        "approval_digest_missing": approval_digest is None,
    }
    reason_codes = _sorted_unique([_policy_reason(code) for code, is_missing in missing.items() if is_missing])
    status = (
        EdgePreregistrationPolicyStatus.POLICY_REJECTED
        if reason_codes
        else EdgePreregistrationPolicyStatus.POLICY_READY
    )
    seed = EdgePreregistrationPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        status=status,
        ready=status is EdgePreregistrationPolicyStatus.POLICY_READY,
        policy_id=policy_id,
        correlation_id=correlation_id,
        candidate_strategy_id=candidate_strategy_id,
        parameter_bounds=bounds,
        parameter_bounds_digest=_records_digest(bounds),
        min_oos_window_count=min_count,
        approved_variant_ledger_digest=ledger_digest,
        approved=approved,
        approval_reference=approval_reference,
        approval_digest=approval_digest,
        reason_codes=reason_codes,
        policy_digest="",
    )
    return replace(seed, policy_digest=edge_payload_digest(_to_payload(seed), _POLICY_SELF_DIGEST_FIELD))


def edge_preregistration_policy_to_dict(policy: EdgePreregistrationPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping for a preregistration policy, including its self-digest."""

    return _to_payload(policy)


def edge_preregistration_policy_digest(policy: EdgePreregistrationPolicy) -> str:
    """Recompute the canonical policy digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(policy), _POLICY_SELF_DIGEST_FIELD)


_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgePreregistrationPolicyStatus),
    "ready": _as_bool,
    "parameter_bounds": _PARAMETER_BOUNDS_CONVERTER,
    "min_oos_window_count": _as_optional_int,
    "approved_variant_ledger_digest": _as_optional_str,
    "approved": _as_bool,
    "approval_reference": _as_optional_str,
    "approval_digest": _as_optional_str,
    "reason_codes": _as_str_tuple,
    "policy_only": _as_bool,
    **dict.fromkeys(_BASELINE_FLAG_NAMES, _as_bool),
}


def edge_preregistration_policy_from_payload(payload: object) -> EdgePreregistrationPolicy:
    """Strictly reconstruct a preregistration policy from its serialized payload (no semantic proof)."""

    return _parse_exact(EdgePreregistrationPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def edge_preregistration_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a preregistration policy snapshot."""

    return _is_well_formed(edge_preregistration_policy_from_payload, payload)


def _reassemble_policy(policy: object) -> EdgePreregistrationPolicy:
    return build_edge_preregistration_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        correlation_id=policy.correlation_id,  # type: ignore[attr-defined]
        candidate_strategy_id=policy.candidate_strategy_id,  # type: ignore[attr-defined]
        parameter_bounds=policy.parameter_bounds,  # type: ignore[attr-defined]
        min_oos_window_count=policy.min_oos_window_count,  # type: ignore[attr-defined]
        approved_variant_ledger_digest=policy.approved_variant_ledger_digest,  # type: ignore[attr-defined]
        approved=policy.approved,  # type: ignore[attr-defined]
        approval_reference=policy.approval_reference,  # type: ignore[attr-defined]
        approval_digest=policy.approval_digest,  # type: ignore[attr-defined]
    )


def verify_edge_preregistration_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a preregistration policy by strict parse and reassembly through its builder. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=EdgePreregistrationPolicy,
        to_payload=_to_payload,
        parse_payload=edge_preregistration_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_POLICY_SELF_DIGEST_FIELD,
        reason=_policy_reason,
    )


def _policy_authority(
    binding: EdgeAuthorityBinding | None,
    *,
    correlation_id: str,
    candidate_strategy_id: str,
    parameter_bounds_digest: str,
    variant_ledger_digest: str,
) -> tuple[tuple[str, ...], tuple[str, ...], int | None]:
    """Returns unprefixed ``(integrity_codes, governance_needs, approved_min_oos_window_count)``."""

    if binding is None:
        return (), ("preregistration_policy_missing",), None
    policy = edge_preregistration_policy_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_preregistration_policy(policy)
    if not verification.intact:
        return tuple(f"preregistration_policy_integrity_failure:{code}" for code in verification.reason_codes), (), None
    if verification.recomputed_digest != binding.expected_digest:
        return ("preregistration_policy_digest_mismatch",), (), None
    mismatches = {
        "preregistration_policy_not_ready": policy.status is not EdgePreregistrationPolicyStatus.POLICY_READY,
        "preregistration_policy_correlation_mismatch": policy.correlation_id != correlation_id,
        "preregistration_policy_candidate_mismatch": policy.candidate_strategy_id != candidate_strategy_id,
        "preregistration_policy_parameter_bounds_mismatch": policy.parameter_bounds_digest != parameter_bounds_digest,
        "preregistration_policy_variant_ledger_mismatch": (
            policy.approved_variant_ledger_digest != variant_ledger_digest
        ),
    }
    needs = tuple(code for code, mismatched in mismatches.items() if mismatched)
    return (), needs, None if needs else policy.min_oos_window_count


# --- authenticated admission chain ----------------------------------------------------------------------------------


def reprove_edge_admitted_chain(
    admission_binding: EdgeAuthorityBinding, *, root_intake_digest: str, correlation_id: str
) -> tuple[tuple[str, ...], EdgeAdmittedChain | None]:
    """Independently re-prove the EF-4 → EF-3 → EF-2 chain behind an EF-4 admission binding.

    Every level is re-proven through its public verifier; every nested digest edge, the explicit EF-2 root anchor and
    the correlation must match, and every level must be READY. Returns unprefixed integrity codes and the
    authenticated chain (``None`` on any failure). A binding that is not a well-formed EF-4 authority raises
    ``EdgeLeakageBiasEvidenceError``.
    """

    binding = require_edge_authority_binding(
        admission_binding,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("admission"),
        optional=False,
    )
    admission = edge_strategy_spec_admission_from_payload(edge_authority_binding_snapshot(binding))  # type: ignore[arg-type]
    verification = verify_edge_strategy_spec_admission(admission)
    if not verification.intact:
        return tuple(f"admission_integrity_failure:{code}" for code in verification.reason_codes), None
    if verification.recomputed_digest != binding.expected_digest:  # type: ignore[union-attr]
        return ("admission_digest_mismatch",), None
    if admission.correlation_id != correlation_id:
        return ("admission_correlation_mismatch",), None
    if admission.status is not EdgeEvidenceStatus.READY:
        return ("admission_rejected",), None
    source_packet = edge_source_packet_evidence_from_payload(
        edge_authority_binding_snapshot(admission.predecessor_binding)
    )
    source_verification = verify_edge_source_packet_evidence(source_packet)
    if not source_verification.intact:
        return tuple(f"source_packet_integrity_failure:{code}" for code in source_verification.reason_codes), None
    if source_verification.recomputed_digest != admission.predecessor_digest:
        return ("chain_splice_source_packet_mismatch",), None
    if source_packet.correlation_id != correlation_id:
        return ("source_packet_correlation_mismatch",), None
    if source_packet.status is not EdgeEvidenceStatus.READY:
        return ("source_packet_rejected",), None
    intake = edge_idea_intake_evidence_from_payload(edge_authority_binding_snapshot(source_packet.root_intake_binding))
    intake_verification = verify_edge_idea_intake_evidence(intake)
    if not intake_verification.intact:
        return tuple(f"intake_integrity_failure:{code}" for code in intake_verification.reason_codes), None
    root_digests = {
        intake_verification.recomputed_digest,
        source_packet.root_intake_digest,
        admission.root_intake_digest,
    }
    if root_digests != {root_intake_digest}:
        return ("chain_splice_root_intake_mismatch",), None
    if intake.correlation_id != correlation_id:
        return ("intake_correlation_mismatch",), None
    if intake.status is not EdgeEvidenceStatus.READY:
        return ("intake_rejected",), None
    spec_result = validate_strategy_spec(edge_authority_binding_snapshot(admission.strategy_spec_binding))
    if spec_result.accepted is not True or type(spec_result.spec) is not StrategySpec:
        return ("admission_strategy_spec_not_accepted",), None
    return (), EdgeAdmittedChain(intake, source_packet, admission, spec_result.spec)


# --- semantic evaluation ----------------------------------------------------------------------------------------------


def _predecessor_reasons(admission: EdgeStrategySpecAdmissionEvidence) -> tuple[list[str], list[str], list[str]]:
    if admission.advances is True:
        return [], [], []
    code = [_reason(f"predecessor_not_advanced:{admission.gate_verdict.value}")]
    if admission.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        return [], code, []
    if admission.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        return [], [], code
    return code, [], []


def _pit_policy(source_packet: EdgeSourcePacketEvidence) -> dict[str, dict[str, str | None]]:
    return {
        record.data_requirement_key: {
            "event_time_policy": record.event_time_policy,
            "available_at_policy": record.available_at_policy,
            "finalized_at_policy": record.finalized_at_policy,
        }
        for record in source_packet.series
        if record.registry_requirement_bound
    }


def _leakage_reasons(
    chain: EdgeAdmittedChain,
    proof: EdgeLeakageProof,
    assumptions: Sequence[EdgeEvaluationAssumption],
    feature_set: Sequence[str],
) -> tuple[str, tuple[str, ...], list[str], list[str]]:
    model_ids = {assumption.kind: assumption.model_id for assumption in assumptions}
    result = evaluate_leakage_bias_repaint(
        LeakageBiasRepaintInput(
            strategy_spec=chain.strategy_spec,
            decision_timestamp_ns=proof.decision_timestamp_ns,
            pit_policy=_pit_policy(chain.source_packet),
            feature_timestamps=proof.feature_timestamps,
            funding_observations=proof.funding_observations,
            indicator_policies=proof.indicator_policies,
            fee_assumption=model_ids.get(EdgeEvaluationAssumptionKind.FEE_MODEL),
            slippage_assumption=model_ids.get(EdgeEvaluationAssumptionKind.SLIPPAGE_MODEL),
            funding_assumption=model_ids.get(EdgeEvaluationAssumptionKind.FUNDING_MODEL),
            needs_research_reasons=proof.needs_research_reasons,
            insufficient_evidence_reasons=proof.insufficient_evidence_reasons,
        )
    )
    validator_codes = (*result.rejection_reasons, *result.needs_research_reasons)
    fail: list[str] = []
    needs_external: list[str] = []
    if result.status is LeakageBiasRepaintStatus.REJECT:
        fail.extend(_reason(code) for code in validator_codes)
    elif result.status is not LeakageBiasRepaintStatus.PASS:
        needs_external.extend(_reason(code) for code in validator_codes)
    features = set(feature_set)
    proven = {item.feature_name for item in proof.feature_timestamps}
    fail.extend(_reason(f"leakage_proof_feature_missing:{name}") for name in sorted(features - proven))
    fail.extend(_reason(f"leakage_proof_feature_unregistered:{name}") for name in sorted(proven - features))
    fail.extend(
        _reason(f"leakage_proof_indicator_unregistered:{item.indicator_name}")
        for item in proof.indicator_policies
        if item.indicator_name not in features
    )
    return result.status.value, validator_codes, fail, needs_external


def _ledger_structure_reasons(
    bounds: Sequence[EdgeParameterBound],
    structures: Sequence[EdgeLabelThresholdStructure],
    variants: Sequence[EdgeVariantRegistration],
    assumptions: Sequence[EdgeEvaluationAssumption],
) -> tuple[list[str], list[str]]:
    bound_by_id = {bound.parameter_id: bound for bound in bounds}
    fail: list[str] = []
    for variant in variants:
        assigned = {item.parameter_id for item in variant.parameter_assignment}
        fail.extend(
            _reason(f"variant_parameter_unassigned:{variant.variant_id}:{parameter_id}")
            for parameter_id in sorted(set(bound_by_id) - assigned)
        )
        for item in variant.parameter_assignment:
            bound = bound_by_id.get(item.parameter_id)
            if bound is None:
                fail.append(_reason(f"variant_parameter_unbound:{variant.variant_id}:{item.parameter_id}"))
            elif not Decimal(bound.lower) <= Decimal(item.value) <= Decimal(bound.upper):
                fail.append(_reason(f"variant_parameter_out_of_bounds:{variant.variant_id}:{item.parameter_id}"))
    for structure in structures:
        fail.extend(
            _reason(f"label_threshold_structure_parameter_unbound:{structure.structure_id}:{parameter_id}")
            for parameter_id in structure.parameter_ids
            if parameter_id not in bound_by_id
        )
    needs_external = [
        _reason(f"evaluation_assumption_unresolved:{assumption.kind.value}")
        for assumption in assumptions
        if assumption.model_digest is None
    ]
    return fail, needs_external


def _survivorship_reasons(
    snapshots: Sequence[EdgeUniverseSnapshot],
    windows: Sequence[EdgePreregisteredWindow],
    instrument_universe: Sequence[str],
) -> tuple[list[str], list[str]]:
    fail: list[str] = []
    needs_external: list[str] = []
    by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    for snapshot in snapshots:
        for member in snapshot.members:
            if member.listed_at_ns > snapshot.as_of_ns:
                fail.append(
                    _reason(f"universe_member_listed_after_snapshot:{snapshot.snapshot_id}:{member.instrument}")
                )
            if member.delisted_at_ns is not None and member.delisted_at_ns <= snapshot.as_of_ns:
                fail.append(
                    _reason(f"universe_member_delisted_before_snapshot:{snapshot.snapshot_id}:{member.instrument}")
                )
        if snapshot.membership_evidence_digest is None:
            needs_external.append(_reason(f"survivorship_membership_evidence_unresolved:{snapshot.snapshot_id}"))
    for window in windows:
        snapshot = by_id[window.universe_snapshot_id]
        if snapshot.as_of_ns > window.in_sample_start_ns:
            fail.append(_reason(f"window_universe_snapshot_after_window_start:{window.window_id}"))
        members = {member.instrument: member for member in snapshot.members}
        for instrument in instrument_universe:
            member = members.get(instrument)
            if member is None:
                fail.append(_reason(f"window_universe_missing_spec_instrument:{window.window_id}:{instrument}"))
            elif member.delisted_at_ns is not None and member.delisted_at_ns < window.oos_end_ns:
                fail.append(_reason(f"spec_instrument_delisted_before_window_end:{window.window_id}:{instrument}"))
    return fail, needs_external


def _ledger_entries(
    variants: Sequence[EdgeVariantRegistration], component_digests: Mapping[str, str]
) -> tuple[EdgeVariantLedgerEntry, ...]:
    entries: list[EdgeVariantLedgerEntry] = []
    for variant in variants:
        body = {
            "variant_id": variant.variant_id,
            "parameter_assignment": [_to_payload(item) for item in variant.parameter_assignment],
            **component_digests,
        }
        entries.append(
            EdgeVariantLedgerEntry(
                variant_id=variant.variant_id,
                parameter_assignment=variant.parameter_assignment,
                variant_registration_digest=_digest(body),
                **component_digests,
            )
        )
    return tuple(entries)


# --- EF-5 ledger -----------------------------------------------------------------------------------------------------


def _assemble_ledger(
    *,
    predecessor_binding: object,
    root_intake_digest: object,
    preregistration_policy_binding: object,
    ledger_id: object,
    correlation_id: object,
    parameter_bounds: object,
    label_threshold_structures: object,
    evaluation_assumptions: object,
    universe_snapshots: object,
    windows: object,
    variants: object,
    primary_variant_id: object,
    leakage_proof: object,
) -> EdgeLeakageBiasEvidence:
    """The one EF-5 assembly path, shared by the builder and verifier reassembly."""

    admission_binding = require_edge_authority_binding(
        predecessor_binding,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )
    policy_binding = require_edge_authority_binding(
        preregistration_policy_binding,
        shape=edge_preregistration_policy_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("preregistration_policy"),
        optional=True,
    )
    if not edge_is_hex64(root_intake_digest):
        raise _fail("root_intake_digest_invalid")
    ledger_id = _require_text(ledger_id, "ledger_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    bounds = _canonical_parameter_bounds(parameter_bounds)
    structures = _canonical_label_threshold_structures(label_threshold_structures)
    assumptions = canonical_edge_evaluation_assumptions(evaluation_assumptions)
    snapshots = _canonical_universe_snapshots(universe_snapshots)
    schedule = _canonical_windows(windows, snapshots)
    registrations = _canonical_variants(variants)
    primary = _require_token(primary_variant_id, "primary_variant_id")
    if primary not in {variant.variant_id for variant in registrations}:
        raise _fail("primary_variant_id_unregistered")
    proof = _canonical_leakage_proof(leakage_proof)

    chain_codes, chain = reprove_edge_admitted_chain(
        admission_binding,  # type: ignore[arg-type]
        root_intake_digest=root_intake_digest,  # type: ignore[arg-type]
        correlation_id=correlation_id,
    )
    spec = None if chain is None else chain.strategy_spec
    feature_set = () if spec is None else tuple(sorted(spec.feature_requirements))
    instrument_universe = () if spec is None else spec.instrument_universe
    digests = {
        "feature_set_digest": _digest(list(feature_set)),
        "label_threshold_structures_digest": _records_digest(structures),
        "evaluation_assumptions_digest": _records_digest(assumptions),
        "window_schedule_digest": _records_digest(schedule),
        "universe_snapshot_set_digest": _records_digest(snapshots),
    }
    bounds_digest = _records_digest(bounds)
    entries = _ledger_entries(registrations, digests)
    variant_ledger_digest = _digest(
        {"primary_variant_id": primary, "ledger_entries": [_to_payload(entry) for entry in entries]}
    )
    policy_integrity, policy_needs, approved_min = _policy_authority(
        policy_binding,  # type: ignore[arg-type]
        correlation_id=correlation_id,
        candidate_strategy_id="" if chain is None else chain.intake.candidate_strategy_id,
        parameter_bounds_digest=bounds_digest,
        variant_ledger_digest=variant_ledger_digest,
    )
    integrity = _sorted_unique([_reason(code) for code in (*chain_codes, *policy_integrity)])

    leakage_status, leakage_codes = "", ()
    survivorship_proven, survivorship_basis = False, _SURVIVORSHIP_TRUTH_UNRESOLVED
    if integrity or chain is None:
        status, verdict, verdict_reasons, approved_min = (
            EdgeEvidenceStatus.REJECTED,
            EdgeGateVerdict.NOT_EVALUATED,
            (),
            None,
        )
    else:
        fail, needs_external, needs_governance = _predecessor_reasons(chain.admission)
        leakage_status, leakage_codes, leakage_fail, leakage_needs = _leakage_reasons(
            chain, proof, assumptions, feature_set
        )
        structure_fail, assumption_needs = _ledger_structure_reasons(bounds, structures, registrations, assumptions)
        survivorship_fail, survivorship_needs = _survivorship_reasons(snapshots, schedule, instrument_universe)
        fail.extend([*leakage_fail, *structure_fail, *survivorship_fail])
        needs_external.extend([*leakage_needs, *assumption_needs, *survivorship_needs])
        needs_governance.extend(_reason(code) for code in policy_needs)
        if approved_min is not None and len(schedule) < approved_min:
            fail.append(_reason("preregistered_window_count_below_approved_minimum"))
        survivorship_proven = not survivorship_fail
        if survivorship_proven and not survivorship_needs and policy_binding is not None and not policy_needs:
            survivorship_basis = _SURVIVORSHIP_TRUTH_ATTESTED
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    seed = EdgeLeakageBiasEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        ledger_id=ledger_id,
        correlation_id=correlation_id,
        root_intake_digest=root_intake_digest,  # type: ignore[arg-type]
        predecessor_binding=admission_binding,  # type: ignore[arg-type]
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        predecessor_digest=admission_binding.expected_digest,  # type: ignore[union-attr]
        candidate_strategy_id="" if chain is None else chain.intake.candidate_strategy_id,
        strategy_id="" if spec is None else spec.strategy_id,
        strategy_spec_digest="" if chain is None else chain.admission.strategy_spec_digest,
        admitted_kill_criteria_digest="" if chain is None else chain.admission.admitted_kill_criteria_digest,
        instrument_universe=instrument_universe,
        feature_set=feature_set,
        feature_set_digest=digests["feature_set_digest"],
        spec_conditions_digest=""
        if spec is None
        else _digest(
            {
                "entry_conditions": list(spec.entry_conditions),
                "exit_conditions": list(spec.exit_conditions),
                "invalidation_conditions": list(spec.invalidation_conditions),
            }
        ),
        pit_policy_digest="" if chain is None else _digest(_pit_policy(chain.source_packet)),
        parameter_bounds=bounds,
        parameter_bounds_digest=bounds_digest,
        label_threshold_structures=structures,
        label_threshold_structures_digest=digests["label_threshold_structures_digest"],
        evaluation_assumptions=assumptions,
        evaluation_assumptions_digest=digests["evaluation_assumptions_digest"],
        universe_snapshots=snapshots,
        universe_snapshot_set_digest=digests["universe_snapshot_set_digest"],
        windows=schedule,
        window_schedule_digest=digests["window_schedule_digest"],
        variants=registrations,
        ledger_entries=entries,
        primary_variant_id=primary,
        variant_ledger_digest=variant_ledger_digest,
        multiple_testing_count=len(registrations),
        leakage_proof=proof,
        leakage_repaint_status=leakage_status,
        leakage_repaint_reason_codes=leakage_codes,
        survivorship_internal_consistency_proven=survivorship_proven,
        survivorship_external_truth_basis=survivorship_basis,
        preregistration_policy_binding=policy_binding,
        approved_min_oos_window_count=approved_min,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        ledger_digest="",
        **edge_gate_milestone_claims(
            _GATE_ID, preregistration_sealed=status is EdgeEvidenceStatus.READY, performance_data_consumed=False
        ),
    )
    return replace(seed, ledger_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_leakage_bias_evidence(
    predecessor: EdgeStrategySpecAdmissionEvidence,
    *,
    expected_predecessor_digest: str,
    expected_root_intake_digest: str,
    ledger_id: str,
    correlation_id: str,
    parameter_bounds: Sequence[EdgeParameterBound],
    label_threshold_structures: Sequence[EdgeLabelThresholdStructure],
    evaluation_assumptions: Sequence[EdgeEvaluationAssumption],
    universe_snapshots: Sequence[EdgeUniverseSnapshot],
    windows: Sequence[EdgePreregisteredWindow],
    variants: Sequence[EdgeVariantRegistration],
    primary_variant_id: str,
    leakage_proof: EdgeLeakageProof,
    preregistration_policy: EdgePreregistrationPolicy | None = None,
    expected_preregistration_policy_digest: str | None = None,
) -> EdgeLeakageBiasEvidence:
    """Build a deterministic EF-5 preregistration ledger over an EF-4 admission, before any performance exists.

    Malformed caller input or a non-serializable upstream object raises ``EdgeLeakageBiasEvidenceError``. An
    authentic chain or policy that fails re-proof (or a splice) yields ``REJECTED``/``NOT_EVALUATED``. Otherwise the
    ledger is ``READY`` and sealed with ``FAIL``, ``NEEDS_EXTERNAL_FACTS``, ``NEEDS_GOVERNANCE_APPROVAL`` or ``PASS``.
    """

    if type(predecessor) is not EdgeStrategySpecAdmissionEvidence:
        raise _fail("predecessor_malformed")
    try:
        predecessor_payload = edge_strategy_spec_admission_to_dict(predecessor)
    except Exception as exc:  # noqa: BLE001 - a hollow predecessor object is a construction error, never a receipt
        raise _fail("predecessor_not_serializable") from exc
    admission_binding = build_edge_authority_binding(
        snapshot_payload=predecessor_payload,
        expected_digest=expected_predecessor_digest,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("predecessor"),
    )
    policy_binding = None
    if preregistration_policy is None:
        if expected_preregistration_policy_digest is not None:
            raise _fail("preregistration_policy_expected_digest_unexpected")
    else:
        if type(preregistration_policy) is not EdgePreregistrationPolicy:
            raise _fail("preregistration_policy_malformed")
        try:
            policy_payload = _to_payload(preregistration_policy)
        except Exception as exc:  # noqa: BLE001 - a hollow policy object is a construction error, never a receipt
            raise _fail("preregistration_policy_not_serializable") from exc
        policy_binding = build_edge_authority_binding(
            snapshot_payload=policy_payload,
            expected_digest=expected_preregistration_policy_digest,
            shape=edge_preregistration_policy_payload_is_well_formed,
            error=EdgeLeakageBiasEvidenceError,
            code=_reason("preregistration_policy"),
        )
    return _assemble_ledger(
        predecessor_binding=admission_binding,
        root_intake_digest=expected_root_intake_digest,
        preregistration_policy_binding=policy_binding,
        ledger_id=ledger_id,
        correlation_id=correlation_id,
        parameter_bounds=parameter_bounds,
        label_threshold_structures=label_threshold_structures,
        evaluation_assumptions=evaluation_assumptions,
        universe_snapshots=universe_snapshots,
        windows=windows,
        variants=variants,
        primary_variant_id=primary_variant_id,
        leakage_proof=leakage_proof,
    )


def edge_leakage_bias_evidence_to_dict(evidence: EdgeLeakageBiasEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-5 evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_leakage_bias_evidence_digest(evidence: EdgeLeakageBiasEvidence) -> str:
    """Recompute the canonical EF-5 ledger digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def _parse_predecessor_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_strategy_spec_admission_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )


def _parse_policy_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_preregistration_policy_payload_is_well_formed,
        error=EdgeLeakageBiasEvidenceError,
        code=_reason("preregistration_policy"),
        optional=True,
    )


_TIMES = {"event_time_ns": _as_int, "available_at_ns": _as_int, "finalized_at_ns": _as_optional_int}
_LEDGER_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "predecessor_binding": _parse_predecessor_binding,
    "instrument_universe": _as_str_tuple,
    "feature_set": _as_str_tuple,
    "parameter_bounds": _PARAMETER_BOUNDS_CONVERTER,
    "label_threshold_structures": _as_records(
        EdgeLabelThresholdStructure, {"kind": _as_enum(EdgeLabelThresholdKind), "parameter_ids": _as_str_tuple}
    ),
    "evaluation_assumptions": _ASSUMPTIONS_CONVERTER,
    "universe_snapshots": _as_records(
        EdgeUniverseSnapshot,
        {
            "as_of_ns": _as_int,
            "members": _as_records(EdgeUniverseMember, {"listed_at_ns": _as_int, "delisted_at_ns": _as_optional_int}),
            "membership_evidence_digest": _as_optional_str,
        },
    ),
    "windows": _as_records(
        EdgePreregisteredWindow,
        dict.fromkeys(("in_sample_start_ns", "in_sample_end_ns", "oos_start_ns", "oos_end_ns"), _as_int),
    ),
    "variants": _as_records(EdgeVariantRegistration, {"parameter_assignment": _ASSIGNMENT_CONVERTER}),
    "ledger_entries": _as_records(EdgeVariantLedgerEntry, {"parameter_assignment": _ASSIGNMENT_CONVERTER}),
    "multiple_testing_count": _as_int,
    "leakage_proof": _as_record(
        EdgeLeakageProof,
        {
            "decision_timestamp_ns": _as_int,
            "feature_timestamps": _as_records(
                ValidationFeatureTimestamp,
                {**_TIMES, "is_candle_or_bar_derived": _as_bool, "uses_current_bar": _as_bool},
            ),
            "funding_observations": _as_records(
                ValidationFundingObservation, {**_TIMES, "final_rate": _as_optional_number}
            ),
            "indicator_policies": _as_records(
                ValidationIndicatorPolicy, {"repaint_risk": _as_bool, "confirmation_rule": _as_optional_str}
            ),
            "needs_research_reasons": _as_str_tuple,
            "insufficient_evidence_reasons": _as_str_tuple,
        },
    ),
    "leakage_repaint_reason_codes": _as_str_tuple,
    "survivorship_internal_consistency_proven": _as_bool,
    "preregistration_policy_binding": _parse_policy_binding,
    "approved_min_oos_window_count": _as_optional_int,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    "preregistration_sealed": _as_bool,
    "performance_data_consumed": _as_bool,
    **dict.fromkeys(_PERMANENT_FLAG_NAMES, _as_bool),
}


def edge_leakage_bias_evidence_from_payload(payload: object) -> EdgeLeakageBiasEvidence:
    """Strictly reconstruct EF-5 evidence from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_leakage_bias_evidence`` on the result.
    """

    return _parse_exact(EdgeLeakageBiasEvidence, payload, _LEDGER_CONVERTERS)  # type: ignore[return-value]


def edge_leakage_bias_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-5 predecessor snapshot."""

    return _is_well_formed(edge_leakage_bias_evidence_from_payload, payload)


def _reassemble_ledger(evidence: object) -> EdgeLeakageBiasEvidence:
    return _assemble_ledger(
        predecessor_binding=evidence.predecessor_binding,  # type: ignore[attr-defined]
        root_intake_digest=evidence.root_intake_digest,  # type: ignore[attr-defined]
        preregistration_policy_binding=evidence.preregistration_policy_binding,  # type: ignore[attr-defined]
        ledger_id=evidence.ledger_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        parameter_bounds=evidence.parameter_bounds,  # type: ignore[attr-defined]
        label_threshold_structures=evidence.label_threshold_structures,  # type: ignore[attr-defined]
        evaluation_assumptions=evidence.evaluation_assumptions,  # type: ignore[attr-defined]
        universe_snapshots=evidence.universe_snapshots,  # type: ignore[attr-defined]
        windows=evidence.windows,  # type: ignore[attr-defined]
        variants=evidence.variants,  # type: ignore[attr-defined]
        primary_variant_id=evidence.primary_variant_id,  # type: ignore[attr-defined]
        leakage_proof=evidence.leakage_proof,  # type: ignore[attr-defined]
    )


def verify_edge_leakage_bias_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-5 evidence by strict parse and reassembly from its carried bindings, anchors and registrations.

    READY and builder-produced REJECTED ledgers alike must equal the reassembled artifact. Total: never raises.
    """

    return verify_edge_artifact_total(
        evidence,
        cls=EdgeLeakageBiasEvidence,
        to_payload=_to_payload,
        parse_payload=edge_leakage_bias_evidence_from_payload,
        reassemble=_reassemble_ledger,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EdgeAdmittedChain",
    "EdgeEvaluationAssumption",
    "EdgeEvaluationAssumptionKind",
    "EdgeLabelThresholdKind",
    "EdgeLabelThresholdStructure",
    "EdgeLeakageBiasEvidence",
    "EdgeLeakageBiasEvidenceError",
    "EdgeLeakageProof",
    "EdgeParameterAssignment",
    "EdgeParameterBound",
    "EdgePreregisteredWindow",
    "EdgePreregistrationPolicy",
    "EdgePreregistrationPolicyStatus",
    "EdgeUniverseMember",
    "EdgeUniverseSnapshot",
    "EdgeVariantLedgerEntry",
    "EdgeVariantRegistration",
    "build_edge_leakage_bias_evidence",
    "build_edge_preregistration_policy",
    "canonical_edge_evaluation_assumptions",
    "edge_evaluation_assumptions_digest",
    "edge_leakage_bias_evidence_digest",
    "edge_leakage_bias_evidence_from_payload",
    "edge_leakage_bias_evidence_payload_is_well_formed",
    "edge_leakage_bias_evidence_to_dict",
    "edge_parameter_bounds_digest",
    "edge_preregistration_policy_digest",
    "edge_preregistration_policy_from_payload",
    "edge_preregistration_policy_payload_is_well_formed",
    "edge_preregistration_policy_to_dict",
    "edge_universe_snapshot_set_digest",
    "reprove_edge_admitted_chain",
    "verify_edge_leakage_bias_evidence",
    "verify_edge_preregistration_policy",
]
