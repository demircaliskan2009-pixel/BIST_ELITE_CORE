"""RG-5 paper sleeve correlation evidence (RG5_PAPER_SLEEVE_CORRELATION_EVIDENCE_V1).

``docs/crypto_core/multi_sleeve_risk_governance_design.md`` §1 (RG-5). For EVERY unordered pair of the sleeves the
re-pinned RG-2 envelope declares, this artifact measures the Pearson product-moment correlation of the two sleeves'
re-proven paper daily returns over their exact common UTC days inside the governed trailing lookback. It is
MEASUREMENT EVIDENCE ONLY. It decides no correlation-cap breach, diversification credit, allocation, promotion,
demotion, portfolio stop, execution or readiness: RG-7 owns how worst-case correlation enters combined exposure and
the envelope check. It is never capital, equity or execution permission.

Binding, every element re-proven:

* RG-2: the ``PaperPortfolioRiskEnvelope`` is re-pinned through its total verifier. Its sleeve-cap set is the pair
  universe, and its ``correlation_cap`` is the only source of ``lookback_window_days`` and ``min_overlap_days``. The cap
  value itself is carried as provenance only and never compared;
* RG-3: every supplied sleeve's ``PaperSleevePerformanceEvidence`` is REBUILT from its exact inputs and must equal the
  supplied evidence. Only the reconstruction is used, and the sleeve and market identity are copied from it. It must
  re-pin the same envelope, and the envelope must declare its sleeve. A provenance or binding contradiction raises; it
  is never turned into an unknown pair.

Methodology ``RG5_PEARSON_CORRELATION_METHODOLOGY_V1`` (code-defined rule set
``PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST``):

* day identity: RG-3 rebuilds its series over the valuation's own contiguous UTC-day buckets, so daily return ``i`` of
  a READY sleeve is the return of the UTC day starting at ``window_start_ns + i`` days. Pairs are aligned on that exact
  day identity, never by position;
* lookback: the trailing window ``[evaluation_end_ns - lookback_window_days days, evaluation_end_ns)``, with an
  injected UTC-day-aligned ``evaluation_end_ns`` and no clock. No observation at or after ``evaluation_end_ns`` takes
  part;
* currency: a READY sleeve counts only when its evidence window ends exactly at ``evaluation_end_ns``. Evidence
  that stops earlier is stale, and evidence that runs past it carries later observations whose values and whose
  bearing on RG-3 readiness must not take part; either makes its pairs worst-case unknowns;
* overlap: the exact common UTC days of the pair inside the lookback. Fewer than ``min_overlap_days`` makes the pair a
  worst-case unknown; there is no second sample rule;
* estimator: for the aligned vectors ``x`` and ``y`` of length ``n``, ``mean_x = sum(x)/n`` and ``mean_y = sum(y)/n``,
  ``Sxy = sum((x_i - mean_x)*(y_i - mean_y))``, ``Sxx = sum((x_i - mean_x)^2)``, ``Syy = sum((y_i - mean_y)^2)`` and
  ``rho = Sxy / sqrt(Sxx*Syy)``. The moments are exact ``Fraction`` values, and the sample-versus-population
  denominator cancels, so it is no choice. A zero ``Sxx`` or ``Syy`` leaves the correlation undefined: a worst-case
  unknown. An exact algebraic ``+1`` or ``-1`` is preserved exactly;
* decimal policy ``decimal_quantized_scale_18_round_half_even_internal_precision_80.v1``: the public value is
  ``rho`` rounded half-even to exactly 18 fractional digits. A ``Decimal`` evaluation of the irrational square root and
  the final division at precision 80, through one fresh, fully specified context (``ROUND_HALF_EVEN``, fixed exponent
  limits and traps) passed to every operation, only proposes a candidate unit. The published unit is decided by exact
  rational comparisons of ``(2 * 10**18 * Sxy)**2`` with ``Sxx*Syy`` times the squared half-unit boundaries, so no
  input digit beyond any fixed precision is lost and there is no second rounding. The thread's ambient context is
  never read or set. Signed zero is normalized to positive zero, and the value lies in ``[-1, 1]``;
* unknown: a missing sleeve, a sleeve whose RG-3 evidence is not READY or not current, insufficient overlap, or an
  undefined estimator makes the pair ``WORST_CASE_UNKNOWN``. Its effective correlation is exactly
  ``1.000000000000000000``: never zero, never dropped, never the governed cap.

The pair matrix is always complete: every unordered pair of declared sleeves appears exactly once as
``(min(sleeve_id), max(sleeve_id))``, sorted lexicographically. A one-sleeve envelope has none.

Status precedence: ``NEEDS_GOVERNANCE_APPROVAL`` when the envelope or a supplied sleeve's RG-3 evidence does not
advance its governance; otherwise ``READY``. READY means the complete conservative pair matrix is materialized, never
that every pair was observed: ``observed_pair_count``, ``worst_case_pair_count`` and ``all_pairs_observed`` say so.

Regime-stratified correlation stays ``PENDING_RF_LABEL_ENUM_UNAVAILABLE`` and regime evidence unavailable until an
accepted RF chain exists; ``crypto_core.regime`` is never imported.

Malformed input and any provenance or binding defect raise ``PaperSleeveCorrelationEvidenceError``.
``verify_paper_sleeve_correlation_evidence`` re-proves an evidence by rebuilding it from its inputs and is total.
``measure_paper_pearson_correlation`` exposes the exact estimator for two aligned return vectors.

Non-overclaim: no statistical significance, profitability, edge or readiness claim. Mark, instant and funding origins
and episode-set completeness stay unproven. No float, and no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow
from enum import Enum
from fractions import Fraction
from itertools import combinations
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
    PaperPortfolioRiskEnvelope,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    build_paper_sleeve_performance_evidence,
    paper_sleeve_performance_evidence_to_dict,
)

_SCHEMA_VERSION = "paper-sleeve-correlation-evidence.v1"
_REASON_PREFIX = "paper_sleeve_correlation_evidence"
_SELF_DIGEST_FIELD = "correlation_evidence_digest"
_T = TypeVar("_T")

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_sleeve_correlation_evidence_rules.v1",
    "methodology_id": "RG5_PEARSON_CORRELATION_METHODOLOGY_V1",
    "scope_rule_id": "measurement_only_never_cap_breach_diversification_allocation_promotion_stop_or_execution.v1",
    "decision_ownership_rule_id": "rg7_owns_worst_case_correlation_exposure_and_envelope_checks_rg5_decides_nothing.v1",
    "envelope_correlation_measure_id": "pairwise_sleeve_daily_return_correlation_over_aligned_utc_day_indices.v1",
    "envelope_unknown_correlation_rule_id": (
        "missing_data_or_overlap_below_minimum_is_worst_case_one_never_zero_or_skipped.v1"
    ),
    "estimator_rule_id": "centered_pearson_product_moment_rho_equals_sxy_over_sqrt_sxx_times_syy.v1",
    "moment_rule_id": "exact_fraction_means_and_centered_sums_so_the_denominator_convention_cancels.v1",
    "perfect_correlation_rule_id": "exact_algebraic_plus_or_minus_one_preserved_exactly.v1",
    "decimal_policy_id": "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1",
    "decimal_context_rule_id": "one_fresh_fully_specified_context_passed_to_every_operation_ambient_never_used.v1",
    "rounding_adjudication_rule_id": (
        "exact_squared_half_unit_boundary_comparisons_decide_the_half_even_unit_the_decimal_value_is_a_candidate.v1"
    ),
    "decimal_scale": 18,
    "decimal_internal_precision": 80,
    "decimal_rounding": "ROUND_HALF_EVEN",
    "decimal_exponent_limit": 999999,
    "signed_zero_rule_id": "negative_zero_normalized_to_positive_zero.v1",
    "pair_universe_rule_id": "every_unordered_pair_of_envelope_declared_sleeves_once_as_min_max_lexicographic.v1",
    "day_identity_rule_id": "rg3_daily_return_i_is_the_utc_day_starting_at_window_start_plus_i_days.v1",
    "lookback_rule_id": "trailing_governed_lookback_window_days_ending_at_the_injected_utc_aligned_evaluation_end.v1",
    "currency_rule_id": "ready_sleeve_counts_only_when_its_window_ends_exactly_at_the_evaluation_end.v1",
    "overlap_rule_id": "exact_common_utc_days_inside_the_lookback_below_governed_min_overlap_is_worst_case_unknown.v1",
    "zero_variance_rule_id": "zero_variance_in_either_aligned_vector_is_worst_case_unknown.v1",
    "unknown_rule_id": "worst_case_unknown_effective_correlation_one_never_zero_never_dropped_never_the_cap.v1",
    "observation_rule_id": "no_positional_zip_interpolation_carry_forward_backfill_nearest_match_or_future_day.v1",
    "status_rule_id": "needs_governance_approval_over_ready_ready_is_the_complete_conservative_pair_matrix.v1",
    "regime_rule_id": "regime_stratified_correlation_pending_until_an_accepted_rf_chain.v1",
    "unknown_effective_correlation": "1.000000000000000000",
    "utc_day_ns": 86_400_000_000_000,
    "return_max_text_length": 4096,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_METHODOLOGY_ID = str(_RULE_SET_V1["methodology_id"])
_DECIMAL_POLICY_ID = str(_RULE_SET_V1["decimal_policy_id"])
_UNKNOWN_EFFECTIVE = str(_RULE_SET_V1["unknown_effective_correlation"])
_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_PRECISION: int = _RULE_SET_V1["decimal_internal_precision"]  # type: ignore[assignment]
_ROUNDING = str(_RULE_SET_V1["decimal_rounding"])
_EXPONENT_LIMIT: int = _RULE_SET_V1["decimal_exponent_limit"]  # type: ignore[assignment]
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_MAX_RETURN_TEXT: int = _RULE_SET_V1["return_max_text_length"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_UNITS = 10**_SCALE


def paper_sleeve_correlation_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class PaperSleeveCorrelationEvidenceError(EdgeArtifactError):
    """Raised on malformed input or any provenance or binding defect: an invalid evidence is never represented."""


class PaperSleeveCorrelationStatus(str, Enum):
    """READY is the complete conservative pair matrix; NEEDS_GOVERNANCE_APPROVAL when governance does not advance."""

    READY = "READY"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class PaperSleeveCorrelationPairStatus(str, Enum):
    """``WORST_CASE_UNKNOWN`` pairs carry the effective correlation one and no observed value."""

    OBSERVED = "OBSERVED"
    WORST_CASE_UNKNOWN = "WORST_CASE_UNKNOWN"


@dataclass(frozen=True)
class PaperPearsonCorrelationMeasurement:
    """The exact Pearson estimate of two aligned paper daily-return vectors; undefined when either variance is zero."""

    observation_count: int
    x_variance_zero: bool
    y_variance_zero: bool
    defined: bool
    correlation: str


@dataclass(frozen=True)
class PaperSleeveCorrelationSleeveInputs:
    """One sleeve's RG-3 evidence and the exact inputs it is rebuilt from."""

    performance_inputs: PaperSleevePerformanceInputs
    performance_evidence: PaperSleevePerformanceEvidence


@dataclass(frozen=True)
class PaperSleeveCorrelationInputs:
    """Everything RG-5 consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    correlation_evidence_id: str
    correlation_id: str
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    evaluation_end_ns: int
    sleeves: tuple[PaperSleeveCorrelationSleeveInputs, ...]


@dataclass(frozen=True)
class PaperSleeveCorrelationSleeveRecord:
    """One supplied sleeve's re-proven RG-3 binding and what it contributes to the lookback."""

    sleeve_id: str
    market_symbol: str
    performance_evidence_digest: str
    performance_status: str
    window_start_ns: int
    window_end_ns: int
    day_count: int
    current_for_evaluation: bool
    lookback_day_count: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PaperSleeveCorrelationPair:
    """One canonical unordered sleeve pair: its exact overlap and its observed or worst-case effective correlation."""

    sleeve_a_id: str
    sleeve_b_id: str
    pair_status: PaperSleeveCorrelationPairStatus
    overlap_start_ns: int
    overlap_end_ns: int
    overlap_day_count: int
    observed_correlation: str
    effective_correlation: str
    reason_codes: tuple[str, ...]


PAPER_SLEEVE_CORRELATION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("correlation_cap_breach_evaluated", False),
    ("diversification_credit_granted", False),
    ("portfolio_allocation_approved", False),
    ("capital_allocated", False),
    ("promotion_demotion_decided", False),
    ("portfolio_stop_evaluated", False),
    ("execution_authorized", False),
    ("account_equity_represented", False),
    ("capital_represented", False),
    ("regime_evidence_available", False),
    ("statistical_significance_proven", False),
    ("positional_alignment_used", False),
    ("interpolation_used", False),
    ("carry_forward_used", False),
    ("backfill_used", False),
    ("future_observation_used", False),
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
    ("mark_price_origin_proven", False),
    ("timestamp_origin_proven", False),
    ("episode_set_completeness_proven", False),
)


@dataclass(frozen=True)
class PaperSleeveCorrelationEvidence:
    """Immutable, digest-bound RG-5 correlation measurement evidence. Paper only; decides nothing."""

    schema_version: str
    status: PaperSleeveCorrelationStatus
    ready: bool
    correlation_evidence_id: str
    correlation_id: str
    envelope_digest: str
    envelope_policy_digest: str
    envelope_advances: bool
    envelope_rule_set_digest: str
    max_pairwise_correlation: str
    lookback_window_days: int
    min_overlap_days: int
    evaluation_end_ns: int
    lookback_start_ns: int
    declared_sleeve_ids: tuple[str, ...]
    sleeves: tuple[PaperSleeveCorrelationSleeveRecord, ...]
    missing_sleeve_ids: tuple[str, ...]
    pairs: tuple[PaperSleeveCorrelationPair, ...]
    pair_count: int
    observed_pair_count: int
    worst_case_pair_count: int
    all_pairs_observed: bool
    correlation_method_id: str
    decimal_policy_id: str
    unknown_effective_correlation: str
    regime_stratified_correlation_status: str
    regime_evidence_status: str
    rule_set_id: str
    rule_set_digest: str
    reason_codes: tuple[str, ...]
    correlation_evidence_digest: str
    paper_only: bool = True
    correlation_cap_breach_evaluated: bool = False
    diversification_credit_granted: bool = False
    portfolio_allocation_approved: bool = False
    capital_allocated: bool = False
    promotion_demotion_decided: bool = False
    portfolio_stop_evaluated: bool = False
    execution_authorized: bool = False
    account_equity_represented: bool = False
    capital_represented: bool = False
    regime_evidence_available: bool = False
    statistical_significance_proven: bool = False
    positional_alignment_used: bool = False
    interpolation_used: bool = False
    carry_forward_used: bool = False
    backfill_used: bool = False
    future_observation_used: bool = False
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
    mark_price_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    episode_set_completeness_proven: bool = False


_RECORD_TYPES = frozenset({PaperSleeveCorrelationSleeveRecord, PaperSleeveCorrelationPair})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperSleeveCorrelationEvidence: {"status": PaperSleeveCorrelationStatus},
    PaperSleeveCorrelationPair: {"pair_status": PaperSleeveCorrelationPairStatus},
}


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperSleeveCorrelationEvidenceError:
    return PaperSleeveCorrelationEvidenceError(_reason(code))


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


def _require_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _snapshot(values: object, field_name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    return tuple(values)  # type: ignore[arg-type]


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    """Call one accepted public builder; any failure is a provenance defect of this evidence."""

    try:
        return builder(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed at this boundary
        raise _fail(f"{code}_reconstruction_failed") from exc


def _parse_decimal(value: object, max_length: int) -> Fraction | None:
    """Exact value of canonical plain decimal text (no exponent, trailing zero or negative zero), else ``None``."""

    if type(value) is not str or value == "" or len(value) > max_length or not value.isascii():
        return None
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if not _ascii_digits(integer) or (integer != "0" and integer.startswith("0")):
        return None
    if dot == "." and (not _ascii_digits(fraction) or fraction.endswith("0")):
        return None
    if negative and integer == "0" and dot == "":
        return None
    return Fraction(value)


# --- the Pearson estimator ------------------------------------------------------------------------------------------


def _decimal_context() -> Context:
    """A fresh, fully specified context: nothing comes from the thread's ambient or the module default context."""

    return Context(
        prec=_PRECISION,
        rounding=_ROUNDING,
        Emin=-_EXPONENT_LIMIT,
        Emax=_EXPONENT_LIMIT,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def _render_units(units: int) -> str:
    """Exactly ``_SCALE`` fractional digits of an integer count of ``10**-_SCALE``; zero is never signed."""

    whole, fraction = divmod(abs(units), _UNITS)
    sign = "-" if units < 0 else ""
    return f"{sign}{whole}.{fraction:0{_SCALE}d}"


def _decimal_units(context: Context, value: Fraction) -> Decimal:
    """``value`` correctly rounded to the context: an exact integer quotient, every step through ``context``."""

    return context.divide(Decimal(value.numerator, context), Decimal(value.denominator, context))


def _candidate_units(sxy: Fraction, product: Fraction) -> int:
    """A precision-80 ``Decimal`` approximation of ``|Sxy| / sqrt(product)`` in ``10**-_SCALE`` units: a candidate only.

    Every operation receives the one explicit context and the quantized value is read back through ``as_tuple``, so no
    step reads or sets the thread's ambient context. The candidate never decides the published unit by itself.
    """

    context = _decimal_context()
    try:
        numerator = _decimal_units(context, abs(sxy))
        denominator = context.sqrt(_decimal_units(context, product))
        quantum = Decimal((0, (1,), -_SCALE), context)
        _, digits, exponent = context.quantize(context.divide(numerator, denominator), quantum).as_tuple()
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise _fail("correlation_decimal_evaluation_failed") from exc
    if exponent != -_SCALE:
        raise _fail("correlation_decimal_evaluation_failed")
    candidate = 0
    for digit in digits:
        candidate = candidate * 10 + digit
    return candidate


def _rounds_half_even_to(units: int, doubled_square: Fraction) -> bool:
    """Whether ``units`` is the half-even rounding of ``t >= 0``, given exactly ``doubled_square == (2 * t) ** 2``.

    ``t`` must lie strictly inside ``(units - 1/2, units + 1/2)``, or on one of those boundaries with ``units`` even.
    Both sides of every boundary comparison are non-negative, so squaring them keeps it exact: ``t < units + 1/2`` iff
    ``doubled_square < (2 * units + 1) ** 2``, and ``t > units - 1/2`` iff ``doubled_square > (2 * units - 1) ** 2``.
    """

    upper = (2 * units + 1) ** 2
    if doubled_square > upper or (doubled_square == upper and units % 2 == 1):
        return False
    if units == 0:
        return True
    lower = (2 * units - 1) ** 2
    return doubled_square > lower or (doubled_square == lower and units % 2 == 0)


def _correlation_units(sxy: Fraction, product: Fraction) -> int:
    """The signed scale-18 half-even unit of ``Sxy / sqrt(product)``, decided by exact rational comparisons.

    ``doubled_square = (2 * 10**18 * |rho|) ** 2`` is exact, so no input digit is lost before the decision. The
    precision-80 candidate is within one unit of the exact rounding: each of its four ``Decimal`` steps is correctly
    rounded to 80 significant digits, inside an exponent range the accepted input bounds never leave, so its relative
    error stays below ``10**-78``. As ``10**18 * |rho| <= 10**18``, the candidate before its own rounding is within
    ``10**-60`` units of ``10**18 * |rho|``, and two reals closer than one unit round to integers at most one apart.
    Exactly one integer passes the exact half-even boundary test; it is published, with no second rounding. Should no
    integer of that one-unit neighbourhood pass, the evaluation fails closed instead of publishing.
    """

    doubled_square = 4 * _UNITS * _UNITS * sxy * sxy / product
    candidate = _candidate_units(sxy, product)
    for units in (candidate, candidate - 1, candidate + 1):
        if 0 <= units <= _UNITS and _rounds_half_even_to(units, doubled_square):
            return -units if sxy < 0 else units
    raise _fail("correlation_rounding_not_adjudicated")


def _render_correlation(sxy: Fraction, product: Fraction) -> str:
    """``Sxy / sqrt(product)`` at the public scale, rounded half-even by exact adjudication; +1 and -1 stay exact."""

    if sxy * sxy == product:
        return _render_units(_UNITS if sxy > 0 else -_UNITS)
    return _render_units(_correlation_units(sxy, product))


def _pearson(xs: tuple[Fraction, ...], ys: tuple[Fraction, ...]) -> PaperPearsonCorrelationMeasurement:
    count = len(xs)
    mean_x = sum(xs, Fraction(0)) / count
    mean_y = sum(ys, Fraction(0)) / count
    sxx = sum(((x - mean_x) ** 2 for x in xs), Fraction(0))
    syy = sum(((y - mean_y) ** 2 for y in ys), Fraction(0))
    sxy = sum(((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)), Fraction(0))
    x_zero = sxx == 0
    y_zero = syy == 0
    correlation = "" if x_zero or y_zero else _render_correlation(sxy, sxx * syy)
    return PaperPearsonCorrelationMeasurement(
        observation_count=count,
        x_variance_zero=x_zero,
        y_variance_zero=y_zero,
        defined=correlation != "",
        correlation=correlation,
    )


def _parse_returns(values: object, field_name: str) -> tuple[Fraction, ...]:
    items = _snapshot(values, field_name)
    if not items:
        raise _fail(f"{field_name}_empty")
    parsed: list[Fraction] = []
    for item in items:
        value = _parse_decimal(item, _MAX_RETURN_TEXT)
        if value is None:
            raise _fail(f"{field_name}_observation_invalid")
        parsed.append(value)
    return tuple(parsed)


def measure_paper_pearson_correlation(
    x_returns: Sequence[str], y_returns: Sequence[str]
) -> PaperPearsonCorrelationMeasurement:
    """The exact Pearson estimate of two aligned vectors of canonical plain decimal daily-return text.

    Malformed or empty input, an invalid observation or vectors of different lengths raise
    ``PaperSleeveCorrelationEvidenceError``. A zero variance in either vector leaves the estimate undefined.
    """

    xs = _parse_returns(x_returns, "x_returns")
    ys = _parse_returns(y_returns, "y_returns")
    if len(xs) != len(ys):
        raise _fail("returns_length_mismatch")
    return _pearson(xs, ys)


# --- sleeve re-proof ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _ProvenSleeve:
    sleeve_id: str
    evidence: PaperSleevePerformanceEvidence
    returns: tuple[Fraction, ...] | None


def _prove_sleeve(item: object, *, envelope: PaperPortfolioRiskEnvelope, declared: frozenset[str]) -> _ProvenSleeve:
    _require_exact(item, PaperSleeveCorrelationSleeveInputs, "sleeve")
    sleeve = cast(PaperSleeveCorrelationSleeveInputs, item)
    _require_exact(getattr(sleeve, "performance_inputs", None), PaperSleevePerformanceInputs, "performance_inputs")
    _require_exact(
        getattr(sleeve, "performance_evidence", None), PaperSleevePerformanceEvidence, "performance_evidence"
    )
    rebuilt = _rebuild("sleeve_performance", build_paper_sleeve_performance_evidence, sleeve.performance_inputs)
    if not _canonically_equal(sleeve.performance_evidence, rebuilt, paper_sleeve_performance_evidence_to_dict):
        raise _fail("sleeve_performance_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("sleeve_performance_envelope_mismatch")
    if rebuilt.sleeve_id not in declared:
        raise _fail("sleeve_not_declared_by_envelope")
    if rebuilt.status is not PaperSleevePerformanceStatus.READY:
        return _ProvenSleeve(sleeve_id=rebuilt.sleeve_id, evidence=rebuilt, returns=None)
    if (
        rebuilt.window_start_ns % _DAY_NS != 0
        or rebuilt.window_end_ns - rebuilt.window_start_ns != rebuilt.day_count * _DAY_NS
        or len(rebuilt.daily_returns) != rebuilt.day_count
    ):
        raise _fail("sleeve_daily_returns_not_the_window")
    returns: list[Fraction] = []
    for text in rebuilt.daily_returns:
        value = _parse_decimal(text, _MAX_RETURN_TEXT)
        if value is None:
            raise _fail("sleeve_daily_return_invalid")
        returns.append(value)
    return _ProvenSleeve(sleeve_id=rebuilt.sleeve_id, evidence=rebuilt, returns=tuple(returns))


def _is_current(sleeve: _ProvenSleeve, evaluation_end: int) -> bool:
    """READY evidence as of the evaluation end: its window ends exactly there, so it holds the final lookback day."""

    return sleeve.returns is not None and sleeve.evidence.window_end_ns == evaluation_end


def _sleeve_record(
    sleeve: _ProvenSleeve, *, lookback_start: int, evaluation_end: int
) -> PaperSleeveCorrelationSleeveRecord:
    evidence = sleeve.evidence
    current = _is_current(sleeve, evaluation_end)
    reasons: list[str] = []
    lookback_days = 0
    if sleeve.returns is None:
        reasons.append(_reason("sleeve_performance_not_ready"))
        reasons.extend(evidence.reason_codes)
    elif evidence.window_end_ns < evaluation_end:
        reasons.append(_reason("sleeve_evidence_ends_before_the_evaluation_end"))
    elif not current:
        reasons.append(_reason("sleeve_evidence_extends_past_the_evaluation_end"))
    else:
        lookback_days = (evaluation_end - max(lookback_start, evidence.window_start_ns)) // _DAY_NS
    return PaperSleeveCorrelationSleeveRecord(
        sleeve_id=sleeve.sleeve_id,
        market_symbol=evidence.market_symbol,
        performance_evidence_digest=evidence.performance_evidence_digest,
        performance_status=evidence.status.value,
        window_start_ns=evidence.window_start_ns,
        window_end_ns=evidence.window_end_ns,
        day_count=evidence.day_count,
        current_for_evaluation=current,
        lookback_day_count=lookback_days,
        reason_codes=tuple(sorted(set(reasons))),
    )


# --- pairs ----------------------------------------------------------------------------------------------------------


def _aligned(sleeve: _ProvenSleeve, start: int, count: int) -> tuple[Fraction, ...]:
    """The sleeve's returns of the ``count`` UTC days from ``start``, selected by exact day identity."""

    returns = cast(tuple[Fraction, ...], sleeve.returns)
    offset = (start - sleeve.evidence.window_start_ns) // _DAY_NS
    selected = returns[offset : offset + count]
    if offset < 0 or len(selected) != count:
        raise _fail("sleeve_day_alignment_out_of_window")
    return selected


def _worst_case_pair(
    pair: tuple[str, str], start: int, end: int, count: int, reasons: Sequence[str]
) -> PaperSleeveCorrelationPair:
    return PaperSleeveCorrelationPair(
        sleeve_a_id=pair[0],
        sleeve_b_id=pair[1],
        pair_status=PaperSleeveCorrelationPairStatus.WORST_CASE_UNKNOWN,
        overlap_start_ns=start,
        overlap_end_ns=end,
        overlap_day_count=count,
        observed_correlation="",
        effective_correlation=_UNKNOWN_EFFECTIVE,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _measure_pair(
    pair: tuple[str, str],
    *,
    proven: dict[str, _ProvenSleeve],
    records: dict[str, PaperSleeveCorrelationSleeveRecord],
    lookback_start: int,
    evaluation_end: int,
    min_overlap: int,
) -> PaperSleeveCorrelationPair:
    reasons: list[str] = []
    for sleeve_id in pair:
        if sleeve_id not in proven:
            reasons.append(_reason(f"pair_sleeve_evidence_missing:{sleeve_id}"))
        elif proven[sleeve_id].returns is None:
            reasons.append(_reason(f"pair_sleeve_performance_not_ready:{sleeve_id}"))
        elif not records[sleeve_id].current_for_evaluation:
            reasons.append(_reason(f"pair_sleeve_evidence_not_current:{sleeve_id}"))
    if reasons:
        return _worst_case_pair(pair, evaluation_end, evaluation_end, 0, reasons)

    first, second = proven[pair[0]], proven[pair[1]]
    start = max(lookback_start, first.evidence.window_start_ns, second.evidence.window_start_ns)
    count = (evaluation_end - start) // _DAY_NS
    if count < min_overlap:
        return _worst_case_pair(pair, start, evaluation_end, count, [_reason("pair_overlap_below_governed_minimum")])
    measurement = _pearson(_aligned(first, start, count), _aligned(second, start, count))
    if not measurement.defined:
        zero = [
            sleeve_id
            for sleeve_id, is_zero in zip(pair, (measurement.x_variance_zero, measurement.y_variance_zero), strict=True)
            if is_zero
        ]
        return _worst_case_pair(
            pair, start, evaluation_end, count, [_reason(f"pair_variance_zero:{sleeve_id}") for sleeve_id in zero]
        )
    return PaperSleeveCorrelationPair(
        sleeve_a_id=pair[0],
        sleeve_b_id=pair[1],
        pair_status=PaperSleeveCorrelationPairStatus.OBSERVED,
        overlap_start_ns=start,
        overlap_end_ns=evaluation_end,
        overlap_day_count=count,
        observed_correlation=measurement.correlation,
        effective_correlation=measurement.correlation,
        reason_codes=(),
    )


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


# --- evidence -------------------------------------------------------------------------------------------------------


def _require_envelope(value: object) -> PaperPortfolioRiskEnvelope:
    _require_exact(value, PaperPortfolioRiskEnvelope, "portfolio_risk_envelope")
    if not verify_paper_portfolio_risk_envelope(value).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    envelope = cast(PaperPortfolioRiskEnvelope, value)
    if envelope.rule_set_digest != PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST:
        raise _fail("portfolio_risk_envelope_rule_set_unsupported")
    if envelope.regime_stratified_correlation_status != EDGE_REGIME_LABEL_BINDING_PENDING:
        raise _fail("portfolio_risk_envelope_regime_status_unsupported")
    return envelope


def build_paper_sleeve_correlation_evidence(inputs: PaperSleeveCorrelationInputs) -> PaperSleeveCorrelationEvidence:
    """Measure the correlation of every declared sleeve pair from re-proven evidence over the governed lookback.

    Malformed input and every provenance or binding defect raise ``PaperSleeveCorrelationEvidenceError``. Missing
    governance yields ``NEEDS_GOVERNANCE_APPROVAL``. Missing, unavailable, stale, insufficiently overlapping or
    zero-variance evidence yields a ``WORST_CASE_UNKNOWN`` pair. Inputs are read once and never mutated. The evidence
    decides nothing.
    """

    _require_exact(inputs, PaperSleeveCorrelationInputs, "inputs")
    evidence_id = _require_text(inputs.correlation_evidence_id, "correlation_evidence_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    evaluation_end = _require_int(inputs.evaluation_end_ns, "evaluation_end_ns")
    if evaluation_end % _DAY_NS != 0:
        raise _fail("evaluation_end_ns_not_utc_day_aligned")
    envelope = _require_envelope(inputs.portfolio_risk_envelope)
    cap = envelope.correlation_cap
    lookback_start = evaluation_end - cap.lookback_window_days * _DAY_NS
    if lookback_start < 0:
        raise _fail("evaluation_end_ns_precedes_the_lookback_window")
    declared = tuple(sorted(item.sleeve_id for item in envelope.sleeve_caps))

    proven: dict[str, _ProvenSleeve] = {}
    for item in _snapshot(inputs.sleeves, "sleeves"):
        sleeve = _prove_sleeve(item, envelope=envelope, declared=frozenset(declared))
        if sleeve.sleeve_id in proven:
            raise _fail("sleeve_duplicate")
        proven[sleeve.sleeve_id] = sleeve

    governance: list[str] = []
    if envelope.advances is not True:
        governance.append(_reason("portfolio_risk_envelope_not_governed"))
    records: dict[str, PaperSleeveCorrelationSleeveRecord] = {}
    for sleeve_id in sorted(proven):
        if proven[sleeve_id].evidence.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL:
            governance.append(_reason(f"sleeve_performance_needs_governance_approval:{sleeve_id}"))
        records[sleeve_id] = _sleeve_record(
            proven[sleeve_id], lookback_start=lookback_start, evaluation_end=evaluation_end
        )
    pairs = tuple(
        _measure_pair(
            pair,
            proven=proven,
            records=records,
            lookback_start=lookback_start,
            evaluation_end=evaluation_end,
            min_overlap=cap.min_overlap_days,
        )
        for pair in combinations(declared, 2)
    )
    observed = sum(1 for pair in pairs if pair.pair_status is PaperSleeveCorrelationPairStatus.OBSERVED)
    status = (
        PaperSleeveCorrelationStatus.NEEDS_GOVERNANCE_APPROVAL if governance else PaperSleeveCorrelationStatus.READY
    )
    seed = PaperSleeveCorrelationEvidence(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=status is PaperSleeveCorrelationStatus.READY,
        correlation_evidence_id=evidence_id,
        correlation_id=correlation_id,
        envelope_digest=envelope.envelope_digest,
        envelope_policy_digest=envelope.policy_digest,
        envelope_advances=envelope.advances,
        envelope_rule_set_digest=envelope.rule_set_digest,
        max_pairwise_correlation=cap.max_pairwise_correlation,
        lookback_window_days=cap.lookback_window_days,
        min_overlap_days=cap.min_overlap_days,
        evaluation_end_ns=evaluation_end,
        lookback_start_ns=lookback_start,
        declared_sleeve_ids=declared,
        sleeves=tuple(records[sleeve_id] for sleeve_id in sorted(records)),
        missing_sleeve_ids=tuple(sleeve_id for sleeve_id in declared if sleeve_id not in proven),
        pairs=pairs,
        pair_count=len(pairs),
        observed_pair_count=observed,
        worst_case_pair_count=len(pairs) - observed,
        all_pairs_observed=observed == len(pairs),
        correlation_method_id=_METHODOLOGY_ID,
        decimal_policy_id=_DECIMAL_POLICY_ID,
        unknown_effective_correlation=_UNKNOWN_EFFECTIVE,
        regime_stratified_correlation_status=envelope.regime_stratified_correlation_status,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST,
        reason_codes=tuple(sorted(set(governance))),
        correlation_evidence_digest="",
    )
    return replace(seed, correlation_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def paper_sleeve_correlation_evidence_to_dict(evidence: PaperSleeveCorrelationEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def paper_sleeve_correlation_evidence_digest(evidence: PaperSleeveCorrelationEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``correlation_evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def verify_paper_sleeve_correlation_evidence(
    evidence: object, inputs: PaperSleeveCorrelationInputs
) -> EdgeEvidenceVerification:
    """Re-prove an evidence by rebuilding it from its exact inputs. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not PaperSleeveCorrelationEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _to_payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _SELF_DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _to_payload(build_paper_sleeve_correlation_evidence(inputs))
        codes: set[str] = set()
        if carried[_SELF_DIGEST_FIELD] != recomputed:
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
    "PAPER_SLEEVE_CORRELATION_NON_CLAIM_FLAGS",
    "PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST",
    "PaperPearsonCorrelationMeasurement",
    "PaperSleeveCorrelationEvidence",
    "PaperSleeveCorrelationEvidenceError",
    "PaperSleeveCorrelationInputs",
    "PaperSleeveCorrelationPair",
    "PaperSleeveCorrelationPairStatus",
    "PaperSleeveCorrelationSleeveInputs",
    "PaperSleeveCorrelationSleeveRecord",
    "PaperSleeveCorrelationStatus",
    "build_paper_sleeve_correlation_evidence",
    "measure_paper_pearson_correlation",
    "paper_sleeve_correlation_evidence_digest",
    "paper_sleeve_correlation_evidence_to_dict",
    "paper_sleeve_correlation_rule_set",
    "verify_paper_sleeve_correlation_evidence",
]
