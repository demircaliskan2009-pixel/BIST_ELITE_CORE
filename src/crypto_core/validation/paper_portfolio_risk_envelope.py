"""RG-2 governed paper-only portfolio risk constitution (RG2_PAPER_PORTFOLIO_RISK_ENVELOPE_V1).

``docs/crypto_core/multi_sleeve_risk_governance_design.md`` §1 (RG-2). A ``PaperPortfolioRiskEnvelope`` is POLICY
EVIDENCE ONLY: the human-owned portfolio constitution that every later RG artifact re-pins. It is never an allocation,
an order, execution permission, real money, or a capital, equity, margin or balance figure, and it claims no readiness,
edge or profitability. It consumes no evidence: no sleeve performance, drawdown, correlation, admission or kill state,
and it decides no promotion, demotion or portfolio stop.

Governed structure. Every value is a caller-supplied GOVERNANCE input; nothing is defaulted and this module holds no
production value:

* ``total_paper_risk_budget`` and the per-sleeve and per-market caps are inclusive upper bounds in abstract paper
  risk-budget units. The total and every cap are strictly positive and no cap exceeds the total; the caps need not sum
  to anything. Only declared sleeves and markets hold envelope capacity, so absence is never a default cap.
* ``max_sleeve_count``: the declared sleeve caps may not outnumber it.
* ``correlation_cap``: the pairwise sleeve-return correlation cap over aligned UTC-day indices, its lookback window and
  the minimum overlap below which a correlation is unknown. The cap lies in ``[-1, 1)``. Limits are inclusive, so the
  worst-case unknown correlation ``1`` always breaches every legal cap and missing evidence never earns
  diversification credit. The overlap minimum is at least two days, because a correlation of fewer paired
  observations is undefined, and at most the lookback window.
* ``ladder_boundaries``: the two adjacent sleeve-ladder boundaries PROBATION|STANDARD and STANDARD|EXPANDED. Each
  carries a probation window, promotion levels (paper Sharpe floor and drawdown ceiling) and demotion levels (paper
  Sharpe floor and drawdown ceiling). The levels are consistent by construction: no single evidence snapshot can make a
  sleeve both promotion-eligible and demotion-eligible for one tier.
* ``portfolio_stop_levels``: contiguous stop levels from 1 with strictly increasing portfolio drawdown thresholds.
* Regime-conditioned caps and the regime-concentration demotion reason stay digest-bound PENDING markers until an
  accepted RF chain exists. Nothing regime-dependent is fabricated.

Limits are inclusive: a measurement at or below a ceiling, or at or above a floor, is within the limit, and a breach is
strictly beyond it. Drawdown is the peak-distance fraction of the running peak of a strictly positive paper index, so
drawdown levels lie in ``[0, 1)``. A level at or above one could never be breached and is refused.

Governance. ``policy_digest`` commits every governed value, both pending markers, the structural non-claims and the
code-defined rule set (``PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST``, which commits every rule identity and numeric
bound that this module reads). A ``PaperPortfolioRiskEnvelopeApproval`` must commit the exact envelope id, version,
``policy_digest`` and rule-set digest:

* a missing or non-matching approval leaves the envelope ``NEEDS_GOVERNANCE_APPROVAL``;
* changing any governed value changes ``policy_digest`` and so makes every earlier approval stale;
* a ``TEST_ONLY_SYNTHETIC`` approval is surfaced through ``synthetic_test_approval_used`` and never advances;
* only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``.

``approval_reference`` and ``approval_digest`` identify the external governance record and are carried, not re-proven:
this module cannot prove who approved the envelope and claims only that the record commits to these exact digests.

Malformed, missing, out-of-domain, duplicate, ambiguous or inconsistent governed input raises
``PaperPortfolioRiskEnvelopeError``: an invalid constitution is never represented.

``envelope_digest`` is the self-digest over everything, approval included, and is the anchor that later RG artifacts
pin. One assembly path serves the builder and the verifier reassembly, and ``verify_paper_portfolio_risk_envelope`` is
total.

Numeric discipline: canonical fixed scale-18 ASCII decimal text (no exponent, plus sign or negative zero, at most 60
characters), native integers bounded to int64, and exact ``Fraction`` comparison. There is no float and no ``decimal``
context. Deterministic and pure: no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from itertools import pairwise

from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
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

_SCHEMA_VERSION = "paper-portfolio-risk-envelope.v1"
_REASON_PREFIX = "paper_portfolio_risk_envelope"
_SELF_DIGEST_FIELD = "envelope_digest"
_IDENTIFIER_EXTRA_CHARS = frozenset("-_./:")


class PaperPortfolioRiskEnvelopeError(EdgeArtifactError):
    """Raised on malformed, missing, out-of-domain, duplicate or inconsistent governed input, or a scope token."""


class PaperSleeveLadderTier(str, Enum):
    """The RG sleeve ladder, lowest tier first."""

    PROBATION = "PROBATION"
    STANDARD = "STANDARD"
    EXPANDED = "EXPANDED"


class PaperPortfolioRiskEnvelopeApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` approvals exist for tests only: they are surfaced and never advance an envelope."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_portfolio_risk_envelope_rules.v1",
    "scope_rule_id": "paper_only_policy_evidence_never_allocation_order_execution_permission_or_account_value.v1",
    "budget_unit_id": "abstract_paper_risk_budget_units_never_currency_or_account_value.v1",
    "budget_rule_id": "total_and_every_cap_strictly_positive_each_cap_at_most_total_no_sum_rule.v1",
    "coverage_rule_id": "only_declared_sleeves_and_markets_hold_envelope_capacity_absence_is_never_a_default_cap.v1",
    "sleeve_count_rule_id": "declared_sleeve_cap_count_at_most_max_sleeve_count.v1",
    "identifier_rule_id": "ascii_token_ids_unique_exactly_and_case_insensitively_canonically_sorted.v1",
    "limit_rule_id": "inclusive_limits_within_iff_at_most_ceiling_or_at_least_floor_breach_iff_strictly_beyond.v1",
    "correlation_measure_id": "pairwise_sleeve_daily_return_correlation_over_aligned_utc_day_indices.v1",
    "unknown_correlation_rule_id": "missing_data_or_overlap_below_minimum_is_worst_case_one_never_zero_or_skipped.v1",
    "correlation_cap_lower_bound_inclusive": -1,
    "correlation_cap_upper_bound_exclusive": 1,
    "correlation_min_overlap_floor_days": 2,
    "drawdown_measure_id": "peak_distance_fraction_of_running_peak_of_strictly_positive_paper_index.v1",
    "drawdown_lower_bound_inclusive": 0,
    "drawdown_upper_bound_exclusive": 1,
    "performance_measure_id": "paper-sharpe-evidence.v1:paper_sharpe_annualized",
    "ladder_tiers": tuple(tier.value for tier in PaperSleeveLadderTier),
    "ladder_boundary_rule_id": "exactly_the_adjacent_ascending_tier_boundaries_each_once.v1",
    "promotion_rule_id": "probation_days_met_and_snapshot_sharpe_at_least_floor_and_drawdown_at_most_ceiling.v1",
    "demotion_rule_id": "snapshot_sharpe_strictly_below_floor_or_drawdown_strictly_above_ceiling.v1",
    "ladder_consistency_rule_id": "no_single_evidence_snapshot_promotion_and_demotion_eligible_for_one_tier.v1",
    "ladder_exit_rule_id": "no_envelope_tier_below_probation_kill_and_quarantine_authority_out_of_scope.v1",
    "portfolio_stop_rule_id": "levels_contiguous_from_one_with_strictly_increasing_drawdown_thresholds.v1",
    "regime_rule_id": "regime_conditioned_caps_and_concentration_demotion_pending_until_accepted_rf_chain.v1",
    "governance_rule_id": "approval_commits_envelope_id_version_policy_digest_and_rule_set_digest.v1",
    "gate_rule_id": "pass_iff_exact_matching_human_governance_approval_test_only_synthetic_never_advances.v1",
    "numeric_rule_id": "canonical_fixed_scale_decimal_text_exact_fraction_comparison_no_float_no_decimal_context.v1",
    "decimal_scale": 18,
    "decimal_max_text_length": 60,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_sleeve_id_length": 128,
    "max_market_symbol_length": 64,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_max_text_length"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_SLEEVE_ID: int = _RULE_SET_V1["max_sleeve_id_length"]  # type: ignore[assignment]
_MAX_MARKET_SYMBOL: int = _RULE_SET_V1["max_market_symbol_length"]  # type: ignore[assignment]
_MIN_OVERLAP_DAYS: int = _RULE_SET_V1["correlation_min_overlap_floor_days"]  # type: ignore[assignment]
_CORRELATION_LOWER = Fraction(_RULE_SET_V1["correlation_cap_lower_bound_inclusive"])  # type: ignore[arg-type]
_CORRELATION_UPPER = Fraction(_RULE_SET_V1["correlation_cap_upper_bound_exclusive"])  # type: ignore[arg-type]
_DRAWDOWN_LOWER = Fraction(_RULE_SET_V1["drawdown_lower_bound_inclusive"])  # type: ignore[arg-type]
_DRAWDOWN_UPPER = Fraction(_RULE_SET_V1["drawdown_upper_bound_exclusive"])  # type: ignore[arg-type]
_LADDER_BOUNDARIES: tuple[tuple[PaperSleeveLadderTier, PaperSleeveLadderTier], ...] = tuple(
    pairwise(PaperSleeveLadderTier)
)


def paper_portfolio_risk_envelope_rule_set() -> dict[str, object]:
    """A fresh copy of the RG-2 V1 rule set that ``PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("execution_authorized", False),
    ("portfolio_allocation_approved", False),
    ("capital_allocated", False),
    ("promotion_demotion_decided", False),
    ("portfolio_stop_evaluated", False),
    ("current_lifecycle_head_proven", False),
    ("paper_performance_proven", False),
    ("prdv4_stage4_complete", False),
)
_FLAG_NAMES = frozenset(name for name, _ in PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS)


@dataclass(frozen=True)
class PaperPortfolioSleeveCap:
    """Governed inclusive upper bound of paper risk budget for one declared sleeve. Never an allocation."""

    sleeve_id: str
    max_paper_risk_budget: str


@dataclass(frozen=True)
class PaperPortfolioMarketCap:
    """Governed inclusive upper bound of paper risk budget across every sleeve on one market. Never an allocation."""

    market_symbol: str
    max_paper_risk_budget: str


@dataclass(frozen=True)
class PaperPortfolioCorrelationCap:
    """Governed pairwise sleeve-return correlation cap and the aligned UTC-day evidence window it applies to."""

    max_pairwise_correlation: str
    lookback_window_days: int
    min_overlap_days: int


@dataclass(frozen=True)
class PaperSleeveLadderBoundary:
    """Governed promotion (lower to upper) and demotion (upper to lower) levels at one adjacent ladder boundary.

    ``min_probation_days`` is the minimum number of aligned UTC days a sleeve spends in the lower tier before a
    promotion can be evaluated. Promotion needs the paper Sharpe at or above ``promotion_min_paper_sharpe`` and the
    drawdown at or below ``promotion_max_drawdown_fraction``. A sleeve in the upper tier becomes demotion-eligible
    when its paper Sharpe is strictly below ``demotion_min_paper_sharpe`` or its drawdown strictly above
    ``demotion_max_drawdown_fraction``. The envelope records these levels and decides nothing.
    """

    lower_tier: PaperSleeveLadderTier
    upper_tier: PaperSleeveLadderTier
    min_probation_days: int
    promotion_min_paper_sharpe: str
    promotion_max_drawdown_fraction: str
    demotion_min_paper_sharpe: str
    demotion_max_drawdown_fraction: str


@dataclass(frozen=True)
class PaperPortfolioStopLevel:
    """One governed portfolio-stop level, breached when portfolio peak-distance strictly exceeds its threshold."""

    stop_level: int
    max_portfolio_drawdown_fraction: str


@dataclass(frozen=True)
class PaperPortfolioRiskEnvelopeApproval:
    """Governance approval of one exact envelope: every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approval_kind: PaperPortfolioRiskEnvelopeApprovalKind
    approved_envelope_id: str
    approved_envelope_version: str
    approved_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class PaperPortfolioRiskEnvelope:
    """Immutable, digest-bound RG-2 paper portfolio risk envelope. POLICY EVIDENCE ONLY; never an allocation."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    envelope_id: str
    envelope_version: str
    rule_set_id: str
    rule_set_digest: str
    total_paper_risk_budget: str
    sleeve_caps: tuple[PaperPortfolioSleeveCap, ...]
    market_caps: tuple[PaperPortfolioMarketCap, ...]
    max_sleeve_count: int
    correlation_cap: PaperPortfolioCorrelationCap
    ladder_boundaries: tuple[PaperSleeveLadderBoundary, ...]
    portfolio_stop_levels: tuple[PaperPortfolioStopLevel, ...]
    regime_stratified_correlation_status: str
    regime_concentration_demotion_status: str
    policy_digest: str
    approval: PaperPortfolioRiskEnvelopeApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    envelope_digest: str
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
    execution_authorized: bool = False
    portfolio_allocation_approved: bool = False
    capital_allocated: bool = False
    promotion_demotion_decided: bool = False
    portfolio_stop_evaluated: bool = False
    current_lifecycle_head_proven: bool = False
    paper_performance_proven: bool = False
    prdv4_stage4_complete: bool = False


# Everything outside the governed constitution: the approval, the verdict it yields, and the two digests themselves.
_NON_POLICY_FIELDS = frozenset(
    {
        "gate_verdict",
        "advances",
        "policy_digest",
        "approval",
        "synthetic_test_approval_used",
        "verdict_reason_codes",
        "envelope_digest",
    }
)
_RECORD_TYPES = frozenset(
    {
        PaperPortfolioSleeveCap,
        PaperPortfolioMarketCap,
        PaperPortfolioCorrelationCap,
        PaperSleeveLadderBoundary,
        PaperPortfolioStopLevel,
        PaperPortfolioRiskEnvelopeApproval,
    }
)
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperSleeveLadderBoundary: {"lower_tier": PaperSleeveLadderTier, "upper_tier": PaperSleeveLadderTier},
    PaperPortfolioRiskEnvelopeApproval: {"approval_kind": PaperPortfolioRiskEnvelopeApprovalKind},
    PaperPortfolioRiskEnvelope: {"gate_verdict": EdgeGateVerdict},
}


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperPortfolioRiskEnvelopeError:
    return PaperPortfolioRiskEnvelopeError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _decimal_is_canonical(value: object) -> bool:
    """Canonical ASCII fixed-scale decimal text within the rule set's representation-safety length."""

    if type(value) is not str or len(value) > _MAX_DECIMAL_TEXT or not value.isascii():
        return False
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if dot != "." or len(fraction) != _SCALE:
        return False
    if not _ascii_digits(integer) or not _ascii_digits(fraction):
        return False
    if integer != "0" and integer.startswith("0"):
        return False
    if negative and integer == "0" and fraction.strip("0") == "":
        return False
    return True


def _wire_int_is_valid(value: object, *, minimum: int) -> bool:
    return type(value) is int and minimum <= value <= _MAX_WIRE_INT


def _require_decimal(value: object, field_name: str) -> tuple[str, Fraction]:
    if not _decimal_is_canonical(value):
        raise _fail(f"{field_name}_invalid")
    return value, Fraction(value)  # type: ignore[return-value,arg-type]


def _require_positive_decimal(value: object, field_name: str) -> tuple[str, Fraction]:
    text, number = _require_decimal(value, field_name)
    if number <= 0:
        raise _fail(f"{field_name}_not_positive")
    return text, number


def _require_drawdown(value: object, field_name: str) -> tuple[str, Fraction]:
    text, number = _require_decimal(value, field_name)
    if number < _DRAWDOWN_LOWER or number >= _DRAWDOWN_UPPER:
        raise _fail(f"{field_name}_out_of_domain")
    return text, number


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if not _wire_int_is_valid(value, minimum=minimum):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


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


def _require_identifier(value: object, field_name: str, *, max_length: int) -> str:
    if type(value) is not str or value == "" or len(value) > max_length or not value.isascii():
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


def _snapshot(values: object, field_name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    return tuple(values)  # type: ignore[arg-type]


# --- governed structure ---------------------------------------------------------------------------------------------


def _canonical_caps(
    values: object,
    *,
    record_type: type,
    key_name: str,
    key_max_length: int,
    label: str,
    total: Fraction,
) -> tuple:
    """Canonical cap set: non-empty, exact records, unique exact and case-insensitive keys, sorted by key."""

    items = _snapshot(values, f"{label}s")
    if not items:
        raise _fail(f"{label}s_missing")
    by_key: dict[str, object] = {}
    folded: set[str] = set()
    for item in items:
        if type(item) is not record_type:
            raise _fail(f"{label}_malformed")
        key = _require_identifier(getattr(item, key_name, None), key_name, max_length=key_max_length)
        cap_text, cap = _require_positive_decimal(
            getattr(item, "max_paper_risk_budget", None), f"{label}_max_paper_risk_budget"
        )
        if cap > total:
            raise _fail(f"{label}_exceeds_total_paper_risk_budget")
        if key in by_key:
            raise _fail(f"{label}_duplicate")
        if key.lower() in folded:
            raise _fail(f"{label}_case_ambiguous")
        folded.add(key.lower())
        by_key[key] = record_type(**{key_name: key, "max_paper_risk_budget": cap_text})
    return tuple(by_key[key] for key in sorted(by_key))


def _canonical_correlation_cap(value: object) -> PaperPortfolioCorrelationCap:
    if value is None:
        raise _fail("correlation_cap_missing")
    if type(value) is not PaperPortfolioCorrelationCap:
        raise _fail("correlation_cap_malformed")
    cap_text, cap = _require_decimal(getattr(value, "max_pairwise_correlation", None), "max_pairwise_correlation")
    if cap < _CORRELATION_LOWER or cap >= _CORRELATION_UPPER:
        raise _fail("max_pairwise_correlation_out_of_domain")
    lookback = _require_int(getattr(value, "lookback_window_days", None), "lookback_window_days", minimum=1)
    overlap = _require_int(getattr(value, "min_overlap_days", None), "min_overlap_days", minimum=_MIN_OVERLAP_DAYS)
    if overlap > lookback:
        raise _fail("min_overlap_days_exceeds_lookback_window_days")
    return PaperPortfolioCorrelationCap(
        max_pairwise_correlation=cap_text, lookback_window_days=lookback, min_overlap_days=overlap
    )


def _canonical_ladder_boundary(item: object) -> PaperSleeveLadderBoundary:
    if type(item) is not PaperSleeveLadderBoundary:
        raise _fail("ladder_boundary_malformed")
    lower = _require_member(getattr(item, "lower_tier", None), PaperSleeveLadderTier, "ladder_lower_tier")
    upper = _require_member(getattr(item, "upper_tier", None), PaperSleeveLadderTier, "ladder_upper_tier")
    if (lower, upper) not in _LADDER_BOUNDARIES:
        raise _fail("ladder_boundary_not_adjacent_ascending")
    probation = _require_int(getattr(item, "min_probation_days", None), "min_probation_days", minimum=1)
    promotion_sharpe_text, promotion_sharpe = _require_decimal(
        getattr(item, "promotion_min_paper_sharpe", None), "promotion_min_paper_sharpe"
    )
    promotion_drawdown_text, promotion_drawdown = _require_drawdown(
        getattr(item, "promotion_max_drawdown_fraction", None), "promotion_max_drawdown_fraction"
    )
    demotion_sharpe_text, demotion_sharpe = _require_decimal(
        getattr(item, "demotion_min_paper_sharpe", None), "demotion_min_paper_sharpe"
    )
    demotion_drawdown_text, demotion_drawdown = _require_drawdown(
        getattr(item, "demotion_max_drawdown_fraction", None), "demotion_max_drawdown_fraction"
    )
    # A sleeve promoted into the upper tier must not be demotion-eligible from it on the same evidence snapshot.
    if promotion_sharpe < demotion_sharpe:
        raise _fail("ladder_promotion_sharpe_floor_below_demotion_sharpe_floor")
    if promotion_drawdown > demotion_drawdown:
        raise _fail("ladder_promotion_drawdown_ceiling_above_demotion_drawdown_ceiling")
    return PaperSleeveLadderBoundary(
        lower_tier=lower,  # type: ignore[arg-type]
        upper_tier=upper,  # type: ignore[arg-type]
        min_probation_days=probation,
        promotion_min_paper_sharpe=promotion_sharpe_text,
        promotion_max_drawdown_fraction=promotion_drawdown_text,
        demotion_min_paper_sharpe=demotion_sharpe_text,
        demotion_max_drawdown_fraction=demotion_drawdown_text,
    )


def _canonical_ladder(values: object) -> tuple[PaperSleeveLadderBoundary, ...]:
    items = _snapshot(values, "ladder_boundaries")
    if not items:
        raise _fail("ladder_boundaries_missing")
    by_pair: dict[tuple[Enum, Enum], PaperSleeveLadderBoundary] = {}
    for item in items:
        boundary = _canonical_ladder_boundary(item)
        pair = (boundary.lower_tier, boundary.upper_tier)
        if pair in by_pair:
            raise _fail("ladder_boundary_duplicate")
        by_pair[pair] = boundary
    if set(by_pair) != set(_LADDER_BOUNDARIES):
        raise _fail("ladder_boundaries_incomplete")
    ordered = tuple(by_pair[pair] for pair in _LADDER_BOUNDARIES)
    # A middle tier is the upper tier of one boundary and the lower tier of the next: one evidence snapshot must never
    # make it promotion-eligible over the upper boundary and demotion-eligible over the lower boundary.
    for lower, upper in pairwise(ordered):
        if Fraction(upper.promotion_min_paper_sharpe) < Fraction(lower.demotion_min_paper_sharpe):
            raise _fail("ladder_middle_tier_promotion_sharpe_floor_below_demotion_sharpe_floor")
        if Fraction(upper.promotion_max_drawdown_fraction) > Fraction(lower.demotion_max_drawdown_fraction):
            raise _fail("ladder_middle_tier_promotion_drawdown_ceiling_above_demotion_drawdown_ceiling")
    return ordered


def _canonical_stop_levels(values: object) -> tuple[PaperPortfolioStopLevel, ...]:
    items = _snapshot(values, "portfolio_stop_levels")
    if not items:
        raise _fail("portfolio_stop_levels_missing")
    by_level: dict[int, PaperPortfolioStopLevel] = {}
    for item in items:
        if type(item) is not PaperPortfolioStopLevel:
            raise _fail("portfolio_stop_level_malformed")
        level = _require_int(getattr(item, "stop_level", None), "stop_level", minimum=1)
        threshold_text, _threshold = _require_drawdown(
            getattr(item, "max_portfolio_drawdown_fraction", None), "max_portfolio_drawdown_fraction"
        )
        if level in by_level:
            raise _fail("portfolio_stop_level_duplicate")
        by_level[level] = PaperPortfolioStopLevel(stop_level=level, max_portfolio_drawdown_fraction=threshold_text)
    ordered = tuple(by_level[level] for level in sorted(by_level))
    if [item.stop_level for item in ordered] != list(range(1, len(ordered) + 1)):
        raise _fail("portfolio_stop_levels_not_contiguous_from_one")
    for lower, upper in pairwise(ordered):
        lower_threshold = Fraction(lower.max_portfolio_drawdown_fraction)
        upper_threshold = Fraction(upper.max_portfolio_drawdown_fraction)
        if upper_threshold == lower_threshold:
            raise _fail("portfolio_stop_level_threshold_ambiguous")
        if upper_threshold < lower_threshold:
            raise _fail("portfolio_stop_level_thresholds_not_increasing")
    return ordered


# --- governance approval --------------------------------------------------------------------------------------------


def _canonical_approval(approval: object) -> PaperPortfolioRiskEnvelopeApproval | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if approval is None:
        return None
    if type(approval) is not PaperPortfolioRiskEnvelopeApproval:
        raise _fail("governance_approval_malformed")

    def attribute(name: str) -> object:
        return getattr(approval, name, None)

    return PaperPortfolioRiskEnvelopeApproval(
        approval_reference=_require_text(attribute("approval_reference"), "governance_approval_reference"),
        approval_digest=_require_hex64(attribute("approval_digest"), "governance_approval_digest"),
        approval_kind=_require_member(  # type: ignore[arg-type]
            attribute("approval_kind"), PaperPortfolioRiskEnvelopeApprovalKind, "governance_approval_kind"
        ),
        approved_envelope_id=_require_text(attribute("approved_envelope_id"), "governance_approved_envelope_id"),
        approved_envelope_version=_require_text(
            attribute("approved_envelope_version"), "governance_approved_envelope_version"
        ),
        approved_policy_digest=_require_hex64(attribute("approved_policy_digest"), "governance_approved_policy_digest"),
        approved_rule_set_digest=_require_hex64(
            attribute("approved_rule_set_digest"), "governance_approved_rule_set_digest"
        ),
    )


def _governance_reasons(approval: PaperPortfolioRiskEnvelopeApproval | None, committed: Mapping[str, str]) -> list[str]:
    if approval is None:
        return [_reason("governance_approval_missing")]
    reasons = [
        _reason(f"governance_approval_{name}_mismatch")
        for name, value in committed.items()
        if getattr(approval, f"approved_{name}") != value
    ]
    if approval.approval_kind is PaperPortfolioRiskEnvelopeApprovalKind.TEST_ONLY_SYNTHETIC:
        reasons.append(_reason("governance_approval_test_only_synthetic"))
    return reasons


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
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


def _policy_digest(payload: Mapping[str, object]) -> str:
    return edge_sha256_text(
        edge_canonical_json({name: value for name, value in payload.items() if name not in _NON_POLICY_FIELDS})
    )


# --- envelope assembly ----------------------------------------------------------------------------------------------


def _assemble_envelope(
    *,
    envelope_id: object,
    envelope_version: object,
    total_paper_risk_budget: object,
    sleeve_caps: object,
    market_caps: object,
    max_sleeve_count: object,
    correlation_cap: object,
    ladder_boundaries: object,
    portfolio_stop_levels: object,
    approval: object,
) -> PaperPortfolioRiskEnvelope:
    """The one envelope assembly path, shared by the builder and verifier reassembly."""

    envelope_id = _require_text(envelope_id, "envelope_id")
    envelope_version = _require_text(envelope_version, "envelope_version")
    total_text, total = _require_positive_decimal(total_paper_risk_budget, "total_paper_risk_budget")
    sleeves = _canonical_caps(
        sleeve_caps,
        record_type=PaperPortfolioSleeveCap,
        key_name="sleeve_id",
        key_max_length=_MAX_SLEEVE_ID,
        label="sleeve_cap",
        total=total,
    )
    markets = _canonical_caps(
        market_caps,
        record_type=PaperPortfolioMarketCap,
        key_name="market_symbol",
        key_max_length=_MAX_MARKET_SYMBOL,
        label="market_cap",
        total=total,
    )
    max_sleeves = _require_int(max_sleeve_count, "max_sleeve_count", minimum=1)
    if len(sleeves) > max_sleeves:
        raise _fail("declared_sleeve_count_exceeds_max_sleeve_count")
    correlation = _canonical_correlation_cap(correlation_cap)
    ladder = _canonical_ladder(ladder_boundaries)
    stops = _canonical_stop_levels(portfolio_stop_levels)
    approval_record = _canonical_approval(approval)

    seed = PaperPortfolioRiskEnvelope(
        schema_version=_SCHEMA_VERSION,
        gate_verdict=EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        advances=False,
        envelope_id=envelope_id,
        envelope_version=envelope_version,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
        total_paper_risk_budget=total_text,
        sleeve_caps=sleeves,
        market_caps=markets,
        max_sleeve_count=max_sleeves,
        correlation_cap=correlation,
        ladder_boundaries=ladder,
        portfolio_stop_levels=stops,
        regime_stratified_correlation_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_concentration_demotion_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        policy_digest="",
        approval=approval_record,
        synthetic_test_approval_used=approval_record is not None
        and approval_record.approval_kind is PaperPortfolioRiskEnvelopeApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=(),
        envelope_digest="",
    )
    policy_digest = _policy_digest(_to_payload(seed))
    committed = {
        "envelope_id": envelope_id,
        "envelope_version": envelope_version,
        "policy_digest": policy_digest,
        "rule_set_digest": PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
    }
    needs_governance = _governance_reasons(approval_record, committed)
    verdict = resolve_edge_gate_verdict([], [], needs_governance)
    governed = replace(
        seed,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        policy_digest=policy_digest,
        verdict_reason_codes=_sorted_unique(needs_governance),
    )
    return replace(governed, envelope_digest=edge_payload_digest(_to_payload(governed), _SELF_DIGEST_FIELD))


def build_paper_portfolio_risk_envelope(
    *,
    envelope_id: str,
    envelope_version: str,
    total_paper_risk_budget: str,
    sleeve_caps: Sequence[PaperPortfolioSleeveCap],
    market_caps: Sequence[PaperPortfolioMarketCap],
    max_sleeve_count: int,
    correlation_cap: PaperPortfolioCorrelationCap,
    ladder_boundaries: Sequence[PaperSleeveLadderBoundary],
    portfolio_stop_levels: Sequence[PaperPortfolioStopLevel],
    approval: PaperPortfolioRiskEnvelopeApproval | None,
) -> PaperPortfolioRiskEnvelope:
    """Build the governed envelope; every governed value is explicit (there are no defaults).

    Malformed, missing, out-of-domain, duplicate, ambiguous or inconsistent governed input, or a malformed approval,
    raises ``PaperPortfolioRiskEnvelopeError``. A missing, non-matching or ``TEST_ONLY_SYNTHETIC`` approval yields
    ``NEEDS_GOVERNANCE_APPROVAL``; only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``. Inputs
    are read once and never mutated.
    """

    return _assemble_envelope(
        envelope_id=envelope_id,
        envelope_version=envelope_version,
        total_paper_risk_budget=total_paper_risk_budget,
        sleeve_caps=sleeve_caps,
        market_caps=market_caps,
        max_sleeve_count=max_sleeve_count,
        correlation_cap=correlation_cap,
        ladder_boundaries=ladder_boundaries,
        portfolio_stop_levels=portfolio_stop_levels,
        approval=approval,
    )


def paper_portfolio_risk_envelope_to_dict(envelope: PaperPortfolioRiskEnvelope) -> dict[str, object]:
    """Canonical JSON-ready mapping of an envelope, including its self-digest."""

    return _to_payload(envelope)


def paper_portfolio_risk_envelope_digest(envelope: PaperPortfolioRiskEnvelope) -> str:
    """Recompute the canonical envelope digest, excluding only ``envelope_digest``."""

    return edge_payload_digest(_to_payload(envelope), _SELF_DIGEST_FIELD)


# --- strict parsing -------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if not _wire_int_is_valid(value, minimum=0):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_decimal(value: object) -> str:
    if not _decimal_is_canonical(value):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


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


def _as_nested(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return _parse_exact(cls, value, converters)

    return convert


def _as_optional(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return None if value is None else _parse_exact(cls, value, converters)

    return convert


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


_CAP_CONVERTERS: dict[str, Callable[[object], object]] = {"max_paper_risk_budget": _as_decimal}
_CORRELATION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "max_pairwise_correlation": _as_decimal,
    "lookback_window_days": _as_int,
    "min_overlap_days": _as_int,
}
_LADDER_CONVERTERS: dict[str, Callable[[object], object]] = {
    "lower_tier": _as_enum(PaperSleeveLadderTier),
    "upper_tier": _as_enum(PaperSleeveLadderTier),
    "min_probation_days": _as_int,
    "promotion_min_paper_sharpe": _as_decimal,
    "promotion_max_drawdown_fraction": _as_decimal,
    "demotion_min_paper_sharpe": _as_decimal,
    "demotion_max_drawdown_fraction": _as_decimal,
}
_STOP_CONVERTERS: dict[str, Callable[[object], object]] = {
    "stop_level": _as_int,
    "max_portfolio_drawdown_fraction": _as_decimal,
}
_APPROVAL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approval_kind": _as_enum(PaperPortfolioRiskEnvelopeApprovalKind),
}
_ENVELOPE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "total_paper_risk_budget": _as_decimal,
    "sleeve_caps": _as_records(PaperPortfolioSleeveCap, _CAP_CONVERTERS),
    "market_caps": _as_records(PaperPortfolioMarketCap, _CAP_CONVERTERS),
    "max_sleeve_count": _as_int,
    "correlation_cap": _as_nested(PaperPortfolioCorrelationCap, _CORRELATION_CONVERTERS),
    "ladder_boundaries": _as_records(PaperSleeveLadderBoundary, _LADDER_CONVERTERS),
    "portfolio_stop_levels": _as_records(PaperPortfolioStopLevel, _STOP_CONVERTERS),
    "approval": _as_optional(PaperPortfolioRiskEnvelopeApproval, _APPROVAL_CONVERTERS),
    "synthetic_test_approval_used": _as_bool,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def paper_portfolio_risk_envelope_from_payload(payload: object) -> PaperPortfolioRiskEnvelope:
    """Strictly reconstruct an envelope from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(PaperPortfolioRiskEnvelope, payload, _ENVELOPE_CONVERTERS)  # type: ignore[return-value]


def paper_portfolio_risk_envelope_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an envelope snapshot."""

    try:
        paper_portfolio_risk_envelope_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_envelope(envelope: object) -> PaperPortfolioRiskEnvelope:
    return _assemble_envelope(
        envelope_id=envelope.envelope_id,  # type: ignore[attr-defined]
        envelope_version=envelope.envelope_version,  # type: ignore[attr-defined]
        total_paper_risk_budget=envelope.total_paper_risk_budget,  # type: ignore[attr-defined]
        sleeve_caps=envelope.sleeve_caps,  # type: ignore[attr-defined]
        market_caps=envelope.market_caps,  # type: ignore[attr-defined]
        max_sleeve_count=envelope.max_sleeve_count,  # type: ignore[attr-defined]
        correlation_cap=envelope.correlation_cap,  # type: ignore[attr-defined]
        ladder_boundaries=envelope.ladder_boundaries,  # type: ignore[attr-defined]
        portfolio_stop_levels=envelope.portfolio_stop_levels,  # type: ignore[attr-defined]
        approval=envelope.approval,  # type: ignore[attr-defined]
    )


def verify_paper_portfolio_risk_envelope(envelope: object) -> EdgeEvidenceVerification:
    """Re-prove an envelope by strict parse, self-digest recomputation and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        envelope,
        cls=PaperPortfolioRiskEnvelope,
        to_payload=_to_payload,
        parse_payload=paper_portfolio_risk_envelope_from_payload,
        reassemble=_reassemble_envelope,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS",
    "PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST",
    "PaperPortfolioCorrelationCap",
    "PaperPortfolioMarketCap",
    "PaperPortfolioRiskEnvelope",
    "PaperPortfolioRiskEnvelopeApproval",
    "PaperPortfolioRiskEnvelopeApprovalKind",
    "PaperPortfolioRiskEnvelopeError",
    "PaperPortfolioSleeveCap",
    "PaperPortfolioStopLevel",
    "PaperSleeveLadderBoundary",
    "PaperSleeveLadderTier",
    "build_paper_portfolio_risk_envelope",
    "paper_portfolio_risk_envelope_digest",
    "paper_portfolio_risk_envelope_from_payload",
    "paper_portfolio_risk_envelope_payload_is_well_formed",
    "paper_portfolio_risk_envelope_rule_set",
    "paper_portfolio_risk_envelope_to_dict",
    "verify_paper_portfolio_risk_envelope",
]
