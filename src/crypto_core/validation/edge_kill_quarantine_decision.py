"""Edge Factory EF-8: the governed kill / disable / quarantine / re-admission lifecycle of a paper-admitted candidate.

EF-8 is the lifecycle state machine of ``docs/crypto_core/edge_factory_design.md`` §1.7: ACTIVE → DISABLED (a sealed
kill criterion is hit) → [> 30 UTC days] QUARANTINE → [>= 14 UTC days + revalidation from EF-5 onward] governed
re-admission to ACTIVE. Inside a bound chain there is NO auto-reactivation. Every transition is one immutable,
digest-bound HISTORICAL receipt that carries its reason and authenticates its exact prior. EF-8 proves lifecycle PROCESS
history only; it never means current paper admission, the current lifecycle head, an edge, profitability, paper
performance, portfolio allocation, capital, execution permission, operational readiness or any live/shadow/Deribit
authority.

Authority (shared kernel ``edge_artifact_core``):

* Admission. ``INITIAL_ACTIVATION`` consumes an actual ``EdgePaperAdmissionDecision`` as an ``EdgeAuthorityBinding``
  re-proven through the public ``verify_edge_paper_admission_decision`` against the caller's anchor (which re-proves
  EF-6 → EF-2); its root and correlation must equal this artifact's anchors. Only an EF-7 that is READY + PASS +
  advancing, admitted to paper and SEALED opens a lifecycle chain (a historical ACTIVE result); an authentic
  non-advancing EF-7 propagates its verdict and anything else is REJECTED. An activation may not precede its
  admission's out-of-sample evaluation horizon (the latest OOS end of the authenticated EF-6 frames).
* Seal. No caller input carries kill criteria. The immutable kill policy is the EF-7 seal: the final criteria, their
  digest (recomputed through the public EF-2 digest) and the kill-criteria record digest (recomputed from the EF-7
  lineage fields) must agree with ``sealed_kill_criteria_digest``. Every later artifact re-derives the seal from its
  authenticated prior, so a criterion, threshold, comparator, metric, basis, order or digest mutation anywhere in the
  chain never verifies. Every sealed threshold must be evaluable under the committed numeric rule before activation.
* Chain. Every later transition binds its exact prior EF-8 artifact and re-proves it through the public
  ``verify_edge_kill_quarantine_decision`` against the caller's anchor (recursively down to the EF-7 genesis); root and
  correlation must match. A REJECTED prior is REJECTED and a non-advancing prior propagates its verdict, so only an
  advancing receipt is ever a valid predecessor. A prior digest alone is never authority.
* Transitions: INITIAL_ACTIVATION → ACTIVE; KILL_DISABLE ACTIVE → DISABLED; QUARANTINE_ENTRY DISABLED → QUARANTINE;
  GOVERNED_READMISSION QUARANTINE → ACTIVE as a NEW cycle. Any other source state is FAIL. Coordinates are explicit
  caller UTC epoch nanoseconds (int64, never a clock) and strictly increase along the chain.
* Kill. KILL_DISABLE evaluates ONE ``EdgeKillObservation`` against the sealed criterion with the same id, metric and
  evaluation basis by exact integer comparison of canonical scale-18 texts (above ``>``, at_or_above ``>=``, below
  ``<``, at_or_below ``<=``); one triggered criterion suffices (``any_single_criterion_triggers_kill.v1``). The
  observation is caller-declared, digest-bound provenance that can only DISABLE: it never activates or re-admits and
  never proves performance, profitability or a venue fact. An unsealed criterion, a mismatched metric or basis, or an
  untriggered value is FAIL; nothing is defaulted or invented.
* Time. QUARANTINE_ENTRY needs strictly more than 30 UTC days since the disable (exactly 30 is not enough);
  GOVERNED_READMISSION needs at least 14 UTC days since the quarantine entry (exactly 14 is enough). Elapsed time alone
  never re-admits.
* Revalidation (EF-5 onward). GOVERNED_READMISSION consumes a NEW authentic EF-7 re-proven like the admission, with the
  same lifecycle subject (root, correlation, candidate, edge family, strategy, spec, EF-4 admission, EF-3 manifest,
  market type, pinned universe, paper sleeve) and the same seal, else REJECTED. It must be READY + PASS (else its
  verdict propagates), never an EF-7 or EF-6 this lifecycle already consumed, and its OOS evaluation horizon must lie
  strictly after the current cycle's disable and not after the re-admission coordinate, so a re-admission always rests
  on post-kill evaluation evidence the killed admission never had. EF-5 may be re-proven unchanged.
* Governance. ``EdgeReadmissionGovernance`` commits to the prior (QUARANTINE) artifact, the lifecycle subject, the
  revalidation EF-7, the seal, the re-admission coordinate and the EF-8 rule set. Missing or non-matching is
  NEEDS_GOVERNANCE_APPROVAL; nothing is defaulted. Kill and quarantine need no approval: they grant nothing.
* History, never current authority. EF-8 is stateless and no accepted lifecycle registry or head authority exists in
  this slice: a receipt cannot see its successors, so an old ACTIVE receipt stays authentic after a later disable and
  another INITIAL_ACTIVATION over the same EF-7 can always be built, after a kill too. A receipt therefore proves only
  that its exact transition, from its exact authenticated prior or EF-7, met every committed rule at its coordinate:
  ``resulting_lifecycle_state`` is that historical result (``resulting_lifecycle_state_status`` states it in every
  receipt), ``advances`` means a valid predecessor for the next receipt of this exact chain, and ``lifecycle_sequence``
  orders one chain without ever selecting a head. No receipt (a genesis, a second genesis, a stale ACTIVE receipt, one
  of several forked children or a governed re-admission) claims current paper admission or the current lifecycle head:
  ``candidate_admitted_to_paper``, ``current_lifecycle_head_proven`` and ``auto_reactivation_enabled`` are structural
  False. The nested EF-7 is the historical admission evidence and EF-8 never re-grants it; current-head authority is
  UNPROVEN here and fails closed.
* ``status`` is integrity only and ``gate_verdict`` the outcome (FAIL > NEEDS_EXTERNAL_FACTS >
  NEEDS_GOVERNANCE_APPROVAL > PASS); REJECTED implies NOT_EVALUATED; only READY + PASS advances and only an advancing
  receipt carries ``resulting_lifecycle_state``; ``lifecycle_subject_digest`` names the lifecycle. One assembly path
  serves the four builders and verifier reassembly; ``verify_edge_kill_quarantine_decision`` is total. Paper-only,
  deterministic, no IO/clock/network/float/decimal.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
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
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    edge_kill_criteria_digest,
    edge_kill_criteria_from_payload,
    edge_kill_criterion_to_dict,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS,
    EdgePaperAdmissionDecision,
    edge_paper_admission_decision_from_payload,
    edge_paper_admission_decision_payload_is_well_formed,
    edge_paper_admission_decision_to_dict,
    verify_edge_paper_admission_decision,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import edge_walk_forward_oos_evidence_from_payload

_SCHEMA_VERSION = "edge-kill-quarantine-decision.v1"
_GATE_ID = "EF-8"
_REASON_PREFIX = "edge_kill_quarantine_decision"
_SELF_DIGEST_FIELD = "kill_quarantine_decision_digest"
_INT64_MAX = 9223372036854775807
_MAX_TEXT_LENGTH = 256
_MAX_TOKEN_LENGTH = 128
_DIGITS = frozenset("0123456789")
# The EF-7 seal EF-8 enforces, and the stage EF-8 records for it (design: draft → strengthened → sealed → immutable).
_ADMISSION_SEALED_STAGE = "SEALED"
_IMMUTABLE_STAGE = "IMMUTABLE"
_KILL_CRITERIA_COMBINATION_POLICY = "any_single_criterion_triggers_kill.v1"

EDGE_KILL_OBSERVATION_STATUS = "CALLER_DECLARED_NEGATIVE_DIRECTION_ONLY_NOT_PERFORMANCE_OR_VENUE_EVIDENCE"
EDGE_RESULTING_LIFECYCLE_STATE_STATUS = "HISTORICAL_TRANSITION_RESULT_NOT_CURRENT_LIFECYCLE_HEAD_OR_PAPER_AUTHORITY"
# The claims only an accepted lifecycle-head authority could support. A stateless EF-8 receipt carries each as a
# structural False; as in every other EF artifact, EF-7 alone grants paper admission.
_CURRENT_AUTHORITY_NON_CLAIMS = (
    "candidate_admitted_to_paper",
    "current_lifecycle_head_proven",
    "auto_reactivation_enabled",
)


class EdgeLifecycleState(str, Enum):
    """The HISTORICAL result of one advancing EF-8 receipt's exact transition.

    Never the current lifecycle state or head, and never a readiness, allocation or live state.
    """

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    QUARANTINE = "QUARANTINE"


class EdgeLifecycleTransition(str, Enum):
    """The only four EF-8 transitions; each has exactly one allowed source state."""

    INITIAL_ACTIVATION = "INITIAL_ACTIVATION"
    KILL_DISABLE = "KILL_DISABLE"
    QUARANTINE_ENTRY = "QUARANTINE_ENTRY"
    GOVERNED_READMISSION = "GOVERNED_READMISSION"


_ACTIVE = EdgeLifecycleState.ACTIVE
_TRANSITION_MATRIX: dict[EdgeLifecycleTransition, tuple[EdgeLifecycleState | None, EdgeLifecycleState]] = {
    EdgeLifecycleTransition.INITIAL_ACTIVATION: (None, EdgeLifecycleState.ACTIVE),
    EdgeLifecycleTransition.KILL_DISABLE: (EdgeLifecycleState.ACTIVE, EdgeLifecycleState.DISABLED),
    EdgeLifecycleTransition.QUARANTINE_ENTRY: (EdgeLifecycleState.DISABLED, EdgeLifecycleState.QUARANTINE),
    EdgeLifecycleTransition.GOVERNED_READMISSION: (EdgeLifecycleState.QUARANTINE, EdgeLifecycleState.ACTIVE),
}
# (prior lifecycle artifact, EF-7 decision, kill observation, governance allowed) per transition.
_TRANSITION_INPUTS: dict[EdgeLifecycleTransition, tuple[bool, bool, bool, bool]] = {
    EdgeLifecycleTransition.INITIAL_ACTIVATION: (False, True, False, False),
    EdgeLifecycleTransition.KILL_DISABLE: (True, False, True, False),
    EdgeLifecycleTransition.QUARANTINE_ENTRY: (True, False, False, False),
    EdgeLifecycleTransition.GOVERNED_READMISSION: (True, True, False, True),
}
_TRANSITION_REASON_CODES: dict[EdgeLifecycleTransition, str] = {
    EdgeLifecycleTransition.INITIAL_ACTIVATION: "initial_activation:authenticated_ef7_admission_with_sealed_kill_criteria",
    EdgeLifecycleTransition.KILL_DISABLE: "kill_disable:sealed_kill_criterion_observation",
    EdgeLifecycleTransition.QUARANTINE_ENTRY: "quarantine_entry:disabled_more_than_30_utc_days",
    EdgeLifecycleTransition.GOVERNED_READMISSION: (
        "governed_readmission:quarantine_at_least_14_utc_days_with_fresh_ef5_onward_revalidation"
    ),
}

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "edge_kill_quarantine_rules.v1",
    "transition_matrix": [
        f"{transition.value}:{'NONE' if source is None else source.value}->{target.value}"
        for transition, (source, target) in _TRANSITION_MATRIX.items()
    ],
    "admission_rule_id": "ef7_public_reproof_exact_anchor_root_correlation_ready_pass_advancing_admitted_sealed.v1",
    "prior_lifecycle_rule_id": "ef8_public_reproof_exact_anchor_root_correlation_only_advancing_prior_is_a_state.v1",
    "sealed_kill_criteria_rule_id": "ef7_seal_recomputed_criteria_and_record_digests_immutable_no_caller_criteria.v1",
    "kill_criteria_combination_policy": _KILL_CRITERIA_COMBINATION_POLICY,
    "kill_evaluation_rule_id": "one_observation_of_one_sealed_criterion_exact_id_metric_basis_integer_comparison.v1",
    "kill_comparator_semantics_id": "above_gt_at_or_above_ge_below_lt_at_or_below_le.v1",
    "kill_observation_trust_rule_id": "caller_declared_digest_bound_observation_disables_only_never_performance_proof.v1",
    "observed_value_scale": 18,
    "observed_value_max_text_length": 60,
    "time_rule_id": "explicit_caller_utc_epoch_ns_int64_coordinates_strictly_increasing_no_clock.v1",
    "utc_day_ns": 86_400_000_000_000,
    "quarantine_rule_id": "disabled_to_quarantine_elapsed_strictly_greater_than_the_day_count.v1",
    "quarantine_min_elapsed_days_exclusive": 30,
    "readmission_rule_id": "quarantine_to_active_elapsed_at_least_the_day_count.v1",
    "readmission_min_elapsed_days_inclusive": 14,
    "activation_horizon_rule_id": "every_activation_at_or_after_its_admission_oos_evaluation_horizon.v1",
    "revalidation_rule_id": "new_passing_ef7_same_subject_and_seal_unconsumed_ef7_ef6_horizon_after_disable.v1",
    "governance_rule_id": "readmission_approval_commits_prior_subject_revalidation_seal_coordinate_rule_set.v1",
    "no_auto_reactivation_rule_id": "bound_chain_active_only_by_genesis_or_governed_fresh_readmission.v1",
    "lifecycle_identity_rule_id": "subject_digest_over_ef2_to_ef4_identity_market_universe_sleeve_correlation.v1",
    "receipt_authority_rule_id": "stateless_historical_transition_receipt_never_current_paper_admission_or_head.v1",
    "resulting_lifecycle_state_status": EDGE_RESULTING_LIFECYCLE_STATE_STATUS,
    "advances_rule_id": "advances_is_valid_predecessor_for_the_next_receipt_of_this_exact_chain_never_current_head.v1",
    "lifecycle_head_rule_id": "no_head_authority_here_head_never_inferred_from_sequence_state_or_verdict.v1",
    "current_authority_non_claims": list(_CURRENT_AUTHORITY_NON_CLAIMS),
    "gate_rule_id": "pass_iff_authentic_chain_allowed_transition_and_every_transition_rule_holds.v1",
    "numeric_rule_id": "signed_canonical_scale18_text_bounded_exact_integer_units_no_float_no_decimal_context.v1",
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_OBSERVED_VALUE_SCALE: int = _RULE_SET_V1["observed_value_scale"]  # type: ignore[assignment]
_OBSERVED_VALUE_MAX_TEXT_LENGTH: int = _RULE_SET_V1["observed_value_max_text_length"]  # type: ignore[assignment]
_UTC_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_QUARANTINE_MIN_ELAPSED_NS_EXCLUSIVE = _RULE_SET_V1["quarantine_min_elapsed_days_exclusive"] * _UTC_DAY_NS  # type: ignore[operator]
_READMISSION_MIN_ELAPSED_NS_INCLUSIVE = _RULE_SET_V1["readmission_min_elapsed_days_inclusive"] * _UTC_DAY_NS  # type: ignore[operator]
EDGE_KILL_QUARANTINE_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))


def edge_kill_quarantine_rule_set() -> dict[str, object]:
    """A fresh copy of the code-defined EF-8 V1 rule set committed by ``EDGE_KILL_QUARANTINE_RULE_SET_DIGEST``."""

    return {key: list(value) if isinstance(value, list) else value for key, value in _RULE_SET_V1.items()}


# EF-8 computes these four historical facts from authenticated proof; every other non-claim is a structural default,
# reusing the EF-7 vocabulary plus the current-authority and kill-observation non-claims.
_COMPUTED_FLAGS = frozenset(
    {
        "kill_criteria_sealed",
        "preregistration_sealed",
        "performance_data_consumed",
        "oos_evidence_consumed",
    }
)
EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS,
    *((name, False) for name in _CURRENT_AUTHORITY_NON_CLAIMS),
    ("kill_observation_verified", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS)
# The stable identity a lifecycle keeps across every cycle; EF-2 → EF-4 facts plus the traded market and paper sleeve.
_SUBJECT_FIELDS = (
    "candidate_strategy_id",
    "edge_family",
    "strategy_id",
    "strategy_version",
    "strategy_spec_digest",
    "strategy_spec_admission_digest",
    "source_manifest_digest",
    "market_type",
    "pinned_instrument_universe",
    "paper_sleeve_id",
)
_MIRRORED_FLAGS = ("preregistration_sealed", "performance_data_consumed", "oos_evidence_consumed")


class EdgeKillQuarantineDecisionError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


@dataclass(frozen=True)
class EdgeKillObservation:
    """One caller-declared observation of ONE sealed kill criterion's governed metric.

    ``observed_value`` is a signed canonical scale-18 text. The record is digest-bound provenance (a bounded reference and
    the digest of the source record it was read from), usable ONLY to disable: it is never verified performance, never
    a current venue fact and never an activation or re-admission input.
    """

    criterion_id: str
    metric_id: str
    evaluation_basis: str
    observed_value: str
    observation_reference: str
    observation_source_digest: str


@dataclass(frozen=True)
class EdgeKillEvaluation:
    """The exact evaluation of one observation against the matching sealed criterion (derived, never caller input)."""

    criterion_id: str
    metric_id: str
    evaluation_basis: str
    comparator: EdgeKillCriterionComparator
    threshold: str
    observed_value: str
    observation_digest: str
    triggered: bool


@dataclass(frozen=True)
class EdgeReadmissionGovernance:
    """Human governance approval of one exact re-admission; every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approved_prior_lifecycle_digest: str
    approved_lifecycle_subject_digest: str
    approved_revalidation_decision_digest: str
    approved_sealed_kill_criteria_digest: str
    approved_effective_at_ns: int
    approved_rule_set_digest: str


@dataclass(frozen=True)
class EdgeKillQuarantineDecision:
    """Immutable, digest-bound HISTORICAL receipt of one EF-8 lifecycle transition. PAPER ONLY.

    It records lifecycle process history: never the current lifecycle head, current paper admission or an edge.
    """

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    decision_id: str
    correlation_id: str
    root_intake_digest: str
    transition: EdgeLifecycleTransition
    prior_binding: EdgeAuthorityBinding | None
    prior_digest: str
    prior_lifecycle_state: EdgeLifecycleState | None
    prior_effective_at_ns: int | None
    resulting_lifecycle_state: EdgeLifecycleState | None
    resulting_lifecycle_state_status: str
    effective_at_ns: int
    transition_reason_code: str
    transition_reason_reference: str
    lifecycle_subject_digest: str
    candidate_strategy_id: str
    edge_family: str
    strategy_id: str
    strategy_version: str
    strategy_spec_digest: str
    strategy_spec_admission_digest: str
    source_manifest_digest: str
    market_type: str
    pinned_instrument_universe: tuple[str, ...]
    paper_sleeve_id: str
    lifecycle_sequence: int
    lifecycle_cycle: int
    admission_binding: EdgeAuthorityBinding | None
    admission_decision_digest: str
    admission_walk_forward_evidence_digest: str
    admission_evaluation_horizon_end_ns: int | None
    cycle_admission_decision_digest: str
    cycle_activated_at_ns: int | None
    cycle_disabled_at_ns: int | None
    consumed_admission_decision_digests: tuple[str, ...]
    consumed_walk_forward_evidence_digests: tuple[str, ...]
    sealed_kill_criteria: tuple[EdgeKillCriterion, ...]
    final_kill_criteria_digest: str
    sealed_kill_criteria_digest: str
    kill_criteria_combination_policy: str
    kill_criteria_lifecycle_stage: str
    kill_observation: EdgeKillObservation | None
    kill_observation_digest: str
    kill_observation_status: str
    kill_evaluation: EdgeKillEvaluation | None
    governance: EdgeReadmissionGovernance | None
    governance_digest: str
    rule_set_id: str
    rule_set_digest: str
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    kill_criteria_sealed: bool
    preregistration_sealed: bool
    performance_data_consumed: bool
    oos_evidence_consumed: bool
    kill_quarantine_decision_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
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
    paper_performance_proven: bool = False
    prdv4_stage4_complete: bool = False
    portfolio_allocation_approved: bool = False
    capital_allocated: bool = False
    execution_authorized: bool = False
    capacity_empirically_proven: bool = False
    candidate_admitted_to_paper: bool = False
    auto_reactivation_enabled: bool = False
    kill_observation_verified: bool = False
    current_lifecycle_head_proven: bool = False


@dataclass(frozen=True)
class _Admission:
    """An authenticated EF-7 decision and the EF-6 facts EF-8 relies on."""

    decision: EdgePaperAdmissionDecision
    walk_forward_evidence_digest: str
    evaluation_horizon_end_ns: int | None


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeKillQuarantineDecisionError:
    return EdgeKillQuarantineDecisionError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT_LENGTH
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_token(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_TOKEN_LENGTH
        or not (value[0].isascii() and value[0].isalnum())
        or any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_coordinate(value: object, field_name: str) -> int:
    """An explicit UTC epoch nanosecond coordinate: an exact int (never bool) inside the int64 range."""

    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        raise _fail(f"{field_name}_invalid")
    return value


def _scale18_units(value: object) -> int | None:
    """Exact signed scale units of a canonical fixed-scale text under the committed rule set; else ``None``.

    The grammar is ``[-]digits.digits`` with exactly the committed scale, no redundant leading zero, no negative zero,
    ASCII digits only and at most the committed text length, so float, bool, NaN, Infinity, exponent, whitespace,
    underscore, plus-sign and non-ASCII digit forms are all refused. No float or decimal context.
    """

    if type(value) is not str or not value or len(value) > _OBSERVED_VALUE_MAX_TEXT_LENGTH:
        return None
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if dot != "." or len(fraction) != _OBSERVED_VALUE_SCALE or not integer:
        return None
    if not set(integer) <= _DIGITS or not set(fraction) <= _DIGITS:
        return None
    if integer != "0" and integer.startswith("0"):
        return None
    units = int(integer + fraction)
    if negative and units == 0:
        return None
    return -units if negative else units


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if type(value) is EdgeKillCriterion:
        if type(value.comparator) is not EdgeKillCriterionComparator:
            raise _fail("payload_enum_field_not_exact_member")
        return edge_kill_criterion_to_dict(value)
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize a record; an enum-typed field must hold the exact enum member, never an equal plain string."""

    for name, enum_cls, optional in _ENUM_FIELDS.get(type(artifact), ()):
        value = getattr(artifact, name)
        if value is None and optional:
            continue
        if type(value) is not enum_cls:
            raise _fail("payload_enum_field_not_exact_member")
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


_RECORD_TYPES = frozenset({EdgeKillObservation, EdgeKillEvaluation, EdgeReadmissionGovernance})
_ENUM_FIELDS: dict[type, tuple[tuple[str, type[Enum], bool], ...]] = {
    EdgeKillQuarantineDecision: (
        ("status", EdgeEvidenceStatus, False),
        ("gate_verdict", EdgeGateVerdict, False),
        ("transition", EdgeLifecycleTransition, False),
        ("prior_lifecycle_state", EdgeLifecycleState, True),
        ("resulting_lifecycle_state", EdgeLifecycleState, True),
    ),
    EdgeKillEvaluation: (("comparator", EdgeKillCriterionComparator, False),),
}


# --- caller declarations -----------------------------------------------------------------------------------------------


def _require_transition_inputs(
    transition: object, prior: object, admission: object, observation: object, governance: object
) -> EdgeLifecycleTransition:
    """Each transition takes exactly its own inputs: no ACTIVE without an EF-7, no observation outside a disable."""

    if type(transition) is not EdgeLifecycleTransition:
        raise _fail("transition_invalid")
    needs_prior, needs_admission, needs_observation, allows_governance = _TRANSITION_INPUTS[transition]
    if (
        (prior is not None) is not needs_prior
        or (admission is not None) is not needs_admission
        or (observation is not None) is not needs_observation
        or (governance is not None and not allows_governance)
    ):
        raise _fail("transition_inputs_malformed")
    return transition


def _canonical_observation(observation: object) -> EdgeKillObservation | None:
    """Structural validation only: whether the observation MATCHES a sealed criterion is decided at assembly."""

    if observation is None:
        return None
    if type(observation) is not EdgeKillObservation:
        raise _fail("kill_observation_malformed")

    def attribute(name: str) -> object:
        return getattr(observation, name, None)

    record = EdgeKillObservation(
        criterion_id=_require_token(attribute("criterion_id"), "kill_observation_criterion_id"),
        metric_id=_require_token(attribute("metric_id"), "kill_observation_metric_id"),
        evaluation_basis=_require_token(attribute("evaluation_basis"), "kill_observation_evaluation_basis"),
        observed_value=attribute("observed_value"),  # type: ignore[arg-type]
        observation_reference=_require_text(attribute("observation_reference"), "kill_observation_reference"),
        observation_source_digest=_require_hex64(
            attribute("observation_source_digest"), "kill_observation_source_digest"
        ),
    )
    if _scale18_units(record.observed_value) is None:
        raise _fail("kill_observation_observed_value_invalid")
    return record


def _canonical_governance(governance: object) -> EdgeReadmissionGovernance | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if governance is None:
        return None
    if type(governance) is not EdgeReadmissionGovernance:
        raise _fail("governance_malformed")

    def attribute(name: str) -> object:
        return getattr(governance, name, None)

    return EdgeReadmissionGovernance(
        approval_reference=_require_text(attribute("approval_reference"), "governance_approval_reference"),
        approval_digest=_require_hex64(attribute("approval_digest"), "governance_approval_digest"),
        approved_prior_lifecycle_digest=_require_hex64(
            attribute("approved_prior_lifecycle_digest"), "governance_approved_prior_lifecycle_digest"
        ),
        approved_lifecycle_subject_digest=_require_hex64(
            attribute("approved_lifecycle_subject_digest"), "governance_approved_lifecycle_subject_digest"
        ),
        approved_revalidation_decision_digest=_require_hex64(
            attribute("approved_revalidation_decision_digest"), "governance_approved_revalidation_decision_digest"
        ),
        approved_sealed_kill_criteria_digest=_require_hex64(
            attribute("approved_sealed_kill_criteria_digest"), "governance_approved_sealed_kill_criteria_digest"
        ),
        approved_effective_at_ns=_require_coordinate(
            attribute("approved_effective_at_ns"), "governance_approved_effective_at_ns"
        ),
        approved_rule_set_digest=_require_hex64(
            attribute("approved_rule_set_digest"), "governance_approved_rule_set_digest"
        ),
    )


def _require_caller_fields(
    root_intake_digest: object, effective_at_ns: object, decision_id: object, correlation_id: object, reason: object
) -> None:
    _require_hex64(root_intake_digest, "root_intake_digest")
    _require_coordinate(effective_at_ns, "effective_at_ns")
    _require_text(decision_id, "decision_id")
    _require_text(correlation_id, "correlation_id")
    _require_text(reason, "reason_reference")


# --- the kill evaluation -----------------------------------------------------------------------------------------------


def edge_kill_criterion_triggered(criterion: EdgeKillCriterion, observed_value: str) -> bool:
    """Exact evaluation of one sealed criterion against one canonical scale-18 observed value.

    ``kill_if_above`` triggers on ``observed > threshold``, ``kill_if_at_or_above`` on ``>=``, ``kill_if_below`` on
    ``<`` and ``kill_if_at_or_below`` on ``<=``, compared as exact integer scale units. A criterion without an evaluable
    threshold, or a non-canonical value, raises ``EdgeKillQuarantineDecisionError``; nothing is defaulted.
    """

    comparator = getattr(criterion, "comparator", None)
    if type(criterion) is not EdgeKillCriterion or type(comparator) is not EdgeKillCriterionComparator:
        raise _fail("kill_criterion_not_evaluable")
    threshold = _scale18_units(getattr(criterion, "threshold", None))
    if threshold is None:
        raise _fail("kill_criterion_not_evaluable")
    observed = _scale18_units(observed_value)
    if observed is None:
        raise _fail("kill_observation_observed_value_invalid")
    if comparator is EdgeKillCriterionComparator.KILL_IF_ABOVE:
        return observed > threshold
    if comparator is EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE:
        return observed >= threshold
    if comparator is EdgeKillCriterionComparator.KILL_IF_BELOW:
        return observed < threshold
    return observed <= threshold


def _kill_evaluation(
    observation: EdgeKillObservation, criteria: Sequence[EdgeKillCriterion], observation_digest: str
) -> tuple[EdgeKillEvaluation | None, list[str]]:
    """``(evaluation, fail_reasons)``: only a sealed criterion with the same id, metric and basis is ever evaluated."""

    matches = [item for item in criteria if item.criterion_id == observation.criterion_id]
    if not matches:
        return None, [_reason(f"kill_observation_criterion_not_sealed:{observation.criterion_id}")]
    criterion = matches[0]
    codes: list[str] = []
    if criterion.metric_id != observation.metric_id:
        codes.append(_reason(f"kill_observation_metric_mismatch:{criterion.criterion_id}"))
    if criterion.evaluation_basis != observation.evaluation_basis:
        codes.append(_reason(f"kill_observation_evaluation_basis_mismatch:{criterion.criterion_id}"))
    if _scale18_units(criterion.threshold) is None:
        codes.append(_reason(f"sealed_kill_criterion_not_evaluable:{criterion.criterion_id}"))
    if codes:
        return None, codes
    triggered = edge_kill_criterion_triggered(criterion, observation.observed_value)
    evaluation = EdgeKillEvaluation(
        criterion_id=criterion.criterion_id,
        metric_id=criterion.metric_id,
        evaluation_basis=criterion.evaluation_basis,
        comparator=criterion.comparator,
        threshold=criterion.threshold,  # type: ignore[arg-type]
        observed_value=observation.observed_value,
        observation_digest=observation_digest,
        triggered=triggered,
    )
    if triggered:
        return evaluation, []
    return evaluation, [_reason(f"kill_criterion_not_triggered:{criterion.criterion_id}")]


# --- EF-7 admission authority ------------------------------------------------------------------------------------------


def _kill_criteria_record_payload(decision: EdgePaperAdmissionDecision) -> dict[str, object]:
    """The EF-7 kill-criteria record, recomputed from the decision's public lineage fields (never read as a digest)."""

    return {
        "root_intake_digest": decision.root_intake_digest,
        "strategy_spec_admission_digest": decision.strategy_spec_admission_digest,
        "strategy_spec_digest": decision.strategy_spec_digest,
        "root_kill_criteria_digest": decision.root_kill_criteria_digest,
        "kill_criteria": [edge_kill_criterion_to_dict(item) for item in decision.final_kill_criteria],
        "kill_criteria_digest": decision.final_kill_criteria_digest,
        "added_kill_criterion_ids": list(decision.added_kill_criterion_ids),
        "combination_policy": decision.kill_criteria_combination_policy,
        "kill_criteria_policy_digest": decision.kill_criteria_policy_digest,
    }


def _seal_codes(decision: EdgePaperAdmissionDecision, label: str) -> list[str]:
    """The EF-7 seal EF-8 enforces must recompute exactly; the carried sealed digest is never trusted alone."""

    try:
        final_digest = edge_kill_criteria_digest(decision.final_kill_criteria)
    except EdgeArtifactError:
        return [_reason(f"{label}_sealed_kill_criteria_inconsistent:final_kill_criteria")]
    record_digest = _digest_of(_kill_criteria_record_payload(decision))
    codes: list[str] = []
    if final_digest != decision.final_kill_criteria_digest:
        codes.append(_reason(f"{label}_sealed_kill_criteria_inconsistent:final_kill_criteria_digest"))
    if record_digest != decision.kill_criteria_record_digest:
        codes.append(_reason(f"{label}_sealed_kill_criteria_inconsistent:kill_criteria_record_digest"))
    if decision.kill_criteria_combination_policy != _KILL_CRITERIA_COMBINATION_POLICY:
        codes.append(_reason(f"{label}_sealed_kill_criteria_inconsistent:combination_policy"))
    if decision.advances is True and (
        decision.kill_criteria_sealed is not True
        or decision.candidate_admitted_to_paper is not True
        or decision.kill_criteria_lifecycle_stage != _ADMISSION_SEALED_STAGE
        or decision.sealed_kill_criteria_digest != record_digest
    ):
        codes.append(_reason(f"{label}_sealed_kill_criteria_inconsistent:seal"))
    return codes


def _admission_authority(
    binding: EdgeAuthorityBinding, *, label: str, root_intake_digest: str, correlation_id: str
) -> tuple[list[str], _Admission | None]:
    """Re-prove an EF-7 decision through its public verifier and read its authenticated EF-6 evaluation horizon."""

    decision = edge_paper_admission_decision_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_paper_admission_decision(decision)
    if not verification.intact:
        return [_reason(f"{label}_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason(f"{label}_digest_mismatch")], None
    if decision.correlation_id != correlation_id:
        return [_reason(f"{label}_correlation_mismatch")], None
    if decision.root_intake_digest != root_intake_digest:
        return [_reason("chain_splice_root_intake_mismatch")], None
    if decision.status is not EdgeEvidenceStatus.READY:
        return [_reason(f"{label}_rejected")], None
    # EF-7's READY verification re-proved its EF-6 predecessor against this anchor, so the snapshot is authenticated.
    evidence = edge_walk_forward_oos_evidence_from_payload(
        edge_authority_binding_snapshot(decision.predecessor_binding)
    )
    horizon = max((frame.out_of_sample_end_ns for frame in evidence.window_frames), default=None)
    codes = _seal_codes(decision, label)
    if evidence.walk_forward_oos_evidence_digest != decision.predecessor_digest:
        codes.append(_reason(f"{label}_walk_forward_evidence_mismatch"))
    if decision.advances is True and horizon is None:
        codes.append(_reason(f"{label}_evaluation_horizon_missing"))
    if codes:
        return codes, None
    return [], _Admission(
        decision=decision, walk_forward_evidence_digest=decision.predecessor_digest, evaluation_horizon_end_ns=horizon
    )


def _admission_binding(decision: object, expected_digest: object, label: str) -> EdgeAuthorityBinding:
    if type(decision) is not EdgePaperAdmissionDecision:
        raise _fail(f"{label}_malformed")
    try:
        payload = edge_paper_admission_decision_to_dict(decision)
    except Exception as exc:  # noqa: BLE001 - a hollow decision object is a construction error, never a receipt
        raise _fail(f"{label}_not_serializable") from exc
    return build_edge_authority_binding(
        snapshot_payload=payload,
        expected_digest=expected_digest,
        shape=edge_paper_admission_decision_payload_is_well_formed,
        error=EdgeKillQuarantineDecisionError,
        code=_reason(label),
    )


# --- the prior lifecycle artifact --------------------------------------------------------------------------------------


def _prior_authority(
    binding: EdgeAuthorityBinding, *, root_intake_digest: str, correlation_id: str
) -> tuple[list[str], EdgeKillQuarantineDecision | None]:
    """Re-prove the exact prior EF-8 artifact through the public verifier (recursively down to its EF-7 genesis)."""

    prior = edge_kill_quarantine_decision_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_kill_quarantine_decision(prior)
    if not verification.intact:
        return [_reason(f"prior_lifecycle_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("prior_lifecycle_digest_mismatch")], None
    if prior.correlation_id != correlation_id:
        return [_reason("prior_lifecycle_correlation_mismatch")], None
    if prior.root_intake_digest != root_intake_digest:
        return [_reason("chain_splice_root_intake_mismatch")], None
    if prior.status is not EdgeEvidenceStatus.READY:
        return [_reason("prior_lifecycle_rejected")], None
    return [], prior


def _prior_binding(prior: object, expected_digest: object) -> EdgeAuthorityBinding:
    if type(prior) is not EdgeKillQuarantineDecision:
        raise _fail("prior_lifecycle_malformed")
    try:
        payload = _to_payload(prior)
    except Exception as exc:  # noqa: BLE001 - a hollow prior object is a construction error, never a receipt
        raise _fail("prior_lifecycle_not_serializable") from exc
    return build_edge_authority_binding(
        snapshot_payload=payload,
        expected_digest=expected_digest,
        shape=edge_kill_quarantine_decision_payload_is_well_formed,
        error=EdgeKillQuarantineDecisionError,
        code=_reason("prior_lifecycle"),
    )


def _subject_payload(root_intake_digest: str, correlation_id: str, source: object) -> dict[str, object]:
    """The lifecycle subject: identical for the EF-7 that opened the lifecycle and every EF-7 that re-admits it."""

    payload: dict[str, object] = {"root_intake_digest": root_intake_digest, "correlation_id": correlation_id}
    for name in _SUBJECT_FIELDS:
        value = getattr(source, name)
        payload[name] = list(value) if name == "pinned_instrument_universe" else value
    return payload


def _revalidation_identity_codes(prior: EdgeKillQuarantineDecision, decision: EdgePaperAdmissionDecision) -> list[str]:
    """A re-admission EF-7 must revalidate THIS lifecycle: same subject and the same immutable seal."""

    codes = [
        _reason(f"revalidation_identity_mismatch:{name}")
        for name in _SUBJECT_FIELDS
        if getattr(decision, name) != getattr(prior, name)
    ]
    if prior.sealed_kill_criteria_digest and (
        decision.kill_criteria_record_digest != prior.sealed_kill_criteria_digest
        or decision.final_kill_criteria != prior.sealed_kill_criteria
    ):
        codes.append(_reason("revalidation_sealed_kill_criteria_mismatch"))
    return codes


# --- verdict rules -----------------------------------------------------------------------------------------------------


def _propagate(label: str, verdict: EdgeGateVerdict, buckets: tuple[list[str], list[str], list[str]]) -> None:
    fail, needs_external, needs_governance = buckets
    code = _reason(f"{label}_not_advanced:{verdict.value}")
    if verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        needs_external.append(code)
    elif verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        needs_governance.append(code)
    else:
        fail.append(code)


def _horizon_codes(admission: _Admission, effective_at_ns: int) -> list[str]:
    """No activation (initial or re-admission) may precede the OOS evaluation horizon its admission rests on."""

    horizon = admission.evaluation_horizon_end_ns
    if horizon is not None and effective_at_ns < horizon:
        return [_reason("activation_before_admission_evaluation_horizon")]
    return []


def _freshness_codes(prior: EdgeKillQuarantineDecision, admission: _Admission, admission_digest: str) -> list[str]:
    """A revalidation must be new evidence: an unconsumed EF-7 and EF-6 whose OOS horizon lies after the disable."""

    codes: list[str] = []
    if admission_digest in prior.consumed_admission_decision_digests:
        codes.append(_reason("revalidation_admission_reused"))
    if admission.walk_forward_evidence_digest in prior.consumed_walk_forward_evidence_digests:
        codes.append(_reason("revalidation_walk_forward_evidence_reused"))
    horizon, disabled_at = admission.evaluation_horizon_end_ns, prior.cycle_disabled_at_ns
    if horizon is not None and disabled_at is not None and horizon <= disabled_at:
        codes.append(_reason("revalidation_horizon_not_after_disable"))
    return codes


def _governance_reasons(governance: EdgeReadmissionGovernance | None, committed: Mapping[str, object]) -> list[str]:
    if governance is None:
        return [_reason("readmission_governance_missing")]
    return [
        _reason(f"readmission_governance_{name}_mismatch")
        for name, value in committed.items()
        if getattr(governance, f"approved_{name}") != value
    ]


# --- EF-8 decision -----------------------------------------------------------------------------------------------------


def _assemble_decision(
    *,
    transition: object,
    prior_binding: object,
    admission_binding: object,
    root_intake_digest: object,
    effective_at_ns: object,
    decision_id: object,
    correlation_id: object,
    reason_reference: object,
    kill_observation: object,
    governance: object,
) -> EdgeKillQuarantineDecision:
    """The one EF-8 assembly path, shared by the four builders and verifier reassembly."""

    kind = _require_transition_inputs(transition, prior_binding, admission_binding, kill_observation, governance)
    source_state, target_state = _TRANSITION_MATRIX[kind]
    genesis = kind is EdgeLifecycleTransition.INITIAL_ACTIVATION
    root_anchor = _require_hex64(root_intake_digest, "root_intake_digest")
    effective = _require_coordinate(effective_at_ns, "effective_at_ns")
    decision_id = _require_text(decision_id, "decision_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    reason_reference = _require_text(reason_reference, "reason_reference")
    observation = _canonical_observation(kill_observation)
    governance_record = _canonical_governance(governance)
    prior_link = require_edge_authority_binding(
        prior_binding,
        shape=edge_kill_quarantine_decision_payload_is_well_formed,
        error=EdgeKillQuarantineDecisionError,
        code=_reason("prior_lifecycle"),
        optional=True,
    )
    label = "admission" if genesis else "revalidation"
    admission_link = require_edge_authority_binding(
        admission_binding,
        shape=edge_paper_admission_decision_payload_is_well_formed,
        error=EdgeKillQuarantineDecisionError,
        code=_reason(label),
        optional=True,
    )

    prior_codes, prior = (
        ([], None)
        if prior_link is None
        else _prior_authority(prior_link, root_intake_digest=root_anchor, correlation_id=correlation_id)
    )
    admission_codes, admission = (
        ([], None)
        if admission_link is None
        else _admission_authority(
            admission_link, label=label, root_intake_digest=root_anchor, correlation_id=correlation_id
        )
    )
    identity_codes = (
        [] if prior is None or admission is None else _revalidation_identity_codes(prior, admission.decision)
    )
    integrity = _sorted_unique([*prior_codes, *admission_codes, *identity_codes])
    rejected = (
        bool(integrity)
        or (prior_link is not None and prior is None)
        or (admission_link is not None and admission is None)
    )
    admission_digest = "" if admission_link is None else admission_link.expected_digest
    observation_digest = "" if observation is None else _digest_of(_to_payload(observation))
    evaluation: EdgeKillEvaluation | None = None

    if rejected:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
        source: object = None
    else:
        buckets: tuple[list[str], list[str], list[str]] = ([], [], [])
        fail, needs_external, needs_governance = buckets
        if genesis:
            decision = admission.decision  # type: ignore[union-attr]
            source = decision
            if decision.advances is not True:
                _propagate(label, decision.gate_verdict, buckets)
            else:
                fail.extend(_horizon_codes(admission, effective))  # type: ignore[arg-type]
                fail.extend(
                    _reason(f"sealed_kill_criterion_not_evaluable:{item.criterion_id}")
                    for item in decision.final_kill_criteria
                    if _scale18_units(item.threshold) is None
                )
        else:
            source = prior
            if prior.advances is not True:  # type: ignore[union-attr]
                _propagate("prior_lifecycle", prior.gate_verdict, buckets)  # type: ignore[union-attr]
            prior_state = prior.resulting_lifecycle_state  # type: ignore[union-attr]
            if prior_state is not None and prior_state is not source_state:
                fail.append(_reason(f"transition_not_allowed:{prior_state.value}->{target_state.value}"))
            in_source_state = prior_state is source_state
            elapsed = effective - prior.effective_at_ns  # type: ignore[union-attr]
            if elapsed <= 0:
                fail.append(_reason("transition_time_not_after_prior"))
            if kind is EdgeLifecycleTransition.KILL_DISABLE:
                evaluation, kill_codes = _kill_evaluation(
                    observation,  # type: ignore[arg-type]
                    prior.sealed_kill_criteria,  # type: ignore[union-attr]
                    observation_digest,
                )
                fail.extend(kill_codes)
            elif kind is EdgeLifecycleTransition.QUARANTINE_ENTRY:
                if in_source_state and elapsed <= _QUARANTINE_MIN_ELAPSED_NS_EXCLUSIVE:
                    fail.append(_reason("quarantine_elapsed_not_more_than_30_utc_days"))
            else:
                if in_source_state and elapsed < _READMISSION_MIN_ELAPSED_NS_INCLUSIVE:
                    fail.append(_reason("readmission_elapsed_less_than_14_utc_days"))
                decision = admission.decision  # type: ignore[union-attr]
                if decision.advances is not True:
                    _propagate(label, decision.gate_verdict, buckets)
                fail.extend(_freshness_codes(prior, admission, admission_digest))  # type: ignore[arg-type]
                fail.extend(_horizon_codes(admission, effective))  # type: ignore[arg-type]
                committed: dict[str, object] = {
                    "prior_lifecycle_digest": prior_link.expected_digest,  # type: ignore[union-attr]
                    "lifecycle_subject_digest": _digest_of(_subject_payload(root_anchor, correlation_id, prior)),
                    "revalidation_decision_digest": admission_digest,
                    "sealed_kill_criteria_digest": prior.sealed_kill_criteria_digest,  # type: ignore[union-attr]
                    "effective_at_ns": effective,
                    "rule_set_digest": EDGE_KILL_QUARANTINE_RULE_SET_DIGEST,
                }
                needs_governance.extend(_governance_reasons(governance_record, committed))
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    ready = status is EdgeEvidenceStatus.READY
    advances = ready and verdict is EdgeGateVerdict.PASS
    # A historical ACTIVE result opens a new cycle of this chain; it is bookkeeping only and sets no authority flag.
    activates = advances and target_state is _ACTIVE
    if source is None:
        subject = dict.fromkeys(_SUBJECT_FIELDS, "")
        subject["pinned_instrument_universe"] = ()
        subject_digest = ""
    else:
        subject = {name: getattr(source, name) for name in _SUBJECT_FIELDS}
        subject_digest = _digest_of(_subject_payload(root_anchor, correlation_id, source))

    if genesis and admission is not None and not rejected and admission.decision.advances is True:
        sealed_criteria = admission.decision.final_kill_criteria
        final_digest = admission.decision.final_kill_criteria_digest
        sealed_digest = admission.decision.sealed_kill_criteria_digest
    elif not genesis and prior is not None and not rejected:
        sealed_criteria = prior.sealed_kill_criteria
        final_digest = prior.final_kill_criteria_digest
        sealed_digest = prior.sealed_kill_criteria_digest
    else:
        sealed_criteria, final_digest, sealed_digest = (), "", ""

    if genesis or prior is None or rejected:
        sequence, cycle = 0, 0
        cycle_admission, activated_at, disabled_at = "", None, None
        consumed_admissions: tuple[str, ...] = ()
        consumed_evidence: tuple[str, ...] = ()
    else:
        sequence, cycle = prior.lifecycle_sequence + 1, prior.lifecycle_cycle
        cycle_admission, activated_at = prior.cycle_admission_decision_digest, prior.cycle_activated_at_ns
        disabled_at = prior.cycle_disabled_at_ns
        consumed_admissions = prior.consumed_admission_decision_digests
        consumed_evidence = prior.consumed_walk_forward_evidence_digests
    if activates:
        cycle += 1
        cycle_admission, activated_at, disabled_at = admission_digest, effective, None
        consumed_admissions = (*consumed_admissions, admission_digest)
        consumed_evidence = (*consumed_evidence, admission.walk_forward_evidence_digest)  # type: ignore[union-attr]
    elif advances and kind is EdgeLifecycleTransition.KILL_DISABLE:
        disabled_at = effective

    authorities: list[object] = [] if rejected else [item for item in (prior,) if item is not None]
    if not rejected and admission is not None:
        authorities.append(admission.decision)
    mirrored = {name: ready and all(getattr(item, name) is True for item in authorities) for name in _MIRRORED_FLAGS}
    reason_code = _TRANSITION_REASON_CODES[kind]
    if observation is not None:
        reason_code = f"{reason_code}:{observation.criterion_id}"

    seed = EdgeKillQuarantineDecision(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=advances,
        decision_id=decision_id,
        correlation_id=correlation_id,
        root_intake_digest=root_anchor,
        transition=kind,
        prior_binding=prior_link,
        prior_digest="" if prior_link is None else prior_link.expected_digest,
        prior_lifecycle_state=None if prior is None or rejected else prior.resulting_lifecycle_state,
        prior_effective_at_ns=None if prior is None or rejected else prior.effective_at_ns,
        resulting_lifecycle_state=target_state if advances else None,
        resulting_lifecycle_state_status=EDGE_RESULTING_LIFECYCLE_STATE_STATUS,
        effective_at_ns=effective,
        transition_reason_code=reason_code,
        transition_reason_reference=reason_reference,
        lifecycle_subject_digest=subject_digest,
        candidate_strategy_id=subject["candidate_strategy_id"],  # type: ignore[arg-type]
        edge_family=subject["edge_family"],  # type: ignore[arg-type]
        strategy_id=subject["strategy_id"],  # type: ignore[arg-type]
        strategy_version=subject["strategy_version"],  # type: ignore[arg-type]
        strategy_spec_digest=subject["strategy_spec_digest"],  # type: ignore[arg-type]
        strategy_spec_admission_digest=subject["strategy_spec_admission_digest"],  # type: ignore[arg-type]
        source_manifest_digest=subject["source_manifest_digest"],  # type: ignore[arg-type]
        market_type=subject["market_type"],  # type: ignore[arg-type]
        pinned_instrument_universe=subject["pinned_instrument_universe"],  # type: ignore[arg-type]
        paper_sleeve_id=subject["paper_sleeve_id"],  # type: ignore[arg-type]
        lifecycle_sequence=sequence,
        lifecycle_cycle=cycle,
        admission_binding=admission_link,
        admission_decision_digest=admission_digest,
        admission_walk_forward_evidence_digest=""
        if admission is None or rejected
        else admission.walk_forward_evidence_digest,
        admission_evaluation_horizon_end_ns=None
        if admission is None or rejected
        else admission.evaluation_horizon_end_ns,
        cycle_admission_decision_digest=cycle_admission,
        cycle_activated_at_ns=activated_at,
        cycle_disabled_at_ns=disabled_at,
        consumed_admission_decision_digests=consumed_admissions,
        consumed_walk_forward_evidence_digests=consumed_evidence,
        sealed_kill_criteria=sealed_criteria,
        final_kill_criteria_digest=final_digest,
        sealed_kill_criteria_digest=sealed_digest,
        kill_criteria_combination_policy=_KILL_CRITERIA_COMBINATION_POLICY if sealed_digest else "",
        kill_criteria_lifecycle_stage=_IMMUTABLE_STAGE if sealed_digest else "",
        kill_observation=observation,
        kill_observation_digest=observation_digest,
        kill_observation_status=EDGE_KILL_OBSERVATION_STATUS,
        kill_evaluation=evaluation,
        governance=governance_record,
        governance_digest="" if governance_record is None else _digest_of(_to_payload(governance_record)),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=EDGE_KILL_QUARANTINE_RULE_SET_DIGEST,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        kill_criteria_sealed=ready and sealed_digest != "",
        preregistration_sealed=mirrored["preregistration_sealed"],
        performance_data_consumed=mirrored["performance_data_consumed"],
        oos_evidence_consumed=mirrored["oos_evidence_consumed"],
        kill_quarantine_decision_digest="",
    )
    return replace(seed, kill_quarantine_decision_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_kill_quarantine_initial_activation(
    admission: EdgePaperAdmissionDecision,
    *,
    expected_admission_digest: str,
    expected_root_intake_digest: str,
    effective_at_ns: int,
    decision_id: str,
    correlation_id: str,
    reason_reference: str,
) -> EdgeKillQuarantineDecision:
    """Record a genesis receipt (INITIAL_ACTIVATION, historical result ACTIVE) over an authentic, passing, sealed EF-7.

    There is deliberately no input for a state, a flag, kill criteria or a prior: the historical ACTIVE result derives
    only from the re-proven EF-7 and the committed rules. The receipt is history, never current paper admission or the
    current head, so a second genesis over the same EF-7 (after a kill, too) grants nothing and is no successor of that
    kill. Malformed caller input raises ``EdgeKillQuarantineDecisionError``; a broken, spliced or rejected admission is
    ``REJECTED``; an authentic non-advancing admission propagates its verdict.
    """

    _require_caller_fields(expected_root_intake_digest, effective_at_ns, decision_id, correlation_id, reason_reference)
    binding = _admission_binding(admission, expected_admission_digest, "admission")
    return _assemble_decision(
        transition=EdgeLifecycleTransition.INITIAL_ACTIVATION,
        prior_binding=None,
        admission_binding=binding,
        root_intake_digest=expected_root_intake_digest,
        effective_at_ns=effective_at_ns,
        decision_id=decision_id,
        correlation_id=correlation_id,
        reason_reference=reason_reference,
        kill_observation=None,
        governance=None,
    )


def build_edge_kill_quarantine_kill_disable(
    prior: EdgeKillQuarantineDecision,
    *,
    expected_prior_digest: str,
    expected_root_intake_digest: str,
    kill_observation: EdgeKillObservation,
    effective_at_ns: int,
    decision_id: str,
    correlation_id: str,
    reason_reference: str,
) -> EdgeKillQuarantineDecision:
    """KILL_DISABLE (ACTIVE → DISABLED) iff the observation triggers the sealed criterion it names.

    The observation can only disable; no caller flag says a kill happened. An untriggered, unsealed or mismatched
    observation is ``READY``/``FAIL`` and establishes no state.
    """

    _require_caller_fields(expected_root_intake_digest, effective_at_ns, decision_id, correlation_id, reason_reference)
    if _canonical_observation(kill_observation) is None:
        raise _fail("kill_observation_malformed")
    binding = _prior_binding(prior, expected_prior_digest)
    return _assemble_decision(
        transition=EdgeLifecycleTransition.KILL_DISABLE,
        prior_binding=binding,
        admission_binding=None,
        root_intake_digest=expected_root_intake_digest,
        effective_at_ns=effective_at_ns,
        decision_id=decision_id,
        correlation_id=correlation_id,
        reason_reference=reason_reference,
        kill_observation=kill_observation,
        governance=None,
    )


def build_edge_kill_quarantine_quarantine_entry(
    prior: EdgeKillQuarantineDecision,
    *,
    expected_prior_digest: str,
    expected_root_intake_digest: str,
    effective_at_ns: int,
    decision_id: str,
    correlation_id: str,
    reason_reference: str,
) -> EdgeKillQuarantineDecision:
    """QUARANTINE_ENTRY (DISABLED → QUARANTINE) strictly more than 30 UTC days after the disable; grants nothing."""

    _require_caller_fields(expected_root_intake_digest, effective_at_ns, decision_id, correlation_id, reason_reference)
    binding = _prior_binding(prior, expected_prior_digest)
    return _assemble_decision(
        transition=EdgeLifecycleTransition.QUARANTINE_ENTRY,
        prior_binding=binding,
        admission_binding=None,
        root_intake_digest=expected_root_intake_digest,
        effective_at_ns=effective_at_ns,
        decision_id=decision_id,
        correlation_id=correlation_id,
        reason_reference=reason_reference,
        kill_observation=None,
        governance=None,
    )


def build_edge_kill_quarantine_governed_readmission(
    prior: EdgeKillQuarantineDecision,
    *,
    expected_prior_digest: str,
    expected_root_intake_digest: str,
    revalidation: EdgePaperAdmissionDecision,
    expected_revalidation_digest: str,
    effective_at_ns: int,
    decision_id: str,
    correlation_id: str,
    reason_reference: str,
    governance: EdgeReadmissionGovernance | None = None,
) -> EdgeKillQuarantineDecision:
    """GOVERNED_READMISSION (QUARANTINE → ACTIVE, a new cycle) over a fresh EF-5-onward revalidation EF-7.

    Requires at least 14 UTC days of quarantine, a new authentic passing EF-7 of the same lifecycle subject and seal
    whose EF-7 and EF-6 were never consumed by this lifecycle and whose OOS horizon lies after the disable, and one exact
    human approval (``None`` is ``NEEDS_GOVERNANCE_APPROVAL``). A passing receipt proves this exact historical
    re-admission, never current paper admission or the current head.
    """

    _require_caller_fields(expected_root_intake_digest, effective_at_ns, decision_id, correlation_id, reason_reference)
    _canonical_governance(governance)
    prior_link = _prior_binding(prior, expected_prior_digest)
    admission_link = _admission_binding(revalidation, expected_revalidation_digest, "revalidation")
    return _assemble_decision(
        transition=EdgeLifecycleTransition.GOVERNED_READMISSION,
        prior_binding=prior_link,
        admission_binding=admission_link,
        root_intake_digest=expected_root_intake_digest,
        effective_at_ns=effective_at_ns,
        decision_id=decision_id,
        correlation_id=correlation_id,
        reason_reference=reason_reference,
        kill_observation=None,
        governance=governance,
    )


def edge_kill_quarantine_decision_to_dict(decision: EdgeKillQuarantineDecision) -> dict[str, object]:
    """Canonical JSON-ready mapping for an EF-8 lifecycle artifact, including its self-digest."""

    return _to_payload(decision)


def edge_kill_quarantine_decision_digest(decision: EdgeKillQuarantineDecision) -> str:
    """Recompute the canonical EF-8 digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(decision), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_str(item) for item in value)


def _as_enum(enum_cls: type[Enum], *, optional: bool = False) -> Callable[[object], Enum | None]:
    def convert(value: object) -> Enum | None:
        if value is None and optional:
            return None
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _as_kill_criteria(value: object) -> tuple[EdgeKillCriterion, ...]:
    """Canonical criteria only (sorted, unique, exact keys); an empty list is the empty tuple of an unsealed artifact."""

    if type(value) is list and not value:
        return ()
    try:
        return edge_kill_criteria_from_payload(value)
    except EdgeArtifactError as exc:
        raise _fail("payload_field_malformed") from exc


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_optional_record(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return None if value is None else _parse_exact(cls, value, converters)

    return convert


def _parse_prior_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_kill_quarantine_decision_payload_is_well_formed,
        error=EdgeKillQuarantineDecisionError,
        code=_reason("prior_lifecycle"),
        optional=True,
    )


def _parse_admission_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_paper_admission_decision_payload_is_well_formed,
        error=EdgeKillQuarantineDecisionError,
        code=_reason("admission"),
        optional=True,
    )


_DECISION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "transition": _as_enum(EdgeLifecycleTransition),
    "prior_binding": _parse_prior_binding,
    "prior_lifecycle_state": _as_enum(EdgeLifecycleState, optional=True),
    "prior_effective_at_ns": _as_optional_int,
    "resulting_lifecycle_state": _as_enum(EdgeLifecycleState, optional=True),
    "effective_at_ns": _as_int,
    "pinned_instrument_universe": _as_str_tuple,
    "lifecycle_sequence": _as_int,
    "lifecycle_cycle": _as_int,
    "admission_binding": _parse_admission_binding,
    "admission_evaluation_horizon_end_ns": _as_optional_int,
    "cycle_activated_at_ns": _as_optional_int,
    "cycle_disabled_at_ns": _as_optional_int,
    "consumed_admission_decision_digests": _as_str_tuple,
    "consumed_walk_forward_evidence_digests": _as_str_tuple,
    "sealed_kill_criteria": _as_kill_criteria,
    "kill_observation": _as_optional_record(EdgeKillObservation, {}),
    "kill_evaluation": _as_optional_record(
        EdgeKillEvaluation, {"comparator": _as_enum(EdgeKillCriterionComparator), "triggered": _as_bool}
    ),
    "governance": _as_optional_record(EdgeReadmissionGovernance, {"approved_effective_at_ns": _as_int}),
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_COMPUTED_FLAGS, _as_bool),
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_kill_quarantine_decision_from_payload(payload: object) -> EdgeKillQuarantineDecision:
    """Strictly reconstruct an EF-8 artifact from its serialized payload (exact fields, types, bindings and inputs).

    Reconstruction is not verification: consumers call ``verify_edge_kill_quarantine_decision`` on the result.
    """

    decision: EdgeKillQuarantineDecision = _parse_exact(  # type: ignore[assignment]
        EdgeKillQuarantineDecision, payload, _DECISION_CONVERTERS
    )
    _require_transition_inputs(
        decision.transition,
        decision.prior_binding,
        decision.admission_binding,
        decision.kill_observation,
        decision.governance,
    )
    return decision


def edge_kill_quarantine_decision_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-8 snapshot consumed by a later transition."""

    try:
        edge_kill_quarantine_decision_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_decision(decision: object) -> EdgeKillQuarantineDecision:
    return _assemble_decision(
        transition=decision.transition,  # type: ignore[attr-defined]
        prior_binding=decision.prior_binding,  # type: ignore[attr-defined]
        admission_binding=decision.admission_binding,  # type: ignore[attr-defined]
        root_intake_digest=decision.root_intake_digest,  # type: ignore[attr-defined]
        effective_at_ns=decision.effective_at_ns,  # type: ignore[attr-defined]
        decision_id=decision.decision_id,  # type: ignore[attr-defined]
        correlation_id=decision.correlation_id,  # type: ignore[attr-defined]
        reason_reference=decision.transition_reason_reference,  # type: ignore[attr-defined]
        kill_observation=decision.kill_observation,  # type: ignore[attr-defined]
        governance=decision.governance,  # type: ignore[attr-defined]
    )


def verify_edge_kill_quarantine_decision(decision: object) -> EdgeEvidenceVerification:
    """Re-prove an EF-8 artifact by strict parse and reassembly from its carried bindings, anchors and declarations.

    Every derived field — lifecycle states, subject, seal, cycle facts, kill evaluation, flags and verdict — must equal
    the reassembled artifact, which re-proves the prior lifecycle artifact and any EF-7 through their public verifiers.
    ``intact`` proves the historical receipt, never that it is the current lifecycle head or current paper authority:
    a receipt asserting either never verifies. Total: never raises.
    """

    return verify_edge_artifact_total(
        decision,
        cls=EdgeKillQuarantineDecision,
        to_payload=_to_payload,
        parse_payload=edge_kill_quarantine_decision_from_payload,
        reassemble=_reassemble_decision,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EDGE_KILL_OBSERVATION_STATUS",
    "EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS",
    "EDGE_KILL_QUARANTINE_RULE_SET_DIGEST",
    "EDGE_RESULTING_LIFECYCLE_STATE_STATUS",
    "EdgeKillEvaluation",
    "EdgeKillObservation",
    "EdgeKillQuarantineDecision",
    "EdgeKillQuarantineDecisionError",
    "EdgeLifecycleState",
    "EdgeLifecycleTransition",
    "EdgeReadmissionGovernance",
    "build_edge_kill_quarantine_governed_readmission",
    "build_edge_kill_quarantine_initial_activation",
    "build_edge_kill_quarantine_kill_disable",
    "build_edge_kill_quarantine_quarantine_entry",
    "edge_kill_criterion_triggered",
    "edge_kill_quarantine_decision_digest",
    "edge_kill_quarantine_decision_from_payload",
    "edge_kill_quarantine_decision_payload_is_well_formed",
    "edge_kill_quarantine_decision_to_dict",
    "edge_kill_quarantine_rule_set",
    "verify_edge_kill_quarantine_decision",
]
