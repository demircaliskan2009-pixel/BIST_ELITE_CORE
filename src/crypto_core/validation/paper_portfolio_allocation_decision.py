"""RG-7 paper portfolio allocation decision (RG7_PAPER_PORTFOLIO_ALLOCATION_DECISION_V1).

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 1, item 6 (RG-7), under the
controller structural authority ``RG7_ALLOCATION_AUTHORITY_AND_MATH_POLICY_V1``.

The allocator turns one exact, fully re-proven proposal into digest-bound PAPER allocation EVIDENCE. READY means the
paper allocation evidence is accepted. It never means capital allocated, an order or execution permitted, or live,
shadow or operational readiness, and nothing here is an order, a fill, a position or an account value.

Current lifecycle authority (``RG7_HUMAN_GOVERNANCE_PAPER_CURRENT_HEAD_ATTESTATION_V1``). Accepted EF-8 receipts stay
HISTORICAL ONLY and EF-8 is not changed. A ``PaperLifecycleHeadAuthority`` records one bounded, paper-only claim: for
this exact RG-7 evaluation coordinate, HUMAN_GOVERNANCE attests that this exact, independently re-proven EF-8 receipt is
the current lifecycle head of this exact allocation subject. Its builder re-proves the receipt through
``verify_edge_kill_quarantine_decision`` and requires an advancing receipt, the same sleeve, the declared head digest,
lifecycle subject and current-cycle EF-7 admission, and ``effective_at_ns <= evaluation_end_ns``. The approval supplies
the one fact no receipt can prove, that no later successor exists as of this evaluation coordinate. Nothing infers it
from the lifecycle sequence, an effective time, the newest object, a state, a digest or caller ordering. Only an exact
``HUMAN_GOVERNANCE`` approval establishes the paper current head; ``TEST_ONLY_SYNTHETIC`` never does, and a missing,
stale or mismatching approval leaves it ``NEEDS_GOVERNANCE_APPROVAL``. ``global_current_lifecycle_head_proven`` and
``live_current_lifecycle_head_proven`` are structurally False.

Proposal (``RG7_ONE_ALLOCATION_SUBJECT_PER_SLEEVE_V1``): every envelope-declared sleeve has exactly one allocation
subject, made of one EF-7 admission, one lifecycle-head authority over its exact EF-8 chain and one intra-sleeve
risk-budget source. A duplicate, missing or extra sleeve is refused. Every element is re-proven:

* RG-2: the envelope, through its total verifier, its rule set and its pending regime marker. It owns every cap;
* EF-7: the ``EdgePaperAdmissionDecision``, through ``verify_edge_paper_admission_decision``. It must be READY, PASS,
  advancing and admitted to paper, for the same sleeve, equal to the governed head's current-cycle admission and bound
  to the exact risk-budget policy of the sleeve's proposal;
* risk budget: the ``PaperSleeveRiskBudgetDecision``, rebuilt by ``evaluate_paper_sleeve_risk_budget`` from the exact
  ``PaperSleeveState`` and ``PaperSleeveRiskBudgetPolicy`` with the decision's own correlation id and metadata, and
  canonically equal to the supplied decision. A sleeve's pre-kill proposal is exactly its reconstructed
  ``total_reserved_budget`` (``REPROVEN_INTRA_SLEEVE_TOTAL_RESERVED_BUDGET_PASSTHROUGH_V1``): no performance, Sharpe,
  Kelly, volatility, risk-parity or tier sizing and no discretionary adjustment. RG-6 has no numeric effect, because
  RG-2 defines no tier-to-budget multiplier;
* RG-5: the ``PaperSleeveCorrelationEvidence``, rebuilt from its exact inputs on the same envelope and evaluation end,
  with the complete canonical pair matrix.

Order of operations (the P1 invariant):

1. provenance, then governance. A malformed input or any provenance contradiction raises
   ``PaperPortfolioAllocationError``. Missing governance of the envelope, the correlation evidence or any sleeve's
   current head yields ``NEEDS_GOVERNANCE_APPROVAL``, and no exposure is evaluated. An unproven current head never
   means ACTIVE;
2. kill/quarantine override FIRST: a sleeve whose governed paper head is DISABLED or QUARANTINE requests zero for
   itself and every record, and no numeric field of it enters any later arithmetic: not the total, a sleeve or market
   sum, the positive-sleeve count or a correlation pair;
3. exposure: every positive post-kill record's ``instrument_id`` must equal one envelope ``market_symbol`` and lie in the
   EF-7 ``pinned_instrument_universe``; no mapping table exists. A market's exposure is the exact sum of the positive
   post-kill reservations on it across sleeves;
4. correlation (``RG7_CORRELATION_ACTIVE_PAIR_CAP_RULE_V1``): a pair is exposed only when both of its sleeves have a
   positive post-kill budget, and its RG-5 effective correlation must then be at most the envelope's pairwise cap. A
   ``WORST_CASE_UNKNOWN`` pair carries exactly one, so two simultaneously positive sleeves without an observed
   correlation always breach, while a pair with a zero sleeve creates no combined exposure. No covariance, square-root
   portfolio risk, correlation-weighted scaling, diversification credit, averaging or matrix inversion;
5. envelope check, every limit inclusive: the total, each sleeve, each market, the positive-sleeve count and every
   exposed pair. ANY breach makes the whole proposal ``ALLOCATION_REJECTED``, with exact sorted breach reasons, every
   final allocation zero and the rejected proposal kept as evidence. There is no partial fit, clipping, truncation or
   scaling;
6. otherwise READY, and every final allocation equals its post-kill reservation exactly.

Numeric discipline: exact ``Fraction`` arithmetic over the accepted plain decimal texts, and every amount RG-7 computes
is rendered as minimal exact plain decimal text. No float, no ``decimal``, and no IO, clock, randomness, network or
environment access. Both verifiers rebuild from their exact inputs and are total.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from itertools import combinations
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
)
from crypto_core.validation.edge_kill_quarantine_decision import (
    EdgeKillQuarantineDecision,
    EdgeLifecycleState,
    verify_edge_kill_quarantine_decision,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EdgePaperAdmissionDecision,
    verify_edge_paper_admission_decision,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
    PaperPortfolioRiskEnvelope,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PaperSleeveCorrelationEvidence,
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationPair,
    PaperSleeveCorrelationPairStatus,
    PaperSleeveCorrelationStatus,
    build_paper_sleeve_correlation_evidence,
    paper_sleeve_correlation_evidence_to_dict,
)
from crypto_core.validation.paper_sleeve_intent_ledger import PaperSleeveState
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetDecision,
    PaperSleeveRiskBudgetPolicy,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_to_dict,
)

_T = TypeVar("_T")
_PREFIX = "paper_portfolio_allocation_decision"
_AUTHORITY_PREFIX = "paper_lifecycle_head_authority"
_AUTHORITY_SCHEMA = "paper-lifecycle-head-authority.v1"
_DECISION_SCHEMA = "paper-portfolio-allocation-decision.v1"
_AUTHORITY_DIGEST_FIELD = "authority_digest"
_DECISION_DIGEST_FIELD = "allocation_decision_digest"
_IDENTIFIER_PUNCTUATION = frozenset("-_./:")
_ZERO = "0"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_portfolio_allocation_decision_rules.v1",
    "contract_id": "RG7_PAPER_PORTFOLIO_ALLOCATION_DECISION_V1",
    "structural_authority_id": "RG7_ALLOCATION_AUTHORITY_AND_MATH_POLICY_V1",
    "scope_rule_id": "paper_allocation_evidence_only_never_capital_order_execution_live_shadow_or_readiness.v1",
    "current_head_authority_id": "RG7_HUMAN_GOVERNANCE_PAPER_CURRENT_HEAD_ATTESTATION_V1",
    "current_head_rule_id": "human_governance_attests_one_reproven_advancing_ef8_receipt_as_one_subject_paper_head.v1",
    "current_head_coordinate_rule_id": "one_utc_day_aligned_evaluation_end_at_or_after_the_head_effective_coordinate.v1",
    "current_head_inference_rule_id": "never_inferred_from_sequence_effective_time_newest_object_state_digest_or_order.v1",
    "current_head_scope_rule_id": "paper_snapshot_claim_only_never_global_or_live_currentness_ef8_stays_historical.v1",
    "authority_approval_rule_id": "approval_commits_authority_id_version_authority_policy_digest_and_rule_set_digest.v1",
    "authority_verdict_rule_id": "only_an_exact_human_governance_approval_establishes_test_only_synthetic_never_does.v1",
    "subject_cardinality_rule_id": "RG7_ONE_ALLOCATION_SUBJECT_PER_SLEEVE_V1",
    "subject_rule_id": "one_ef7_admission_head_authority_and_risk_budget_source_per_declared_sleeve_none_missing.v1",
    "admission_rule_id": "ef7_public_reproof_ready_pass_advancing_admitted_same_sleeve_cycle_and_budget_policy.v1",
    "proposal_rule_id": "REPROVEN_INTRA_SLEEVE_TOTAL_RESERVED_BUDGET_PASSTHROUGH_V1",
    "proposal_source_rule_id": "risk_budget_decision_rebuilt_from_exact_state_policy_correlation_id_and_metadata.v1",
    "rg6_numeric_effect": "NONE",
    "rg6_rule_id": "rg2_defines_no_tier_to_budget_multiplier_so_no_ladder_tier_sizes_an_allocation.v1",
    "correlation_evidence_rule_id": "rg5_rebuilt_on_the_same_envelope_and_evaluation_end_complete_canonical_pairs.v1",
    "order_of_operations": (
        "provenance_and_governance",
        "kill_quarantine_override",
        "instrument_binding_and_market_exposure",
        "correlation_pair_exposure",
        "envelope_check",
        "final_allocation",
    ),
    "kill_override_rule_id": "disabled_or_quarantine_zeroes_the_sleeve_and_every_record_before_any_arithmetic.v1",
    "unproven_head_rule_id": "an_unproven_current_head_is_never_active_and_the_decision_needs_governance.v1",
    "instrument_binding_rule_id": "positive_post_kill_record_instrument_is_an_envelope_market_in_the_ef7_universe.v1",
    "market_exposure_rule_id": "exact_sum_of_positive_post_kill_record_reservations_per_market_across_sleeves.v1",
    "correlation_rule_id": "RG7_CORRELATION_ACTIVE_PAIR_CAP_RULE_V1",
    "correlation_exposure_rule_id": "pair_exposed_iff_both_sleeves_positive_post_kill_effective_at_most_cap.v1",
    "unknown_correlation_rule_id": "worst_case_unknown_effective_one_breaches_every_legal_cap_never_credited.v1",
    "envelope_check_rule_id": "inclusive_total_sleeve_market_count_and_exposed_pair_caps_any_breach_rejects_all.v1",
    "no_scaling_rule_id": "no_partial_fit_clipping_truncation_or_scaling.v1",
    "final_allocation_rule_id": "ready_final_is_the_exact_post_kill_reservation_otherwise_every_final_is_zero.v1",
    "status_rule_id": "provenance_raises_then_needs_governance_approval_then_allocation_rejected_then_ready.v1",
    "excluded_method_ids": (
        "covariance",
        "square_root_portfolio_risk",
        "correlation_weighted_scaling",
        "diversification_credit",
        "averaging",
        "correlation_matrix_inversion",
        "risk_parity",
        "kelly",
        "sharpe_sizing",
        "volatility_scaling",
        "performance_weight_sizing",
        "tier_multiplier",
        "discretionary_adjustment",
    ),
    "regime_rule_id": "regime_conditioned_caps_pending_until_an_accepted_rf_chain.v1",
    "numeric_rule_id": "exact_fraction_arithmetic_minimal_plain_decimal_text_no_float_no_decimal.v1",
    "unknown_effective_correlation": "1.000000000000000000",
    "utc_day_ns": 86_400_000_000_000,
    "decimal_scale": 18,
    "decimal_text_max_length": 60,
    "amount_text_max_length": 4096,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_identifier_length": 128,
}
PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_UNKNOWN_EFFECTIVE = str(_RULE_SET_V1["unknown_effective_correlation"])
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_text_max_length"]  # type: ignore[assignment]
_MAX_AMOUNT_TEXT: int = _RULE_SET_V1["amount_text_max_length"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_IDENTIFIER: int = _RULE_SET_V1["max_identifier_length"]  # type: ignore[assignment]


def paper_portfolio_allocation_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class PaperPortfolioAllocationError(EdgeArtifactError):
    """A malformed input or any provenance or binding defect: an invalid authority or decision is never represented."""


class PaperLifecycleHeadAuthorityApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` exists for tests only: it is recorded and never establishes a paper current head."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class PaperPortfolioAllocationStatus(str, Enum):
    """READY is accepted paper allocation evidence; ALLOCATION_REJECTED allocates nothing and keeps the proposal."""

    READY = "READY"
    ALLOCATION_REJECTED = "ALLOCATION_REJECTED"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class PaperGovernedLifecycleState(str, Enum):
    """A sleeve's governed paper current-head state at the evaluation end; UNPROVEN without an exact human attestation."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    QUARANTINE = "QUARANTINE"
    UNPROVEN = "UNPROVEN"


class PaperAllocationMarketBinding(str, Enum):
    """How one risk-budget record's post-kill reservation binds to an envelope market."""

    NOT_EVALUATED = "NOT_EVALUATED"
    NOT_EXPOSED = "NOT_EXPOSED"
    BOUND = "BOUND"
    UNBOUND = "UNBOUND"


class PaperAllocationPairExposure(str, Enum):
    """NOT_EXPOSED unless both sleeves of the pair carry a positive post-kill budget."""

    NOT_EXPOSED = "NOT_EXPOSED"
    WITHIN_CAP = "WITHIN_CAP"
    BREACH = "BREACH"


@dataclass(frozen=True)
class PaperLifecycleHeadAuthorityApproval:
    """Governance approval of one exact authority; every commitment must equal the assembled value to establish it."""

    approval_reference: str
    approval_digest: str
    approval_kind: PaperLifecycleHeadAuthorityApprovalKind
    approved_authority_id: str
    approved_authority_version: str
    approved_authority_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class PaperLifecycleHeadAuthorityInputs:
    """Everything one paper current-head attestation consumes; consumers re-prove it by rebuilding from these.

    ``lifecycle_head_digest``, ``lifecycle_subject_digest`` and ``current_cycle_admission_decision_digest`` are the
    caller's declared anchors: each must equal the re-proven receipt, and a digest alone is never authority.
    """

    authority_id: str
    authority_version: str
    sleeve_id: str
    lifecycle_head_digest: str
    lifecycle_subject_digest: str
    current_cycle_admission_decision_digest: str
    evaluation_end_ns: int
    lifecycle_head: EdgeKillQuarantineDecision
    approval: PaperLifecycleHeadAuthorityApproval | None


PAPER_LIFECYCLE_HEAD_AUTHORITY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("global_current_lifecycle_head_proven", False),
    ("live_current_lifecycle_head_proven", False),
    ("current_head_inferred_from_history", False),
    ("candidate_admitted_to_paper", False),
    ("portfolio_allocation_approved", False),
    ("capital_allocated", False),
    ("execution_authorized", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("real_orders_enabled", False),
    ("real_capital_reserved", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
)


@dataclass(frozen=True)
class PaperLifecycleHeadAuthority:
    """The governed, digest-bound paper current-head attestation of one allocation subject at one evaluation end.

    ``paper_current_head_attested`` is True exactly when an exact ``HUMAN_GOVERNANCE`` approval commits to this
    authority. It is a paper snapshot claim for this RG-7 evaluation only, never a global or live lifecycle head.
    """

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    paper_current_head_attested: bool
    authority_id: str
    authority_version: str
    sleeve_id: str
    evaluation_end_ns: int
    lifecycle_head_digest: str
    lifecycle_subject_digest: str
    current_cycle_admission_decision_digest: str
    resulting_lifecycle_state: EdgeLifecycleState
    lifecycle_head_effective_at_ns: int
    rule_set_id: str
    rule_set_digest: str
    authority_policy_digest: str
    approval: PaperLifecycleHeadAuthorityApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    authority_digest: str
    paper_only: bool = True
    global_current_lifecycle_head_proven: bool = False
    live_current_lifecycle_head_proven: bool = False
    current_head_inferred_from_history: bool = False
    candidate_admitted_to_paper: bool = False
    portfolio_allocation_approved: bool = False
    capital_allocated: bool = False
    execution_authorized: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    real_orders_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False


@dataclass(frozen=True)
class PaperPortfolioAllocationSleeveInputs:
    """One envelope-declared sleeve's single allocation subject (``RG7_ONE_ALLOCATION_SUBJECT_PER_SLEEVE_V1``)."""

    sleeve_id: str
    paper_admission: EdgePaperAdmissionDecision
    lifecycle_head_authority_inputs: PaperLifecycleHeadAuthorityInputs
    lifecycle_head_authority: PaperLifecycleHeadAuthority
    risk_budget_state: PaperSleeveState
    risk_budget_policy: PaperSleeveRiskBudgetPolicy
    risk_budget_decision: PaperSleeveRiskBudgetDecision


@dataclass(frozen=True)
class PaperPortfolioAllocationInputs:
    """Everything RG-7 consumes; consumers re-prove a decision by rebuilding it from exactly these."""

    allocation_id: str
    correlation_id: str
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    evaluation_end_ns: int
    sleeves: tuple[PaperPortfolioAllocationSleeveInputs, ...]
    correlation_inputs: PaperSleeveCorrelationInputs
    correlation_evidence: PaperSleeveCorrelationEvidence


@dataclass(frozen=True)
class PaperPortfolioAllocationRecord:
    """One risk-budget record: its pre-kill reservation, its post-kill request and its final paper allocation."""

    sequence: int
    record_decision_digest: str
    instrument_id: str
    risk_budget_record_status: str
    pre_kill_requested_budget: str
    post_kill_requested_budget: str
    final_allocated_budget: str
    market_binding: PaperAllocationMarketBinding
    binding_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PaperPortfolioAllocationSleeveRecord:
    """One sleeve's re-proven bindings, governed state, consumed cap and its pre-kill, post-kill and final budgets."""

    sleeve_id: str
    paper_admission_decision_digest: str
    lifecycle_subject_digest: str
    lifecycle_head_digest: str
    lifecycle_head_authority_digest: str
    current_head_attested: bool
    governed_lifecycle_state: PaperGovernedLifecycleState
    kill_override_applied: bool
    risk_budget_policy_id: str
    risk_budget_policy_digest: str
    risk_budget_state_digest: str
    risk_budget_decision_digest: str
    sleeve_cap: str
    pre_kill_requested_budget: str
    post_kill_requested_budget: str
    final_allocated_budget: str
    records: tuple[PaperPortfolioAllocationRecord, ...]


@dataclass(frozen=True)
class PaperPortfolioMarketExposure:
    """One envelope market: its consumed cap and the exact positive post-kill exposure bound to it."""

    market_symbol: str
    market_cap: str
    post_kill_requested_budget: str
    within_cap: bool


@dataclass(frozen=True)
class PaperPortfolioCorrelationPairCheck:
    """One canonical RG-5 pair: its effective correlation and whether two positive sleeves expose it."""

    sleeve_a_id: str
    sleeve_b_id: str
    pair_status: str
    effective_correlation: str
    exposure: PaperAllocationPairExposure


PAPER_PORTFOLIO_ALLOCATION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("capital_allocated", False),
    ("real_capital_reserved", False),
    ("portfolio_allocation_approved", False),
    ("execution_authorized", False),
    ("order_permitted", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("portfolio_stop_evaluated", False),
    ("promotion_demotion_decided", False),
    ("diversification_credit_granted", False),
    ("covariance_used", False),
    ("tier_multiplier_applied", False),
    ("partial_fit_applied", False),
    ("silent_scaling_applied", False),
    ("global_current_lifecycle_head_proven", False),
    ("live_current_lifecycle_head_proven", False),
    ("regime_evidence_available", False),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("prdv4_stage4_complete", False),
)


@dataclass(frozen=True)
class PaperPortfolioAllocationDecision:
    """Immutable, digest-bound RG-7 paper allocation evidence. Paper only: never capital, an order or readiness."""

    schema_version: str
    status: PaperPortfolioAllocationStatus
    ready: bool
    paper_allocation_evidence_accepted: bool
    allocation_id: str
    correlation_id: str
    evaluation_end_ns: int
    envelope_id: str
    envelope_version: str
    envelope_digest: str
    envelope_policy_digest: str
    envelope_advances: bool
    correlation_evidence_digest: str
    correlation_evidence_status: str
    total_paper_risk_budget: str
    max_sleeve_count: int
    max_pairwise_correlation: str
    declared_sleeve_ids: tuple[str, ...]
    sleeves: tuple[PaperPortfolioAllocationSleeveRecord, ...]
    exposure_evaluated: bool
    market_exposures: tuple[PaperPortfolioMarketExposure, ...]
    correlation_pair_checks: tuple[PaperPortfolioCorrelationPairCheck, ...]
    total_post_kill_requested_budget: str
    total_final_allocated_budget: str
    positive_exposure_sleeve_count: int
    governance_reason_codes: tuple[str, ...]
    breach_reason_codes: tuple[str, ...]
    regime_conditioned_caps_status: str
    regime_evidence_status: str
    rule_set_id: str
    rule_set_digest: str
    allocation_decision_digest: str
    paper_only: bool = True
    capital_allocated: bool = False
    real_capital_reserved: bool = False
    portfolio_allocation_approved: bool = False
    execution_authorized: bool = False
    order_permitted: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    portfolio_stop_evaluated: bool = False
    promotion_demotion_decided: bool = False
    diversification_credit_granted: bool = False
    covariance_used: bool = False
    tier_multiplier_applied: bool = False
    partial_fit_applied: bool = False
    silent_scaling_applied: bool = False
    global_current_lifecycle_head_proven: bool = False
    live_current_lifecycle_head_proven: bool = False
    regime_evidence_available: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    prdv4_stage4_complete: bool = False


# The authority policy excludes only its governance: the approval, the verdict derived from it, and the two digests.
_AUTHORITY_GOVERNANCE_FIELDS = frozenset(
    {
        "gate_verdict",
        "advances",
        "paper_current_head_attested",
        "authority_policy_digest",
        "approval",
        "synthetic_test_approval_used",
        "verdict_reason_codes",
        "authority_digest",
    }
)
_RECORD_TYPES = frozenset(
    {
        PaperLifecycleHeadAuthorityApproval,
        PaperPortfolioAllocationRecord,
        PaperPortfolioAllocationSleeveRecord,
        PaperPortfolioMarketExposure,
        PaperPortfolioCorrelationPairCheck,
    }
)
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperLifecycleHeadAuthorityApproval: {"approval_kind": PaperLifecycleHeadAuthorityApprovalKind},
    PaperLifecycleHeadAuthority: {"gate_verdict": EdgeGateVerdict, "resulting_lifecycle_state": EdgeLifecycleState},
    PaperPortfolioAllocationRecord: {"market_binding": PaperAllocationMarketBinding},
    PaperPortfolioAllocationSleeveRecord: {"governed_lifecycle_state": PaperGovernedLifecycleState},
    PaperPortfolioCorrelationPairCheck: {"exposure": PaperAllocationPairExposure},
    PaperPortfolioAllocationDecision: {"status": PaperPortfolioAllocationStatus},
}
_KILLED_STATES = frozenset({PaperGovernedLifecycleState.DISABLED, PaperGovernedLifecycleState.QUARANTINE})


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _authority_reason(code: str) -> str:
    return f"{_AUTHORITY_PREFIX}:{code}"


def _fail(code: str) -> PaperPortfolioAllocationError:
    return PaperPortfolioAllocationError(_reason(code))


def _authority_fail(code: str) -> PaperPortfolioAllocationError:
    return PaperPortfolioAllocationError(_authority_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _require_exact(value: object, cls: type, code: str, fail: Callable[[str], Exception] = _fail) -> None:
    if type(value) is not cls:
        raise fail(f"{code}_malformed")


def _require_text(value: object, name: str, fail: Callable[[str], Exception] = _fail) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise fail(f"{violation}:{name}")
    return value


def _require_identifier(value: object, name: str, fail: Callable[[str], Exception] = _fail) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_IDENTIFIER or not value.isascii():
        raise fail(f"{name}_invalid")
    if not value[0].isalnum() or not all(char.isalnum() or char in _IDENTIFIER_PUNCTUATION for char in value):
        raise fail(f"{name}_invalid")
    return _require_text(value, name, fail)


def _require_hex64(value: object, name: str, fail: Callable[[str], Exception] = _fail) -> str:
    if not edge_is_hex64(value):
        raise fail(f"{name}_invalid")
    return cast(str, value)


def _require_member(value: object, enum_cls: type[Enum], name: str, fail: Callable[[str], Exception] = _fail) -> Enum:
    if type(value) is enum_cls:
        return cast(Enum, value)
    if type(value) is str and value in {member.value for member in enum_cls}:
        return enum_cls(value)
    raise fail(f"{name}_invalid")


def _require_utc_day(value: object, name: str, fail: Callable[[str], Exception] = _fail) -> int:
    """An exact non-negative int64 epoch-nanosecond coordinate on a UTC day boundary; never a bool, never a clock."""

    if type(value) is not int or not 0 <= value <= _MAX_WIRE_INT:
        raise fail(f"{name}_invalid")
    if value % _DAY_NS:
        raise fail(f"{name}_not_utc_day_aligned")
    return value


def _snapshot(values: object, name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{name}_malformed")
    return tuple(cast(Sequence[object], values))


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    """One accepted public builder call; any failure is a provenance defect of this decision."""

    try:
        return builder(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed here
        raise _fail(f"{code}_reconstruction_failed") from exc


# --- exact numbers --------------------------------------------------------------------------------------------------


def _is_plain_amount(value: object) -> bool:
    """Accepted risk-budget amount text: unsigned plain decimal, no exponent, sign or redundant leading zero.

    Only the grammar is read here. Provenance applies it to every sleeve, while the numeric value of an amount is taken
    only during the exposure stage, which sees ACTIVE sleeves alone.
    """

    if type(value) is not str or not value.isascii():
        return False
    whole, point, decimals = value.partition(".")
    if not _digits(whole) or (whole != "0" and whole.startswith("0")):
        return False
    return point == "" or _digits(decimals)


def _amount_value(text: str) -> Fraction:
    """The exact value of an ACTIVE sleeve's accepted amount text: the single point where an amount becomes a number."""

    if len(text) > _MAX_AMOUNT_TEXT:
        raise _fail("risk_budget_amount_text_too_long")
    return Fraction(text)


def _governed_value(value: object, code: str) -> Fraction:
    """The exact value of a canonical scale-18 decimal text, as RG-2 caps and RG-5 effective correlations carry it."""

    if type(value) is not str or len(value) > _MAX_DECIMAL_TEXT or not value.isascii():
        raise _fail(code)
    negative = value.startswith("-")
    whole, point, decimals = (value[1:] if negative else value).partition(".")
    if point != "." or len(decimals) != _SCALE or not _digits(whole) or not _digits(decimals):
        raise _fail(code)
    if whole != "0" and whole.startswith("0"):
        raise _fail(code)
    units = int(whole + decimals)
    if negative and units == 0:
        raise _fail(code)
    return Fraction(-units if negative else units, 10**_SCALE)


def _render_amount(value: Fraction) -> str:
    """Minimal exact plain decimal text of a non-negative terminating amount: no exponent, sign or trailing zero."""

    remainder, twos, fives = value.denominator, 0, 0
    while remainder % 2 == 0:
        remainder, twos = remainder // 2, twos + 1
    while remainder % 5 == 0:
        remainder, fives = remainder // 5, fives + 1
    if value < 0 or remainder != 1:
        raise _fail("amount_not_a_non_negative_terminating_decimal")
    scale = max(twos, fives)
    units = value.numerator * 10**scale // value.denominator
    if scale == 0:
        return str(units)
    digits = str(units).rjust(scale + 1, "0")
    return f"{digits[:-scale]}.{digits[-scale:]}"


# --- canonical wire form --------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in cast(tuple, value)]
    if type(value) is int:
        if 0 <= cast(int, value) <= _MAX_WIRE_INT:
            return value
        raise _fail("payload_integer_out_of_range")
    if value is None or type(value) is str or type(value) is bool:
        return value
    raise _fail("payload_value_not_canonical")


def _payload(artifact: object) -> dict[str, object]:
    """The exact wire form: an enum field holds its exact member, everything else exact records and scalars."""

    enums = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for item in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, item.name)
        enum_cls = enums.get(item.name)
        if enum_cls is None:
            payload[item.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[item.name] = cast(Enum, value).value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


def _verify_rebuilt(
    artifact: object, *, cls: type, rebuild: Callable[[], object], digest_field: str, reason: Callable[[str], str]
) -> EdgeEvidenceVerification:
    """Re-prove an artifact by rebuilding it from its exact inputs and comparing every field. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(artifact) is not cls:
            return EdgeEvidenceVerification(False, (reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _payload(artifact)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, digest_field)
        stage = "evidence_reconstruction_failed"
        expected = _payload(rebuild())
        codes = {reason("self_digest_mismatch")} if carried[digest_field] != recomputed else set()
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(reason(f"field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(not reason_codes, reason_codes, recomputed, canonical)
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (reason(stage),), "", "")


# --- the governed paper current-head authority ----------------------------------------------------------------------


def _authority_approval(approval: object) -> PaperLifecycleHeadAuthorityApproval | None:
    """Exact structure only; whether the commitments match is decided at assembly."""

    if approval is None:
        return None
    _require_exact(approval, PaperLifecycleHeadAuthorityApproval, "governance_approval", _authority_fail)

    def read(name: str) -> object:
        return getattr(approval, name, None)

    return PaperLifecycleHeadAuthorityApproval(
        approval_reference=_require_text(read("approval_reference"), "governance_approval_reference", _authority_fail),
        approval_digest=_require_hex64(read("approval_digest"), "governance_approval_digest", _authority_fail),
        approval_kind=cast(
            PaperLifecycleHeadAuthorityApprovalKind,
            _require_member(
                read("approval_kind"),
                PaperLifecycleHeadAuthorityApprovalKind,
                "governance_approval_kind",
                _authority_fail,
            ),
        ),
        approved_authority_id=_require_text(
            read("approved_authority_id"), "governance_approved_authority_id", _authority_fail
        ),
        approved_authority_version=_require_text(
            read("approved_authority_version"), "governance_approved_authority_version", _authority_fail
        ),
        approved_authority_policy_digest=_require_hex64(
            read("approved_authority_policy_digest"), "governance_approved_authority_policy_digest", _authority_fail
        ),
        approved_rule_set_digest=_require_hex64(
            read("approved_rule_set_digest"), "governance_approved_rule_set_digest", _authority_fail
        ),
    )


def _approval_reasons(approval: PaperLifecycleHeadAuthorityApproval | None, committed: Mapping[str, str]) -> list[str]:
    if approval is None:
        return [_authority_reason("governance_approval_missing")]
    reasons = [
        _authority_reason(f"governance_approval_{name}_mismatch")
        for name, expected in committed.items()
        if getattr(approval, f"approved_{name}") != expected
    ]
    if approval.approval_kind is PaperLifecycleHeadAuthorityApprovalKind.TEST_ONLY_SYNTHETIC:
        reasons.append(_authority_reason("governance_approval_test_only_synthetic"))
    return reasons


def _proven_head(value: object) -> tuple[EdgeKillQuarantineDecision, str]:
    """The EF-8 receipt re-proven through its public verifier; only an advancing receipt is a lifecycle state."""

    _require_exact(value, EdgeKillQuarantineDecision, "lifecycle_head", _authority_fail)
    verification = verify_edge_kill_quarantine_decision(value)
    if not verification.intact:
        raise _authority_fail("lifecycle_head_not_intact")
    head = cast(EdgeKillQuarantineDecision, value)
    if (
        head.status is not EdgeEvidenceStatus.READY
        or head.gate_verdict is not EdgeGateVerdict.PASS
        or head.advances is not True
        or type(head.resulting_lifecycle_state) is not EdgeLifecycleState
    ):
        raise _authority_fail("lifecycle_head_not_advancing")
    return head, verification.recomputed_digest


def _assemble_authority(inputs: object) -> PaperLifecycleHeadAuthority:
    """The single authority assembly path, shared by the builder and by verifier reconstruction."""

    _require_exact(inputs, PaperLifecycleHeadAuthorityInputs, "inputs", _authority_fail)
    source = cast(PaperLifecycleHeadAuthorityInputs, inputs)
    identity = _require_text(source.authority_id, "authority_id", _authority_fail)
    version = _require_text(source.authority_version, "authority_version", _authority_fail)
    sleeve_id = _require_identifier(source.sleeve_id, "sleeve_id", _authority_fail)
    declared_head = _require_hex64(source.lifecycle_head_digest, "lifecycle_head_digest", _authority_fail)
    declared_subject = _require_hex64(source.lifecycle_subject_digest, "lifecycle_subject_digest", _authority_fail)
    declared_admission = _require_hex64(
        source.current_cycle_admission_decision_digest, "current_cycle_admission_decision_digest", _authority_fail
    )
    evaluation_end = _require_utc_day(source.evaluation_end_ns, "evaluation_end_ns", _authority_fail)
    record = _authority_approval(source.approval)
    head, head_digest = _proven_head(source.lifecycle_head)
    if head_digest != declared_head:
        raise _authority_fail("lifecycle_head_digest_mismatch")
    if head.paper_sleeve_id != sleeve_id:
        raise _authority_fail("lifecycle_head_sleeve_mismatch")
    if head.lifecycle_subject_digest != declared_subject:
        raise _authority_fail("lifecycle_head_subject_mismatch")
    if head.cycle_admission_decision_digest != declared_admission:
        raise _authority_fail("lifecycle_head_current_cycle_admission_mismatch")
    if head.effective_at_ns > evaluation_end:
        raise _authority_fail("lifecycle_head_after_the_evaluation_end")

    draft = PaperLifecycleHeadAuthority(
        schema_version=_AUTHORITY_SCHEMA,
        gate_verdict=EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        advances=False,
        paper_current_head_attested=False,
        authority_id=identity,
        authority_version=version,
        sleeve_id=sleeve_id,
        evaluation_end_ns=evaluation_end,
        lifecycle_head_digest=head_digest,
        lifecycle_subject_digest=head.lifecycle_subject_digest,
        current_cycle_admission_decision_digest=head.cycle_admission_decision_digest,
        resulting_lifecycle_state=cast(EdgeLifecycleState, head.resulting_lifecycle_state),
        lifecycle_head_effective_at_ns=head.effective_at_ns,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST,
        authority_policy_digest="",
        approval=record,
        synthetic_test_approval_used=record is not None
        and record.approval_kind is PaperLifecycleHeadAuthorityApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=(),
        authority_digest="",
    )
    policy = {name: value for name, value in _payload(draft).items() if name not in _AUTHORITY_GOVERNANCE_FIELDS}
    policy_digest = edge_sha256_text(edge_canonical_json(policy))
    blockers = _approval_reasons(
        record,
        {
            "authority_id": identity,
            "authority_version": version,
            "authority_policy_digest": policy_digest,
            "rule_set_digest": PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST,
        },
    )
    verdict = resolve_edge_gate_verdict([], [], blockers)
    attested = verdict is EdgeGateVerdict.PASS
    governed = replace(
        draft,
        gate_verdict=verdict,
        advances=attested,
        paper_current_head_attested=attested,
        authority_policy_digest=policy_digest,
        verdict_reason_codes=_sorted_unique(blockers),
    )
    return replace(governed, authority_digest=edge_payload_digest(_payload(governed), _AUTHORITY_DIGEST_FIELD))


def build_paper_lifecycle_head_authority(inputs: PaperLifecycleHeadAuthorityInputs) -> PaperLifecycleHeadAuthority:
    """Attest one exact EF-8 receipt as one sleeve's paper current head at one evaluation end, under governance.

    The receipt is re-proven through ``verify_edge_kill_quarantine_decision`` and must advance, belong to the sleeve,
    equal every declared anchor and take effect at or before the evaluation end. Malformed input or any mismatch raises
    ``PaperPortfolioAllocationError``. Only an exact ``HUMAN_GOVERNANCE`` approval establishes the head; otherwise the
    authority is ``NEEDS_GOVERNANCE_APPROVAL``. EF-8 is not changed and stays historical.
    """

    return _assemble_authority(inputs)


def paper_lifecycle_head_authority_to_dict(authority: PaperLifecycleHeadAuthority) -> dict[str, object]:
    """Canonical JSON-ready mapping of an authority, its self-digest included."""

    return _payload(authority)


def paper_lifecycle_head_authority_digest(authority: PaperLifecycleHeadAuthority) -> str:
    """Recompute the canonical authority digest, excluding only ``authority_digest``."""

    return edge_payload_digest(_payload(authority), _AUTHORITY_DIGEST_FIELD)


def verify_paper_lifecycle_head_authority(
    authority: object, inputs: PaperLifecycleHeadAuthorityInputs
) -> EdgeEvidenceVerification:
    """Re-prove an authority by rebuilding it, receipt re-proof included, from its exact inputs. Total: never raises."""

    return _verify_rebuilt(
        authority,
        cls=PaperLifecycleHeadAuthority,
        rebuild=lambda: _assemble_authority(inputs),
        digest_field=_AUTHORITY_DIGEST_FIELD,
        reason=_authority_reason,
    )


# --- provenance -----------------------------------------------------------------------------------------------------


def _require_envelope(value: object) -> PaperPortfolioRiskEnvelope:
    """The RG-2 envelope, re-pinned through its total verifier, its rule set and its pending regime marker."""

    _require_exact(value, PaperPortfolioRiskEnvelope, "portfolio_risk_envelope")
    if not verify_paper_portfolio_risk_envelope(value).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    envelope = cast(PaperPortfolioRiskEnvelope, value)
    if envelope.rule_set_digest != PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST:
        raise _fail("portfolio_risk_envelope_rule_set_unsupported")
    # V1 applies no regime-conditioned cap: an envelope no longer marking them pending is out of scope.
    if envelope.regime_stratified_correlation_status != EDGE_REGIME_LABEL_BINDING_PENDING:
        raise _fail("regime_conditioned_caps_status_unsupported")
    return envelope


def _prove_correlation(
    inputs: object, evidence: object, *, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int
) -> PaperSleeveCorrelationEvidence:
    """RG-5 rebuilt from its exact inputs on the same envelope and evaluation end, with the complete pair matrix."""

    _require_exact(inputs, PaperSleeveCorrelationInputs, "correlation_inputs")
    _require_exact(evidence, PaperSleeveCorrelationEvidence, "correlation_evidence")
    rebuilt = _rebuild("correlation_evidence", build_paper_sleeve_correlation_evidence, inputs)
    if not _canonically_equal(evidence, rebuilt, paper_sleeve_correlation_evidence_to_dict):
        raise _fail("correlation_evidence_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("correlation_evidence_envelope_mismatch")
    if rebuilt.evaluation_end_ns != evaluation_end:
        raise _fail("correlation_evidence_evaluation_end_mismatch")
    declared = tuple(cap.sleeve_id for cap in envelope.sleeve_caps)
    if rebuilt.declared_sleeve_ids != declared or tuple(
        (pair.sleeve_a_id, pair.sleeve_b_id) for pair in rebuilt.pairs
    ) != tuple(combinations(declared, 2)):
        raise _fail("correlation_pair_matrix_incomplete")
    for pair in rebuilt.pairs:
        unknown = pair.pair_status is PaperSleeveCorrelationPairStatus.WORST_CASE_UNKNOWN
        if unknown and pair.effective_correlation != _UNKNOWN_EFFECTIVE:
            raise _fail("correlation_unknown_pair_not_worst_case")
    return rebuilt


def _proven_admission(value: object) -> tuple[EdgePaperAdmissionDecision, str]:
    """The EF-7 admission re-proven through its public verifier; only a sealed PASS admission is a subject."""

    _require_exact(value, EdgePaperAdmissionDecision, "paper_admission")
    verification = verify_edge_paper_admission_decision(value)
    if not verification.intact:
        raise _fail("paper_admission_not_intact")
    admission = cast(EdgePaperAdmissionDecision, value)
    if (
        admission.status is not EdgeEvidenceStatus.READY
        or admission.gate_verdict is not EdgeGateVerdict.PASS
        or admission.advances is not True
        or admission.candidate_admitted_to_paper is not True
        or admission.kill_criteria_sealed is not True
    ):
        raise _fail("paper_admission_not_admitted")
    return admission, verification.recomputed_digest


def _risk_budget_metadata(decision: PaperSleeveRiskBudgetDecision) -> tuple[str, dict[str, str]]:
    """The decision's own correlation id and metadata, the exact arguments it is rebuilt with."""

    correlation_id = getattr(decision, "correlation_id", None)
    metadata = getattr(decision, "metadata", None)
    if type(correlation_id) is not str or type(metadata) is not tuple:
        raise _fail("risk_budget_decision_malformed")
    entries: dict[str, str] = {}
    for pair in cast(tuple[object, ...], metadata):
        if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise _fail("risk_budget_decision_malformed")
        entries[pair[0]] = pair[1]
    return correlation_id, entries


@dataclass(frozen=True)
class _ProvenSubject:
    sleeve_id: str
    admission_digest: str
    universe: tuple[str, ...]
    authority: PaperLifecycleHeadAuthority
    budget: PaperSleeveRiskBudgetDecision


def _prove_subject(item: object, *, declared: frozenset[str], evaluation_end: int) -> _ProvenSubject:
    """One sleeve's single allocation subject, every element rebuilt or re-proven and bound to the others."""

    _require_exact(item, PaperPortfolioAllocationSleeveInputs, "sleeve")
    sleeve = cast(PaperPortfolioAllocationSleeveInputs, item)
    sleeve_id = _require_identifier(sleeve.sleeve_id, "sleeve_id")
    if sleeve_id not in declared:
        raise _fail("sleeve_not_declared_by_envelope")

    _require_exact(sleeve.lifecycle_head_authority, PaperLifecycleHeadAuthority, "lifecycle_head_authority")
    authority = _rebuild("lifecycle_head_authority", _assemble_authority, sleeve.lifecycle_head_authority_inputs)
    if not _canonically_equal(sleeve.lifecycle_head_authority, authority, paper_lifecycle_head_authority_to_dict):
        raise _fail("lifecycle_head_authority_not_reconstructed")
    if authority.sleeve_id != sleeve_id:
        raise _fail("lifecycle_head_authority_sleeve_mismatch")
    if authority.evaluation_end_ns != evaluation_end:
        raise _fail("lifecycle_head_authority_evaluation_end_mismatch")
    head = sleeve.lifecycle_head_authority_inputs.lifecycle_head

    admission, admission_digest = _proven_admission(sleeve.paper_admission)
    if admission.paper_sleeve_id != sleeve_id:
        raise _fail("paper_admission_sleeve_mismatch")
    if admission_digest != authority.current_cycle_admission_decision_digest:
        raise _fail("paper_admission_not_the_current_cycle_admission")
    if (
        admission.pinned_instrument_universe != head.pinned_instrument_universe
        or admission.root_intake_digest != head.root_intake_digest
        or admission.correlation_id != head.correlation_id
    ):
        raise _fail("paper_admission_lifecycle_subject_mismatch")

    _require_exact(sleeve.risk_budget_state, PaperSleeveState, "risk_budget_state")
    _require_exact(sleeve.risk_budget_policy, PaperSleeveRiskBudgetPolicy, "risk_budget_policy")
    _require_exact(sleeve.risk_budget_decision, PaperSleeveRiskBudgetDecision, "risk_budget_decision")
    correlation_id, metadata = _risk_budget_metadata(sleeve.risk_budget_decision)
    budget = _rebuild(
        "risk_budget_decision",
        evaluate_paper_sleeve_risk_budget,
        sleeve.risk_budget_state,
        sleeve.risk_budget_policy,
        correlation_id=correlation_id,
        metadata=metadata,
    )
    if not _canonically_equal(sleeve.risk_budget_decision, budget, paper_sleeve_risk_budget_decision_to_dict):
        raise _fail("risk_budget_decision_not_reconstructed")
    if budget.sleeve_id != sleeve_id:
        raise _fail("risk_budget_sleeve_mismatch")
    if (
        budget.policy_id != admission.risk_budget_policy_id
        or budget.policy_digest != admission.risk_budget_policy_digest
    ):
        raise _fail("risk_budget_policy_not_the_admission_policy")
    if not _is_plain_amount(budget.total_reserved_budget) or not all(
        _is_plain_amount(record.reserved_budget) and type(record.instrument_id) is str
        for record in budget.record_decisions
    ):
        raise _fail("risk_budget_amount_not_plain_decimal")
    return _ProvenSubject(
        sleeve_id=sleeve_id,
        admission_digest=admission_digest,
        universe=admission.pinned_instrument_universe,
        authority=authority,
        budget=budget,
    )


def _prove_subjects(values: object, *, declared: tuple[str, ...], evaluation_end: int) -> dict[str, _ProvenSubject]:
    """Exactly one allocation subject per declared sleeve (``RG7_ONE_ALLOCATION_SUBJECT_PER_SLEEVE_V1``)."""

    subjects: dict[str, _ProvenSubject] = {}
    for item in _snapshot(values, "sleeves"):
        subject = _prove_subject(item, declared=frozenset(declared), evaluation_end=evaluation_end)
        if subject.sleeve_id in subjects:
            raise _fail("sleeve_subject_duplicate")
        subjects[subject.sleeve_id] = subject
    if set(subjects) != set(declared):
        raise _fail("sleeve_subjects_incomplete")
    return subjects


# --- kill override, exposure and the envelope check -----------------------------------------------------------------


def _governed_state(authority: PaperLifecycleHeadAuthority) -> PaperGovernedLifecycleState:
    """The attested head's state, or UNPROVEN: an unattested head is never ACTIVE."""

    if authority.paper_current_head_attested is not True:
        return PaperGovernedLifecycleState.UNPROVEN
    return PaperGovernedLifecycleState(authority.resulting_lifecycle_state.value)


@dataclass(frozen=True)
class _ExposureRecord:
    sequence: int
    instrument_id: str
    reserved_budget: str


@dataclass(frozen=True)
class _ExposureSleeve:
    """An ACTIVE sleeve after the kill override; a killed or unproven sleeve never becomes one."""

    sleeve_id: str
    reserved_total: str
    sleeve_cap: str
    universe: frozenset[str]
    records: tuple[_ExposureRecord, ...]


@dataclass(frozen=True)
class _Exposure:
    bindings: Mapping[tuple[str, int], tuple[PaperAllocationMarketBinding, tuple[str, ...]]]
    market_exposures: tuple[PaperPortfolioMarketExposure, ...]
    pair_checks: tuple[PaperPortfolioCorrelationPairCheck, ...]
    total: Fraction
    positive: frozenset[str]
    breaches: tuple[str, ...]


def _exposure_sleeve(subject: _ProvenSubject, sleeve_cap: str) -> _ExposureSleeve:
    return _ExposureSleeve(
        sleeve_id=subject.sleeve_id,
        reserved_total=subject.budget.total_reserved_budget,
        sleeve_cap=sleeve_cap,
        universe=frozenset(subject.universe),
        records=tuple(
            _ExposureRecord(record.sequence, record.instrument_id, record.reserved_budget)
            for record in subject.budget.record_decisions
        ),
    )


def _evaluate_exposure(
    active: Sequence[_ExposureSleeve],
    *,
    envelope: PaperPortfolioRiskEnvelope,
    pairs: Sequence[PaperSleeveCorrelationPair],
) -> _Exposure:
    """Stages 3 to 5 over the ACTIVE sleeves alone: instrument binding, market sums, exposed pairs and every cap."""

    market_caps = {cap.market_symbol: cap.max_paper_risk_budget for cap in envelope.market_caps}
    market_sums = dict.fromkeys(market_caps, Fraction(0))
    bindings: dict[tuple[str, int], tuple[PaperAllocationMarketBinding, tuple[str, ...]]] = {}
    breaches: list[str] = []
    positive: set[str] = set()
    total = Fraction(0)
    for sleeve in active:
        sleeve_total = _amount_value(sleeve.reserved_total)
        record_sum = Fraction(0)
        for record in sleeve.records:
            reserved = _amount_value(record.reserved_budget)
            record_sum += reserved
            key = (sleeve.sleeve_id, record.sequence)
            if reserved == 0:
                bindings[key] = (PaperAllocationMarketBinding.NOT_EXPOSED, ())
                continue
            unbound: list[str] = []
            if record.instrument_id not in market_caps:
                unbound.append("record_instrument_not_an_envelope_market")
            if record.instrument_id not in sleeve.universe:
                unbound.append("record_instrument_outside_admitted_universe")
            if unbound:
                bindings[key] = (
                    PaperAllocationMarketBinding.UNBOUND,
                    _sorted_unique([_reason(code) for code in unbound]),
                )
                breaches.extend(_reason(f"{code}:{sleeve.sleeve_id}:{record.sequence}") for code in unbound)
            else:
                bindings[key] = (PaperAllocationMarketBinding.BOUND, ())
                market_sums[record.instrument_id] += reserved
        if record_sum != sleeve_total:
            raise _fail("risk_budget_total_reserved_not_the_record_sum")
        if sleeve_total > _governed_value(sleeve.sleeve_cap, "sleeve_cap_invalid"):
            breaches.append(_reason(f"sleeve_cap_exceeded:{sleeve.sleeve_id}"))
        if sleeve_total > 0:
            positive.add(sleeve.sleeve_id)
        total += sleeve_total
    if total > _governed_value(envelope.total_paper_risk_budget, "total_paper_risk_budget_invalid"):
        breaches.append(_reason("total_paper_risk_budget_exceeded"))
    exposures: list[PaperPortfolioMarketExposure] = []
    for market, cap in market_caps.items():
        within = market_sums[market] <= _governed_value(cap, "market_cap_invalid")
        if not within:
            breaches.append(_reason(f"market_cap_exceeded:{market}"))
        exposures.append(PaperPortfolioMarketExposure(market, cap, _render_amount(market_sums[market]), within))
    if len(positive) > envelope.max_sleeve_count:
        breaches.append(_reason("max_sleeve_count_exceeded"))
    pair_cap = _governed_value(envelope.correlation_cap.max_pairwise_correlation, "correlation_cap_invalid")
    checks: list[PaperPortfolioCorrelationPairCheck] = []
    for pair in pairs:
        exposure = PaperAllocationPairExposure.NOT_EXPOSED
        if pair.sleeve_a_id in positive and pair.sleeve_b_id in positive:
            effective = _governed_value(pair.effective_correlation, "correlation_effective_invalid")
            exposure = (
                PaperAllocationPairExposure.WITHIN_CAP if effective <= pair_cap else PaperAllocationPairExposure.BREACH
            )
            if exposure is PaperAllocationPairExposure.BREACH:
                breaches.append(_reason(f"pairwise_correlation_cap_exceeded:{pair.sleeve_a_id}:{pair.sleeve_b_id}"))
        checks.append(
            PaperPortfolioCorrelationPairCheck(
                sleeve_a_id=pair.sleeve_a_id,
                sleeve_b_id=pair.sleeve_b_id,
                pair_status=pair.pair_status.value,
                effective_correlation=pair.effective_correlation,
                exposure=exposure,
            )
        )
    return _Exposure(
        bindings=bindings,
        market_exposures=tuple(exposures),
        pair_checks=tuple(checks),
        total=total,
        positive=frozenset(positive),
        breaches=_sorted_unique(breaches),
    )


def _sleeve_record(
    subject: _ProvenSubject,
    *,
    sleeve_cap: str,
    state: PaperGovernedLifecycleState,
    exposure: _Exposure | None,
    ready: bool,
) -> PaperPortfolioAllocationSleeveRecord:
    active = state is PaperGovernedLifecycleState.ACTIVE
    budget = subject.budget
    records: list[PaperPortfolioAllocationRecord] = []
    for record in budget.record_decisions:
        post = record.reserved_budget if active else _ZERO
        if exposure is None:
            binding: tuple[PaperAllocationMarketBinding, tuple[str, ...]] = (
                PaperAllocationMarketBinding.NOT_EVALUATED,
                (),
            )
        elif not active:
            binding = (PaperAllocationMarketBinding.NOT_EXPOSED, ())
        else:
            binding = exposure.bindings[(subject.sleeve_id, record.sequence)]
        records.append(
            PaperPortfolioAllocationRecord(
                sequence=record.sequence,
                record_decision_digest=record.record_decision_digest,
                instrument_id=record.instrument_id,
                risk_budget_record_status=record.status.value,
                pre_kill_requested_budget=record.reserved_budget,
                post_kill_requested_budget=post,
                final_allocated_budget=post if ready else _ZERO,
                market_binding=binding[0],
                binding_reason_codes=binding[1],
            )
        )
    post_total = budget.total_reserved_budget if active else _ZERO
    authority = subject.authority
    return PaperPortfolioAllocationSleeveRecord(
        sleeve_id=subject.sleeve_id,
        paper_admission_decision_digest=subject.admission_digest,
        lifecycle_subject_digest=authority.lifecycle_subject_digest,
        lifecycle_head_digest=authority.lifecycle_head_digest,
        lifecycle_head_authority_digest=authority.authority_digest,
        current_head_attested=authority.paper_current_head_attested,
        governed_lifecycle_state=state,
        kill_override_applied=state in _KILLED_STATES,
        risk_budget_policy_id=budget.policy_id,
        risk_budget_policy_digest=budget.policy_digest,
        risk_budget_state_digest=budget.state_digest,
        risk_budget_decision_digest=budget.decision_digest,
        sleeve_cap=sleeve_cap,
        pre_kill_requested_budget=budget.total_reserved_budget,
        post_kill_requested_budget=post_total,
        final_allocated_budget=post_total if ready else _ZERO,
        records=tuple(records),
    )


# --- the decision ---------------------------------------------------------------------------------------------------


def build_paper_portfolio_allocation_decision(
    inputs: PaperPortfolioAllocationInputs,
) -> PaperPortfolioAllocationDecision:
    """Decide one whole paper allocation proposal at ``evaluation_end_ns`` from fully re-proven inputs.

    Malformed input and every provenance or binding defect raise ``PaperPortfolioAllocationError``. Missing governance
    of the envelope, the correlation evidence or any sleeve's current head yields ``NEEDS_GOVERNANCE_APPROVAL`` with no
    exposure evaluated. Otherwise the kill override runs before any arithmetic, and any envelope breach rejects the
    whole proposal (``ALLOCATION_REJECTED``, every final zero); without a breach the decision is READY and every final
    allocation is its exact post-kill reservation. Inputs are never mutated.
    """

    _require_exact(inputs, PaperPortfolioAllocationInputs, "inputs")
    allocation_id = _require_text(inputs.allocation_id, "allocation_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    evaluation_end = _require_utc_day(inputs.evaluation_end_ns, "evaluation_end_ns")
    envelope = _require_envelope(inputs.portfolio_risk_envelope)
    declared = tuple(cap.sleeve_id for cap in envelope.sleeve_caps)
    sleeve_caps = {cap.sleeve_id: cap.max_paper_risk_budget for cap in envelope.sleeve_caps}
    correlation = _prove_correlation(
        inputs.correlation_inputs, inputs.correlation_evidence, envelope=envelope, evaluation_end=evaluation_end
    )
    subjects = _prove_subjects(inputs.sleeves, declared=declared, evaluation_end=evaluation_end)

    # Stage 1: governance. Without every governance no exposure is evaluated at all.
    governance: list[str] = []
    if envelope.advances is not True:
        governance.append(_reason("portfolio_risk_envelope_not_governed"))
    if correlation.status is not PaperSleeveCorrelationStatus.READY:
        governance.append(_reason("correlation_evidence_needs_governance_approval"))
    governance.extend(
        _reason(f"lifecycle_head_authority_not_governed:{sleeve_id}")
        for sleeve_id in declared
        if subjects[sleeve_id].authority.paper_current_head_attested is not True
    )

    # Stage 2: the kill/quarantine override, before any arithmetic. Only ACTIVE sleeves reach the exposure stages.
    states = {sleeve_id: _governed_state(subjects[sleeve_id].authority) for sleeve_id in declared}
    exposure: _Exposure | None = None
    if not governance:
        active = tuple(
            _exposure_sleeve(subjects[sleeve_id], sleeve_caps[sleeve_id])
            for sleeve_id in declared
            if states[sleeve_id] is PaperGovernedLifecycleState.ACTIVE
        )
        exposure = _evaluate_exposure(active, envelope=envelope, pairs=correlation.pairs)

    if governance:
        status = PaperPortfolioAllocationStatus.NEEDS_GOVERNANCE_APPROVAL
    elif exposure is not None and exposure.breaches:
        status = PaperPortfolioAllocationStatus.ALLOCATION_REJECTED
    else:
        status = PaperPortfolioAllocationStatus.READY
    ready = status is PaperPortfolioAllocationStatus.READY
    total_post_kill = "" if exposure is None else _render_amount(exposure.total)

    seed = PaperPortfolioAllocationDecision(
        schema_version=_DECISION_SCHEMA,
        status=status,
        ready=ready,
        paper_allocation_evidence_accepted=ready,
        allocation_id=allocation_id,
        correlation_id=correlation_id,
        evaluation_end_ns=evaluation_end,
        envelope_id=envelope.envelope_id,
        envelope_version=envelope.envelope_version,
        envelope_digest=envelope.envelope_digest,
        envelope_policy_digest=envelope.policy_digest,
        envelope_advances=envelope.advances,
        correlation_evidence_digest=correlation.correlation_evidence_digest,
        correlation_evidence_status=correlation.status.value,
        total_paper_risk_budget=envelope.total_paper_risk_budget,
        max_sleeve_count=envelope.max_sleeve_count,
        max_pairwise_correlation=envelope.correlation_cap.max_pairwise_correlation,
        declared_sleeve_ids=declared,
        sleeves=tuple(
            _sleeve_record(
                subjects[sleeve_id],
                sleeve_cap=sleeve_caps[sleeve_id],
                state=states[sleeve_id],
                exposure=exposure,
                ready=ready,
            )
            for sleeve_id in declared
        ),
        exposure_evaluated=exposure is not None,
        market_exposures=() if exposure is None else exposure.market_exposures,
        correlation_pair_checks=() if exposure is None else exposure.pair_checks,
        total_post_kill_requested_budget=total_post_kill,
        total_final_allocated_budget=total_post_kill if ready else _ZERO,
        positive_exposure_sleeve_count=0 if exposure is None else len(exposure.positive),
        governance_reason_codes=_sorted_unique(governance),
        breach_reason_codes=() if exposure is None else exposure.breaches,
        regime_conditioned_caps_status=envelope.regime_stratified_correlation_status,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST,
        allocation_decision_digest="",
    )
    return replace(seed, allocation_decision_digest=edge_payload_digest(_payload(seed), _DECISION_DIGEST_FIELD))


def paper_portfolio_allocation_decision_to_dict(decision: PaperPortfolioAllocationDecision) -> dict[str, object]:
    """Canonical JSON-ready mapping of a decision, its self-digest included."""

    return _payload(decision)


def paper_portfolio_allocation_decision_digest(decision: PaperPortfolioAllocationDecision) -> str:
    """Recompute the canonical decision digest, excluding only ``allocation_decision_digest``."""

    return edge_payload_digest(_payload(decision), _DECISION_DIGEST_FIELD)


def verify_paper_portfolio_allocation_decision(
    decision: object, inputs: PaperPortfolioAllocationInputs
) -> EdgeEvidenceVerification:
    """Re-prove a decision by rebuilding it, every upstream re-proof included, from its exact inputs. Total."""

    return _verify_rebuilt(
        decision,
        cls=PaperPortfolioAllocationDecision,
        rebuild=lambda: build_paper_portfolio_allocation_decision(inputs),
        digest_field=_DECISION_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "PAPER_LIFECYCLE_HEAD_AUTHORITY_NON_CLAIM_FLAGS",
    "PAPER_PORTFOLIO_ALLOCATION_NON_CLAIM_FLAGS",
    "PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST",
    "PaperAllocationMarketBinding",
    "PaperAllocationPairExposure",
    "PaperGovernedLifecycleState",
    "PaperLifecycleHeadAuthority",
    "PaperLifecycleHeadAuthorityApproval",
    "PaperLifecycleHeadAuthorityApprovalKind",
    "PaperLifecycleHeadAuthorityInputs",
    "PaperPortfolioAllocationDecision",
    "PaperPortfolioAllocationError",
    "PaperPortfolioAllocationInputs",
    "PaperPortfolioAllocationRecord",
    "PaperPortfolioAllocationSleeveInputs",
    "PaperPortfolioAllocationSleeveRecord",
    "PaperPortfolioAllocationStatus",
    "PaperPortfolioCorrelationPairCheck",
    "PaperPortfolioMarketExposure",
    "build_paper_lifecycle_head_authority",
    "build_paper_portfolio_allocation_decision",
    "paper_lifecycle_head_authority_digest",
    "paper_lifecycle_head_authority_to_dict",
    "paper_portfolio_allocation_decision_digest",
    "paper_portfolio_allocation_decision_to_dict",
    "paper_portfolio_allocation_rule_set",
    "verify_paper_lifecycle_head_authority",
    "verify_paper_portfolio_allocation_decision",
]
