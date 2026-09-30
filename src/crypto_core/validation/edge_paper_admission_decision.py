"""Edge Factory EF-7: governed paper-admission decision over an authenticated, passing EF-6 walk-forward/OOS result.

EF-7 is the sleeve-entry gate of ``docs/crypto_core/edge_factory_design.md`` §1.6 and the gate where the final kill
criteria become SEALED. PASS means ONLY process-level paper candidate admission: the whole EF-2 → EF-6 chain is
authentic and passing, the complete EF-6 surviving set is admitted without any selection, the exact authenticated EF-4
kill criteria are sealed, the admission is linked to one re-proven paper-only intra-sleeve risk-budget policy, explicit
bounded capacity ASSUMPTIONS are recorded, and one human governance approval commits to all of it. It never means an
edge, profitability, paper performance, Stage-4 completion, portfolio allocation, capital reservation, execution
permission, operational readiness or any live/shadow/Deribit authority.

Authority (shared kernel ``edge_artifact_core``):

* Back-chain. EF-6 is a required ``EdgeAuthorityBinding`` re-proven through ``verify_edge_walk_forward_oos_evidence``
  against the caller's predecessor anchor; a caller digest alone is never authority. EF-5 (from the EF-6 snapshot) and
  EF-4 (from the EF-5 snapshot) are re-proven through ``verify_edge_leakage_bias_evidence`` and
  ``verify_edge_strategy_spec_admission`` against the digests their successors carry; EF-3 and the EF-2 root are read
  from the snapshots EF-4's verification authenticated. Every link shares this decision's correlation, every carried
  root digest equals the explicit root anchor, and the identities EF-7 relies on (spec, admission, manifest, registry,
  executable binding, profile, market type, pinned universe, variant ledger, registered set, trial count) must agree
  across links, so no chain can be spliced. EF-5 must be READY + PASS + advancing + sealed, EF-4 READY + PASS +
  advancing, EF-3 and EF-2 advancing; anything else is REJECTED.
* Prior gates. An authentic EF-6 that is REJECTED is REJECTED here. An authentic READY EF-6 that does not advance is
  valid negative evidence: its verdict is propagated (FAIL, NEEDS_EXTERNAL_FACTS or NEEDS_GOVERNANCE_APPROVAL), so
  nothing short of an EF-6 PASS can ever be admitted.
* Selection firewall (``COMPLETE_SURVIVING_SET_NO_SELECTION``). EF-6 ranks nothing and no accepted authority holds a
  preregistered selector, so EF-7 selects nothing: the admission subject is the complete, canonically ordered set of
  EF-6 surviving assignments, each mapped to its variant id through the authenticated EF-5 ledger. No caller input
  names, orders or prefers a variant; a survivor outside the registered set, or a survivor set that disagrees with the
  EF-6 evaluations, is REJECTED.
* Kill-criteria seal. No caller input carries kill criteria. The final criteria are exactly the authenticated EF-4
  ``admitted_kill_criteria`` (the EF-2 draft strengthened superset-only and approved by the EF-4 kill-criteria policy),
  re-checked against their carried digest, the root draft, the combination policy and the approving policy. The
  kill-criteria record digest commits them with their lineage; ``sealed_kill_criteria_digest`` equals it and
  ``kill_criteria_sealed`` is True exactly on PASS, which is the digest EF-8 must enforce immutability against.
* Risk-budget linkage. The only accepted budget authority is the merged paper-only intra-sleeve
  ``PaperSleeveRiskBudgetPolicy``: a required binding re-proven by reconstruction through its public builder, canonical
  equality with the public serializer and its public digest against the caller anchor; its sleeve must equal the
  declared paper sleeve. The linkage is identity only — never an allocation, an order, execution permission or a capital
  reservation. The portfolio RG envelope and allocator do not exist yet: their absence is the digest-bound marker
  ``PENDING_RG_PORTFOLIO_RISK_ENVELOPE_UNAVAILABLE``, never a fabricated envelope; the future allocator consumes EF-7.
* Capacity. Caller-supplied, explicit, finite ASSUMPTIONS (measure, unit, scope and basis tokens plus a strictly
  positive canonical scale-18 inclusive upper bound) per pinned instrument; never an empirical fact, never a current
  venue fact, never unlimited. They are bound separately from the risk budget and no arithmetic relates the two. No
  assumption is NEEDS_GOVERNANCE_APPROVAL; an assumption outside the pinned universe is FAIL.
* Governance. ``EdgePaperAdmissionGovernance`` commits to the EF-6 digest, the admission subject, the kill-criteria
  record, the risk-budget policy, the capacity assumption set and the EF-7 rule set. Missing or non-matching is
  NEEDS_GOVERNANCE_APPROVAL; no value is defaulted or invented.
* ``status`` is integrity only and ``gate_verdict`` the outcome (FAIL > NEEDS_EXTERNAL_FACTS >
  NEEDS_GOVERNANCE_APPROVAL > PASS); REJECTED implies NOT_EVALUATED; only READY + PASS advances, and
  ``candidate_admitted_to_paper``/``kill_criteria_sealed`` are True exactly then. ``preregistration_sealed`` and the two
  consumption flags mirror authenticated EF-6 proof. One assembly path serves the builder and verifier reassembly;
  ``verify_edge_paper_admission_decision`` is total. Paper-only, deterministic, no IO/clock/network/float/decimal.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
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
    EdgeKillCriteriaPolicyStatus,
    EdgeKillCriterion,
    edge_idea_intake_evidence_from_payload,
    edge_kill_criteria_digest,
    edge_kill_criteria_from_payload,
    edge_kill_criteria_policy_from_payload,
    edge_kill_criterion_to_dict,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeLeakageBiasEvidence,
    edge_leakage_bias_evidence_from_payload,
    verify_edge_leakage_bias_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    edge_source_packet_evidence_from_payload,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmissionEvidence,
    edge_strategy_spec_admission_from_payload,
    verify_edge_strategy_spec_admission,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EdgeVariantEvaluationStatus,
    EdgeWalkForwardOosEvidence,
    edge_walk_forward_oos_evidence_from_payload,
    edge_walk_forward_oos_evidence_payload_is_well_formed,
    edge_walk_forward_oos_evidence_to_dict,
    verify_edge_walk_forward_oos_evidence,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetPolicy,
    build_paper_sleeve_risk_budget_policy,
    paper_sleeve_risk_budget_policy_digest,
    paper_sleeve_risk_budget_policy_to_dict,
)

_SCHEMA_VERSION = "edge-paper-admission-decision.v1"
_GATE_ID = "EF-7"
_PREDECESSOR_GATE_ID = "EF-6"
_REASON_PREFIX = "edge_paper_admission_decision"
_SELF_DIGEST_FIELD = "paper_admission_decision_digest"
_INT64_MAX = 9223372036854775807
_MAX_TEXT_LENGTH = 256
_MAX_TOKEN_LENGTH = 128
_DIGITS = frozenset("0123456789")
# The EF-4 kill-criteria lifecycle stage and combination policy EF-7 seals; any other upstream value is refused.
_UPSTREAM_KILL_CRITERIA_STAGE = "SUPERSET_STRENGTHENED_UNSEALED"
_SEALED_KILL_CRITERIA_STAGE = "SEALED"
_KILL_CRITERIA_COMBINATION_POLICY = "any_single_criterion_triggers_kill.v1"
# Words that would declare capacity unbounded; an assumption must be a finite bound, never an asymptotic claim.
_UNBOUNDED_CAPACITY_WORDS = ("unlimited", "unbounded", "uncapped", "infinite", "infinity", "asymptotic")

EDGE_PORTFOLIO_RISK_ENVELOPE_PENDING = "PENDING_RG_PORTFOLIO_RISK_ENVELOPE_UNAVAILABLE"
EDGE_CAPACITY_EVIDENCE_STATUS = "GOVERNED_ASSUMPTION_NOT_EMPIRICALLY_PROVEN"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "edge_paper_admission_rules.v1",
    "predecessor_rule_id": "ef6_exact_anchor_public_reproof_rejected_rejects_non_advancing_verdict_propagates.v1",
    "backchain_rule_id": "ef6_ef5_ef4_public_verifiers_dual_anchor_correlation_and_identity_cross_binding.v1",
    "prior_gate_rule_id": "ef2_ef3_ef4_ef5_ef6_all_ready_passing_and_advancing_ef5_sealed.v1",
    "selection_rule_id": "complete_ef6_surviving_registered_assignment_set_no_selection_no_ranking.v1",
    "kill_criteria_seal_rule_id": "exact_authenticated_ef4_admitted_criteria_sealed_on_pass_only_no_caller_criteria.v1",
    "kill_criteria_combination_policy": _KILL_CRITERIA_COMBINATION_POLICY,
    "risk_budget_rule_id": "paper_sleeve_risk_budget_policy_public_rebuild_reproof_sleeve_bound_identity_linkage_only.v1",
    "portfolio_risk_rule_id": "portfolio_rg_envelope_and_allocator_pending_admission_is_allocator_input_never_allocation.v1",
    "capacity_rule_id": "explicit_finite_positive_inclusive_upper_bound_assumption_per_pinned_instrument_not_proven.v1",
    "capacity_budget_separation_rule_id": "capacity_assumptions_and_risk_budget_bound_separately_no_arithmetic.v1",
    "capacity_value_scale": 18,
    "capacity_value_max_text_length": 60,
    "governance_rule_id": "approval_commits_predecessor_subject_kill_record_budget_policy_capacity_set_rule_set.v1",
    "gate_rule_id": "pass_iff_passing_chain_valid_linkage_governed_capacity_and_exact_approval.v1",
    "numeric_rule_id": "unsigned_canonical_fixed_scale_text_exact_integer_units_no_float_no_decimal_context.v1",
    "regime_rule_id": "regime_evidence_unavailable_until_accepted_rf_chain.v1",
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_CAPACITY_VALUE_SCALE: int = _RULE_SET_V1["capacity_value_scale"]  # type: ignore[assignment]
_CAPACITY_VALUE_MAX_TEXT_LENGTH: int = _RULE_SET_V1["capacity_value_max_text_length"]  # type: ignore[assignment]
EDGE_PAPER_ADMISSION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))


def edge_paper_admission_rule_set() -> dict[str, object]:
    """A fresh copy of the code-defined EF-7 V1 rule set committed by ``EDGE_PAPER_ADMISSION_RULE_SET_DIGEST``."""

    return dict(_RULE_SET_V1)


# EF-7 computes these five flags from authenticated proof; every other non-claim is a structural default.
_COMPUTED_FLAGS = frozenset(
    {
        "candidate_admitted_to_paper",
        "kill_criteria_sealed",
        "preregistration_sealed",
        "performance_data_consumed",
        "oos_evidence_consumed",
    }
)
EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *(flag for flag in EDGE_STRUCTURAL_NON_CLAIM_FLAGS if flag[0] not in _COMPUTED_FLAGS),
    ("pbo_passed", False),
    ("stress_passed", False),
    ("paper_performance_proven", False),
    ("prdv4_stage4_complete", False),
    ("portfolio_allocation_approved", False),
    ("capital_allocated", False),
    ("execution_authorized", False),
    ("capacity_empirically_proven", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS)


class EdgePaperAdmissionDecisionError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


@dataclass(frozen=True)
class EdgeCapacityAssumption:
    """One explicit capacity ASSUMPTION: an inclusive finite upper bound in a declared unit, scope and basis.

    ``max_value`` is an unsigned canonical scale-18 text strictly above zero. It is governance-approved input, never an
    empirical measurement, a current venue fact or a risk budget.
    """

    assumption_id: str
    instrument: str
    capacity_measure_id: str
    unit_id: str
    scope_id: str
    basis_id: str
    max_value: str


@dataclass(frozen=True)
class EdgePaperAdmissionGovernance:
    """Human governance approval of one exact EF-7 admission; every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approved_predecessor_digest: str
    approved_admission_subject_digest: str
    approved_kill_criteria_record_digest: str
    approved_risk_budget_policy_digest: str
    approved_capacity_assumption_set_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class EdgeAdmittedVariant:
    """One admitted registered variant: an EF-6 survivor and its EF-5 ledger identity. Never ranked or chosen."""

    variant_id: str
    parameter_assignment_digest: str


@dataclass(frozen=True)
class EdgePaperAdmissionDecision:
    """Immutable, digest-bound EF-7 paper-admission decision. PAPER ONLY; process admission, never an edge."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    decision_id: str
    correlation_id: str
    root_intake_digest: str
    predecessor_binding: EdgeAuthorityBinding
    predecessor_gate_id: str
    predecessor_digest: str
    predecessor_gate_verdict: str
    preregistration_digest: str
    strategy_spec_admission_digest: str
    source_manifest_digest: str
    candidate_strategy_id: str
    edge_family: str
    strategy_id: str
    strategy_version: str
    strategy_spec_digest: str
    executable_binding_digest: str
    profile_semantics_digest: str
    market_type: str
    pinned_instrument_universe: tuple[str, ...]
    variant_ledger_digest: str
    multiple_testing_count: int
    registered_variant_count: int
    evaluation_frame_digest: str
    oos_governance_digest: str
    paper_sleeve_id: str
    admitted_variants: tuple[EdgeAdmittedVariant, ...]
    admitted_variant_count: int
    admission_subject_digest: str
    root_kill_criteria_digest: str
    final_kill_criteria: tuple[EdgeKillCriterion, ...]
    final_kill_criteria_digest: str
    added_kill_criterion_ids: tuple[str, ...]
    kill_criteria_combination_policy: str
    kill_criteria_policy_digest: str
    kill_criteria_record_digest: str
    kill_criteria_lifecycle_stage: str
    sealed_kill_criteria_digest: str
    risk_budget_policy_binding: EdgeAuthorityBinding
    risk_budget_policy_id: str
    risk_budget_policy_digest: str
    portfolio_risk_envelope_status: str
    capacity_assumptions: tuple[EdgeCapacityAssumption, ...]
    capacity_assumption_set_digest: str
    capacity_evidence_status: str
    rule_set_id: str
    rule_set_digest: str
    governance: EdgePaperAdmissionGovernance | None
    governance_digest: str
    regime_label_binding_status: str
    regime_evidence_status: str
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    preregistration_sealed: bool
    performance_data_consumed: bool
    oos_evidence_consumed: bool
    candidate_admitted_to_paper: bool
    kill_criteria_sealed: bool
    paper_admission_decision_digest: str
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


@dataclass(frozen=True)
class _Chain:
    """The authenticated EF-6 → EF-2 chain facts EF-7 relies on."""

    ef6: EdgeWalkForwardOosEvidence
    ef5: EdgeLeakageBiasEvidence
    admission: EdgeStrategySpecAdmissionEvidence
    manifest: EdgeSourcePacketEvidence
    root: EdgeIdeaIntakeEvidence
    kill_criteria_policy_digest: str


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgePaperAdmissionDecisionError:
    return EdgePaperAdmissionDecisionError(_reason(code))


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


def _capacity_units(value: object) -> int | None:
    """Exact signed scale units of a canonical fixed-scale capacity text under the committed rule set; else ``None``.

    The grammar is ``[-]digits.digits`` with exactly the committed scale, no redundant leading zero, no negative zero,
    ASCII digits only and at most the committed text length, so float, bool, NaN, Infinity, exponent, whitespace,
    underscore and sign-prefixed forms other than one leading minus are all refused. No float or decimal context.
    """

    if type(value) is not str or not value or len(value) > _CAPACITY_VALUE_MAX_TEXT_LENGTH:
        return None
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if dot != "." or len(fraction) != _CAPACITY_VALUE_SCALE or not integer:
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

    for name, enum_cls in _ENUM_FIELDS.get(type(artifact), ()):
        if type(getattr(artifact, name)) is not enum_cls:
            raise _fail("payload_enum_field_not_exact_member")
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


_RECORD_TYPES = frozenset({EdgeCapacityAssumption, EdgePaperAdmissionGovernance, EdgeAdmittedVariant})
_ENUM_FIELDS: dict[type, tuple[tuple[str, type[Enum]], ...]] = {
    EdgePaperAdmissionDecision: (("status", EdgeEvidenceStatus), ("gate_verdict", EdgeGateVerdict)),
}


# --- caller declarations -----------------------------------------------------------------------------------------------


def _canonical_capacity_assumptions(values: object) -> tuple[EdgeCapacityAssumption, ...]:
    """Validate explicit bounded assumptions and order them by ``assumption_id`` (order-insensitive input)."""

    if type(values) not in (tuple, list):
        raise _fail("capacity_assumptions_malformed")
    by_id: dict[str, EdgeCapacityAssumption] = {}
    scopes: set[tuple[str, str, str]] = set()
    for item in values:  # type: ignore[union-attr]
        if type(item) is not EdgeCapacityAssumption:
            raise _fail("capacity_assumption_malformed")
        record = EdgeCapacityAssumption(
            assumption_id=_require_token(getattr(item, "assumption_id", None), "capacity_assumption_id"),
            instrument=_require_text(getattr(item, "instrument", None), "capacity_assumption_instrument"),
            capacity_measure_id=_require_token(
                getattr(item, "capacity_measure_id", None), "capacity_assumption_capacity_measure_id"
            ),
            unit_id=_require_token(getattr(item, "unit_id", None), "capacity_assumption_unit_id"),
            scope_id=_require_token(getattr(item, "scope_id", None), "capacity_assumption_scope_id"),
            basis_id=_require_token(getattr(item, "basis_id", None), "capacity_assumption_basis_id"),
            max_value=getattr(item, "max_value", None),  # type: ignore[arg-type]
        )
        tokens = (record.assumption_id, record.capacity_measure_id, record.unit_id, record.scope_id, record.basis_id)
        if any(word in token for token in tokens for word in _UNBOUNDED_CAPACITY_WORDS):
            raise _fail("capacity_assumption_unbounded_declaration")
        units = _capacity_units(record.max_value)
        if units is None:
            raise _fail("capacity_assumption_max_value_invalid")
        if units <= 0:
            raise _fail("capacity_assumption_max_value_not_positive")
        if record.assumption_id in by_id:
            raise _fail("capacity_assumption_duplicate")
        scope = (record.instrument, record.capacity_measure_id, record.scope_id)
        if scope in scopes:
            raise _fail("capacity_assumption_ambiguous")
        scopes.add(scope)
        by_id[record.assumption_id] = record
    return tuple(by_id[assumption_id] for assumption_id in sorted(by_id))


def _canonical_governance(governance: object) -> EdgePaperAdmissionGovernance | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if governance is None:
        return None
    if type(governance) is not EdgePaperAdmissionGovernance:
        raise _fail("governance_malformed")

    def attribute(name: str) -> object:
        return getattr(governance, name, None)

    return EdgePaperAdmissionGovernance(
        approval_reference=_require_text(attribute("approval_reference"), "governance_approval_reference"),
        approval_digest=_require_hex64(attribute("approval_digest"), "governance_approval_digest"),
        approved_predecessor_digest=_require_hex64(
            attribute("approved_predecessor_digest"), "governance_approved_predecessor_digest"
        ),
        approved_admission_subject_digest=_require_hex64(
            attribute("approved_admission_subject_digest"), "governance_approved_admission_subject_digest"
        ),
        approved_kill_criteria_record_digest=_require_hex64(
            attribute("approved_kill_criteria_record_digest"), "governance_approved_kill_criteria_record_digest"
        ),
        approved_risk_budget_policy_digest=_require_hex64(
            attribute("approved_risk_budget_policy_digest"), "governance_approved_risk_budget_policy_digest"
        ),
        approved_capacity_assumption_set_digest=_require_hex64(
            attribute("approved_capacity_assumption_set_digest"), "governance_approved_capacity_assumption_set_digest"
        ),
        approved_rule_set_digest=_require_hex64(
            attribute("approved_rule_set_digest"), "governance_approved_rule_set_digest"
        ),
    )


# --- the paper-only risk-budget policy authority -----------------------------------------------------------------------

_RISK_BUDGET_POLICY_TEXT_FIELDS = frozenset(
    {"schema_version", "policy_id", "sleeve_id", "total_budget", "per_intent_budget_cap", "policy_digest"}
)
_RISK_BUDGET_POLICY_BOOL_FIELDS = frozenset(
    {"require_journal_bound", "paper_only", "real_orders_enabled", "real_money_enabled"}
)
_RISK_BUDGET_POLICY_FIELDS = (
    _RISK_BUDGET_POLICY_TEXT_FIELDS | _RISK_BUDGET_POLICY_BOOL_FIELDS | {"per_instrument_budget_cap", "metadata"}
)


def _risk_budget_policy_snapshot_is_well_formed(snapshot: object) -> bool:
    """Binding shape predicate: the exact structure ``paper_sleeve_risk_budget_policy_to_dict`` produces."""

    if type(snapshot) is not dict or set(snapshot) != _RISK_BUDGET_POLICY_FIELDS:
        return False
    cap = snapshot["per_instrument_budget_cap"]
    metadata = snapshot["metadata"]
    return (
        all(type(snapshot[name]) is str for name in _RISK_BUDGET_POLICY_TEXT_FIELDS)
        and all(type(snapshot[name]) is bool for name in _RISK_BUDGET_POLICY_BOOL_FIELDS)
        and (cap is None or type(cap) is str)
        and type(metadata) is list
        and all(type(pair) is list and len(pair) == 2 and all(type(text) is str for text in pair) for pair in metadata)
    )


def _risk_budget_policy_authority(
    binding: EdgeAuthorityBinding,
) -> tuple[list[str], PaperSleeveRiskBudgetPolicy | None]:
    """Re-prove the policy through its public builder, serializer and digest; the stored digest is never trusted."""

    snapshot = edge_authority_binding_snapshot(binding)
    try:
        rebuilt = build_paper_sleeve_risk_budget_policy(
            policy_id=snapshot["policy_id"],
            sleeve_id=snapshot["sleeve_id"],
            total_budget=snapshot["total_budget"],
            per_intent_budget_cap=snapshot["per_intent_budget_cap"],
            per_instrument_budget_cap=snapshot["per_instrument_budget_cap"],
            require_journal_bound=snapshot["require_journal_bound"],
            metadata=dict(snapshot["metadata"]),
        )
    except Exception:  # noqa: BLE001 - the public builder refusing authenticated fields is a truthful rejection
        return [_reason("risk_budget_policy_rebuild_failed")], None
    codes: list[str] = []
    if paper_sleeve_risk_budget_policy_to_dict(rebuilt) != snapshot:
        codes.append(_reason("risk_budget_policy_noncanonical"))
    recomputed = paper_sleeve_risk_budget_policy_digest(rebuilt)
    if recomputed != snapshot["policy_digest"] or recomputed != binding.expected_digest:
        codes.append(_reason("risk_budget_policy_digest_mismatch"))
    texts = (rebuilt.policy_id, rebuilt.sleeve_id, *(text for pair in rebuilt.metadata for text in pair))
    if any(edge_scope_violation(text) is not None for text in texts):
        codes.append(_reason("risk_budget_policy_scope_violation"))
    if codes:
        return codes, None
    return [], rebuilt


# --- the authenticated back-chain --------------------------------------------------------------------------------------


def _identity_codes(
    ef6: EdgeWalkForwardOosEvidence,
    ef5: EdgeLeakageBiasEvidence,
    admission: EdgeStrategySpecAdmissionEvidence,
    manifest: EdgeSourcePacketEvidence,
    root: EdgeIdeaIntakeEvidence,
) -> list[str]:
    """Every identity EF-7 relies on must agree across the authenticated links (no chain splicing)."""

    checks = (
        ("strategy_spec_admission_digest", ef6.admission_digest, ef5.predecessor_digest),
        ("source_manifest_digest", ef6.source_manifest_digest, ef5.source_manifest_digest),
        ("source_manifest_digest", ef5.source_manifest_digest, admission.predecessor_digest),
        (
            "data_requirement_registry_digest",
            ef6.data_requirement_registry_digest,
            manifest.data_requirement_registry_digest,
        ),
        ("strategy_spec_digest", ef6.strategy_spec_digest, ef5.strategy_spec_digest),
        ("strategy_spec_digest", ef5.strategy_spec_digest, admission.strategy_spec_digest),
        ("strategy_id", ef5.strategy_id, admission.strategy_id),
        ("candidate_strategy_id", ef5.candidate_strategy_id, root.candidate_strategy_id),
        ("edge_family", ef5.edge_family, root.edge_family),
        ("executable_binding_digest", ef6.executable_binding_digest, ef5.executable_binding_digest),
        ("profile_semantics_digest", ef6.profile_semantics_digest, ef5.profile_semantics_digest),
        ("market_type", ef6.market_type, admission.market_type),
        ("pinned_instrument_universe", ef6.pinned_instrument_universe, ef5.pinned_instrument_universe),
        ("variant_ledger_digest", ef6.variant_ledger_digest, ef5.variant_ledger_digest),
        (
            "registered_parameter_assignment_digests",
            ef6.registered_parameter_assignment_digests,
            ef5.registered_parameter_assignment_digests,
        ),
        ("multiple_testing_count", ef6.multiple_testing_count, ef5.multiple_testing_count),
    )
    return [_reason(f"chain_identity_mismatch:{name}") for name, left, right in checks if left != right]


def _predecessor_consistency_codes(ef6: EdgeWalkForwardOosEvidence, ef5: EdgeLeakageBiasEvidence) -> list[str]:
    """The EF-6 facts EF-7 consumes must be internally consistent (always true for an intact EF-6; checked anyway)."""

    codes: list[str] = []
    survivors = ef6.surviving_assignment_digests
    survived = sorted(
        item.parameter_assignment_digest
        for item in ef6.variant_evaluations
        if item.evaluation_status is EdgeVariantEvaluationStatus.SURVIVED
    )
    if list(survivors) != survived or len(set(survivors)) != len(survivors):
        codes.append(_reason("predecessor_inconsistent:surviving_set"))
    if not set(survivors) <= set(ef5.registered_parameter_assignment_digests):
        codes.append(_reason("predecessor_inconsistent:unregistered_survivor"))
    passing = ef6.gate_verdict is EdgeGateVerdict.PASS
    if ef6.advances is not passing:
        codes.append(_reason("predecessor_inconsistent:advances"))
    if passing is not bool(survivors):
        codes.append(_reason("predecessor_inconsistent:verdict_survivor_mismatch"))
    consumed = (ef6.performance_data_consumed, ef6.oos_evidence_consumed, ef6.walk_forward_evaluated)
    if passing and consumed != (True, True, True):
        codes.append(_reason("predecessor_inconsistent:performance_not_consumed"))
    if ef6.preregistration_sealed is not True:
        codes.append(_reason("predecessor_inconsistent:preregistration_not_sealed"))
    if ef6.regime_evidence_status != EDGE_REGIME_EVIDENCE_UNAVAILABLE or ef6.regime_evidence_available is not False:
        codes.append(_reason("predecessor_inconsistent:regime"))
    return codes


def _kill_criteria_codes(
    admission: EdgeStrategySpecAdmissionEvidence, root: EdgeIdeaIntakeEvidence
) -> tuple[list[str], str]:
    """``(codes, approving_policy_digest)`` for the authenticated EF-4 criteria EF-7 seals."""

    codes: list[str] = []
    admitted = admission.admitted_kill_criteria
    try:
        recomputed = edge_kill_criteria_digest(admitted)
    except EdgeArtifactError:
        return [_reason("kill_criteria_malformed")], ""
    if recomputed != admission.admitted_kill_criteria_digest:
        codes.append(_reason("kill_criteria_digest_mismatch"))
    if admission.root_kill_criteria_digest != root.kill_criteria_digest:
        codes.append(_reason("kill_criteria_root_draft_mismatch"))
    admitted_by_id = {item.criterion_id: edge_kill_criterion_to_dict(item) for item in admitted}
    if any(
        admitted_by_id.get(item.criterion_id) != edge_kill_criterion_to_dict(item) for item in root.kill_criteria_draft
    ):
        codes.append(_reason("kill_criteria_weaker_than_root_draft"))
    draft_ids = {item.criterion_id for item in root.kill_criteria_draft}
    added = tuple(item.criterion_id for item in admitted if item.criterion_id not in draft_ids)
    if admission.added_kill_criterion_ids != added:
        codes.append(_reason("kill_criteria_added_ids_mismatch"))
    if any(item.threshold is None for item in admitted):
        codes.append(_reason("kill_criteria_threshold_pending"))
    if (
        admission.kill_criteria_combination_policy != _KILL_CRITERIA_COMBINATION_POLICY
        or root.kill_criteria_combination_policy != _KILL_CRITERIA_COMBINATION_POLICY
    ):
        codes.append(_reason("kill_criteria_combination_policy_unsupported"))
    if admission.kill_criteria_lifecycle_stage != _UPSTREAM_KILL_CRITERIA_STAGE:
        codes.append(_reason("kill_criteria_lifecycle_stage_unexpected"))
    binding = admission.kill_criteria_policy_binding
    if binding is None:
        return [*codes, _reason("kill_criteria_policy_missing")], ""
    policy = edge_kill_criteria_policy_from_payload(edge_authority_binding_snapshot(binding))
    if (
        policy.status is not EdgeKillCriteriaPolicyStatus.POLICY_READY
        or policy.kill_criteria_digest != admission.admitted_kill_criteria_digest
        or policy.correlation_id != admission.correlation_id
    ):
        codes.append(_reason("kill_criteria_policy_not_approving"))
    return codes, binding.expected_digest


def _chain_authority(
    binding: EdgeAuthorityBinding, *, root_intake_digest: str, correlation_id: str
) -> tuple[list[str], _Chain | None]:
    """Re-prove EF-6 → EF-5 → EF-4 through the public verifiers and read EF-3/EF-2 from EF-4's authenticated chain."""

    ef6 = edge_walk_forward_oos_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_walk_forward_oos_evidence(ef6)
    if not verification.intact:
        return [_reason(f"predecessor_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("predecessor_digest_mismatch")], None
    if ef6.correlation_id != correlation_id:
        return [_reason("predecessor_correlation_mismatch")], None
    if ef6.status is not EdgeEvidenceStatus.READY:
        return [_reason("predecessor_rejected")], None
    ef5 = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(ef6.predecessor_binding))
    ef5_verification = verify_edge_leakage_bias_evidence(ef5)
    if not ef5_verification.intact:
        return [_reason(f"preregistration_integrity_failure:{code}") for code in ef5_verification.reason_codes], None
    if ef5_verification.recomputed_digest != ef6.predecessor_digest or ef5.correlation_id != correlation_id:
        return [_reason("preregistration_chain_mismatch")], None
    if (
        ef5.status is not EdgeEvidenceStatus.READY
        or ef5.gate_verdict is not EdgeGateVerdict.PASS
        or ef5.advances is not True
        or ef5.preregistration_sealed is not True
    ):
        return [_reason("preregistration_not_sealed")], None
    admission = edge_strategy_spec_admission_from_payload(edge_authority_binding_snapshot(ef5.predecessor_binding))
    admission_verification = verify_edge_strategy_spec_admission(admission)
    if not admission_verification.intact:
        codes = [
            _reason(f"strategy_spec_admission_integrity_failure:{code}") for code in admission_verification.reason_codes
        ]
        return codes, None
    if admission_verification.recomputed_digest != ef5.predecessor_digest or admission.correlation_id != correlation_id:
        return [_reason("strategy_spec_admission_chain_mismatch")], None
    if (
        admission.status is not EdgeEvidenceStatus.READY
        or admission.gate_verdict is not EdgeGateVerdict.PASS
        or admission.advances is not True
    ):
        return [_reason("strategy_spec_admission_not_passing")], None
    # EF-4's READY verification re-proved its EF-3 predecessor and the EF-2 root nested in it against their anchors,
    # so both snapshots are authenticated here and are read, never re-derived.
    manifest = edge_source_packet_evidence_from_payload(edge_authority_binding_snapshot(admission.predecessor_binding))
    root = edge_idea_intake_evidence_from_payload(edge_authority_binding_snapshot(manifest.root_intake_binding))
    carried_roots = (
        ef6.root_intake_digest,
        ef5.root_intake_digest,
        admission.root_intake_digest,
        manifest.root_intake_digest,
        root.intake_digest,
    )
    if any(carried != root_intake_digest for carried in carried_roots):
        return [_reason("chain_splice_root_intake_mismatch")], None
    if (
        manifest.status is not EdgeEvidenceStatus.READY
        or manifest.advances is not True
        or manifest.correlation_id != correlation_id
        or root.status is not EdgeEvidenceStatus.READY
        or root.advances is not True
        or root.correlation_id != correlation_id
    ):
        return [_reason("upstream_gate_not_passing")], None
    kill_codes, policy_digest = _kill_criteria_codes(admission, root)
    codes = [
        *_identity_codes(ef6, ef5, admission, manifest, root),
        *_predecessor_consistency_codes(ef6, ef5),
        *kill_codes,
    ]
    if codes:
        return codes, None
    return [], _Chain(
        ef6=ef6, ef5=ef5, admission=admission, manifest=manifest, root=root, kill_criteria_policy_digest=policy_digest
    )


# --- derived admission facts -------------------------------------------------------------------------------------------


def _admitted_variants(chain: _Chain) -> tuple[EdgeAdmittedVariant, ...]:
    """The COMPLETE EF-6 surviving set in its canonical order; no selection, ranking or caller preference."""

    variant_ids = {item.parameter_assignment_digest: item.variant_id for item in chain.ef5.registered_variants}
    return tuple(
        EdgeAdmittedVariant(variant_id=variant_ids[digest], parameter_assignment_digest=digest)
        for digest in chain.ef6.surviving_assignment_digests
    )


def _subject_payload(chain: _Chain, admitted: Sequence[EdgeAdmittedVariant], paper_sleeve_id: str) -> dict[str, object]:
    ef5 = chain.ef5
    return {
        "root_intake_digest": chain.ef6.root_intake_digest,
        "candidate_strategy_id": ef5.candidate_strategy_id,
        "edge_family": ef5.edge_family,
        "strategy_id": ef5.strategy_id,
        "strategy_version": ef5.strategy_version,
        "strategy_spec_digest": ef5.strategy_spec_digest,
        "executable_binding_digest": ef5.executable_binding_digest,
        "profile_semantics_digest": ef5.profile_semantics_digest,
        "market_type": chain.ef6.market_type,
        "pinned_instrument_universe": list(ef5.pinned_instrument_universe),
        "variant_ledger_digest": ef5.variant_ledger_digest,
        "multiple_testing_count": ef5.multiple_testing_count,
        "admitted_variants": [_to_payload(item) for item in admitted],
        "paper_sleeve_id": paper_sleeve_id,
    }


def _kill_criteria_record_payload(chain: _Chain) -> dict[str, object]:
    admission = chain.admission
    return {
        "root_intake_digest": admission.root_intake_digest,
        "strategy_spec_admission_digest": chain.ef5.predecessor_digest,
        "strategy_spec_digest": admission.strategy_spec_digest,
        "root_kill_criteria_digest": admission.root_kill_criteria_digest,
        "kill_criteria": [edge_kill_criterion_to_dict(item) for item in admission.admitted_kill_criteria],
        "kill_criteria_digest": admission.admitted_kill_criteria_digest,
        "added_kill_criterion_ids": list(admission.added_kill_criterion_ids),
        "combination_policy": admission.kill_criteria_combination_policy,
        "kill_criteria_policy_digest": chain.kill_criteria_policy_digest,
    }


def _capacity_set_payload(assumptions: Sequence[EdgeCapacityAssumption]) -> dict[str, object]:
    return {
        "capacity_rule_id": _RULE_SET_V1["capacity_rule_id"],
        "evidence_status": EDGE_CAPACITY_EVIDENCE_STATUS,
        "assumptions": [_to_payload(item) for item in assumptions],
    }


def _propagate(verdict: EdgeGateVerdict, buckets: tuple[list[str], list[str], list[str]]) -> None:
    fail, needs_external, needs_governance = buckets
    code = _reason(f"predecessor_not_advanced:{verdict.value}")
    if verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        needs_external.append(code)
    elif verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        needs_governance.append(code)
    else:
        fail.append(code)


def _capacity_reasons(
    assumptions: Sequence[EdgeCapacityAssumption], universe: Sequence[str]
) -> tuple[list[str], list[str]]:
    """``(fail, needs_governance)``: every pinned instrument needs an assumption; none may lie outside the universe."""

    fail = [
        _reason(f"capacity_assumption_instrument_outside_pinned_universe:{item.assumption_id}")
        for item in assumptions
        if item.instrument not in universe
    ]
    if not assumptions:
        return fail, [_reason("capacity_assumptions_missing")]
    covered = {item.instrument for item in assumptions}
    needs = [
        _reason(f"capacity_assumption_missing_for_instrument:{instrument}")
        for instrument in universe
        if instrument not in covered
    ]
    return fail, needs


def _governance_reasons(governance: EdgePaperAdmissionGovernance | None, committed: Mapping[str, str]) -> list[str]:
    if governance is None:
        return [_reason("admission_governance_missing")]
    return [
        _reason(f"admission_governance_{name}_mismatch")
        for name, value in committed.items()
        if getattr(governance, f"approved_{name}") != value
    ]


# --- EF-7 decision -----------------------------------------------------------------------------------------------------


def _assemble_decision(
    *,
    predecessor_binding: object,
    root_intake_digest: object,
    risk_budget_policy_binding: object,
    paper_sleeve_id: object,
    capacity_assumptions: object,
    decision_id: object,
    correlation_id: object,
    governance: object,
) -> EdgePaperAdmissionDecision:
    """The one EF-7 assembly path, shared by the builder and verifier reassembly."""

    chain_binding = require_edge_authority_binding(
        predecessor_binding,
        shape=edge_walk_forward_oos_evidence_payload_is_well_formed,
        error=EdgePaperAdmissionDecisionError,
        code=_reason("predecessor"),
        optional=False,
    )
    policy_binding = require_edge_authority_binding(
        risk_budget_policy_binding,
        shape=_risk_budget_policy_snapshot_is_well_formed,
        error=EdgePaperAdmissionDecisionError,
        code=_reason("risk_budget_policy"),
        optional=False,
    )
    root_anchor = _require_hex64(root_intake_digest, "root_intake_digest")
    paper_sleeve_id = _require_text(paper_sleeve_id, "paper_sleeve_id")
    assumptions = _canonical_capacity_assumptions(capacity_assumptions)
    decision_id = _require_text(decision_id, "decision_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    governance_record = _canonical_governance(governance)

    chain_codes, chain = _chain_authority(
        chain_binding,  # type: ignore[arg-type]
        root_intake_digest=root_anchor,
        correlation_id=correlation_id,
    )
    policy_codes, policy = _risk_budget_policy_authority(policy_binding)  # type: ignore[arg-type]
    integrity = _sorted_unique([*chain_codes, *policy_codes])
    rejected = bool(integrity) or chain is None or policy is None

    admitted = () if chain is None else _admitted_variants(chain)
    subject_digest = "" if chain is None else _digest_of(_subject_payload(chain, admitted, paper_sleeve_id))
    kill_record_digest = "" if chain is None else _digest_of(_kill_criteria_record_payload(chain))
    committed = {
        "predecessor_digest": chain_binding.expected_digest,  # type: ignore[union-attr]
        "admission_subject_digest": subject_digest,
        "kill_criteria_record_digest": kill_record_digest,
        "risk_budget_policy_digest": policy_binding.expected_digest,  # type: ignore[union-attr]
        "capacity_assumption_set_digest": _digest_of(_capacity_set_payload(assumptions)),
        "rule_set_digest": EDGE_PAPER_ADMISSION_RULE_SET_DIGEST,
    }

    if rejected:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        buckets: tuple[list[str], list[str], list[str]] = ([], [], [])
        fail, needs_external, needs_governance = buckets
        if chain.ef6.advances is not True:  # type: ignore[union-attr]
            _propagate(chain.ef6.gate_verdict, buckets)  # type: ignore[union-attr]
        if policy.sleeve_id != paper_sleeve_id:  # type: ignore[union-attr]
            fail.append(_reason("risk_budget_policy_sleeve_mismatch"))
        capacity_fail, capacity_needs = _capacity_reasons(assumptions, chain.ef5.pinned_instrument_universe)  # type: ignore[union-attr]
        fail.extend(capacity_fail)
        needs_governance.extend(capacity_needs)
        needs_governance.extend(_governance_reasons(governance_record, committed))
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    ready = status is EdgeEvidenceStatus.READY
    advances = ready and verdict is EdgeGateVerdict.PASS
    ef6 = None if chain is None else chain.ef6
    ef5 = None if chain is None else chain.ef5
    admission = None if chain is None else chain.admission
    if advances:
        stage = _SEALED_KILL_CRITERIA_STAGE
    elif chain is not None:
        stage = _UPSTREAM_KILL_CRITERIA_STAGE
    else:
        stage = ""
    seed = EdgePaperAdmissionDecision(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=advances,
        decision_id=decision_id,
        correlation_id=correlation_id,
        root_intake_digest=root_anchor,
        predecessor_binding=chain_binding,  # type: ignore[arg-type]
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        predecessor_digest=committed["predecessor_digest"],
        predecessor_gate_verdict="" if ef6 is None else ef6.gate_verdict.value,
        preregistration_digest="" if ef6 is None else ef6.predecessor_digest,
        strategy_spec_admission_digest="" if ef5 is None else ef5.predecessor_digest,
        source_manifest_digest="" if ef5 is None else ef5.source_manifest_digest,
        candidate_strategy_id="" if ef5 is None else ef5.candidate_strategy_id,
        edge_family="" if ef5 is None else ef5.edge_family,
        strategy_id="" if ef5 is None else ef5.strategy_id,
        strategy_version="" if ef5 is None else ef5.strategy_version,
        strategy_spec_digest="" if ef5 is None else ef5.strategy_spec_digest,
        executable_binding_digest="" if ef5 is None else ef5.executable_binding_digest,
        profile_semantics_digest="" if ef5 is None else ef5.profile_semantics_digest,
        market_type="" if ef6 is None else ef6.market_type,
        pinned_instrument_universe=() if ef5 is None else ef5.pinned_instrument_universe,
        variant_ledger_digest="" if ef5 is None else ef5.variant_ledger_digest,
        multiple_testing_count=0 if ef5 is None else ef5.multiple_testing_count,
        registered_variant_count=0 if ef5 is None else len(ef5.registered_variants),
        evaluation_frame_digest="" if ef6 is None else ef6.evaluation_frame_digest,
        oos_governance_digest="" if ef6 is None else ef6.governance_digest,
        paper_sleeve_id=paper_sleeve_id,
        admitted_variants=admitted,
        admitted_variant_count=len(admitted),
        admission_subject_digest=subject_digest,
        root_kill_criteria_digest="" if admission is None else admission.root_kill_criteria_digest,
        final_kill_criteria=() if admission is None else admission.admitted_kill_criteria,
        final_kill_criteria_digest="" if admission is None else admission.admitted_kill_criteria_digest,
        added_kill_criterion_ids=() if admission is None else admission.added_kill_criterion_ids,
        kill_criteria_combination_policy="" if admission is None else admission.kill_criteria_combination_policy,
        kill_criteria_policy_digest="" if chain is None else chain.kill_criteria_policy_digest,
        kill_criteria_record_digest=kill_record_digest,
        kill_criteria_lifecycle_stage=stage,
        sealed_kill_criteria_digest=kill_record_digest if advances else "",
        risk_budget_policy_binding=policy_binding,  # type: ignore[arg-type]
        risk_budget_policy_id="" if policy is None else policy.policy_id,
        risk_budget_policy_digest=committed["risk_budget_policy_digest"],
        portfolio_risk_envelope_status=EDGE_PORTFOLIO_RISK_ENVELOPE_PENDING,
        capacity_assumptions=assumptions,
        capacity_assumption_set_digest=committed["capacity_assumption_set_digest"],
        capacity_evidence_status=EDGE_CAPACITY_EVIDENCE_STATUS,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=EDGE_PAPER_ADMISSION_RULE_SET_DIGEST,
        governance=governance_record,
        governance_digest="" if governance_record is None else _digest_of(_to_payload(governance_record)),
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        preregistration_sealed=ready,
        performance_data_consumed=ready and ef6 is not None and ef6.performance_data_consumed is True,
        oos_evidence_consumed=ready and ef6 is not None and ef6.oos_evidence_consumed is True,
        candidate_admitted_to_paper=advances,
        kill_criteria_sealed=advances,
        paper_admission_decision_digest="",
    )
    return replace(seed, paper_admission_decision_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_paper_admission_decision(
    predecessor: EdgeWalkForwardOosEvidence,
    *,
    expected_predecessor_digest: str,
    expected_root_intake_digest: str,
    risk_budget_policy: PaperSleeveRiskBudgetPolicy,
    expected_risk_budget_policy_digest: str,
    paper_sleeve_id: str,
    capacity_assumptions: Sequence[EdgeCapacityAssumption],
    decision_id: str,
    correlation_id: str,
    governance: EdgePaperAdmissionGovernance | None = None,
) -> EdgePaperAdmissionDecision:
    """Build a deterministic EF-7 paper-admission decision over an EF-6 result.

    There is deliberately no input for kill criteria, a variant choice, a ranking or any flag: the sealed criteria and
    the admitted set are derived from authenticated authority only. Malformed caller input or a non-serializable
    upstream object raises ``EdgePaperAdmissionDecisionError``. A broken, spliced, rejected or inconsistent chain, or a
    risk-budget policy that fails re-proof, yields ``REJECTED``/``NOT_EVALUATED``. Otherwise the decision is ``READY``
    with ``FAIL``, ``NEEDS_EXTERNAL_FACTS``, ``NEEDS_GOVERNANCE_APPROVAL`` or ``PASS``.
    """

    if type(predecessor) is not EdgeWalkForwardOosEvidence:
        raise _fail("predecessor_malformed")
    try:
        predecessor_payload = edge_walk_forward_oos_evidence_to_dict(predecessor)
    except Exception as exc:  # noqa: BLE001 - a hollow predecessor object is a construction error, never a receipt
        raise _fail("predecessor_not_serializable") from exc
    chain_binding = build_edge_authority_binding(
        snapshot_payload=predecessor_payload,
        expected_digest=expected_predecessor_digest,
        shape=edge_walk_forward_oos_evidence_payload_is_well_formed,
        error=EdgePaperAdmissionDecisionError,
        code=_reason("predecessor"),
    )
    if type(risk_budget_policy) is not PaperSleeveRiskBudgetPolicy:
        raise _fail("risk_budget_policy_malformed")
    try:
        policy_payload = paper_sleeve_risk_budget_policy_to_dict(risk_budget_policy)
    except Exception as exc:  # noqa: BLE001 - a hollow policy object is a construction error, never a receipt
        raise _fail("risk_budget_policy_not_serializable") from exc
    policy_binding = build_edge_authority_binding(
        snapshot_payload=policy_payload,
        expected_digest=expected_risk_budget_policy_digest,
        shape=_risk_budget_policy_snapshot_is_well_formed,
        error=EdgePaperAdmissionDecisionError,
        code=_reason("risk_budget_policy"),
    )
    return _assemble_decision(
        predecessor_binding=chain_binding,
        root_intake_digest=expected_root_intake_digest,
        risk_budget_policy_binding=policy_binding,
        paper_sleeve_id=paper_sleeve_id,
        capacity_assumptions=capacity_assumptions,
        decision_id=decision_id,
        correlation_id=correlation_id,
        governance=governance,
    )


def edge_paper_admission_decision_to_dict(decision: EdgePaperAdmissionDecision) -> dict[str, object]:
    """Canonical JSON-ready mapping for an EF-7 decision, including its self-digest."""

    return _to_payload(decision)


def edge_paper_admission_decision_digest(decision: EdgePaperAdmissionDecision) -> str:
    """Recompute the canonical EF-7 digest, excluding only the self-digest field."""

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


def _as_kill_criteria(value: object) -> tuple[EdgeKillCriterion, ...]:
    """Canonical criteria only (sorted, unique, exact keys); an empty list is the empty tuple of a REJECTED decision."""

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


def _as_records(cls: type) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, {}) for entry in value)

    return convert


def _as_governance(value: object) -> object:
    return None if value is None else _parse_exact(EdgePaperAdmissionGovernance, value, {})


def _parse_predecessor_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_walk_forward_oos_evidence_payload_is_well_formed,
        error=EdgePaperAdmissionDecisionError,
        code=_reason("predecessor"),
        optional=False,
    )


def _parse_risk_budget_policy_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=_risk_budget_policy_snapshot_is_well_formed,
        error=EdgePaperAdmissionDecisionError,
        code=_reason("risk_budget_policy"),
        optional=False,
    )


_DECISION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "predecessor_binding": _parse_predecessor_binding,
    "pinned_instrument_universe": _as_str_tuple,
    "multiple_testing_count": _as_int,
    "registered_variant_count": _as_int,
    "admitted_variants": _as_records(EdgeAdmittedVariant),
    "admitted_variant_count": _as_int,
    "final_kill_criteria": _as_kill_criteria,
    "added_kill_criterion_ids": _as_str_tuple,
    "risk_budget_policy_binding": _parse_risk_budget_policy_binding,
    "capacity_assumptions": _as_records(EdgeCapacityAssumption),
    "governance": _as_governance,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_COMPUTED_FLAGS, _as_bool),
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_paper_admission_decision_from_payload(payload: object) -> EdgePaperAdmissionDecision:
    """Strictly reconstruct an EF-7 decision from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_paper_admission_decision`` on the result.
    """

    return _parse_exact(EdgePaperAdmissionDecision, payload, _DECISION_CONVERTERS)  # type: ignore[return-value]


def edge_paper_admission_decision_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-7 snapshot consumed by a later gate."""

    try:
        edge_paper_admission_decision_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_decision(decision: object) -> EdgePaperAdmissionDecision:
    return _assemble_decision(
        predecessor_binding=decision.predecessor_binding,  # type: ignore[attr-defined]
        root_intake_digest=decision.root_intake_digest,  # type: ignore[attr-defined]
        risk_budget_policy_binding=decision.risk_budget_policy_binding,  # type: ignore[attr-defined]
        paper_sleeve_id=decision.paper_sleeve_id,  # type: ignore[attr-defined]
        capacity_assumptions=decision.capacity_assumptions,  # type: ignore[attr-defined]
        decision_id=decision.decision_id,  # type: ignore[attr-defined]
        correlation_id=decision.correlation_id,  # type: ignore[attr-defined]
        governance=decision.governance,  # type: ignore[attr-defined]
    )


def verify_edge_paper_admission_decision(decision: object) -> EdgeEvidenceVerification:
    """Re-prove an EF-7 decision by strict parse and reassembly from its carried bindings, anchors and declarations.

    Every derived field — chain identities, admitted set, sealed kill criteria and digests, linkage, capacity digest,
    flags and verdict — must equal the reassembled decision. Total: never raises.
    """

    return verify_edge_artifact_total(
        decision,
        cls=EdgePaperAdmissionDecision,
        to_payload=_to_payload,
        parse_payload=edge_paper_admission_decision_from_payload,
        reassemble=_reassemble_decision,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EDGE_CAPACITY_EVIDENCE_STATUS",
    "EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS",
    "EDGE_PAPER_ADMISSION_RULE_SET_DIGEST",
    "EDGE_PORTFOLIO_RISK_ENVELOPE_PENDING",
    "EdgeAdmittedVariant",
    "EdgeCapacityAssumption",
    "EdgePaperAdmissionDecision",
    "EdgePaperAdmissionDecisionError",
    "EdgePaperAdmissionGovernance",
    "build_edge_paper_admission_decision",
    "edge_paper_admission_decision_digest",
    "edge_paper_admission_decision_from_payload",
    "edge_paper_admission_decision_payload_is_well_formed",
    "edge_paper_admission_decision_to_dict",
    "edge_paper_admission_rule_set",
    "verify_edge_paper_admission_decision",
]
