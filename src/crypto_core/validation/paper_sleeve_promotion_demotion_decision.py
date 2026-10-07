"""RG-6 paper sleeve promotion and demotion decision (RG6_PAPER_SLEEVE_PROMOTION_DEMOTION_DECISION_V1).

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 1, item 5 (RG-6), under the
controller structural authority ``RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1`` and the lineage
architecture ``RG6_ROOT_CAUSE_ESCAPE_ITERATIVE_LINEAGE_PORTABLE_VALIDATION_V1``.

A decision moves ONE sleeve at most one adjacent step on the RG-2 ladder ``PROBATION -> STANDARD -> EXPANDED``, or
holds it, at one injected evaluation end, from fully re-proven evidence. It authorizes nothing else: no allocation,
correlation-cap breach, diversification credit, kill or quarantine, portfolio stop, order, execution, capital or
readiness.

Ladder state:

* genesis is a governed ``PaperSleeveLadderSeed``. It binds the exact RG-2 envelope id, version and digest, one
  envelope-declared sleeve, the structurally fixed initial tier ``PROBATION`` and the explicit UTC-day-aligned
  ``tier_entered_at_ns``. Only an exact ``HUMAN_GOVERNANCE`` approval of its id, version, seed policy digest and the
  RG-6 rule-set digest advances it; ``TEST_ONLY_SYNTHETIC`` never does;
* every later decision takes its current tier and tier entry ONLY from its reconstructed prior RG-6 decision, carried
  as a ``PaperSleeveLadderPriorDecision`` (the prior's exact inputs and its decision). The caller never supplies a tier,
  an entry or a previous result. The prior binds the same sleeve, envelope and seed, its evaluation end is strictly
  earlier, and only a READY prior carries state forward: any other prior propagates its status;
* history, never current authority: no registry, head or latest lookup exists, and ``current_ladder_head_proven`` is
  structurally False.

Lineage proof, without recursion: the nested priors are walked back to the seed in a loop (each node's exact type
checked before it is read, and an in-memory identity guard turning a cyclic object graph into a failure). The seed is
re-proven. Then every ancestor, oldest first, is rebuilt exactly once by the same assembly path as the public builder,
from its own exact inputs and the predecessor just rebuilt, and the rebuild must equal the carried decision
canonically under an intact self-digest before it becomes the next predecessor. Stack use is independent of the
lineage length, one replay rebuilds each historical node once, and no length is bounded or trusted. A lineage node
compares by identity and the inputs leave the lineage out of their ``repr``, so generic equality, hashing and
``repr`` of a long lineage do not recurse through it either.

Evidence, each REBUILT through its accepted public builder and required to equal the supplied artifact canonically
(only the reconstruction is used):

* RG-2: the envelope, re-pinned through its total verifier, its rule set and its pending regime marker; it owns every
  threshold, and its ladder consistency invariant is re-checked;
* RG-3: the target ``PaperSleevePerformanceEvidence`` of the lineage sleeve, ending exactly at the evaluation end;
* RG-4: the ``PaperSleeveDrawdownEvidence`` of the envelope ending at the evaluation end, whose target record binds the
  exact RG-3 digest and is measured before any threshold is read;
* RG-5: the ``PaperSleeveCorrelationEvidence`` of the envelope at the evaluation end, whose target record binds the
  exact RG-3 digest. RG-5 is provenance only: no correlation meets the cap and no pair moves a sleeve.

Decision (rule set ``PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST``): tenure is the exact number of UTC days from
the current tier entry to the evaluation end; performance is the RG-3 ``paper_sharpe_annualized``; drawdown is the
target sleeve's RG-4 ``max_peak_distance`` for promotion and demotion alike (``MAX_PEAK_DISTANCE``), never the current
peak distance and never portfolio drawdown. Promotion over a boundary needs tenure ``>= min_probation_days``, Sharpe
``>=`` its floor and maximum drawdown ``<=`` its ceiling; demotion needs Sharpe ``<`` its floor or maximum drawdown
``>`` its ceiling. PROBATION only promotes and EXPANDED only demotes; STANDARD evaluates demotion first and evaluates
promotion only when no demotion breach applies. HOLD keeps the tier and its entry; PROMOTE or DEMOTE moves one tier and
enters it at the evaluation end.

Status: a provenance, lineage or binding defect raises ``PaperSleeveLadderError``; otherwise
``NEEDS_GOVERNANCE_APPROVAL`` over ``NOT_COMPUTABLE`` over ``READY`` (one evaluated transition). Regime-concentration
demotion stays ``PENDING_RF_LABEL_ENUM_UNAVAILABLE`` and unevaluated. Both verifiers are total. Exact ``Fraction``
comparisons only: no float, no ``decimal``, and no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from fractions import Fraction
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeArtifactError,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
    PaperPortfolioRiskEnvelope,
    PaperSleeveLadderBoundary,
    PaperSleeveLadderTier,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PaperSleeveCorrelationEvidence,
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationStatus,
    build_paper_sleeve_correlation_evidence,
    paper_sleeve_correlation_evidence_to_dict,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperPeakDistanceMeasurement,
    PaperSleeveDrawdownEvidence,
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownRecord,
    PaperSleeveDrawdownStatus,
    build_paper_sleeve_drawdown_evidence,
    paper_sleeve_drawdown_evidence_to_dict,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    build_paper_sleeve_performance_evidence,
    paper_sleeve_performance_evidence_to_dict,
)

_T = TypeVar("_T")
_PREFIX = "paper_sleeve_promotion_demotion_decision"
_SEED_SCHEMA = "paper-sleeve-ladder-seed.v1"
_DECISION_SCHEMA = "paper-sleeve-promotion-demotion-decision.v1"
_SEED_DIGEST_FIELD = "ladder_seed_digest"
_DECISION_DIGEST_FIELD = "decision_digest"
_IDENTIFIER_PUNCTUATION = frozenset("-_./:")

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_sleeve_promotion_demotion_decision_rules.v1",
    "structural_authority_id": "RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1",
    "lineage_architecture_id": "RG6_ROOT_CAUSE_ESCAPE_ITERATIVE_LINEAGE_PORTABLE_VALIDATION_V1",
    "scope_rule_id": "one_sleeve_at_most_one_adjacent_ladder_step_no_allocation_cap_credit_kill_stop_or_execution.v1",
    "genesis_rule_id": "a_lineage_starts_at_a_governed_seed_whose_tier_is_fixed_at_probation.v1",
    "genesis_tier": "PROBATION",
    "seed_approval_rule_id": "approval_commits_seed_id_version_seed_policy_digest_and_rule_set_digest.v1",
    "seed_verdict_rule_id": "only_an_exact_human_governance_approval_advances_test_only_synthetic_never_does.v1",
    "lineage_rule_id": "current_tier_and_entry_only_from_the_reconstructed_prior_of_the_same_sleeve_envelope_seed.v1",
    "lineage_proof_rule_id": "iterative_walk_to_the_seed_then_each_ancestor_rebuilt_once_oldest_first_no_bound.v1",
    "prior_status_rule_id": "only_a_ready_prior_carries_state_any_other_prior_propagates_its_status.v1",
    "head_rule_id": "history_only_no_registry_no_latest_lookup_no_current_head_claim.v1",
    "coordinate_rule_id": "utc_day_aligned_evaluation_end_not_before_genesis_entry_and_after_the_prior.v1",
    "tenure_rule_id": "whole_utc_days_from_the_current_tier_entry_to_the_evaluation_end.v1",
    "evidence_rule_id": "rg3_rg4_rg5_rebuilt_on_the_same_envelope_ending_at_the_evaluation_end.v1",
    "performance_metric_id": "paper-sharpe-evidence.v1:paper_sharpe_annualized",
    "drawdown_consumption": "MAX_PEAK_DISTANCE",
    "drawdown_rule_id": "target_sleeve_rg4_max_peak_distance_for_promotion_and_demotion_never_current.v1",
    "correlation_rule_id": "rg5_provenance_only_no_cap_comparison_and_no_pair_moves_a_sleeve.v1",
    "promotion_rule_id": "tenure_ge_min_probation_days_and_sharpe_ge_floor_and_max_drawdown_le_ceiling.v1",
    "demotion_rule_id": "sharpe_lt_floor_or_max_drawdown_gt_ceiling.v1",
    "precedence_rule_id": "standard_demotion_first_promotion_only_when_no_demotion_breach_applies.v1",
    "ladder_consistency_rule_id": "rg2_ladder_consistency_invariant_repinned_a_contradiction_fails_closed.v1",
    "transition_rule_id": "at_most_one_adjacent_step_per_decision.v1",
    "entry_rule_id": "hold_keeps_the_entry_a_transition_enters_at_the_evaluation_end.v1",
    "regime_rule_id": "regime_concentration_demotion_pending_until_an_accepted_rf_chain.v1",
    "status_rule_id": "needs_governance_approval_over_not_computable_over_ready.v1",
    "numeric_rule_id": "exact_fraction_comparison_of_canonical_texts_no_float_no_decimal.v1",
    "utc_day_ns": 86_400_000_000_000,
    "decimal_scale": 18,
    "decimal_text_max_length": 100,
    "fraction_max_part_digits": 4096,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_identifier_length": 128,
}
PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_GENESIS_TIER = PaperSleeveLadderTier(str(_RULE_SET_V1["genesis_tier"]))
_DRAWDOWN_CONSUMPTION = str(_RULE_SET_V1["drawdown_consumption"])
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_text_max_length"]  # type: ignore[assignment]
_MAX_FRACTION_DIGITS: int = _RULE_SET_V1["fraction_max_part_digits"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_IDENTIFIER: int = _RULE_SET_V1["max_identifier_length"]  # type: ignore[assignment]


def paper_sleeve_promotion_demotion_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class PaperSleeveLadderError(EdgeArtifactError):
    """A malformed input or any provenance, lineage or binding defect: an invalid record is never represented."""


class PaperSleeveLadderSeedApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` exists for tests only: it is recorded and never advances a seed."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class PaperSleeveLadderDecisionStatus(str, Enum):
    """READY carries exactly one evaluated transition; the other states carry no transition and no consumed metric."""

    READY = "READY"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class PaperSleeveLadderTransition(str, Enum):
    HOLD = "HOLD"
    PROMOTE = "PROMOTE"
    DEMOTE = "DEMOTE"


@dataclass(frozen=True)
class PaperSleeveLadderSeedApproval:
    """Governance approval of one exact seed; every commitment must equal the assembled value to advance it."""

    approval_reference: str
    approval_digest: str
    approval_kind: PaperSleeveLadderSeedApprovalKind
    approved_seed_id: str
    approved_seed_version: str
    approved_seed_policy_digest: str
    approved_rule_set_digest: str


PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("current_ladder_head_proven", False),
    ("promotion_demotion_decided", False),
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
class PaperSleeveLadderSeed:
    """The governed, digest-bound genesis of one sleeve's ladder lineage; its initial tier is always PROBATION."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    seed_id: str
    seed_version: str
    envelope_id: str
    envelope_version: str
    envelope_digest: str
    sleeve_id: str
    initial_tier: PaperSleeveLadderTier
    tier_entered_at_ns: int
    rule_set_id: str
    rule_set_digest: str
    seed_policy_digest: str
    approval: PaperSleeveLadderSeedApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    ladder_seed_digest: str
    paper_only: bool = True
    current_ladder_head_proven: bool = False
    promotion_demotion_decided: bool = False
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


PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("current_ladder_head_proven", False),
    ("regime_demotion_evaluated", False),
    ("correlation_cap_breach_evaluated", False),
    ("diversification_credit_granted", False),
    ("portfolio_allocation_approved", False),
    ("capital_allocated", False),
    ("portfolio_stop_evaluated", False),
    ("kill_quarantine_decided", False),
    ("execution_authorized", False),
    ("account_equity_represented", False),
    ("capital_represented", False),
    ("statistical_significance_proven", False),
    ("profitability_proven", False),
    ("edge_proven", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("prdv4_stage4_complete", False),
)


@dataclass(frozen=True)
class PaperSleevePromotionDemotionDecision:
    """One sleeve's digest-bound ladder decision at one evaluation end: history, never a current ladder head."""

    schema_version: str
    status: PaperSleeveLadderDecisionStatus
    ready: bool
    advances: bool
    decision_id: str
    correlation_id: str
    envelope_id: str
    envelope_version: str
    envelope_digest: str
    envelope_policy_digest: str
    envelope_advances: bool
    sleeve_id: str
    market_symbol: str
    ladder_seed_digest: str
    ladder_seed_advances: bool
    prior_decision_digest: str
    lineage_sequence: int
    evaluation_end_ns: int
    current_tier: PaperSleeveLadderTier | None
    current_tier_entered_at_ns: int | None
    tier_elapsed_days: int | None
    transition: PaperSleeveLadderTransition | None
    resulting_tier: PaperSleeveLadderTier | None
    resulting_tier_entered_at_ns: int | None
    performance_evidence_digest: str
    performance_status: str
    drawdown_evidence_digest: str
    drawdown_status: str
    correlation_evidence_digest: str
    correlation_status: str
    paper_sharpe_annualized: str
    max_peak_distance: str
    drawdown_consumption: str
    promotion_boundary: PaperSleeveLadderBoundary | None
    demotion_boundary: PaperSleeveLadderBoundary | None
    decision_reason_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    regime_concentration_demotion_status: str
    rule_set_id: str
    rule_set_digest: str
    decision_digest: str
    paper_only: bool = True
    current_ladder_head_proven: bool = False
    regime_demotion_evaluated: bool = False
    correlation_cap_breach_evaluated: bool = False
    diversification_credit_granted: bool = False
    portfolio_allocation_approved: bool = False
    capital_allocated: bool = False
    portfolio_stop_evaluated: bool = False
    kill_quarantine_decided: bool = False
    execution_authorized: bool = False
    account_equity_represented: bool = False
    capital_represented: bool = False
    statistical_significance_proven: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    prdv4_stage4_complete: bool = False


@dataclass(frozen=True)
class PaperSleevePromotionDemotionInputs:
    """Everything one decision consumes. A decision is re-proven by rebuilding it from exactly these inputs.

    ``ladder_state`` is the governed seed (genesis) or the prior decision node. It is left out of ``repr`` so that a long
    lineage never renders recursively; equality and hashing reach it through the node, which compares by identity.
    """

    decision_id: str
    correlation_id: str
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    ladder_state: PaperSleeveLadderSeed | PaperSleeveLadderPriorDecision = field(repr=False)
    evaluation_end_ns: int
    performance_inputs: PaperSleevePerformanceInputs
    performance_evidence: PaperSleevePerformanceEvidence
    drawdown_inputs: PaperSleeveDrawdownInputs
    drawdown_evidence: PaperSleeveDrawdownEvidence
    correlation_inputs: PaperSleeveCorrelationInputs
    correlation_evidence: PaperSleeveCorrelationEvidence


@dataclass(frozen=True, eq=False)
class PaperSleeveLadderPriorDecision:
    """One lineage node: a prior decision and the exact inputs it is rebuilt from.

    A node compares and hashes by identity: it references authenticated history, and value comparison would have to
    descend through the whole lineage.
    """

    decision_inputs: PaperSleevePromotionDemotionInputs
    decision: PaperSleevePromotionDemotionDecision


# The seed policy excludes only its governance: the approval, the verdict derived from it, and the two digests.
_SEED_GOVERNANCE_FIELDS = frozenset(
    {
        "gate_verdict",
        "advances",
        "seed_policy_digest",
        "approval",
        "synthetic_test_approval_used",
        "verdict_reason_codes",
        "ladder_seed_digest",
    }
)
_SEED_FLAGS = frozenset(name for name, _ in PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS)
_RECORD_TYPES = (PaperSleeveLadderSeedApproval, PaperSleeveLadderBoundary)
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperSleeveLadderSeedApproval: {"approval_kind": PaperSleeveLadderSeedApprovalKind},
    PaperSleeveLadderBoundary: {"lower_tier": PaperSleeveLadderTier, "upper_tier": PaperSleeveLadderTier},
    PaperSleeveLadderSeed: {"gate_verdict": EdgeGateVerdict, "initial_tier": PaperSleeveLadderTier},
    PaperSleevePromotionDemotionDecision: {
        "status": PaperSleeveLadderDecisionStatus,
        "current_tier": PaperSleeveLadderTier,
        "transition": PaperSleeveLadderTransition,
        "resulting_tier": PaperSleeveLadderTier,
    },
}
_NULLABLE_ENUM_FIELDS = frozenset({"current_tier", "transition", "resulting_tier"})


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> PaperSleeveLadderError:
    return PaperSleeveLadderError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _require_text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{name}")
    return value


def _require_identifier(value: object, name: str) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_IDENTIFIER or not value.isascii():
        raise _fail(f"{name}_invalid")
    if not value[0].isalnum() or not all(char.isalnum() or char in _IDENTIFIER_PUNCTUATION for char in value):
        raise _fail(f"{name}_invalid")
    return _require_text(value, name)


def _require_hex64(value: object, name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{name}_invalid")
    return cast(str, value)


def _require_member(value: object, enum_cls: type[Enum], name: str) -> Enum:
    if type(value) is enum_cls:
        return cast(Enum, value)
    if type(value) is str and value in {member.value for member in enum_cls}:
        return enum_cls(value)
    raise _fail(f"{name}_invalid")


def _require_utc_day(value: object, name: str) -> int:
    """An exact non-negative int64 epoch-nanosecond coordinate on a UTC day boundary; never a bool, never a clock."""

    if type(value) is not int or not 0 <= value <= _MAX_WIRE_INT:
        raise _fail(f"{name}_invalid")
    if value % _DAY_NS:
        raise _fail(f"{name}_not_utc_day_aligned")
    return value


def _decimal_fraction(value: object, code: str) -> Fraction:
    """The exact value of canonical fixed scale-18 decimal text (no signed zero), as RG-2 and the Sharpe producer emit.

    The length bound sits above both producers' maxima: RG-2 caps its texts at 60 characters, and the Sharpe producer
    quantizes within precision 80.
    """

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


def _peak_distance_fraction(value: object) -> Fraction:
    """The exact value of an RG-4 peak distance: reduced ``"p/q"`` text in ``[0, 1)`` within the RG-4 digit bound."""

    if type(value) is not str or not value.isascii():
        raise _fail("drawdown_peak_distance_invalid")
    numerator, slash, denominator = value.partition("/")
    if slash != "/" or not _digits(numerator) or not _digits(denominator):
        raise _fail("drawdown_peak_distance_invalid")
    if len(numerator) > _MAX_FRACTION_DIGITS or len(denominator) > _MAX_FRACTION_DIGITS:
        raise _fail("drawdown_peak_distance_invalid")
    if (numerator.startswith("0") and numerator != "0") or denominator.startswith("0"):
        raise _fail("drawdown_peak_distance_invalid")
    distance = Fraction(int(numerator), int(denominator))
    if f"{distance.numerator}/{distance.denominator}" != value or not 0 <= distance < 1:
        raise _fail("drawdown_peak_distance_invalid")
    return distance


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object) -> _T:
    """One accepted public builder call; any failure is a provenance defect of this decision."""

    try:
        return builder(*args)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed here
        raise _fail(f"{code}_reconstruction_failed") from exc


# --- canonical wire form --------------------------------------------------------------------------------------------


def _scalar(value: object) -> object:
    if type(value) is int:
        if 0 <= value <= _MAX_WIRE_INT:
            return value
        raise _fail("payload_integer_out_of_range")
    if value is None or type(value) is str or type(value) is bool:
        return value
    raise _fail("payload_value_not_canonical")


def _enum_value(value: object, enum_cls: type[Enum], name: str) -> object:
    if type(value) is enum_cls:
        return cast(Enum, value).value
    if value is None and name in _NULLABLE_ENUM_FIELDS:
        return None
    raise _fail("payload_enum_field_not_exact_member")


def _record_payload(record: object) -> dict[str, object]:
    """A nested record carries only enum members and scalars, so serialization never recurses."""

    enums = _ENUM_FIELDS[type(record)]
    return {
        item.name: (
            _enum_value(getattr(record, item.name), enums[item.name], item.name)
            if item.name in enums
            else _scalar(getattr(record, item.name))
        )
        for item in fields(record)  # type: ignore[arg-type]
    }


def _payload(artifact: object) -> dict[str, object]:
    """The exact wire form: exact enum members, exact records, tuples of exact scalars and exact scalars only."""

    enums = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for item in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, item.name)
        if item.name in enums:
            payload[item.name] = _enum_value(value, enums[item.name], item.name)
        elif type(value) in _RECORD_TYPES:
            payload[item.name] = _record_payload(value)
        elif type(value) is tuple:
            payload[item.name] = [_scalar(element) for element in value]
        else:
            payload[item.name] = _scalar(value)
    return payload


# --- the governed seed ----------------------------------------------------------------------------------------------


def _require_envelope(value: object) -> PaperPortfolioRiskEnvelope:
    """The RG-2 envelope, re-pinned through its total verifier, its rule set and its pending regime marker."""

    _require_exact(value, PaperPortfolioRiskEnvelope, "portfolio_risk_envelope")
    if not verify_paper_portfolio_risk_envelope(value).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    envelope = cast(PaperPortfolioRiskEnvelope, value)
    if envelope.rule_set_digest != PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST:
        raise _fail("portfolio_risk_envelope_rule_set_unsupported")
    # V1 evaluates no regime-concentration demotion: an envelope no longer marking it pending is out of scope.
    if envelope.regime_concentration_demotion_status != EDGE_REGIME_LABEL_BINDING_PENDING:
        raise _fail("regime_concentration_demotion_status_unsupported")
    return envelope


def _declared_sleeve_ids(envelope: PaperPortfolioRiskEnvelope) -> frozenset[str]:
    return frozenset(cap.sleeve_id for cap in envelope.sleeve_caps)


def _approval_record(approval: object) -> PaperSleeveLadderSeedApproval | None:
    """Exact structure only; whether the commitments match is decided at assembly."""

    if approval is None:
        return None
    _require_exact(approval, PaperSleeveLadderSeedApproval, "seed_governance_approval")

    def read(name: str) -> object:
        return getattr(approval, name, None)

    return PaperSleeveLadderSeedApproval(
        approval_reference=_require_text(read("approval_reference"), "seed_governance_approval_reference"),
        approval_digest=_require_hex64(read("approval_digest"), "seed_governance_approval_digest"),
        approval_kind=cast(
            PaperSleeveLadderSeedApprovalKind,
            _require_member(read("approval_kind"), PaperSleeveLadderSeedApprovalKind, "seed_governance_approval_kind"),
        ),
        approved_seed_id=_require_text(read("approved_seed_id"), "seed_governance_approved_seed_id"),
        approved_seed_version=_require_text(read("approved_seed_version"), "seed_governance_approved_seed_version"),
        approved_seed_policy_digest=_require_hex64(
            read("approved_seed_policy_digest"), "seed_governance_approved_seed_policy_digest"
        ),
        approved_rule_set_digest=_require_hex64(
            read("approved_rule_set_digest"), "seed_governance_approved_rule_set_digest"
        ),
    )


def _approval_reasons(approval: PaperSleeveLadderSeedApproval | None, committed: Mapping[str, str]) -> list[str]:
    if approval is None:
        return [_reason("seed_governance_approval_missing")]
    reasons = [
        _reason(f"seed_governance_approval_{name}_mismatch")
        for name, expected in committed.items()
        if getattr(approval, f"approved_{name}") != expected
    ]
    if approval.approval_kind is PaperSleeveLadderSeedApprovalKind.TEST_ONLY_SYNTHETIC:
        reasons.append(_reason("seed_governance_approval_test_only_synthetic"))
    return reasons


def _assemble_seed(
    *,
    seed_id: object,
    seed_version: object,
    envelope_id: object,
    envelope_version: object,
    envelope_digest: object,
    sleeve_id: object,
    tier_entered_at_ns: object,
    approval: object,
) -> PaperSleeveLadderSeed:
    """The single seed assembly path, shared by the builder and by verifier reassembly."""

    identity = _require_text(seed_id, "seed_id")
    version = _require_text(seed_version, "seed_version")
    record = _approval_record(approval)
    draft = PaperSleeveLadderSeed(
        schema_version=_SEED_SCHEMA,
        gate_verdict=EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        advances=False,
        seed_id=identity,
        seed_version=version,
        envelope_id=_require_text(envelope_id, "seed_envelope_id"),
        envelope_version=_require_text(envelope_version, "seed_envelope_version"),
        envelope_digest=_require_hex64(envelope_digest, "seed_envelope_digest"),
        sleeve_id=_require_identifier(sleeve_id, "seed_sleeve_id"),
        initial_tier=_GENESIS_TIER,
        tier_entered_at_ns=_require_utc_day(tier_entered_at_ns, "tier_entered_at_ns"),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
        seed_policy_digest="",
        approval=record,
        synthetic_test_approval_used=record is not None
        and record.approval_kind is PaperSleeveLadderSeedApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=(),
        ladder_seed_digest="",
    )
    policy = {name: value for name, value in _payload(draft).items() if name not in _SEED_GOVERNANCE_FIELDS}
    policy_digest = edge_sha256_text(edge_canonical_json(policy))
    blockers = _approval_reasons(
        record,
        {
            "seed_id": identity,
            "seed_version": version,
            "seed_policy_digest": policy_digest,
            "rule_set_digest": PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
        },
    )
    verdict = resolve_edge_gate_verdict([], [], blockers)
    governed = replace(
        draft,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        seed_policy_digest=policy_digest,
        verdict_reason_codes=_sorted_unique(blockers),
    )
    return replace(governed, ladder_seed_digest=edge_payload_digest(_payload(governed), _SEED_DIGEST_FIELD))


def build_paper_sleeve_ladder_seed(
    *,
    seed_id: str,
    seed_version: str,
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope,
    sleeve_id: str,
    tier_entered_at_ns: int,
    approval: PaperSleeveLadderSeedApproval | None,
) -> PaperSleeveLadderSeed:
    """Build the governed genesis of one sleeve's lineage. There is no tier parameter: genesis is always PROBATION.

    The envelope is re-pinned and must declare the sleeve; ``tier_entered_at_ns`` is an explicit UTC-day-aligned state
    fact. Malformed input raises ``PaperSleeveLadderError``; only an exact ``HUMAN_GOVERNANCE`` approval advances.
    """

    envelope = _require_envelope(portfolio_risk_envelope)
    sleeve = _require_identifier(sleeve_id, "seed_sleeve_id")
    if sleeve not in _declared_sleeve_ids(envelope):
        raise _fail("seed_sleeve_not_declared_by_envelope")
    return _assemble_seed(
        seed_id=seed_id,
        seed_version=seed_version,
        envelope_id=envelope.envelope_id,
        envelope_version=envelope.envelope_version,
        envelope_digest=envelope.envelope_digest,
        sleeve_id=sleeve,
        tier_entered_at_ns=tier_entered_at_ns,
        approval=approval,
    )


def paper_sleeve_ladder_seed_to_dict(seed: PaperSleeveLadderSeed) -> dict[str, object]:
    """Canonical JSON-ready mapping of a seed, its self-digest included."""

    return _payload(seed)


def paper_sleeve_ladder_seed_digest(seed: PaperSleeveLadderSeed) -> str:
    """Recompute the canonical seed digest, excluding only ``ladder_seed_digest``."""

    return edge_payload_digest(_payload(seed), _SEED_DIGEST_FIELD)


def _wire_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _wire_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _wire_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_WIRE_INT:
        raise _fail("payload_field_malformed")
    return value


def _wire_codes(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_wire_str(item) for item in value)


def _wire_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def member(value: object) -> Enum:
        text = _wire_str(value)
        if text not in {item.value for item in enum_cls}:
            raise _fail("payload_field_malformed")
        return enum_cls(text)

    return member


def _parse_record(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _wire_str)(payload[name]) for name in names})


def _wire_approval(value: object) -> object:
    if value is None:
        return None
    return _parse_record(
        PaperSleeveLadderSeedApproval, value, {"approval_kind": _wire_enum(PaperSleeveLadderSeedApprovalKind)}
    )


_SEED_CONVERTERS: dict[str, Callable[[object], object]] = {
    "gate_verdict": _wire_enum(EdgeGateVerdict),
    "advances": _wire_bool,
    "initial_tier": _wire_enum(PaperSleeveLadderTier),
    "tier_entered_at_ns": _wire_int,
    "approval": _wire_approval,
    "synthetic_test_approval_used": _wire_bool,
    "verdict_reason_codes": _wire_codes,
    **dict.fromkeys(_SEED_FLAGS, _wire_bool),
}


def paper_sleeve_ladder_seed_from_payload(payload: object) -> PaperSleeveLadderSeed:
    """Strictly reconstruct a seed from its wire form: exact fields, types and domains, without proving it."""

    return cast(PaperSleeveLadderSeed, _parse_record(PaperSleeveLadderSeed, payload, _SEED_CONVERTERS))


def _reassemble_seed(seed: object) -> PaperSleeveLadderSeed:
    parsed = cast(PaperSleeveLadderSeed, seed)
    return _assemble_seed(
        seed_id=parsed.seed_id,
        seed_version=parsed.seed_version,
        envelope_id=parsed.envelope_id,
        envelope_version=parsed.envelope_version,
        envelope_digest=parsed.envelope_digest,
        sleeve_id=parsed.sleeve_id,
        tier_entered_at_ns=parsed.tier_entered_at_ns,
        approval=parsed.approval,
    )


def verify_paper_sleeve_ladder_seed(seed: object) -> EdgeEvidenceVerification:
    """Re-prove a seed by strict parse, self-digest recomputation and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        seed,
        cls=PaperSleeveLadderSeed,
        to_payload=_payload,
        parse_payload=paper_sleeve_ladder_seed_from_payload,
        reassemble=_reassemble_seed,
        self_digest_field=_SEED_DIGEST_FIELD,
        reason=_reason,
    )


# --- the RG-2 ladder ------------------------------------------------------------------------------------------------


def _threshold(value: object) -> Fraction:
    return _decimal_fraction(value, "ladder_threshold_invalid")


def _require_ladder(
    envelope: PaperPortfolioRiskEnvelope,
) -> tuple[PaperSleeveLadderBoundary, PaperSleeveLadderBoundary]:
    """The ordered RG-2 ladder with its consistency invariant re-checked; any contradiction fails closed.

    Within a boundary, promotion is never looser than demotion; across STANDARD, the upper promotion thresholds are never
    looser than the lower demotion thresholds. One snapshot can then never be eligible to promote and demote together.
    """

    ladder = envelope.ladder_boundaries
    if type(ladder) is not tuple or len(ladder) != 2:
        raise _fail("ladder_boundaries_not_the_accepted_ladder")
    if not all(type(boundary) is PaperSleeveLadderBoundary for boundary in ladder):
        raise _fail("ladder_boundaries_not_the_accepted_ladder")
    lower, upper = ladder
    if (lower.lower_tier, lower.upper_tier, upper.lower_tier, upper.upper_tier) != (
        PaperSleeveLadderTier.PROBATION,
        PaperSleeveLadderTier.STANDARD,
        PaperSleeveLadderTier.STANDARD,
        PaperSleeveLadderTier.EXPANDED,
    ):
        raise _fail("ladder_boundaries_not_the_accepted_ladder")
    if not all(type(boundary.min_probation_days) is int and boundary.min_probation_days >= 1 for boundary in ladder):
        raise _fail("ladder_boundaries_not_the_accepted_ladder")
    for promoting, demoting in ((lower, lower), (upper, upper), (upper, lower)):
        if _threshold(promoting.promotion_min_paper_sharpe) < _threshold(demoting.demotion_min_paper_sharpe):
            raise _fail("ladder_consistency_invariant_violated")
        if _threshold(promoting.promotion_max_drawdown_fraction) > _threshold(demoting.demotion_max_drawdown_fraction):
            raise _fail("ladder_consistency_invariant_violated")
    return lower, upper


# --- the transition -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Movement:
    transition: PaperSleeveLadderTransition
    resulting_tier: PaperSleeveLadderTier
    promotion_boundary: PaperSleeveLadderBoundary | None
    demotion_boundary: PaperSleeveLadderBoundary | None
    reasons: tuple[str, ...]


def _promotion(
    boundary: PaperSleeveLadderBoundary, tenure_days: int, sharpe: Fraction, drawdown: Fraction
) -> tuple[bool, list[str]]:
    """Eligible only if ALL hold, each inclusive: tenure, Sharpe floor and maximum-drawdown ceiling."""

    tenure_met = tenure_days >= boundary.min_probation_days
    sharpe_met = sharpe >= _threshold(boundary.promotion_min_paper_sharpe)
    drawdown_met = drawdown <= _threshold(boundary.promotion_max_drawdown_fraction)
    return tenure_met and sharpe_met and drawdown_met, [
        _reason("promotion_tenure_met" if tenure_met else "promotion_tenure_short"),
        _reason("promotion_sharpe_at_or_above_floor" if sharpe_met else "promotion_sharpe_below_floor"),
        _reason("promotion_max_drawdown_within_ceiling" if drawdown_met else "promotion_max_drawdown_above_ceiling"),
    ]


def _demotion(boundary: PaperSleeveLadderBoundary, sharpe: Fraction, drawdown: Fraction) -> tuple[bool, list[str]]:
    """Eligible if EITHER breach holds, each strict: Sharpe below the floor or maximum drawdown above the ceiling."""

    sharpe_breach = sharpe < _threshold(boundary.demotion_min_paper_sharpe)
    drawdown_breach = drawdown > _threshold(boundary.demotion_max_drawdown_fraction)
    return sharpe_breach or drawdown_breach, [
        _reason("demotion_sharpe_below_floor" if sharpe_breach else "demotion_sharpe_not_below_floor"),
        _reason(
            "demotion_max_drawdown_above_ceiling" if drawdown_breach else "demotion_max_drawdown_not_above_ceiling"
        ),
    ]


def _move(
    tier: PaperSleeveLadderTier,
    tenure_days: int,
    sharpe: Fraction,
    drawdown: Fraction,
    lower: PaperSleeveLadderBoundary,
    upper: PaperSleeveLadderBoundary,
) -> _Movement:
    """The one adjacent movement of ``tier`` over the ordered ladder ``(lower, upper)``, or HOLD."""

    hold, promote, demote = (
        PaperSleeveLadderTransition.HOLD,
        PaperSleeveLadderTransition.PROMOTE,
        PaperSleeveLadderTransition.DEMOTE,
    )
    if tier is PaperSleeveLadderTier.PROBATION:
        eligible, reasons = _promotion(lower, tenure_days, sharpe, drawdown)
        reasons.append(_reason("probation_cannot_demote"))
        if eligible:
            return _Movement(promote, PaperSleeveLadderTier.STANDARD, lower, None, tuple(reasons))
        return _Movement(hold, tier, lower, None, tuple(reasons))
    if tier is PaperSleeveLadderTier.STANDARD:
        breached, reasons = _demotion(lower, sharpe, drawdown)
        reasons.append(_reason("standard_demotion_evaluated_first"))
        if breached:
            reasons.append(_reason("promotion_skipped_after_demotion"))
            return _Movement(demote, PaperSleeveLadderTier.PROBATION, None, lower, tuple(reasons))
        eligible, promotion_reasons = _promotion(upper, tenure_days, sharpe, drawdown)
        reasons.extend(promotion_reasons)
        if eligible:
            return _Movement(promote, PaperSleeveLadderTier.EXPANDED, upper, lower, tuple(reasons))
        return _Movement(hold, tier, upper, lower, tuple(reasons))
    if tier is PaperSleeveLadderTier.EXPANDED:
        breached, reasons = _demotion(upper, sharpe, drawdown)
        reasons.append(_reason("expanded_cannot_promote"))
        if breached:
            return _Movement(demote, PaperSleeveLadderTier.STANDARD, None, upper, tuple(reasons))
        return _Movement(hold, tier, None, upper, tuple(reasons))
    raise _fail("current_tier_invalid")


# --- lineage state and evidence re-proof ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _LineageState:
    sleeve_id: str
    seed_digest: str
    seed_advances: bool
    prior_digest: str
    sequence: int
    tier: PaperSleeveLadderTier | None
    entered_at_ns: int | None
    governance: tuple[str, ...]
    unavailable: tuple[str, ...]


def _state_from_seed(
    seed: PaperSleeveLadderSeed, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int
) -> _LineageState:
    """Genesis state of a seed ALREADY re-proven by the caller, bound to this decision's envelope and coordinate."""

    if seed.rule_set_digest != PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST:
        raise _fail("ladder_seed_rule_set_unsupported")
    if (seed.envelope_id, seed.envelope_version, seed.envelope_digest) != (
        envelope.envelope_id,
        envelope.envelope_version,
        envelope.envelope_digest,
    ):
        raise _fail("ladder_seed_envelope_mismatch")
    if seed.sleeve_id not in _declared_sleeve_ids(envelope):
        raise _fail("ladder_seed_sleeve_not_declared_by_envelope")
    if seed.initial_tier is not _GENESIS_TIER:
        raise _fail("ladder_seed_initial_tier_not_probation")
    if evaluation_end < seed.tier_entered_at_ns:
        raise _fail("evaluation_end_precedes_the_tier_entry")
    return _LineageState(
        sleeve_id=seed.sleeve_id,
        seed_digest=seed.ladder_seed_digest,
        seed_advances=seed.advances,
        prior_digest="",
        sequence=0,
        tier=seed.initial_tier,
        entered_at_ns=seed.tier_entered_at_ns,
        governance=() if seed.advances is True else (_reason("ladder_seed_not_governed"),),
        unavailable=(),
    )


def _state_from_prior(
    prior: PaperSleevePromotionDemotionDecision, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int
) -> _LineageState:
    """The state a prior decision carries forward; ``prior`` is a decision this module has just rebuilt."""

    if prior.rule_set_digest != PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST:
        raise _fail("prior_decision_rule_set_unsupported")
    if (prior.envelope_id, prior.envelope_version, prior.envelope_digest) != (
        envelope.envelope_id,
        envelope.envelope_version,
        envelope.envelope_digest,
    ):
        raise _fail("prior_decision_envelope_mismatch")
    if evaluation_end <= prior.evaluation_end_ns:
        raise _fail("evaluation_end_not_after_the_prior_decision")
    tier: PaperSleeveLadderTier | None = None
    entered: int | None = None
    governance: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    if prior.advances is True:
        tier, entered = prior.resulting_tier, prior.resulting_tier_entered_at_ns
        if tier is None or entered is None or entered > evaluation_end:
            raise _fail("prior_decision_resulting_state_invalid")
    elif prior.status is PaperSleeveLadderDecisionStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance = (_reason("prior_decision_not_advancing"),)
    else:
        unavailable = (_reason("prior_decision_not_advancing"),)
    return _LineageState(
        sleeve_id=prior.sleeve_id,
        seed_digest=prior.ladder_seed_digest,
        seed_advances=prior.ladder_seed_advances,
        prior_digest=prior.decision_digest,
        sequence=prior.lineage_sequence + 1,
        tier=tier,
        entered_at_ns=entered,
        governance=governance,
        unavailable=unavailable,
    )


def _prove_performance(
    inputs: PaperSleevePromotionDemotionInputs, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int
) -> PaperSleevePerformanceEvidence:
    _require_exact(inputs.performance_inputs, PaperSleevePerformanceInputs, "performance_inputs")
    _require_exact(inputs.performance_evidence, PaperSleevePerformanceEvidence, "performance_evidence")
    rebuilt = _rebuild("performance", build_paper_sleeve_performance_evidence, inputs.performance_inputs)
    if not _canonically_equal(inputs.performance_evidence, rebuilt, paper_sleeve_performance_evidence_to_dict):
        raise _fail("performance_evidence_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("performance_evidence_envelope_mismatch")
    if rebuilt.sleeve_id not in _declared_sleeve_ids(envelope):
        raise _fail("performance_sleeve_not_declared_by_envelope")
    if rebuilt.window_end_ns != evaluation_end:
        raise _fail("performance_evidence_not_at_the_evaluation_end")
    return rebuilt


def _prove_drawdown(
    inputs: PaperSleevePromotionDemotionInputs,
    envelope: PaperPortfolioRiskEnvelope,
    evaluation_end: int,
    performance: PaperSleevePerformanceEvidence,
) -> tuple[PaperSleeveDrawdownEvidence, PaperSleeveDrawdownRecord]:
    _require_exact(inputs.drawdown_inputs, PaperSleeveDrawdownInputs, "drawdown_inputs")
    _require_exact(inputs.drawdown_evidence, PaperSleeveDrawdownEvidence, "drawdown_evidence")
    rebuilt = _rebuild("drawdown", build_paper_sleeve_drawdown_evidence, inputs.drawdown_inputs)
    if not _canonically_equal(inputs.drawdown_evidence, rebuilt, paper_sleeve_drawdown_evidence_to_dict):
        raise _fail("drawdown_evidence_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("drawdown_evidence_envelope_mismatch")
    if rebuilt.window_end_ns != evaluation_end:
        raise _fail("drawdown_evidence_not_at_the_evaluation_end")
    targets = [record for record in rebuilt.sleeves if record.sleeve_id == performance.sleeve_id]
    if len(targets) != 1:
        raise _fail("drawdown_evidence_missing_the_target_sleeve")
    if targets[0].performance_evidence_digest != performance.performance_evidence_digest:
        raise _fail("drawdown_target_performance_mismatch")
    return rebuilt, targets[0]


def _prove_correlation(
    inputs: PaperSleevePromotionDemotionInputs,
    envelope: PaperPortfolioRiskEnvelope,
    evaluation_end: int,
    performance: PaperSleevePerformanceEvidence,
) -> PaperSleeveCorrelationEvidence:
    _require_exact(inputs.correlation_inputs, PaperSleeveCorrelationInputs, "correlation_inputs")
    _require_exact(inputs.correlation_evidence, PaperSleeveCorrelationEvidence, "correlation_evidence")
    rebuilt = _rebuild("correlation", build_paper_sleeve_correlation_evidence, inputs.correlation_inputs)
    if not _canonically_equal(inputs.correlation_evidence, rebuilt, paper_sleeve_correlation_evidence_to_dict):
        raise _fail("correlation_evidence_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("correlation_evidence_envelope_mismatch")
    if rebuilt.evaluation_end_ns != evaluation_end:
        raise _fail("correlation_evidence_not_at_the_evaluation_end")
    targets = [record for record in rebuilt.sleeves if record.sleeve_id == performance.sleeve_id]
    if len(targets) != 1:
        raise _fail("correlation_evidence_missing_the_target_sleeve")
    if targets[0].performance_evidence_digest != performance.performance_evidence_digest:
        raise _fail("correlation_target_performance_mismatch")
    return rebuilt


# --- the single decision assembly path ------------------------------------------------------------------------------


def _assemble_decision(
    inputs: PaperSleevePromotionDemotionInputs,
    predecessor: PaperSleeveLadderSeed | PaperSleevePromotionDemotionDecision,
) -> PaperSleevePromotionDemotionDecision:
    """Assemble one decision from its exact inputs and its ALREADY PROVEN predecessor.

    This is the one assembly path: the public builder uses it for the current decision, and the lineage proof uses it to
    rebuild every ancestor. The predecessor is the re-proven seed or the decision this path has just rebuilt for
    ``inputs.ladder_state``; the carried lineage is never read here.
    """

    decision_id = _require_text(inputs.decision_id, "decision_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    evaluation_end = _require_utc_day(inputs.evaluation_end_ns, "evaluation_end_ns")
    envelope = _require_envelope(inputs.portfolio_risk_envelope)
    lower, upper = _require_ladder(envelope)
    if type(predecessor) is PaperSleeveLadderSeed:
        state = _state_from_seed(predecessor, envelope, evaluation_end)
    else:
        state = _state_from_prior(cast(PaperSleevePromotionDemotionDecision, predecessor), envelope, evaluation_end)

    performance = _prove_performance(inputs, envelope, evaluation_end)
    if performance.sleeve_id != state.sleeve_id:
        raise _fail("performance_sleeve_not_the_lineage_sleeve")
    drawdown, target = _prove_drawdown(inputs, envelope, evaluation_end, performance)
    correlation = _prove_correlation(inputs, envelope, evaluation_end, performance)

    governance = list(state.governance)
    if envelope.advances is not True:
        governance.append(_reason("portfolio_risk_envelope_not_governed"))
    if performance.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("performance_evidence_needs_governance_approval"))
    if drawdown.status is PaperSleeveDrawdownStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("drawdown_evidence_needs_governance_approval"))
    if correlation.status is PaperSleeveCorrelationStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("correlation_evidence_needs_governance_approval"))
    unavailable = list(state.unavailable)
    if performance.status is PaperSleevePerformanceStatus.NOT_COMPUTABLE:
        unavailable.append(_reason("performance_evidence_not_computable"))
    elif performance.status is PaperSleevePerformanceStatus.READY and (
        target.computed is not True or target.measurement is None
    ):
        unavailable.append(_reason("drawdown_target_measurement_not_computed"))
    if governance:
        status = PaperSleeveLadderDecisionStatus.NEEDS_GOVERNANCE_APPROVAL
    elif unavailable:
        status = PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE
    else:
        status = PaperSleeveLadderDecisionStatus.READY

    tenure_days: int | None = None
    if state.entered_at_ns is not None:
        elapsed = evaluation_end - state.entered_at_ns
        if elapsed < 0 or elapsed % _DAY_NS:
            raise _fail("tier_tenure_not_whole_utc_days")
        tenure_days = elapsed // _DAY_NS

    movement: _Movement | None = None
    sharpe_text = drawdown_text = ""
    if status is PaperSleeveLadderDecisionStatus.READY:
        sharpe_text = performance.paper_sharpe_annualized
        drawdown_text = cast(PaperPeakDistanceMeasurement, target.measurement).max_peak_distance
        movement = _move(
            cast(PaperSleeveLadderTier, state.tier),
            cast(int, tenure_days),
            _decimal_fraction(sharpe_text, "performance_sharpe_invalid"),
            _peak_distance_fraction(drawdown_text),
            lower,
            upper,
        )

    entered_after: int | None = None
    if movement is not None:
        held = movement.transition is PaperSleeveLadderTransition.HOLD
        entered_after = state.entered_at_ns if held else evaluation_end

    draft = PaperSleevePromotionDemotionDecision(
        schema_version=_DECISION_SCHEMA,
        status=status,
        ready=status is PaperSleeveLadderDecisionStatus.READY,
        advances=status is PaperSleeveLadderDecisionStatus.READY,
        decision_id=decision_id,
        correlation_id=correlation_id,
        envelope_id=envelope.envelope_id,
        envelope_version=envelope.envelope_version,
        envelope_digest=envelope.envelope_digest,
        envelope_policy_digest=envelope.policy_digest,
        envelope_advances=envelope.advances,
        sleeve_id=performance.sleeve_id,
        market_symbol=performance.market_symbol,
        ladder_seed_digest=state.seed_digest,
        ladder_seed_advances=state.seed_advances,
        prior_decision_digest=state.prior_digest,
        lineage_sequence=state.sequence,
        evaluation_end_ns=evaluation_end,
        current_tier=state.tier,
        current_tier_entered_at_ns=state.entered_at_ns,
        tier_elapsed_days=tenure_days,
        transition=None if movement is None else movement.transition,
        resulting_tier=None if movement is None else movement.resulting_tier,
        resulting_tier_entered_at_ns=entered_after,
        performance_evidence_digest=performance.performance_evidence_digest,
        performance_status=performance.status.value,
        drawdown_evidence_digest=drawdown.drawdown_evidence_digest,
        drawdown_status=drawdown.status.value,
        correlation_evidence_digest=correlation.correlation_evidence_digest,
        correlation_status=correlation.status.value,
        paper_sharpe_annualized=sharpe_text,
        max_peak_distance=drawdown_text,
        drawdown_consumption=_DRAWDOWN_CONSUMPTION,
        promotion_boundary=None if movement is None else movement.promotion_boundary,
        demotion_boundary=None if movement is None else movement.demotion_boundary,
        decision_reason_codes=() if movement is None else _sorted_unique(movement.reasons),
        reason_codes=_sorted_unique(governance + unavailable),
        regime_concentration_demotion_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
        decision_digest="",
    )
    return replace(draft, decision_digest=edge_payload_digest(_payload(draft), _DECISION_DIGEST_FIELD))


# --- the non-recursive lineage proof --------------------------------------------------------------------------------


def _walk_to_seed(state: object) -> tuple[PaperSleeveLadderSeed, list[PaperSleeveLadderPriorDecision]]:
    """Follow the nested priors back to the seed in a loop, newest first; every node's exact type is checked first.

    Object identity guards against a malformed cyclic object graph only. It never enters an artifact or a digest, and
    it lives no longer than this call.
    """

    nodes: list[PaperSleeveLadderPriorDecision] = []
    visited: set[int] = set()
    while type(state) is not PaperSleeveLadderSeed:
        if type(state) is not PaperSleeveLadderPriorDecision:
            raise _fail("ladder_state_malformed")
        node = cast(PaperSleeveLadderPriorDecision, state)
        node_inputs = getattr(node, "decision_inputs", None)
        _require_exact(node_inputs, PaperSleevePromotionDemotionInputs, "prior_decision_inputs")
        _require_exact(getattr(node, "decision", None), PaperSleevePromotionDemotionDecision, "prior_decision")
        if id(node) in visited or id(node_inputs) in visited:
            raise _fail("ladder_state_cycle")
        visited.update((id(node), id(node_inputs)))
        nodes.append(node)
        state = cast(PaperSleevePromotionDemotionInputs, node_inputs).ladder_state
    return cast(PaperSleeveLadderSeed, state), nodes


def _require_proven_seed(seed: PaperSleeveLadderSeed) -> PaperSleeveLadderSeed:
    if not verify_paper_sleeve_ladder_seed(seed).intact:
        raise _fail("ladder_seed_not_intact")
    return seed


def _is_exact_rebuild(
    carried: PaperSleevePromotionDemotionDecision, rebuilt: PaperSleevePromotionDemotionDecision
) -> bool:
    """The carried decision is exactly the rebuild: its self-digest is intact and its wire form is canonically equal."""

    payload = _payload(carried)
    if payload[_DECISION_DIGEST_FIELD] != edge_payload_digest(payload, _DECISION_DIGEST_FIELD):
        return False
    return edge_canonical_json(payload) == edge_canonical_json(_payload(rebuilt))


def _proven_predecessor(state: object) -> PaperSleeveLadderSeed | PaperSleevePromotionDemotionDecision:
    """The proven predecessor for a decision whose ``ladder_state`` is ``state``, re-proven without recursion.

    The seed is re-proven, then every ancestor is rebuilt exactly once, oldest first, by ``_assemble_decision`` from its
    own exact inputs and the predecessor just rebuilt. A rebuild becomes the next predecessor only if the carried
    decision is exactly it. The rebuild, never the carried decision, is the state that flows forward.
    """

    seed, nodes = _walk_to_seed(state)
    if not nodes:
        return _require_proven_seed(seed)
    try:
        predecessor: PaperSleeveLadderSeed | PaperSleevePromotionDemotionDecision = _require_proven_seed(seed)
        for node in reversed(nodes):
            rebuilt = _assemble_decision(node.decision_inputs, predecessor)
            if not _is_exact_rebuild(node.decision, rebuilt):
                raise _fail("prior_decision_not_the_rebuild")
            predecessor = rebuilt
    except Exception as exc:  # noqa: BLE001 - a lineage that is not re-proven completely fails closed
        raise _fail("prior_decision_not_reproven") from exc
    return predecessor


# --- public decision API --------------------------------------------------------------------------------------------


def build_paper_sleeve_promotion_demotion_decision(
    inputs: PaperSleevePromotionDemotionInputs,
) -> PaperSleevePromotionDemotionDecision:
    """Decide one sleeve's ladder movement at ``evaluation_end_ns`` from its re-proven lineage and evidence.

    The lineage is re-proven first, without recursion; the decision is then assembled on the same path as every ancestor.
    Malformed input and every provenance, lineage or binding defect raise ``PaperSleeveLadderError``; missing governance
    yields ``NEEDS_GOVERNANCE_APPROVAL``; an unavailable target measurement yields ``NOT_COMPUTABLE``; otherwise exactly
    one HOLD, PROMOTE or DEMOTE. Inputs are never mutated.
    """

    _require_exact(inputs, PaperSleevePromotionDemotionInputs, "inputs")
    return _assemble_decision(inputs, _proven_predecessor(inputs.ladder_state))


def paper_sleeve_promotion_demotion_decision_to_dict(
    decision: PaperSleevePromotionDemotionDecision,
) -> dict[str, object]:
    """Canonical JSON-ready mapping of a decision, its self-digest included."""

    return _payload(decision)


def paper_sleeve_promotion_demotion_decision_digest(decision: PaperSleevePromotionDemotionDecision) -> str:
    """Recompute the canonical decision digest, excluding only ``decision_digest``."""

    return edge_payload_digest(_payload(decision), _DECISION_DIGEST_FIELD)


def verify_paper_sleeve_promotion_demotion_decision(
    decision: object, inputs: PaperSleevePromotionDemotionInputs
) -> EdgeEvidenceVerification:
    """Re-prove a decision by rebuilding it, whole lineage included, from its exact inputs. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(decision) is not PaperSleevePromotionDemotionDecision:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _payload(decision)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DECISION_DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _payload(build_paper_sleeve_promotion_demotion_decision(inputs))
        codes = {_reason("self_digest_mismatch")} if carried[_DECISION_DIGEST_FIELD] != recomputed else set()
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(_reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(_reason(f"field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(not reason_codes, reason_codes, recomputed, canonical)
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (_reason(stage),), "", "")


__all__ = [
    "PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS",
    "PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS",
    "PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST",
    "PaperSleeveLadderDecisionStatus",
    "PaperSleeveLadderError",
    "PaperSleeveLadderPriorDecision",
    "PaperSleeveLadderSeed",
    "PaperSleeveLadderSeedApproval",
    "PaperSleeveLadderSeedApprovalKind",
    "PaperSleeveLadderTransition",
    "PaperSleevePromotionDemotionDecision",
    "PaperSleevePromotionDemotionInputs",
    "build_paper_sleeve_ladder_seed",
    "build_paper_sleeve_promotion_demotion_decision",
    "paper_sleeve_ladder_seed_digest",
    "paper_sleeve_ladder_seed_from_payload",
    "paper_sleeve_ladder_seed_to_dict",
    "paper_sleeve_promotion_demotion_decision_digest",
    "paper_sleeve_promotion_demotion_decision_to_dict",
    "paper_sleeve_promotion_demotion_rule_set",
    "verify_paper_sleeve_ladder_seed",
    "verify_paper_sleeve_promotion_demotion_decision",
]
