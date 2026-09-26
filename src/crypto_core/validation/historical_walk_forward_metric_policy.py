"""Governed historical walk-forward metric policy (HISTORICAL_WALK_FORWARD_METRICS_V1).

A ``HistoricalWalkForwardMetricPolicy`` is the only source of every load-bearing convention the historical walk-forward
metrics layer (``historical_walk_forward_metrics``) may use: calendar and daily bucket, window geometry (in-sample and
out-of-sample durations, stride, embargo, interval semantics, ordering, identity, generic window count), the
parameter-assignment binding rule, the source consistency and authority rules, the observation basis and daily endpoint
rule, the equity domain, the daily return formula, the minimum daily return count, the risk-free policy, the Sharpe
definition (sample standard deviation, annualization, zero-variance rule), the hit-rate, expectancy, maximum-drawdown and
profit-factor definitions with their undefined-value rules, and the numeric policy. Every identity and value is a
first-class field committed by ``policy_digest``; the metrics layer reads them from the verified policy, never from
ambient state.

V1 is closed. The builder accepts only caller identity text (``policy_id``, ``policy_version``) and fills every other
field from the code-defined V1 constants, so a V1 policy carries no ungoverned variant parameter. A payload carrying any
other value is well formed but never verifies, because reassembly re-derives the V1 constants; a consumer that re-proves
the policy therefore refuses an unsupported identity.

Geometry V1: UTC calendar, one-day buckets of 86_400_000_000_000 ns, in-sample 365 days, out-of-sample 90 days, stride
90 days (successive out-of-sample starts), embargo 0 days (the out-of-sample segment starts exactly at the in-sample
end), half-open ``[start, end)`` intervals aligned to UTC days, and a GENERIC window count of one or more (no fixed
count). Within one window the in-sample and out-of-sample segments bind the same parameter assignment; across windows
the assignment may change.

Numeric V1 (``HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1``): exact rational arithmetic; public numbers are canonical
scale-18 decimal text (ASCII, no exponent, no plus sign, no negative zero, at most 60 characters) rendered once by
exact integer ROUND_HALF_EVEN. The one irrational operation, the annualized Sharpe ratio, is evaluated as
``sign(mean) * sqrt(mean^2 * 365 / sample_variance)`` — the exact identity of ``daily_sharpe * sqrt(365)`` — by an exact
integer square root with an exact ROUND_HALF_EVEN tie decision at scale 18. There is no ``decimal`` module, no float
and no near-zero epsilon.

Deterministic and pure: no IO, clock, randomness, network or environment. The policy proves no edge, profitability,
admission or readiness and consumes no evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_payload_digest,
    edge_scope_violation,
    verify_edge_artifact_total,
)

_SCHEMA_VERSION = "historical-walk-forward-metric-policy.v1"
_REASON_PREFIX = "historical_walk_forward_metric_policy"
_SELF_DIGEST_FIELD = "policy_digest"

HISTORICAL_WALK_FORWARD_MAX_WIRE_INT = 9223372036854775807


@dataclass(frozen=True)
class HistoricalWalkForwardMetricNumericPolicy:
    """Numeric rules of the metrics layer; each field is committed by the policy digest and read at execution."""

    numeric_policy_id: str
    arithmetic_id: str
    decimal_grammar_id: str
    decimal_scale: int
    max_decimal_text_length: int
    rounding_id: str
    sqrt_id: str
    signed_zero_rule_id: str
    near_zero_epsilon_policy_id: str
    max_wire_integer: int


HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1 = HistoricalWalkForwardMetricNumericPolicy(
    numeric_policy_id="historical_walk_forward_metric_numeric_policy.v1",
    arithmetic_id="exact_rational_integer_arithmetic.v1",
    decimal_grammar_id="ascii_signed_canonical_integer_dot_fixed_scale_no_exponent_no_plus_no_negative_zero.v1",
    decimal_scale=18,
    max_decimal_text_length=60,
    rounding_id="exact_integer_round_half_even.v1",
    sqrt_id="exact_integer_isqrt_round_half_even.v1",
    signed_zero_rule_id="negative_zero_normalized_to_zero.v1",
    near_zero_epsilon_policy_id="none.v1",
    max_wire_integer=HISTORICAL_WALK_FORWARD_MAX_WIRE_INT,
)

# --- V1 identities and values (committed by the policy digest) -------------------------------------------------------

METRIC_POLICY_ID_V1 = "historical_walk_forward_metric_policy.v1"
CALENDAR_UTC = "UTC"
BUCKET_FREQUENCY_1D_UTC = "1d_utc"
DAY_NS = 86_400_000_000_000
IN_SAMPLE_DURATION_DAYS_V1 = 365
OUT_OF_SAMPLE_DURATION_DAYS_V1 = 90
WINDOW_STRIDE_DAYS_V1 = 90
EMBARGO_DAYS_V1 = 0
INTERVAL_SEMANTICS_V1 = "half_open_start_inclusive_end_exclusive_utc_day_aligned.v1"
WINDOW_COUNT_RULE_V1 = "generic_one_or_more_windows_no_fixed_count.v1"
WINDOW_ORDER_RULE_V1 = "caller_order_strictly_increasing_out_of_sample_start_exact_stride.v1"
WINDOW_IDENTITY_RULE_V1 = "window_id_unique_within_result.v1"
ASSIGNMENT_BINDING_RULE_V1 = "same_parameter_assignment_digest_within_window_may_change_across_windows.v1"
SOURCE_CONSISTENCY_RULE_V1 = (
    "same_strategy_spec_instrument_market_type_economics_policy_profile_semantics_and_registry_across_all_segments.v1"
)
SOURCE_AUTHORITY_RULE_V1 = (
    "historical_execution_economics_reproven_by_public_verifier_against_anchor_same_correlation_computed.v1"
)
OBSERVATION_BASIS_V1 = "authenticated_historical_execution_valuation_equity.v1"
DAILY_ENDPOINT_RULE_V1 = "initial_at_start_then_every_utc_day_boundary_then_evaluation_end_one_per_instant.v1"
EQUITY_DOMAIN_RULE_V1 = "every_daily_endpoint_equity_canonical_and_strictly_positive.v1"
DAILY_RETURN_FORMULA_V1 = "equity_t_over_equity_t_minus_1_minus_1.v1"
MIN_DAILY_RETURN_COUNT_V1 = 2
RISK_FREE_POLICY_ID_V1 = "constant_zero_daily_review_only.v1"
RISK_FREE_POLICY_V1 = "constant_zero_daily_review_only"
RISK_FREE_DAILY_RETURN_V1 = "0.000000000000000000"
SHARPE_STDDEV_POLICY_V1 = "sample_stddev_n_minus_1.v1"
SHARPE_ANNUALIZATION_POLICY_V1 = "daily_utc_365_review_only"
SHARPE_ANNUALIZATION_FACTOR_V1 = 365
SHARPE_ANNUALIZATION_FORMULA_V1 = "daily_sharpe * sqrt(365)"
SHARPE_ZERO_VARIANCE_RULE_V1 = "exact_zero_variance_zero_mean_is_zero_nonzero_mean_fails_closed.v1"
HIT_RATE_FORMULA_V1 = "positive_daily_return_count_over_daily_return_count_zero_is_not_a_hit.v1"
EXPECTANCY_FORMULA_V1 = "arithmetic_mean_daily_return.v1"
MAX_DRAWDOWN_FORMULA_V1 = "max_over_path_of_running_peak_minus_equity_over_running_peak_nonnegative.v1"
MAX_DRAWDOWN_PATH_V1 = "daily_endpoint_equity_path_including_start.v1"
PROFIT_FACTOR_FORMULA_V1 = "gross_positive_daily_returns_over_absolute_gross_negative_daily_returns.v1"
PROFIT_FACTOR_UNDEFINED_RULE_V1 = "zero_gross_negative_daily_returns_fails_closed_no_infinity.v1"

HISTORICAL_WALK_FORWARD_METRIC_POLICY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("pbo_passed", False),
    ("stress_passed", False),
    ("performance_metrics_computed", False),
    ("admission_decided", False),
)
_FLAG_NAMES = frozenset(name for name, _ in HISTORICAL_WALK_FORWARD_METRIC_POLICY_NON_CLAIM_FLAGS)


class HistoricalWalkForwardMetricPolicyError(EdgeArtifactError):
    """Raised on malformed caller input or a forbidden scope token."""


@dataclass(frozen=True)
class HistoricalWalkForwardMetricPolicy:
    """Immutable, digest-bound V1 walk-forward metric policy. Consumes no evidence and proves no edge."""

    schema_version: str
    policy_id: str
    policy_version: str
    metric_policy_id: str
    calendar: str
    bucket_frequency: str
    day_ns: int
    in_sample_duration_days: int
    out_of_sample_duration_days: int
    window_stride_days: int
    embargo_days: int
    interval_semantics_id: str
    window_count_rule_id: str
    window_order_rule_id: str
    window_identity_rule_id: str
    assignment_binding_rule_id: str
    source_consistency_rule_id: str
    source_authority_rule_id: str
    observation_basis_id: str
    daily_endpoint_rule_id: str
    equity_domain_rule_id: str
    daily_return_formula_id: str
    min_daily_return_count: int
    risk_free_policy_id: str
    risk_free_policy: str
    risk_free_daily_return: str
    sharpe_stddev_policy_id: str
    sharpe_annualization_policy: str
    sharpe_annualization_factor: int
    sharpe_annualization_formula: str
    sharpe_zero_variance_rule_id: str
    hit_rate_formula_id: str
    expectancy_formula_id: str
    max_drawdown_formula_id: str
    max_drawdown_path_id: str
    profit_factor_formula_id: str
    profit_factor_undefined_rule_id: str
    numeric_policy: HistoricalWalkForwardMetricNumericPolicy
    policy_digest: str
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
    performance_metrics_computed: bool = False
    admission_decided: bool = False


# --- helpers ------------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> HistoricalWalkForwardMetricPolicyError:
    return HistoricalWalkForwardMetricPolicyError(_reason(code))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


# --- assembly -----------------------------------------------------------------------------------------------------------


def _assemble_policy(*, policy_id: object, policy_version: object) -> HistoricalWalkForwardMetricPolicy:
    """The one policy assembly path, shared by the builder and verifier reassembly."""

    seed = HistoricalWalkForwardMetricPolicy(
        schema_version=_SCHEMA_VERSION,
        policy_id=_require_text(policy_id, "policy_id"),
        policy_version=_require_text(policy_version, "policy_version"),
        metric_policy_id=METRIC_POLICY_ID_V1,
        calendar=CALENDAR_UTC,
        bucket_frequency=BUCKET_FREQUENCY_1D_UTC,
        day_ns=DAY_NS,
        in_sample_duration_days=IN_SAMPLE_DURATION_DAYS_V1,
        out_of_sample_duration_days=OUT_OF_SAMPLE_DURATION_DAYS_V1,
        window_stride_days=WINDOW_STRIDE_DAYS_V1,
        embargo_days=EMBARGO_DAYS_V1,
        interval_semantics_id=INTERVAL_SEMANTICS_V1,
        window_count_rule_id=WINDOW_COUNT_RULE_V1,
        window_order_rule_id=WINDOW_ORDER_RULE_V1,
        window_identity_rule_id=WINDOW_IDENTITY_RULE_V1,
        assignment_binding_rule_id=ASSIGNMENT_BINDING_RULE_V1,
        source_consistency_rule_id=SOURCE_CONSISTENCY_RULE_V1,
        source_authority_rule_id=SOURCE_AUTHORITY_RULE_V1,
        observation_basis_id=OBSERVATION_BASIS_V1,
        daily_endpoint_rule_id=DAILY_ENDPOINT_RULE_V1,
        equity_domain_rule_id=EQUITY_DOMAIN_RULE_V1,
        daily_return_formula_id=DAILY_RETURN_FORMULA_V1,
        min_daily_return_count=MIN_DAILY_RETURN_COUNT_V1,
        risk_free_policy_id=RISK_FREE_POLICY_ID_V1,
        risk_free_policy=RISK_FREE_POLICY_V1,
        risk_free_daily_return=RISK_FREE_DAILY_RETURN_V1,
        sharpe_stddev_policy_id=SHARPE_STDDEV_POLICY_V1,
        sharpe_annualization_policy=SHARPE_ANNUALIZATION_POLICY_V1,
        sharpe_annualization_factor=SHARPE_ANNUALIZATION_FACTOR_V1,
        sharpe_annualization_formula=SHARPE_ANNUALIZATION_FORMULA_V1,
        sharpe_zero_variance_rule_id=SHARPE_ZERO_VARIANCE_RULE_V1,
        hit_rate_formula_id=HIT_RATE_FORMULA_V1,
        expectancy_formula_id=EXPECTANCY_FORMULA_V1,
        max_drawdown_formula_id=MAX_DRAWDOWN_FORMULA_V1,
        max_drawdown_path_id=MAX_DRAWDOWN_PATH_V1,
        profit_factor_formula_id=PROFIT_FACTOR_FORMULA_V1,
        profit_factor_undefined_rule_id=PROFIT_FACTOR_UNDEFINED_RULE_V1,
        numeric_policy=HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1,
        policy_digest="",
    )
    return replace(seed, policy_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_historical_walk_forward_metric_policy(
    *, policy_id: str, policy_version: str
) -> HistoricalWalkForwardMetricPolicy:
    """Build the closed V1 walk-forward metric policy. Malformed identity text raises the policy error."""

    return _assemble_policy(policy_id=policy_id, policy_version=policy_version)


def historical_walk_forward_metric_policy_to_dict(policy: HistoricalWalkForwardMetricPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a policy, including its self-digest."""

    return _to_payload(policy)


def historical_walk_forward_metric_policy_digest(policy: HistoricalWalkForwardMetricPolicy) -> str:
    """Recompute the canonical policy digest, excluding only ``policy_digest``."""

    return edge_payload_digest(_to_payload(policy), _SELF_DIGEST_FIELD)


# --- strict parsing -----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= HISTORICAL_WALK_FORWARD_MAX_WIRE_INT:
        raise _fail("payload_field_malformed")
    return value


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


_NUMERIC_CONVERTERS: dict[str, Callable[[object], object]] = {
    "decimal_scale": _as_int,
    "max_decimal_text_length": _as_int,
    "max_wire_integer": _as_int,
}


def _as_numeric_policy(value: object) -> HistoricalWalkForwardMetricNumericPolicy:
    return _parse_exact(HistoricalWalkForwardMetricNumericPolicy, value, _NUMERIC_CONVERTERS)  # type: ignore[return-value]


_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "day_ns": _as_int,
    "in_sample_duration_days": _as_int,
    "out_of_sample_duration_days": _as_int,
    "window_stride_days": _as_int,
    "embargo_days": _as_int,
    "min_daily_return_count": _as_int,
    "sharpe_annualization_factor": _as_int,
    "numeric_policy": _as_numeric_policy,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def historical_walk_forward_metric_policy_from_payload(payload: object) -> HistoricalWalkForwardMetricPolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(HistoricalWalkForwardMetricPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def historical_walk_forward_metric_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a policy snapshot."""

    try:
        historical_walk_forward_metric_policy_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_policy(policy: object) -> HistoricalWalkForwardMetricPolicy:
    return _assemble_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        policy_version=policy.policy_version,  # type: ignore[attr-defined]
    )


def verify_historical_walk_forward_metric_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-derive the closed V1 policy and compare every field. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=HistoricalWalkForwardMetricPolicy,
        to_payload=_to_payload,
        parse_payload=historical_walk_forward_metric_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "ASSIGNMENT_BINDING_RULE_V1",
    "BUCKET_FREQUENCY_1D_UTC",
    "CALENDAR_UTC",
    "DAILY_ENDPOINT_RULE_V1",
    "DAILY_RETURN_FORMULA_V1",
    "DAY_NS",
    "EMBARGO_DAYS_V1",
    "EQUITY_DOMAIN_RULE_V1",
    "EXPECTANCY_FORMULA_V1",
    "HISTORICAL_WALK_FORWARD_MAX_WIRE_INT",
    "HISTORICAL_WALK_FORWARD_METRIC_POLICY_NON_CLAIM_FLAGS",
    "HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1",
    "HIT_RATE_FORMULA_V1",
    "HistoricalWalkForwardMetricNumericPolicy",
    "HistoricalWalkForwardMetricPolicy",
    "HistoricalWalkForwardMetricPolicyError",
    "INTERVAL_SEMANTICS_V1",
    "IN_SAMPLE_DURATION_DAYS_V1",
    "MAX_DRAWDOWN_FORMULA_V1",
    "MAX_DRAWDOWN_PATH_V1",
    "METRIC_POLICY_ID_V1",
    "MIN_DAILY_RETURN_COUNT_V1",
    "OBSERVATION_BASIS_V1",
    "OUT_OF_SAMPLE_DURATION_DAYS_V1",
    "PROFIT_FACTOR_FORMULA_V1",
    "PROFIT_FACTOR_UNDEFINED_RULE_V1",
    "RISK_FREE_DAILY_RETURN_V1",
    "RISK_FREE_POLICY_ID_V1",
    "RISK_FREE_POLICY_V1",
    "SHARPE_ANNUALIZATION_FACTOR_V1",
    "SHARPE_ANNUALIZATION_FORMULA_V1",
    "SHARPE_ANNUALIZATION_POLICY_V1",
    "SHARPE_STDDEV_POLICY_V1",
    "SHARPE_ZERO_VARIANCE_RULE_V1",
    "SOURCE_AUTHORITY_RULE_V1",
    "SOURCE_CONSISTENCY_RULE_V1",
    "WINDOW_COUNT_RULE_V1",
    "WINDOW_IDENTITY_RULE_V1",
    "WINDOW_ORDER_RULE_V1",
    "WINDOW_STRIDE_DAYS_V1",
    "build_historical_walk_forward_metric_policy",
    "historical_walk_forward_metric_policy_digest",
    "historical_walk_forward_metric_policy_from_payload",
    "historical_walk_forward_metric_policy_payload_is_well_formed",
    "historical_walk_forward_metric_policy_to_dict",
    "verify_historical_walk_forward_metric_policy",
]
