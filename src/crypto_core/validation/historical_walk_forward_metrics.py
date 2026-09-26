"""Deterministic historical walk-forward metrics (HISTORICAL_WALK_FORWARD_METRICS_V1).

A ``HistoricalWalkForwardMetricsResult`` turns an ordered set of walk-forward windows — each one authenticated
in-sample (IS) and one authenticated out-of-sample (OOS) ``HistoricalExecutionEconomicsResult`` — into digest-bound
historical performance metrics under one governed ``HistoricalWalkForwardMetricPolicy``:

authenticated valuation ledgers → one UTC daily mark-to-market endpoint sequence per segment → daily returns →
annualized Sharpe, hit rate, expectancy, maximum drawdown and profit factor for every IS and OOS segment.

METRICS ONLY. A computed result states exactly that these metrics were deterministically computed from authenticated
historical execution-economics evidence. It never states that they are good: it computes no supportive or pass/fail
edge quality, admission, PBO, stress, EF-5 acceptance, ranking, allocation or paper/live readiness, and it advances no
stage. It also does not prove HOW a window's parameter assignment was chosen (for example that only in-sample data
selected it); that selection and its preregistration belong to a later, separately governed stage. Each segment's
point-in-time discipline is the upstream decision run's, re-proven through the economics verifier.

Authority. The policy is re-proven through its public verifier against the caller's anchor. Every IS and OOS source is
re-proven through ``verify_historical_execution_economics`` (which itself re-derives the decision run and every ledger)
against its own caller anchor and must carry this result's correlation id; a carried id or digest is never trusted.
A source must be READY + PASS with ``simulated_economics_computed``. No execution is simulated here, no decision is
recomputed and no second economics model exists: the metrics consume only the authenticated valuation equity.

Window model (policy V1). Each segment is a half-open ``[start, end)`` interval aligned to UTC days; IS lasts exactly
365 days and OOS exactly 90 days; the OOS segment starts exactly at the IS end (embargo 0); successive windows advance
their OOS start by exactly the 90-day stride, in caller order; window ids are unique; the window count is generic (one
or more). The IS and OOS segments of one window bind the same ``parameter_assignment_digest``; different windows may
bind different assignments. All segments share one strategy spec, instrument, market type, economics policy, profile
semantics and data-requirement registry.

Daily endpoints (``initial_at_start_then_every_utc_day_boundary_then_evaluation_end_one_per_instant.v1``). The canonical
valuation ledger holds exactly one ``INITIAL`` valuation first at ``evaluation_start_ns``, exactly one
``UTC_DAY_BOUNDARY`` valuation at every interior UTC day boundary, and exactly one ``EVALUATION_END`` valuation last at
``evaluation_end_ns``; FILL and FUNDING_SETTLEMENT valuations at the same instant are never endpoints, so no instant is
counted twice. A day boundary valuation is taken after every event of its instant (canonical event order). The equity of
each endpoint is the authenticated scale-18 equity text, already net of fees, funding and mark-to-market, and is never
adjusted again. Every endpoint equity must be canonical and strictly positive; a segment of N days yields N daily
returns ``r_t = equity_t / equity_(t-1) - 1``.

Metrics, each committed by the policy digest:

* annualized Sharpe (risk-free 0): ``daily_sharpe * sqrt(365)`` with the sample standard deviation (n - 1), evaluated
  as ``sign(mean_excess) * sqrt(mean_excess^2 * 365 / sample_variance)``; zero variance with zero mean is 0, zero
  variance with a nonzero mean fails closed; no epsilon;
* hit rate: positive daily returns / daily returns (zero is not a hit);
* expectancy: arithmetic mean daily return;
* maximum drawdown: ``max((running_peak - equity) / running_peak)`` over the daily endpoint path including the start,
  a non-negative fraction;
* profit factor: gross positive daily returns / absolute gross negative daily returns; a zero denominator fails closed
  (``profit_factor_undefined_zero_gross_loss``) and infinity is never fabricated.

Numeric discipline: exact rational integer arithmetic. The daily sums are accumulated over one common denominator (the
product of the distinct previous-day equities) so their cost stays linear in the segment length; the common denominator
cancels exactly in the Sharpe radicand. Public numbers are canonical scale-18 text rendered once by exact integer
ROUND_HALF_EVEN (the Sharpe square root by an exact integer square root with an exact tie decision); a value outside
the 60-character representation fails closed (``metric_out_of_representation:<metric>``). No ``decimal`` module, no
float and no near-zero epsilon.

Outcomes: an integrity failure (malformed or non-verifying policy or source, anchor mismatch, correlation mismatch) is
``REJECTED``/``NOT_EVALUATED``; a verified input the V1 contract cannot compute (source not computed, geometry,
ordering, identity, assignment or consistency violation, endpoint or equity-domain violation, undefined metric) is
``READY``/``FAIL``; only ``READY``/``PASS`` carries metrics and ``performance_metrics_computed=True``. Nothing is
fabricated on any other outcome. One assembly path serves the builder and verifier reassembly;
``verify_historical_walk_forward_metrics`` is total. Deterministic and pure: no IO, clock, randomness, network or
environment.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

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
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    verify_edge_artifact_total,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionValuation,
    HistoricalExecutionValuationKind,
    historical_execution_economics_from_payload,
    historical_execution_economics_payload_is_well_formed,
    historical_execution_economics_to_dict,
    verify_historical_execution_economics,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_decimal_is_canonical
from crypto_core.validation.historical_walk_forward_metric_policy import (
    HISTORICAL_WALK_FORWARD_MAX_WIRE_INT,
    HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1,
    HistoricalWalkForwardMetricNumericPolicy,
    HistoricalWalkForwardMetricPolicy,
    historical_walk_forward_metric_policy_from_payload,
    historical_walk_forward_metric_policy_payload_is_well_formed,
    historical_walk_forward_metric_policy_to_dict,
    verify_historical_walk_forward_metric_policy,
)

_SCHEMA_VERSION = "historical-walk-forward-metrics.v1"
_REASON_PREFIX = "historical_walk_forward_metrics"
_SELF_DIGEST_FIELD = "result_digest"

# This artifact consumes IS and OOS simulated economics by construction, so the two structural flags that deny such
# consumption are not carried; every other structural non-claim holds.
_CONSUMPTION_FLAGS = frozenset({"performance_data_consumed", "oos_evidence_consumed"})
HISTORICAL_WALK_FORWARD_METRICS_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *(item for item in EDGE_STRUCTURAL_NON_CLAIM_FLAGS if item[0] not in _CONSUMPTION_FLAGS),
    ("pbo_passed", False),
    ("stress_passed", False),
    ("admission_decided", False),
    ("stage_advanced", False),
    ("external_archive_truth_proven", False),
    ("venue_fill_truth_proven", False),
    ("venue_facts_proven", False),
    ("venue_orders_created", False),
)
_FLAG_NAMES = frozenset(name for name, _ in HISTORICAL_WALK_FORWARD_METRICS_NON_CLAIM_FLAGS)

_SOURCE_CONSISTENCY_FIELDS = (
    "strategy_spec_digest",
    "instrument",
    "market_type",
    "economics_policy_digest",
    "profile_semantics_digest",
    "data_requirement_registry_digest",
)


class HistoricalWalkForwardMetricsError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class HistoricalWalkForwardSegmentKind(str, Enum):
    IN_SAMPLE = "IN_SAMPLE"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"


@dataclass(frozen=True)
class HistoricalWalkForwardWindowInput:
    """Caller input for one window: the IS and OOS economics results and the caller's anchor for each."""

    window_id: str
    in_sample_economics: HistoricalExecutionEconomicsResult
    expected_in_sample_result_digest: str
    out_of_sample_economics: HistoricalExecutionEconomicsResult
    expected_out_of_sample_result_digest: str


@dataclass(frozen=True)
class HistoricalWalkForwardWindowBinding:
    """The consumed authority of one window: its id and the IS/OOS economics bindings (snapshot plus anchor)."""

    window_id: str
    in_sample_binding: EdgeAuthorityBinding
    out_of_sample_binding: EdgeAuthorityBinding


@dataclass(frozen=True)
class HistoricalWalkForwardSegmentMetrics:
    """Metrics of one IS or OOS segment, bound to its authenticated source and daily endpoint sequence."""

    segment_kind: HistoricalWalkForwardSegmentKind
    source_result_id: str
    source_result_digest: str
    source_valuation_ledger_digest: str
    evaluation_start_ns: int
    evaluation_end_ns: int
    daily_endpoint_count: int
    daily_endpoint_digest: str
    daily_return_count: int
    positive_daily_return_count: int
    negative_daily_return_count: int
    zero_daily_return_count: int
    start_equity: str
    end_equity: str
    annualized_sharpe: str
    hit_rate: str
    expectancy: str
    max_drawdown: str
    profit_factor: str
    segment_digest: str


@dataclass(frozen=True)
class HistoricalWalkForwardWindowMetrics:
    """One walk-forward window: its assignment and the IS and OOS segment metrics."""

    window_index: int
    window_id: str
    parameter_assignment_digest: str
    in_sample: HistoricalWalkForwardSegmentMetrics
    out_of_sample: HistoricalWalkForwardSegmentMetrics
    window_digest: str


@dataclass(frozen=True)
class HistoricalWalkForwardMetricsResult:
    """Immutable, digest-bound historical walk-forward metrics. Integrity/computability only; proves no edge."""

    schema_version: str
    status: EdgeEvidenceStatus
    computation_verdict: EdgeGateVerdict
    result_id: str
    correlation_id: str
    policy_binding: EdgeAuthorityBinding
    metric_policy_digest: str
    window_bindings: tuple[HistoricalWalkForwardWindowBinding, ...]
    window_count: int
    window_ids: tuple[str, ...]
    source_result_digests: tuple[str, ...]
    strategy_spec_digest: str
    instrument: str
    market_type: str
    economics_policy_digest: str
    profile_semantics_digest: str
    data_requirement_registry_digest: str
    synthetic_test_facts_used: bool
    synthetic_test_approval_used: bool
    windows: tuple[HistoricalWalkForwardWindowMetrics, ...]
    window_digests: tuple[str, ...]
    performance_metrics_computed: bool
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    result_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    preregistration_sealed: bool = False
    kill_criteria_sealed: bool = False
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
    admission_decided: bool = False
    stage_advanced: bool = False
    external_archive_truth_proven: bool = False
    venue_fill_truth_proven: bool = False
    venue_facts_proven: bool = False
    venue_orders_created: bool = False


# --- helpers ------------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> HistoricalWalkForwardMetricsError:
    return HistoricalWalkForwardMetricsError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


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
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _sealed(record: object, digest_field: str) -> object:
    return replace(record, **{digest_field: edge_payload_digest(_to_payload(record), digest_field)})  # type: ignore[type-var]


def _label(index: int, kind: HistoricalWalkForwardSegmentKind) -> str:
    return f"window_{index}:{kind.value.lower()}"


# --- exact numerics (HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1, read from the verified policy) --------------------------


def _units_text(negative: bool, units: int, numeric: HistoricalWalkForwardMetricNumericPolicy) -> str | None:
    """Canonical fixed-scale text of ``units`` scale units, or ``None`` outside the representation domain.

    The magnitude is bounded by integer comparison BEFORE any ``str`` conversion, so an unrepresentable value can never
    reach the interpreter's integer-to-text limit.
    """

    scale = numeric.decimal_scale
    if units >= 10 ** (numeric.max_decimal_text_length - 1):
        return None
    digits = str(units).rjust(scale + 1, "0")
    rendered = f"{digits[:-scale]}.{digits[-scale:]}"
    if negative and units != 0:
        rendered = f"-{rendered}"
    return rendered if len(rendered) <= numeric.max_decimal_text_length else None


def _render_ratio(numerator: int, denominator: int, numeric: HistoricalWalkForwardMetricNumericPolicy) -> str | None:
    """Exact ROUND_HALF_EVEN render of ``numerator / denominator`` (``denominator > 0``); signed zero normalized."""

    magnitude = abs(numerator)
    quotient, remainder = divmod(magnitude * 10**numeric.decimal_scale, denominator)
    twice = 2 * remainder
    if twice > denominator or (twice == denominator and quotient % 2 == 1):
        quotient += 1
    return _units_text(numerator < 0, quotient, numeric)


def _render_signed_sqrt(
    negative: bool, numerator: int, denominator: int, numeric: HistoricalWalkForwardMetricNumericPolicy
) -> str | None:
    """Exact ROUND_HALF_EVEN render of ``(-1 if negative else 1) * sqrt(numerator / denominator)``.

    With ``R = numerator * 10**(2*scale) / denominator`` the scaled root is ``sqrt(R)``; ``floor(sqrt(R))`` equals
    ``isqrt(floor(R))`` exactly, and ``sqrt(R)`` is compared with ``root + 1/2`` through
    ``4 * numerator * 10**(2*scale)`` versus ``denominator * (2 * root + 1)**2`` — all integers, no approximation.
    """

    radicand = numerator * 10 ** (2 * numeric.decimal_scale)
    root = math.isqrt(radicand // denominator)
    left = 4 * radicand
    right = denominator * (2 * root + 1) ** 2
    if left > right or (left == right and root % 2 == 1):
        root += 1
    return _units_text(negative, root, numeric)


def _equity_units(text: object) -> int | None:
    """Exact scale units of one authenticated canonical scale-18 equity text (bounded to 60 characters)."""

    if not historical_execution_decimal_is_canonical(text):
        return None
    return int(text.replace(".", ""))  # type: ignore[union-attr]


def _risk_free(numeric: HistoricalWalkForwardMetricNumericPolicy, text: str) -> tuple[int, int] | None:
    """The policy's daily risk-free return as an exact ``(numerator, denominator)`` over the policy scale."""

    if not historical_execution_decimal_is_canonical(text):
        return None
    return int(text.replace(".", "")), 10**numeric.decimal_scale


@dataclass(frozen=True)
class _SegmentFigures:
    daily_return_count: int
    positive_daily_return_count: int
    negative_daily_return_count: int
    zero_daily_return_count: int
    annualized_sharpe: str
    hit_rate: str
    expectancy: str
    max_drawdown: str
    profit_factor: str


def _annualized_sharpe(
    *,
    total: int,
    squares: int,
    count: int,
    product: int,
    risk_free: tuple[int, int],
    factor: int,
    numeric: HistoricalWalkForwardMetricNumericPolicy,
) -> tuple[str | None, str | None]:
    """``(text, failure_code)`` of the annualized Sharpe ratio from the common-denominator sums.

    With daily returns ``r_k = scaled_k / product``: ``total = sum(scaled_k)``, ``squares = sum(scaled_k**2)``.
    ``mean_excess = X / (count * product * rf_den)`` with ``X = total * rf_den - count * product * rf_num`` and
    ``sample_variance = D / (product**2 * count * (count - 1))`` with ``D = count * squares - total**2 >= 0``, so
    ``mean_excess**2 * factor / sample_variance = factor * X**2 * (count - 1) / (count * rf_den**2 * D)`` exactly.
    """

    rf_num, rf_den = risk_free
    excess = total * rf_den - count * product * rf_num
    dispersion = count * squares - total * total
    if dispersion == 0:
        if excess == 0:
            return _render_ratio(0, 1, numeric), None
        return None, "sharpe_undefined_zero_variance_nonzero_mean"
    text = _render_signed_sqrt(
        excess < 0, factor * excess * excess * (count - 1), count * rf_den * rf_den * dispersion, numeric
    )
    return (text, None) if text is not None else (None, "metric_out_of_representation:annualized_sharpe")


def _segment_figures(
    equity_units: Sequence[int], policy: HistoricalWalkForwardMetricPolicy
) -> tuple[_SegmentFigures | None, tuple[str, ...]]:
    """Exact metrics of one daily endpoint equity path (units share one scale), or the reasons they are undefined."""

    numeric = policy.numeric_policy
    count = len(equity_units) - 1
    if count < policy.min_daily_return_count:
        return None, ("daily_return_count_insufficient",)
    if any(units <= 0 for units in equity_units):
        return None, ("equity_nonpositive",)
    risk_free = _risk_free(numeric, policy.risk_free_daily_return)
    if risk_free is None:
        return None, ("risk_free_representation_invalid",)
    previous = equity_units[:-1]
    deltas = [equity_units[index + 1] - equity_units[index] for index in range(count)]
    product = 1
    for value in sorted(set(previous)):
        product *= value
    scaled = [delta * (product // base) for delta, base in zip(deltas, previous, strict=True)]
    total = sum(scaled)
    squares = sum(item * item for item in scaled)
    gains = sum(item for item in scaled if item > 0)
    losses = -sum(item for item in scaled if item < 0)
    positive = sum(1 for delta in deltas if delta > 0)
    negative = sum(1 for delta in deltas if delta < 0)

    codes: list[str] = []
    sharpe, sharpe_code = _annualized_sharpe(
        total=total,
        squares=squares,
        count=count,
        product=product,
        risk_free=risk_free,
        factor=policy.sharpe_annualization_factor,
        numeric=numeric,
    )
    if sharpe_code is not None:
        codes.append(sharpe_code)
    hit_rate = _render_ratio(positive, count, numeric)
    expectancy = _render_ratio(total, count * product, numeric)
    peak = equity_units[0]
    drawdown_num, drawdown_den = 0, 1
    for units in equity_units:
        peak = max(peak, units)
        drop = peak - units
        if drop * drawdown_den > drawdown_num * peak:
            drawdown_num, drawdown_den = drop, peak
    max_drawdown = _render_ratio(drawdown_num, drawdown_den, numeric)
    profit_factor: str | None = None
    if losses == 0:
        codes.append("profit_factor_undefined_zero_gross_loss")
    else:
        profit_factor = _render_ratio(gains, losses, numeric)
        if profit_factor is None:
            codes.append("metric_out_of_representation:profit_factor")
    for name, text in (("hit_rate", hit_rate), ("expectancy", expectancy), ("max_drawdown", max_drawdown)):
        if text is None:
            codes.append(f"metric_out_of_representation:{name}")
    if codes:
        return None, tuple(codes)
    return (
        _SegmentFigures(
            daily_return_count=count,
            positive_daily_return_count=positive,
            negative_daily_return_count=negative,
            zero_daily_return_count=count - positive - negative,
            annualized_sharpe=sharpe,  # type: ignore[arg-type]
            hit_rate=hit_rate,  # type: ignore[arg-type]
            expectancy=expectancy,  # type: ignore[arg-type]
            max_drawdown=max_drawdown,  # type: ignore[arg-type]
            profit_factor=profit_factor,  # type: ignore[arg-type]
        ),
        (),
    )


# --- authorities --------------------------------------------------------------------------------------------------------


def _policy_authority(binding: EdgeAuthorityBinding) -> tuple[list[str], HistoricalWalkForwardMetricPolicy | None]:
    policy = historical_walk_forward_metric_policy_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_historical_walk_forward_metric_policy(policy)
    if not verification.intact:
        return [_reason(f"policy_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("policy_digest_mismatch")], None
    return [], policy


def _source_authority(
    binding: EdgeAuthorityBinding, *, correlation_id: str, label: str
) -> tuple[list[str], HistoricalExecutionEconomicsResult | None]:
    result = historical_execution_economics_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_historical_execution_economics(result)
    if not verification.intact:
        return [_reason(f"{label}:source_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason(f"{label}:source_digest_mismatch")], None
    if result.correlation_id != correlation_id:
        return [_reason(f"{label}:source_correlation_mismatch")], None
    return [], result


def _computed(result: HistoricalExecutionEconomicsResult) -> bool:
    return (
        result.status is EdgeEvidenceStatus.READY
        and result.gate_verdict is EdgeGateVerdict.PASS
        and result.advances is True
        and result.simulated_economics_computed is True
    )


# --- structural contract ------------------------------------------------------------------------------------------------


def _structural_codes(
    policy: HistoricalWalkForwardMetricPolicy,
    refs: Sequence[HistoricalWalkForwardWindowBinding],
    sources: Sequence[tuple[HistoricalExecutionEconomicsResult, HistoricalExecutionEconomicsResult]],
) -> list[str]:
    """Every source, geometry, ordering, identity, assignment and consistency violation (complete collection)."""

    day = policy.day_ns
    durations = {
        HistoricalWalkForwardSegmentKind.IN_SAMPLE: policy.in_sample_duration_days * day,
        HistoricalWalkForwardSegmentKind.OUT_OF_SAMPLE: policy.out_of_sample_duration_days * day,
    }
    codes: list[str] = []
    seen: set[str] = set()
    computed: list[HistoricalExecutionEconomicsResult] = []
    previous_oos_start: int | None = None
    for index, (ref, (in_sample, out_of_sample)) in enumerate(zip(refs, sources, strict=True)):
        if ref.window_id in seen:
            codes.append(_reason(f"window_{index}:window_id_duplicate"))
        seen.add(ref.window_id)
        window_computed = True
        for kind, result in (
            (HistoricalWalkForwardSegmentKind.IN_SAMPLE, in_sample),
            (HistoricalWalkForwardSegmentKind.OUT_OF_SAMPLE, out_of_sample),
        ):
            label = _label(index, kind)
            if not _computed(result):
                codes.append(
                    _reason(f"{label}:economics_not_computed:{result.status.value}:{result.gate_verdict.value}")
                )
                window_computed = False
                continue
            computed.append(result)
            start, end = result.evaluation_start_ns, result.evaluation_end_ns
            if start % day != 0 or end % day != 0:
                codes.append(_reason(f"{label}:boundary_not_utc_day_aligned"))
            if end - start != durations[kind]:
                codes.append(_reason(f"{label}:duration_mismatch"))
        if not window_computed:
            previous_oos_start = None
            continue
        if out_of_sample.evaluation_start_ns - in_sample.evaluation_end_ns != policy.embargo_days * day:
            codes.append(_reason(f"window_{index}:embargo_mismatch"))
        if in_sample.parameter_assignment_digest != out_of_sample.parameter_assignment_digest:
            codes.append(_reason(f"window_{index}:assignment_mismatch"))
        if previous_oos_start is not None:
            advance = out_of_sample.evaluation_start_ns - previous_oos_start
            if advance <= 0:
                codes.append(_reason(f"window_{index}:order_invalid"))
            elif advance != policy.window_stride_days * day:
                codes.append(_reason(f"window_{index}:stride_mismatch"))
        previous_oos_start = out_of_sample.evaluation_start_ns
    for name in _SOURCE_CONSISTENCY_FIELDS:
        if len({getattr(result, name) for result in computed}) > 1:
            codes.append(_reason(f"source_inconsistent:{name}"))
    return codes


def _daily_endpoints(
    result: HistoricalExecutionEconomicsResult, policy: HistoricalWalkForwardMetricPolicy
) -> tuple[tuple[HistoricalExecutionValuation, ...] | None, str | None]:
    """The one UTC daily endpoint sequence of a computed, geometry-checked source (or the reason it does not exist)."""

    day = policy.day_ns
    start, end = result.evaluation_start_ns, result.evaluation_end_ns
    valuations = result.valuations
    kinds = HistoricalExecutionValuationKind
    if (
        not valuations
        or valuations[0].valuation_kind is not kinds.INITIAL
        or valuations[-1].valuation_kind is not kinds.EVALUATION_END
    ):
        return None, "daily_endpoint_order_invalid"
    initial = [item for item in valuations if item.valuation_kind is kinds.INITIAL]
    final = [item for item in valuations if item.valuation_kind is kinds.EVALUATION_END]
    boundaries = [item for item in valuations if item.valuation_kind is kinds.UTC_DAY_BOUNDARY]
    if len(initial) != 1 or initial[0].time_ns != start:
        return None, "daily_endpoint_start_invalid"
    if len(final) != 1 or final[0].time_ns != end:
        return None, "daily_endpoint_end_invalid"
    expected = [start + offset * day for offset in range(1, (end - start) // day)]
    if [item.time_ns for item in boundaries] != expected:
        return None, "daily_endpoint_boundary_set_invalid"
    return (initial[0], *boundaries, final[0]), None


def _segment_metrics(
    kind: HistoricalWalkForwardSegmentKind,
    result: HistoricalExecutionEconomicsResult,
    policy: HistoricalWalkForwardMetricPolicy,
) -> tuple[HistoricalWalkForwardSegmentMetrics | None, list[str]]:
    endpoints, endpoint_code = _daily_endpoints(result, policy)
    if endpoints is None:
        return None, [endpoint_code]  # type: ignore[list-item]
    units = [_equity_units(item.equity) for item in endpoints]
    if any(value is None for value in units):
        return None, ["equity_noncanonical"]
    figures, codes = _segment_figures(units, policy)  # type: ignore[arg-type]
    if figures is None:
        return None, list(codes)
    endpoint_digest = edge_sha256_text(
        edge_canonical_json(
            [[item.valuation_sequence, item.time_ns, item.valuation_digest, item.equity] for item in endpoints]
        )
    )
    record = HistoricalWalkForwardSegmentMetrics(
        segment_kind=kind,
        source_result_id=result.result_id,
        source_result_digest=result.result_digest,
        source_valuation_ledger_digest=result.valuation_ledger_digest,
        evaluation_start_ns=result.evaluation_start_ns,
        evaluation_end_ns=result.evaluation_end_ns,
        daily_endpoint_count=len(endpoints),
        daily_endpoint_digest=endpoint_digest,
        daily_return_count=figures.daily_return_count,
        positive_daily_return_count=figures.positive_daily_return_count,
        negative_daily_return_count=figures.negative_daily_return_count,
        zero_daily_return_count=figures.zero_daily_return_count,
        start_equity=endpoints[0].equity,
        end_equity=endpoints[-1].equity,
        annualized_sharpe=figures.annualized_sharpe,
        hit_rate=figures.hit_rate,
        expectancy=figures.expectancy,
        max_drawdown=figures.max_drawdown,
        profit_factor=figures.profit_factor,
        segment_digest="",
    )
    return _sealed(record, "segment_digest"), []  # type: ignore[return-value]


def _compute_windows(
    policy: HistoricalWalkForwardMetricPolicy,
    refs: Sequence[HistoricalWalkForwardWindowBinding],
    sources: Sequence[tuple[HistoricalExecutionEconomicsResult, HistoricalExecutionEconomicsResult]],
) -> tuple[tuple[HistoricalWalkForwardWindowMetrics, ...], list[str]]:
    windows: list[HistoricalWalkForwardWindowMetrics] = []
    codes: list[str] = []
    for index, (ref, (in_sample, out_of_sample)) in enumerate(zip(refs, sources, strict=True)):
        segments: list[HistoricalWalkForwardSegmentMetrics] = []
        for kind, result in (
            (HistoricalWalkForwardSegmentKind.IN_SAMPLE, in_sample),
            (HistoricalWalkForwardSegmentKind.OUT_OF_SAMPLE, out_of_sample),
        ):
            segment, segment_codes = _segment_metrics(kind, result, policy)
            codes.extend(_reason(f"{_label(index, kind)}:{code}") for code in segment_codes)
            if segment is not None:
                segments.append(segment)
        if len(segments) == 2:
            window = HistoricalWalkForwardWindowMetrics(
                window_index=index,
                window_id=ref.window_id,
                parameter_assignment_digest=in_sample.parameter_assignment_digest,
                in_sample=segments[0],
                out_of_sample=segments[1],
                window_digest="",
            )
            windows.append(_sealed(window, "window_digest"))  # type: ignore[arg-type]
    if codes:
        return (), codes
    return tuple(windows), []


# --- result -------------------------------------------------------------------------------------------------------------


def _require_window_bindings(value: object) -> tuple[HistoricalWalkForwardWindowBinding, ...]:
    if type(value) is not tuple:
        raise _fail("windows_malformed")
    if not value:
        raise _fail("windows_empty")
    accepted: list[HistoricalWalkForwardWindowBinding] = []
    for item in value:
        if type(item) is not HistoricalWalkForwardWindowBinding:
            raise _fail("window_binding_malformed")
        accepted.append(
            HistoricalWalkForwardWindowBinding(
                window_id=_require_text(item.window_id, "window_id"),
                in_sample_binding=require_edge_authority_binding(  # type: ignore[arg-type]
                    item.in_sample_binding,
                    shape=historical_execution_economics_payload_is_well_formed,
                    error=HistoricalWalkForwardMetricsError,
                    code=_reason("in_sample"),
                    optional=False,
                ),
                out_of_sample_binding=require_edge_authority_binding(  # type: ignore[arg-type]
                    item.out_of_sample_binding,
                    shape=historical_execution_economics_payload_is_well_formed,
                    error=HistoricalWalkForwardMetricsError,
                    code=_reason("out_of_sample"),
                    optional=False,
                ),
            )
        )
    return tuple(accepted)


def _assemble_result(
    *,
    policy_binding: object,
    window_bindings: object,
    result_id: object,
    correlation_id: object,
) -> HistoricalWalkForwardMetricsResult:
    """The one result assembly path, shared by the builder and verifier re-derivation."""

    policy_ref = require_edge_authority_binding(
        policy_binding,
        shape=historical_walk_forward_metric_policy_payload_is_well_formed,
        error=HistoricalWalkForwardMetricsError,
        code=_reason("policy"),
        optional=False,
    )
    refs = _require_window_bindings(window_bindings)
    result_id = _require_text(result_id, "result_id")
    correlation_id = _require_text(correlation_id, "correlation_id")

    codes, policy = _policy_authority(policy_ref)  # type: ignore[arg-type]
    pairs: list[tuple[HistoricalExecutionEconomicsResult | None, HistoricalExecutionEconomicsResult | None]] = []
    for index, ref in enumerate(refs):
        in_codes, in_sample = _source_authority(
            ref.in_sample_binding,
            correlation_id=correlation_id,
            label=_label(index, HistoricalWalkForwardSegmentKind.IN_SAMPLE),
        )
        out_codes, out_of_sample = _source_authority(
            ref.out_of_sample_binding,
            correlation_id=correlation_id,
            label=_label(index, HistoricalWalkForwardSegmentKind.OUT_OF_SAMPLE),
        )
        codes.extend(in_codes + out_codes)
        pairs.append((in_sample, out_of_sample))
    integrity = _sorted_unique(codes)

    windows: tuple[HistoricalWalkForwardWindowMetrics, ...] = ()
    first: HistoricalExecutionEconomicsResult | None = None
    sources: list[tuple[HistoricalExecutionEconomicsResult, HistoricalExecutionEconomicsResult]] = []
    if integrity or policy is None or any(item is None for pair in pairs for item in pair):
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        sources = [(pair[0], pair[1]) for pair in pairs]  # type: ignore[misc]
        first = sources[0][0]
        fail = _structural_codes(policy, refs, sources)
        if not fail:
            windows, fail = _compute_windows(policy, refs, sources)
        status = EdgeEvidenceStatus.READY
        verdict = EdgeGateVerdict.FAIL if fail else EdgeGateVerdict.PASS
        verdict_reasons = _sorted_unique(fail)

    computed = status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS
    seed = HistoricalWalkForwardMetricsResult(
        schema_version=_SCHEMA_VERSION,
        status=status,
        computation_verdict=verdict,
        result_id=result_id,
        correlation_id=correlation_id,
        policy_binding=policy_ref,  # type: ignore[arg-type]
        metric_policy_digest=policy_ref.expected_digest,  # type: ignore[union-attr]
        window_bindings=refs,
        window_count=len(refs),
        window_ids=tuple(ref.window_id for ref in refs),
        source_result_digests=tuple(
            digest
            for ref in refs
            for digest in (ref.in_sample_binding.expected_digest, ref.out_of_sample_binding.expected_digest)
        ),
        strategy_spec_digest="" if first is None else first.strategy_spec_digest,
        instrument="" if first is None else first.instrument,
        market_type="" if first is None else first.market_type,
        economics_policy_digest="" if first is None else first.economics_policy_digest,
        profile_semantics_digest="" if first is None else first.profile_semantics_digest,
        data_requirement_registry_digest="" if first is None else first.data_requirement_registry_digest,
        synthetic_test_facts_used=any(item.synthetic_test_facts_used for pair in sources for item in pair),
        synthetic_test_approval_used=any(item.synthetic_test_approval_used for pair in sources for item in pair),
        windows=windows,
        window_digests=tuple(window.window_digest for window in windows),
        performance_metrics_computed=computed,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        result_digest="",
    )
    return replace(seed, result_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def _source_binding(economics: object, expected_digest: object, code: str) -> EdgeAuthorityBinding:
    if type(economics) is not HistoricalExecutionEconomicsResult:
        raise _fail(f"{code}_economics_malformed")
    try:
        payload = historical_execution_economics_to_dict(economics)
    except Exception as exc:  # noqa: BLE001 - a hollow economics object is a construction error, never a receipt
        raise _fail(f"{code}_economics_not_serializable") from exc
    return build_edge_authority_binding(
        snapshot_payload=payload,
        expected_digest=expected_digest,
        shape=historical_execution_economics_payload_is_well_formed,
        error=HistoricalWalkForwardMetricsError,
        code=_reason(code),
    )


def build_historical_walk_forward_metrics(
    *,
    metric_policy: HistoricalWalkForwardMetricPolicy,
    expected_metric_policy_digest: str,
    windows: Sequence[HistoricalWalkForwardWindowInput],
    result_id: str,
    correlation_id: str,
) -> HistoricalWalkForwardMetricsResult:
    """Build deterministic walk-forward metrics over authenticated IS/OOS historical execution economics.

    Malformed caller input (policy, window sequence or window, anchors, identity text) or a non-serializable upstream
    object raises ``HistoricalWalkForwardMetricsError``. A policy or source that fails re-proof yields
    ``REJECTED``/``NOT_EVALUATED``; a verified input the V1 contract cannot compute yields ``READY``/``FAIL``. Only
    ``READY``/``PASS`` carries metrics.
    """

    if type(metric_policy) is not HistoricalWalkForwardMetricPolicy:
        raise _fail("policy_malformed")
    try:
        policy_payload = historical_walk_forward_metric_policy_to_dict(metric_policy)
    except Exception as exc:  # noqa: BLE001 - a hollow policy object is a construction error, never a receipt
        raise _fail("policy_not_serializable") from exc
    policy_ref = build_edge_authority_binding(
        snapshot_payload=policy_payload,
        expected_digest=expected_metric_policy_digest,
        shape=historical_walk_forward_metric_policy_payload_is_well_formed,
        error=HistoricalWalkForwardMetricsError,
        code=_reason("policy"),
    )
    if type(windows) not in (tuple, list):
        raise _fail("windows_malformed")
    if not windows:
        raise _fail("windows_empty")
    bindings: list[HistoricalWalkForwardWindowBinding] = []
    for window in windows:
        if type(window) is not HistoricalWalkForwardWindowInput:
            raise _fail("window_malformed")
        bindings.append(
            HistoricalWalkForwardWindowBinding(
                window_id=window.window_id,
                in_sample_binding=_source_binding(
                    window.in_sample_economics, window.expected_in_sample_result_digest, "in_sample"
                ),
                out_of_sample_binding=_source_binding(
                    window.out_of_sample_economics, window.expected_out_of_sample_result_digest, "out_of_sample"
                ),
            )
        )
    return _assemble_result(
        policy_binding=policy_ref,
        window_bindings=tuple(bindings),
        result_id=result_id,
        correlation_id=correlation_id,
    )


def historical_walk_forward_metrics_to_dict(result: HistoricalWalkForwardMetricsResult) -> dict[str, object]:
    """Canonical JSON-ready mapping of a result, including its self-digest."""

    return _to_payload(result)


def historical_walk_forward_metrics_digest(result: HistoricalWalkForwardMetricsResult) -> str:
    """Recompute the canonical result digest, excluding only ``result_digest``."""

    return edge_payload_digest(_to_payload(result), _SELF_DIGEST_FIELD)


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


def _as_decimal(value: object) -> str:
    numeric = HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1
    if (
        type(value) is not str
        or len(value) > numeric.max_decimal_text_length
        or not historical_execution_decimal_is_canonical(value)
    ):
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
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _parse_economics_binding(code: str) -> Callable[[object], object]:
    def convert(value: object) -> EdgeAuthorityBinding | None:
        return parse_edge_authority_binding(
            value,
            shape=historical_execution_economics_payload_is_well_formed,
            error=HistoricalWalkForwardMetricsError,
            code=_reason(code),
            optional=False,
        )

    return convert


def _parse_policy_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=historical_walk_forward_metric_policy_payload_is_well_formed,
        error=HistoricalWalkForwardMetricsError,
        code=_reason("policy"),
        optional=False,
    )


_WINDOW_BINDING_CONVERTERS: dict[str, Callable[[object], object]] = {
    "in_sample_binding": _parse_economics_binding("in_sample"),
    "out_of_sample_binding": _parse_economics_binding("out_of_sample"),
}
_SEGMENT_CONVERTERS: dict[str, Callable[[object], object]] = {
    "segment_kind": _as_enum(HistoricalWalkForwardSegmentKind),
    "evaluation_start_ns": _as_int,
    "evaluation_end_ns": _as_int,
    "daily_endpoint_count": _as_int,
    "daily_return_count": _as_int,
    "positive_daily_return_count": _as_int,
    "negative_daily_return_count": _as_int,
    "zero_daily_return_count": _as_int,
    "start_equity": _as_decimal,
    "end_equity": _as_decimal,
    "annualized_sharpe": _as_decimal,
    "hit_rate": _as_decimal,
    "expectancy": _as_decimal,
    "max_drawdown": _as_decimal,
    "profit_factor": _as_decimal,
}


def _as_segment(value: object) -> object:
    return _parse_exact(HistoricalWalkForwardSegmentMetrics, value, _SEGMENT_CONVERTERS)


_WINDOW_CONVERTERS: dict[str, Callable[[object], object]] = {
    "window_index": _as_int,
    "in_sample": _as_segment,
    "out_of_sample": _as_segment,
}
_RESULT_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "computation_verdict": _as_enum(EdgeGateVerdict),
    "policy_binding": _parse_policy_binding,
    "window_bindings": _as_records(HistoricalWalkForwardWindowBinding, _WINDOW_BINDING_CONVERTERS),
    "window_count": _as_int,
    "window_ids": _as_str_tuple,
    "source_result_digests": _as_str_tuple,
    "synthetic_test_facts_used": _as_bool,
    "synthetic_test_approval_used": _as_bool,
    "windows": _as_records(HistoricalWalkForwardWindowMetrics, _WINDOW_CONVERTERS),
    "window_digests": _as_str_tuple,
    "performance_metrics_computed": _as_bool,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def historical_walk_forward_metrics_from_payload(payload: object) -> HistoricalWalkForwardMetricsResult:
    """Strictly reconstruct a result from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(HistoricalWalkForwardMetricsResult, payload, _RESULT_CONVERTERS)  # type: ignore[return-value]


def historical_walk_forward_metrics_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a result snapshot."""

    try:
        historical_walk_forward_metrics_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_result(result: object) -> HistoricalWalkForwardMetricsResult:
    return _assemble_result(
        policy_binding=result.policy_binding,  # type: ignore[attr-defined]
        window_bindings=result.window_bindings,  # type: ignore[attr-defined]
        result_id=result.result_id,  # type: ignore[attr-defined]
        correlation_id=result.correlation_id,  # type: ignore[attr-defined]
    )


def verify_historical_walk_forward_metrics(result: object) -> EdgeEvidenceVerification:
    """Re-prove the policy and every source and re-derive every metric. Total: never raises."""

    return verify_edge_artifact_total(
        result,
        cls=HistoricalWalkForwardMetricsResult,
        to_payload=_to_payload,
        parse_payload=historical_walk_forward_metrics_from_payload,
        reassemble=_reassemble_result,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "HISTORICAL_WALK_FORWARD_METRICS_NON_CLAIM_FLAGS",
    "HistoricalWalkForwardMetricsError",
    "HistoricalWalkForwardMetricsResult",
    "HistoricalWalkForwardSegmentKind",
    "HistoricalWalkForwardSegmentMetrics",
    "HistoricalWalkForwardWindowBinding",
    "HistoricalWalkForwardWindowInput",
    "HistoricalWalkForwardWindowMetrics",
    "build_historical_walk_forward_metrics",
    "historical_walk_forward_metrics_digest",
    "historical_walk_forward_metrics_from_payload",
    "historical_walk_forward_metrics_payload_is_well_formed",
    "historical_walk_forward_metrics_to_dict",
    "verify_historical_walk_forward_metrics",
]
