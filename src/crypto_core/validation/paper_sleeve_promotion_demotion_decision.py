"""RG-6 paper sleeve promotion and demotion decision (RG6_PAPER_SLEEVE_PROMOTION_DEMOTION_DECISION_V1).

``docs/crypto_core/multi_sleeve_risk_governance_design.md`` §1 (RG-6), under the controller structural authority
``RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1``. One decision moves ONE sleeve at most one adjacent step
on the RG-2 ladder ``PROBATION -> STANDARD -> EXPANDED``, or holds it, from fully re-proven evidence. It decides sleeve
ladder movement ONLY: no allocation, correlation-cap breach, diversification credit, kill or quarantine, portfolio
stop, order, execution, capital or readiness.

Ladder-state lineage:

* genesis: a governed ``PaperSleeveLadderSeed`` binds the exact RG-2 envelope (id, version and digest), one declared
  sleeve, the structurally fixed initial tier ``PROBATION`` and the explicit UTC-day-aligned ``tier_entered_at_ns``
  state fact. Only an exact ``HUMAN_GOVERNANCE`` approval of the seed id, version, seed policy digest and RG-6 rule-set
  digest advances it; a ``TEST_ONLY_SYNTHETIC`` approval never does;
* every later decision takes the current tier and its entry ONLY from exactly one prior RG-6 decision of the same
  lineage, re-proven by rebuilding it from its exact inputs (recursively down to the seed). The caller never supplies a
  current tier, a tier-entry time or a previous transition. The prior must bind the same sleeve and the same envelope,
  and the evaluation end must strictly increase. An authentic prior that does not advance propagates its status: only
  a READY decision is a valid predecessor;
* history, never current authority: a decision proves only that its exact transition, from its exact authenticated
  state, met every committed rule at its coordinate. No registry, head or latest-decision lookup exists, so
  ``current_ladder_head_proven`` is structurally False.

Evidence, each REBUILT through its accepted public builder and required to equal the supplied artifact canonically;
only the reconstruction is used:

* RG-2: the envelope is re-pinned through its total verifier and owns every ladder threshold;
* RG-3: the target ``PaperSleevePerformanceEvidence``. Its sleeve is the lineage sleeve, and its window ends exactly at
  ``evaluation_end_ns``;
* RG-4: the ``PaperSleeveDrawdownEvidence`` over the same envelope and window end. Its record of the target sleeve must
  bind the exact target RG-3 digest;
* RG-5: the ``PaperSleeveCorrelationEvidence`` at the same evaluation end. Its record of the target sleeve must bind the
  exact target RG-3 digest. RG-5 is provenance only: no correlation is compared with the cap, and no worst-case pair
  moves a sleeve.

Decision (code-defined rule set ``PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST``):

* tenure: ``tier_elapsed_days = (evaluation_end_ns - current_tier_entered_at_ns) / day``, exact for UTC-aligned
  coordinates;
* metrics: the RG-3 ``paper_sharpe_annualized`` and the RG-4 ``max_peak_distance`` of the target sleeve, for promotion
  and demotion alike (``MAX_PEAK_DISTANCE``); the current peak distance is never consumed;
* promotion over a boundary needs ALL of ``tier_elapsed_days >= min_probation_days``,
  ``sharpe >= promotion_min_paper_sharpe`` and ``max_peak_distance <= promotion_max_drawdown_fraction``;
* demotion over a boundary needs ANY of ``sharpe < demotion_min_paper_sharpe`` or
  ``max_peak_distance > demotion_max_drawdown_fraction``;
* PROBATION may only promote and EXPANDED may only demote. STANDARD evaluates demotion FIRST and, when it applies,
  never evaluates promotion. The RG-2 consistency invariant, re-pinned on the reconstructed ladder, already rules out a
  snapshot eligible for both; a ladder that contradicts it fails closed;
* at most one adjacent transition: HOLD keeps the tier and its entry; PROMOTE or DEMOTE moves one tier and enters it at
  ``evaluation_end_ns``.

Status precedence: a provenance or binding defect raises ``PaperSleeveLadderError``. ``NEEDS_GOVERNANCE_APPROVAL`` when
the envelope, the genesis seed, a re-proven evidence or the prior does not advance its governance; otherwise
``NOT_COMPUTABLE`` when the target measurement is unavailable or the prior was not computable; otherwise ``READY``, one
evaluated transition. Consumed metric values and the transition are carried only when READY.

Regime-concentration demotion stays ``PENDING_RF_LABEL_ENUM_UNAVAILABLE`` and unevaluated until an accepted RF chain
exists; ``crypto_core.regime`` is never imported. ``verify_paper_sleeve_ladder_seed`` and
``verify_paper_sleeve_promotion_demotion_decision`` are total. Exact ``Fraction`` comparisons, no float, no ``decimal``,
and no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
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

_SEED_SCHEMA_VERSION = "paper-sleeve-ladder-seed.v1"
_DECISION_SCHEMA_VERSION = "paper-sleeve-promotion-demotion-decision.v1"
_REASON_PREFIX = "paper_sleeve_promotion_demotion_decision"
_SEED_DIGEST_FIELD = "ladder_seed_digest"
_DECISION_DIGEST_FIELD = "decision_digest"
_IDENTIFIER_EXTRA_CHARS = frozenset("-_./:")
_T = TypeVar("_T")

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_sleeve_promotion_demotion_decision_rules.v1",
    "structural_authority_id": "RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1",
    "scope_rule_id": "sleeve_ladder_movement_only_never_allocation_cap_diversification_kill_stop_or_execution.v1",
    "genesis_rule_id": "a_lineage_starts_only_at_a_governed_seed_whose_initial_tier_is_probation.v1",
    "genesis_tier": "PROBATION",
    "seed_governance_rule_id": "approval_commits_seed_id_version_seed_policy_digest_and_rule_set_digest.v1",
    "seed_gate_rule_id": "pass_iff_exact_matching_human_governance_approval_test_only_synthetic_never_advances.v1",
    "lineage_rule_id": "later_state_only_from_one_reproven_prior_decision_of_the_same_sleeve_and_envelope.v1",
    "prior_rule_id": "only_a_ready_prior_advances_a_non_advancing_prior_propagates_its_status.v1",
    "head_rule_id": "explicit_chain_history_only_no_registry_and_no_current_ladder_head_claim.v1",
    "evaluation_rule_id": "injected_utc_aligned_evaluation_end_after_the_prior_and_not_before_the_tier_entry.v1",
    "tenure_rule_id": "exact_utc_days_from_the_current_tier_entry_to_the_evaluation_end.v1",
    "evidence_coherence_rule_id": "reproven_rg3_rg4_rg5_on_the_envelope_ending_exactly_at_the_evaluation_end.v1",
    "performance_metric_id": "paper-sharpe-evidence.v1:paper_sharpe_annualized",
    "drawdown_consumption": "MAX_PEAK_DISTANCE",
    "drawdown_metric_rule_id": "rg4_target_sleeve_max_peak_distance_for_promotion_and_demotion_never_current.v1",
    "correlation_rule_id": "rg5_reproven_provenance_only_the_cap_is_never_evaluated_and_no_pair_moves_a_sleeve.v1",
    "promotion_rule_id": "tenure_at_least_min_probation_days_sharpe_at_least_floor_max_drawdown_at_most_ceiling.v1",
    "demotion_rule_id": "sharpe_strictly_below_floor_or_max_drawdown_strictly_above_ceiling.v1",
    "precedence_rule_id": "standard_evaluates_demotion_first_and_never_promotion_once_demoted.v1",
    "ladder_consistency_rule_id": "reproven_rg2_ladder_contradicting_its_consistency_invariant_fails_closed.v1",
    "transition_rule_id": "at_most_one_adjacent_transition_per_decision_no_skip_no_loop.v1",
    "tier_entry_rule_id": "hold_keeps_the_tier_entry_a_transition_enters_at_the_evaluation_end.v1",
    "regime_rule_id": "regime_concentration_demotion_pending_until_an_accepted_rf_chain.v1",
    "status_rule_id": "needs_governance_approval_over_not_computable_over_ready.v1",
    "numeric_rule_id": "exact_fraction_comparison_of_canonical_texts_no_float_no_decimal.v1",
    "utc_day_ns": 86_400_000_000_000,
    "decimal_scale": 18,
    "fraction_max_part_digits": 4096,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_sleeve_id_length": 128,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_GENESIS_TIER = PaperSleeveLadderTier(str(_RULE_SET_V1["genesis_tier"]))
_DRAWDOWN_CONSUMPTION = str(_RULE_SET_V1["drawdown_consumption"])
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_DECIMAL_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_MAX_FRACTION_DIGITS: int = _RULE_SET_V1["fraction_max_part_digits"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_SLEEVE_ID: int = _RULE_SET_V1["max_sleeve_id_length"]  # type: ignore[assignment]


def paper_sleeve_promotion_demotion_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class PaperSleeveLadderError(EdgeArtifactError):
    """Raised on malformed input or any provenance, lineage or binding defect: an invalid record is never represented."""


class PaperSleeveLadderSeedApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` approvals exist for tests only: they are surfaced and never advance a seed."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class PaperSleeveLadderDecisionStatus(str, Enum):
    """READY is one evaluated transition; the other states carry no transition and no consumed metric."""

    READY = "READY"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class PaperSleeveLadderTransition(str, Enum):
    """At most one adjacent step per decision."""

    HOLD = "HOLD"
    PROMOTE = "PROMOTE"
    DEMOTE = "DEMOTE"


@dataclass(frozen=True)
class PaperSleeveLadderSeedApproval:
    """Governance approval of one exact seed: every commitment must equal the assembled value."""

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
_SEED_FLAG_NAMES = frozenset(name for name, _ in PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS)


@dataclass(frozen=True)
class PaperSleeveLadderSeed:
    """Immutable, digest-bound genesis of one sleeve's ladder lineage. Its initial tier is always PROBATION."""

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
    """Immutable, digest-bound RG-6 ladder decision of one sleeve at one evaluation end. History, never a current head."""

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
    """Everything one RG-6 decision consumes; consumers re-prove a decision by rebuilding it from exactly these."""

    decision_id: str
    correlation_id: str
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    ladder_state: PaperSleeveLadderSeed | PaperSleeveLadderPriorDecision
    evaluation_end_ns: int
    performance_inputs: PaperSleevePerformanceInputs
    performance_evidence: PaperSleevePerformanceEvidence
    drawdown_inputs: PaperSleeveDrawdownInputs
    drawdown_evidence: PaperSleeveDrawdownEvidence
    correlation_inputs: PaperSleeveCorrelationInputs
    correlation_evidence: PaperSleeveCorrelationEvidence


@dataclass(frozen=True)
class PaperSleeveLadderPriorDecision:
    """The exact prior RG-6 decision of the same lineage and the exact inputs it is rebuilt from."""

    decision_inputs: PaperSleevePromotionDemotionInputs
    decision: PaperSleevePromotionDemotionDecision


# Everything outside the governed seed policy: the approval, the verdict it yields, and the two digests themselves.
_NON_POLICY_SEED_FIELDS = frozenset(
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
_RECORD_TYPES = frozenset({PaperSleeveLadderSeedApproval, PaperSleeveLadderBoundary})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperSleeveLadderSeedApproval: {"approval_kind": PaperSleeveLadderSeedApprovalKind},
    PaperSleeveLadderSeed: {"gate_verdict": EdgeGateVerdict, "initial_tier": PaperSleeveLadderTier},
    PaperSleeveLadderBoundary: {"lower_tier": PaperSleeveLadderTier, "upper_tier": PaperSleeveLadderTier},
    PaperSleevePromotionDemotionDecision: {
        "status": PaperSleeveLadderDecisionStatus,
        "current_tier": PaperSleeveLadderTier,
        "transition": PaperSleeveLadderTransition,
        "resulting_tier": PaperSleeveLadderTier,
    },
}
_OPTIONAL_ENUM_FIELDS = frozenset({"current_tier", "transition", "resulting_tier"})


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperSleeveLadderError:
    return PaperSleeveLadderError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_identifier(value: object, field_name: str) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_SLEEVE_ID or not value.isascii():
        raise _fail(f"{field_name}_invalid")
    if not value[0].isalnum() or any(not (char.isalnum() or char in _IDENTIFIER_EXTRA_CHARS) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str and value in {member.value for member in enum_cls}:
        return enum_cls(value)
    raise _fail(f"{field_name}_invalid")


def _require_day_coordinate(value: object, field_name: str) -> int:
    """An exact non-negative int64 UTC-day-aligned epoch-nanosecond coordinate; never a bool and never a clock."""

    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    if value % _DAY_NS != 0:
        raise _fail(f"{field_name}_not_utc_day_aligned")
    return value


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    """Call one accepted public builder; any failure is a provenance defect of this decision."""

    try:
        return builder(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed at this boundary
        raise _fail(f"{code}_reconstruction_failed") from exc


def _scale18_value(value: object, code: str) -> Fraction:
    """The exact value of canonical fixed scale-18 decimal text, signed zero excluded.

    It reads the RG-3 annualized Sharpe, whose accepted producer quantizes within precision 80, and the RG-2 thresholds,
    which RG-2 bounds; both are bounded texts already, so this grammar only re-pins their canonical form.
    """

    if type(value) is not str or not value.isascii():
        raise _fail(code)
    negative = value.startswith("-")
    integer, dot, digits = (value[1:] if negative else value).partition(".")
    if dot != "." or len(digits) != _DECIMAL_SCALE or not _ascii_digits(integer) or not _ascii_digits(digits):
        raise _fail(code)
    if (integer != "0" and integer.startswith("0")) or (negative and integer == "0" and digits.strip("0") == ""):
        raise _fail(code)
    try:
        units = int(integer + digits)
    except ValueError as exc:
        raise _fail(code) from exc
    return Fraction(-units if negative else units, 10**_DECIMAL_SCALE)


def _peak_distance_value(value: object) -> Fraction:
    """The exact value of an RG-4 peak distance: canonical reduced fraction text ``"p/q"`` in ``[0, 1)``."""

    if type(value) is not str or not value.isascii():
        raise _fail("drawdown_peak_distance_invalid")
    numerator, slash, denominator = value.partition("/")
    if slash != "/" or not _ascii_digits(numerator) or not _ascii_digits(denominator):
        raise _fail("drawdown_peak_distance_invalid")
    if len(numerator) > _MAX_FRACTION_DIGITS or len(denominator) > _MAX_FRACTION_DIGITS:
        raise _fail("drawdown_peak_distance_invalid")
    if (numerator != "0" and numerator.startswith("0")) or denominator.startswith("0"):
        raise _fail("drawdown_peak_distance_invalid")
    parsed = Fraction(int(numerator), int(denominator))
    if f"{parsed.numerator}/{parsed.denominator}" != value or not 0 <= parsed < 1:
        raise _fail("drawdown_peak_distance_invalid")
    return parsed


# --- serialization --------------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in value]
    if type(value) is int:
        if value < 0 or value > _MAX_WIRE_INT:
            raise _fail("payload_integer_out_of_range")
        return value
    if value is None or type(value) in (str, bool):
        return value
    raise _fail("payload_value_not_canonical")


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize exactly: an enum field must hold the exact member and every other value an exact builtin or record."""

    enum_fields = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for field in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, field.name)
        enum_cls = enum_fields.get(field.name)
        if enum_cls is None:
            payload[field.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[field.name] = value.value
        elif value is None and field.name in _OPTIONAL_ENUM_FIELDS:
            payload[field.name] = None
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


# --- the governed genesis seed --------------------------------------------------------------------------------------


def _canonical_seed_approval(approval: object) -> PaperSleeveLadderSeedApproval | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if approval is None:
        return None
    if type(approval) is not PaperSleeveLadderSeedApproval:
        raise _fail("seed_governance_approval_malformed")

    def attribute(name: str) -> object:
        return getattr(approval, name, None)

    return PaperSleeveLadderSeedApproval(
        approval_reference=_require_text(attribute("approval_reference"), "seed_governance_approval_reference"),
        approval_digest=_require_hex64(attribute("approval_digest"), "seed_governance_approval_digest"),
        approval_kind=_require_member(  # type: ignore[arg-type]
            attribute("approval_kind"), PaperSleeveLadderSeedApprovalKind, "seed_governance_approval_kind"
        ),
        approved_seed_id=_require_text(attribute("approved_seed_id"), "seed_governance_approved_seed_id"),
        approved_seed_version=_require_text(
            attribute("approved_seed_version"), "seed_governance_approved_seed_version"
        ),
        approved_seed_policy_digest=_require_hex64(
            attribute("approved_seed_policy_digest"), "seed_governance_approved_seed_policy_digest"
        ),
        approved_rule_set_digest=_require_hex64(
            attribute("approved_rule_set_digest"), "seed_governance_approved_rule_set_digest"
        ),
    )


def _seed_governance_reasons(approval: PaperSleeveLadderSeedApproval | None, committed: Mapping[str, str]) -> list[str]:
    if approval is None:
        return [_reason("seed_governance_approval_missing")]
    reasons = [
        _reason(f"seed_governance_approval_{name}_mismatch")
        for name, value in committed.items()
        if getattr(approval, f"approved_{name}") != value
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
    """The one seed assembly path, shared by the builder and verifier reassembly."""

    seed_id = _require_text(seed_id, "seed_id")
    seed_version = _require_text(seed_version, "seed_version")
    envelope_id = _require_text(envelope_id, "seed_envelope_id")
    envelope_version = _require_text(envelope_version, "seed_envelope_version")
    envelope_digest = _require_hex64(envelope_digest, "seed_envelope_digest")
    sleeve_id = _require_identifier(sleeve_id, "seed_sleeve_id")
    entered = _require_day_coordinate(tier_entered_at_ns, "tier_entered_at_ns")
    approval_record = _canonical_seed_approval(approval)

    seed = PaperSleeveLadderSeed(
        schema_version=_SEED_SCHEMA_VERSION,
        gate_verdict=EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        advances=False,
        seed_id=seed_id,
        seed_version=seed_version,
        envelope_id=envelope_id,
        envelope_version=envelope_version,
        envelope_digest=envelope_digest,
        sleeve_id=sleeve_id,
        initial_tier=_GENESIS_TIER,
        tier_entered_at_ns=entered,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
        seed_policy_digest="",
        approval=approval_record,
        synthetic_test_approval_used=approval_record is not None
        and approval_record.approval_kind is PaperSleeveLadderSeedApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=(),
        ladder_seed_digest="",
    )
    policy_digest = edge_sha256_text(
        edge_canonical_json(
            {name: value for name, value in _to_payload(seed).items() if name not in _NON_POLICY_SEED_FIELDS}
        )
    )
    committed = {
        "seed_id": seed_id,
        "seed_version": seed_version,
        "seed_policy_digest": policy_digest,
        "rule_set_digest": PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
    }
    needs_governance = _seed_governance_reasons(approval_record, committed)
    verdict = resolve_edge_gate_verdict([], [], needs_governance)
    governed = replace(
        seed,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        seed_policy_digest=policy_digest,
        verdict_reason_codes=_sorted_unique(needs_governance),
    )
    return replace(governed, ladder_seed_digest=edge_payload_digest(_to_payload(governed), _SEED_DIGEST_FIELD))


def _require_envelope(value: object) -> PaperPortfolioRiskEnvelope:
    _require_exact(value, PaperPortfolioRiskEnvelope, "portfolio_risk_envelope")
    if not verify_paper_portfolio_risk_envelope(value).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    envelope = cast(PaperPortfolioRiskEnvelope, value)
    if envelope.rule_set_digest != PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST:
        raise _fail("portfolio_risk_envelope_rule_set_unsupported")
    # V1 evaluates no regime-concentration demotion: an envelope that no longer marks it pending is out of scope.
    if envelope.regime_concentration_demotion_status != EDGE_REGIME_LABEL_BINDING_PENDING:
        raise _fail("regime_concentration_demotion_status_unsupported")
    return envelope


def _declared_sleeves(envelope: PaperPortfolioRiskEnvelope) -> frozenset[str]:
    return frozenset(cap.sleeve_id for cap in envelope.sleeve_caps)


def build_paper_sleeve_ladder_seed(
    *,
    seed_id: str,
    seed_version: str,
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope,
    sleeve_id: str,
    tier_entered_at_ns: int,
    approval: PaperSleeveLadderSeedApproval | None,
) -> PaperSleeveLadderSeed:
    """Build the governed genesis of one sleeve's ladder lineage; its initial tier is always PROBATION.

    The envelope is re-proven through its total verifier and must declare the sleeve. ``tier_entered_at_ns`` is an
    explicit UTC-day-aligned state fact, never a clock. Malformed input raises ``PaperSleeveLadderError``. A missing,
    non-matching or ``TEST_ONLY_SYNTHETIC`` approval yields ``NEEDS_GOVERNANCE_APPROVAL``; only an exact
    ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``.
    """

    envelope = _require_envelope(portfolio_risk_envelope)
    sleeve = _require_identifier(sleeve_id, "seed_sleeve_id")
    if sleeve not in _declared_sleeves(envelope):
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
    """Canonical JSON-ready mapping of a seed, including its self-digest."""

    return _to_payload(seed)


def paper_sleeve_ladder_seed_digest(seed: PaperSleeveLadderSeed) -> str:
    """Recompute the canonical seed digest, excluding only ``ladder_seed_digest``."""

    return edge_payload_digest(_to_payload(seed), _SEED_DIGEST_FIELD)


# --- strict seed parsing --------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
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


def _as_optional_approval(value: object) -> object:
    if value is None:
        return None
    return _parse_exact(
        PaperSleeveLadderSeedApproval, value, {"approval_kind": _as_enum(PaperSleeveLadderSeedApprovalKind)}
    )


_SEED_CONVERTERS: dict[str, Callable[[object], object]] = {
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "initial_tier": _as_enum(PaperSleeveLadderTier),
    "tier_entered_at_ns": _as_int,
    "approval": _as_optional_approval,
    "synthetic_test_approval_used": _as_bool,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_SEED_FLAG_NAMES, _as_bool),
}


def paper_sleeve_ladder_seed_from_payload(payload: object) -> PaperSleeveLadderSeed:
    """Strictly reconstruct a seed from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(PaperSleeveLadderSeed, payload, _SEED_CONVERTERS)  # type: ignore[return-value]


def _reassemble_seed(seed: object) -> PaperSleeveLadderSeed:
    return _assemble_seed(
        seed_id=seed.seed_id,  # type: ignore[attr-defined]
        seed_version=seed.seed_version,  # type: ignore[attr-defined]
        envelope_id=seed.envelope_id,  # type: ignore[attr-defined]
        envelope_version=seed.envelope_version,  # type: ignore[attr-defined]
        envelope_digest=seed.envelope_digest,  # type: ignore[attr-defined]
        sleeve_id=seed.sleeve_id,  # type: ignore[attr-defined]
        tier_entered_at_ns=seed.tier_entered_at_ns,  # type: ignore[attr-defined]
        approval=seed.approval,  # type: ignore[attr-defined]
    )


def verify_paper_sleeve_ladder_seed(seed: object) -> EdgeEvidenceVerification:
    """Re-prove a seed by strict parse, self-digest recomputation and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        seed,
        cls=PaperSleeveLadderSeed,
        to_payload=_to_payload,
        parse_payload=paper_sleeve_ladder_seed_from_payload,
        reassemble=_reassemble_seed,
        self_digest_field=_SEED_DIGEST_FIELD,
        reason=_reason,
    )


# --- the lineage state ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _LineageState:
    sleeve_id: str
    ladder_seed_digest: str
    ladder_seed_advances: bool
    prior_decision_digest: str
    lineage_sequence: int
    current_tier: PaperSleeveLadderTier | None
    current_tier_entered_at_ns: int | None
    governance: tuple[str, ...]
    unavailable: tuple[str, ...]


def _seed_lineage(value: object, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int) -> _LineageState:
    if not verify_paper_sleeve_ladder_seed(value).intact:
        raise _fail("ladder_seed_not_intact")
    seed = cast(PaperSleeveLadderSeed, value)
    if seed.rule_set_digest != PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST:
        raise _fail("ladder_seed_rule_set_unsupported")
    if (seed.envelope_id, seed.envelope_version, seed.envelope_digest) != (
        envelope.envelope_id,
        envelope.envelope_version,
        envelope.envelope_digest,
    ):
        raise _fail("ladder_seed_envelope_mismatch")
    if seed.sleeve_id not in _declared_sleeves(envelope):
        raise _fail("ladder_seed_sleeve_not_declared_by_envelope")
    if seed.initial_tier is not _GENESIS_TIER:
        raise _fail("ladder_seed_initial_tier_not_probation")
    if evaluation_end < seed.tier_entered_at_ns:
        raise _fail("evaluation_end_precedes_the_tier_entry")
    governance = () if seed.advances is True else (_reason("ladder_seed_not_governed"),)
    return _LineageState(
        sleeve_id=seed.sleeve_id,
        ladder_seed_digest=seed.ladder_seed_digest,
        ladder_seed_advances=seed.advances,
        prior_decision_digest="",
        lineage_sequence=0,
        current_tier=seed.initial_tier,
        current_tier_entered_at_ns=seed.tier_entered_at_ns,
        governance=governance,
        unavailable=(),
    )


def _prior_lineage(value: object, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int) -> _LineageState:
    prior = cast(PaperSleeveLadderPriorDecision, value)
    _require_exact(getattr(prior, "decision_inputs", None), PaperSleevePromotionDemotionInputs, "prior_decision_inputs")
    _require_exact(getattr(prior, "decision", None), PaperSleevePromotionDemotionDecision, "prior_decision")
    if not verify_paper_sleeve_promotion_demotion_decision(prior.decision, prior.decision_inputs).intact:
        raise _fail("prior_decision_not_reproven")
    decision = prior.decision
    if decision.rule_set_digest != PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST:
        raise _fail("prior_decision_rule_set_unsupported")
    if (decision.envelope_id, decision.envelope_version, decision.envelope_digest) != (
        envelope.envelope_id,
        envelope.envelope_version,
        envelope.envelope_digest,
    ):
        raise _fail("prior_decision_envelope_mismatch")
    if evaluation_end <= decision.evaluation_end_ns:
        raise _fail("evaluation_end_not_after_the_prior_decision")
    governance: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    current_tier: PaperSleeveLadderTier | None = None
    entered: int | None = None
    if decision.advances is True:
        current_tier, entered = decision.resulting_tier, decision.resulting_tier_entered_at_ns
        if current_tier is None or entered is None or evaluation_end < entered:
            raise _fail("prior_decision_resulting_state_invalid")
    elif decision.status is PaperSleeveLadderDecisionStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance = (_reason("prior_decision_not_advancing"),)
    else:
        unavailable = (_reason("prior_decision_not_advancing"),)
    return _LineageState(
        sleeve_id=decision.sleeve_id,
        ladder_seed_digest=decision.ladder_seed_digest,
        ladder_seed_advances=decision.ladder_seed_advances,
        prior_decision_digest=decision.decision_digest,
        lineage_sequence=decision.lineage_sequence + 1,
        current_tier=current_tier,
        current_tier_entered_at_ns=entered,
        governance=governance,
        unavailable=unavailable,
    )


def _lineage(value: object, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int) -> _LineageState:
    if type(value) is PaperSleeveLadderSeed:
        return _seed_lineage(value, envelope, evaluation_end)
    if type(value) is PaperSleeveLadderPriorDecision:
        return _prior_lineage(value, envelope, evaluation_end)
    raise _fail("ladder_state_malformed")


# --- evidence re-proof ----------------------------------------------------------------------------------------------


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
    if rebuilt.sleeve_id not in _declared_sleeves(envelope):
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
    records = [record for record in rebuilt.sleeves if record.sleeve_id == performance.sleeve_id]
    if len(records) != 1:
        raise _fail("drawdown_evidence_missing_the_target_sleeve")
    if records[0].performance_evidence_digest != performance.performance_evidence_digest:
        raise _fail("drawdown_target_performance_mismatch")
    return rebuilt, records[0]


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
    records = [record for record in rebuilt.sleeves if record.sleeve_id == performance.sleeve_id]
    if len(records) != 1:
        raise _fail("correlation_evidence_missing_the_target_sleeve")
    if records[0].performance_evidence_digest != performance.performance_evidence_digest:
        raise _fail("correlation_target_performance_mismatch")
    return rebuilt


# --- the transition -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Outcome:
    transition: PaperSleeveLadderTransition
    resulting_tier: PaperSleeveLadderTier
    promotion_boundary: PaperSleeveLadderBoundary | None
    demotion_boundary: PaperSleeveLadderBoundary | None
    reasons: tuple[str, ...]


def _threshold(value: object) -> Fraction:
    return _scale18_value(value, "ladder_threshold_invalid")


def _require_consistent_ladder(ladder: object) -> tuple[PaperSleeveLadderBoundary, PaperSleeveLadderBoundary]:
    """Re-pin the accepted ordered RG-2 ladder and its consistency invariant; any contradiction fails closed.

    Within each boundary the promotion floor is at least the demotion floor and the promotion ceiling at most the
    demotion ceiling. Across the middle tier the upper promotion thresholds are no looser than the lower demotion
    thresholds. Together they keep one snapshot from being promotion- and demotion-eligible from the same tier.
    """

    if type(ladder) is not tuple or len(ladder) != 2:
        raise _fail("ladder_boundaries_not_the_accepted_ladder")
    if any(type(item) is not PaperSleeveLadderBoundary for item in ladder):
        raise _fail("ladder_boundaries_not_the_accepted_ladder")
    lower, upper = ladder
    if (lower.lower_tier, lower.upper_tier, upper.lower_tier, upper.upper_tier) != (
        PaperSleeveLadderTier.PROBATION,
        PaperSleeveLadderTier.STANDARD,
        PaperSleeveLadderTier.STANDARD,
        PaperSleeveLadderTier.EXPANDED,
    ):
        raise _fail("ladder_boundaries_not_the_accepted_ladder")
    for boundary in ladder:
        if type(boundary.min_probation_days) is not int or boundary.min_probation_days < 1:
            raise _fail("ladder_boundaries_not_the_accepted_ladder")
    for promotion, demotion in ((lower, lower), (upper, upper), (upper, lower)):
        if _threshold(promotion.promotion_min_paper_sharpe) < _threshold(demotion.demotion_min_paper_sharpe):
            raise _fail("ladder_consistency_invariant_violated")
        if _threshold(promotion.promotion_max_drawdown_fraction) > _threshold(demotion.demotion_max_drawdown_fraction):
            raise _fail("ladder_consistency_invariant_violated")
    return lower, upper


def _promotion_checks(
    boundary: PaperSleeveLadderBoundary, tenure_days: int, sharpe: Fraction, drawdown: Fraction
) -> tuple[bool, list[str]]:
    """ALL of tenure, Sharpe floor and max-drawdown ceiling, each inclusive."""

    tenure_met = tenure_days >= boundary.min_probation_days
    sharpe_met = sharpe >= _threshold(boundary.promotion_min_paper_sharpe)
    drawdown_met = drawdown <= _threshold(boundary.promotion_max_drawdown_fraction)
    reasons = [
        _reason("promotion_tenure_met" if tenure_met else "promotion_tenure_insufficient"),
        _reason("promotion_sharpe_floor_met" if sharpe_met else "promotion_sharpe_below_floor"),
        _reason("promotion_max_drawdown_ceiling_met" if drawdown_met else "promotion_max_drawdown_above_ceiling"),
    ]
    return tenure_met and sharpe_met and drawdown_met, reasons


def _demotion_checks(
    boundary: PaperSleeveLadderBoundary, sharpe: Fraction, drawdown: Fraction
) -> tuple[bool, list[str]]:
    """ANY of a Sharpe strictly below the floor or a max drawdown strictly above the ceiling."""

    sharpe_breach = sharpe < _threshold(boundary.demotion_min_paper_sharpe)
    drawdown_breach = drawdown > _threshold(boundary.demotion_max_drawdown_fraction)
    reasons = [
        _reason("demotion_sharpe_strictly_below_floor" if sharpe_breach else "demotion_sharpe_floor_held"),
        _reason(
            "demotion_max_drawdown_strictly_above_ceiling" if drawdown_breach else "demotion_max_drawdown_ceiling_held"
        ),
    ]
    return sharpe_breach or drawdown_breach, reasons


def _evaluate_transition(
    current_tier: PaperSleeveLadderTier,
    tenure_days: int,
    sharpe: Fraction,
    drawdown: Fraction,
    lower: PaperSleeveLadderBoundary,
    upper: PaperSleeveLadderBoundary,
) -> _Outcome:
    """The one adjacent transition of ``current_tier`` over the ordered ladder ``(lower, upper)``, or HOLD.

    PROBATION may only promote over ``lower`` and EXPANDED may only demote over ``upper``. STANDARD evaluates demotion
    over ``lower`` FIRST and, when it applies, never evaluates promotion over ``upper``.
    """

    if current_tier is PaperSleeveLadderTier.PROBATION:
        promote, reasons = _promotion_checks(lower, tenure_days, sharpe, drawdown)
        reasons.append(_reason("no_demotion_below_probation"))
        if promote:
            return _Outcome(
                PaperSleeveLadderTransition.PROMOTE, PaperSleeveLadderTier.STANDARD, lower, None, tuple(reasons)
            )
        return _Outcome(PaperSleeveLadderTransition.HOLD, PaperSleeveLadderTier.PROBATION, lower, None, tuple(reasons))
    if current_tier is PaperSleeveLadderTier.STANDARD:
        demote, reasons = _demotion_checks(lower, sharpe, drawdown)
        reasons.append(_reason("demotion_evaluated_before_promotion"))
        if demote:
            reasons.append(_reason("promotion_not_evaluated_after_demotion"))
            return _Outcome(
                PaperSleeveLadderTransition.DEMOTE, PaperSleeveLadderTier.PROBATION, None, lower, tuple(reasons)
            )
        promote, promotion_reasons = _promotion_checks(upper, tenure_days, sharpe, drawdown)
        reasons.extend(promotion_reasons)
        if promote:
            return _Outcome(
                PaperSleeveLadderTransition.PROMOTE, PaperSleeveLadderTier.EXPANDED, upper, lower, tuple(reasons)
            )
        return _Outcome(PaperSleeveLadderTransition.HOLD, PaperSleeveLadderTier.STANDARD, upper, lower, tuple(reasons))
    if current_tier is PaperSleeveLadderTier.EXPANDED:
        demote, reasons = _demotion_checks(upper, sharpe, drawdown)
        reasons.append(_reason("no_promotion_above_expanded"))
        if demote:
            return _Outcome(
                PaperSleeveLadderTransition.DEMOTE, PaperSleeveLadderTier.STANDARD, None, upper, tuple(reasons)
            )
        return _Outcome(PaperSleeveLadderTransition.HOLD, PaperSleeveLadderTier.EXPANDED, None, upper, tuple(reasons))
    raise _fail("current_tier_invalid")


# --- the decision ---------------------------------------------------------------------------------------------------


def build_paper_sleeve_promotion_demotion_decision(
    inputs: PaperSleevePromotionDemotionInputs,
) -> PaperSleevePromotionDemotionDecision:
    """Decide one sleeve's ladder movement at ``evaluation_end_ns`` from its lineage state and re-proven evidence.

    Malformed input and every provenance, lineage or binding defect raise ``PaperSleeveLadderError``. Missing governance
    yields ``NEEDS_GOVERNANCE_APPROVAL``; an unavailable target measurement yields ``NOT_COMPUTABLE``; otherwise exactly
    one HOLD, PROMOTE or DEMOTE is evaluated. Inputs are read once and never mutated.
    """

    _require_exact(inputs, PaperSleevePromotionDemotionInputs, "inputs")
    decision_id = _require_text(inputs.decision_id, "decision_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    evaluation_end = _require_day_coordinate(inputs.evaluation_end_ns, "evaluation_end_ns")
    envelope = _require_envelope(inputs.portfolio_risk_envelope)
    lower, upper = _require_consistent_ladder(envelope.ladder_boundaries)
    lineage = _lineage(inputs.ladder_state, envelope, evaluation_end)

    performance = _prove_performance(inputs, envelope, evaluation_end)
    if performance.sleeve_id != lineage.sleeve_id:
        raise _fail("performance_sleeve_not_the_lineage_sleeve")
    drawdown, record = _prove_drawdown(inputs, envelope, evaluation_end, performance)
    correlation = _prove_correlation(inputs, envelope, evaluation_end, performance)

    governance = list(lineage.governance)
    if envelope.advances is not True:
        governance.append(_reason("portfolio_risk_envelope_not_governed"))
    if performance.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("performance_evidence_needs_governance_approval"))
    if drawdown.status is PaperSleeveDrawdownStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("drawdown_evidence_needs_governance_approval"))
    if correlation.status is PaperSleeveCorrelationStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("correlation_evidence_needs_governance_approval"))
    unavailable = list(lineage.unavailable)
    if performance.status is PaperSleevePerformanceStatus.NOT_COMPUTABLE:
        unavailable.append(_reason("performance_evidence_not_computable"))
    elif performance.status is PaperSleevePerformanceStatus.READY and record.computed is not True:
        unavailable.append(_reason("drawdown_target_measurement_not_computed"))

    if governance:
        status = PaperSleeveLadderDecisionStatus.NEEDS_GOVERNANCE_APPROVAL
    elif unavailable:
        status = PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE
    else:
        status = PaperSleeveLadderDecisionStatus.READY

    tenure_days: int | None = None
    if lineage.current_tier_entered_at_ns is not None:
        elapsed = evaluation_end - lineage.current_tier_entered_at_ns
        if elapsed < 0 or elapsed % _DAY_NS != 0:
            raise _fail("tier_tenure_not_whole_utc_days")
        tenure_days = elapsed // _DAY_NS

    outcome: _Outcome | None = None
    sharpe_text = drawdown_text = ""
    if status is PaperSleeveLadderDecisionStatus.READY:
        sharpe_text = performance.paper_sharpe_annualized
        drawdown_text = record.measurement.max_peak_distance  # type: ignore[union-attr]
        outcome = _evaluate_transition(
            cast(PaperSleeveLadderTier, lineage.current_tier),
            cast(int, tenure_days),
            _scale18_value(sharpe_text, "performance_sharpe_invalid"),
            _peak_distance_value(drawdown_text),
            lower,
            upper,
        )

    resulting_entered: int | None = None
    if outcome is not None:
        held = outcome.transition is PaperSleeveLadderTransition.HOLD
        resulting_entered = lineage.current_tier_entered_at_ns if held else evaluation_end

    seed = PaperSleevePromotionDemotionDecision(
        schema_version=_DECISION_SCHEMA_VERSION,
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
        ladder_seed_digest=lineage.ladder_seed_digest,
        ladder_seed_advances=lineage.ladder_seed_advances,
        prior_decision_digest=lineage.prior_decision_digest,
        lineage_sequence=lineage.lineage_sequence,
        evaluation_end_ns=evaluation_end,
        current_tier=lineage.current_tier,
        current_tier_entered_at_ns=lineage.current_tier_entered_at_ns,
        tier_elapsed_days=tenure_days,
        transition=None if outcome is None else outcome.transition,
        resulting_tier=None if outcome is None else outcome.resulting_tier,
        resulting_tier_entered_at_ns=resulting_entered,
        performance_evidence_digest=performance.performance_evidence_digest,
        performance_status=performance.status.value,
        drawdown_evidence_digest=drawdown.drawdown_evidence_digest,
        drawdown_status=drawdown.status.value,
        correlation_evidence_digest=correlation.correlation_evidence_digest,
        correlation_status=correlation.status.value,
        paper_sharpe_annualized=sharpe_text,
        max_peak_distance=drawdown_text,
        drawdown_consumption=_DRAWDOWN_CONSUMPTION,
        promotion_boundary=None if outcome is None else outcome.promotion_boundary,
        demotion_boundary=None if outcome is None else outcome.demotion_boundary,
        decision_reason_codes=() if outcome is None else _sorted_unique(outcome.reasons),
        reason_codes=_sorted_unique(governance + unavailable),
        regime_concentration_demotion_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
        decision_digest="",
    )
    return replace(seed, decision_digest=edge_payload_digest(_to_payload(seed), _DECISION_DIGEST_FIELD))


def paper_sleeve_promotion_demotion_decision_to_dict(
    decision: PaperSleevePromotionDemotionDecision,
) -> dict[str, object]:
    """Canonical JSON-ready mapping of the decision, including its self-digest."""

    return _to_payload(decision)


def paper_sleeve_promotion_demotion_decision_digest(decision: PaperSleevePromotionDemotionDecision) -> str:
    """Recompute the canonical decision digest, excluding only ``decision_digest``."""

    return edge_payload_digest(_to_payload(decision), _DECISION_DIGEST_FIELD)


def verify_paper_sleeve_promotion_demotion_decision(
    decision: object, inputs: PaperSleevePromotionDemotionInputs
) -> EdgeEvidenceVerification:
    """Re-prove a decision by rebuilding it from its exact inputs, its lineage included. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(decision) is not PaperSleevePromotionDemotionDecision:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _to_payload(decision)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DECISION_DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _to_payload(build_paper_sleeve_promotion_demotion_decision(inputs))
        codes: set[str] = set()
        if carried[_DECISION_DIGEST_FIELD] != recomputed:
            codes.add(_reason("self_digest_mismatch"))
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
