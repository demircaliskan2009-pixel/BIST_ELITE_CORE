"""Deterministic paper Sharpe evidence (PRDV4 Stage 4 methodology, review/math only).

This validation artifact consumes a proven ``PaperDailyReturnSeriesEvidence`` and computes a deterministic
paper Sharpe ratio from its already-canonical ``daily_returns`` (one canonical decimal per UTC daily bucket).
It is paper-only, deterministic, digest-bound, and fail-closed.

Governance (user-approved for this slice):

* risk-free policy ``constant_zero_daily_review_only.v1`` (daily excess return = ``return - 0``);
* sample standard deviation with ``n - 1`` (``sample_stddev_n_minus_1.v1``);
* annualization ``paper_sharpe_daily * sqrt(365)`` over the repo-defined factor ``365``;
* exact zero variance is fail-closed (``exact_zero_variance_fail_closed.v1``) with no arbitrary near-zero
  epsilon (``none.v1``);
* deterministic decimal policy ``decimal_quantized_scale_18_round_half_even_internal_precision_80.v1`` -
  no float arithmetic anywhere: the mean and the (sample) variance are computed in exact rational arithmetic
  (``fractions.Fraction``) so the variance is exactly zero iff all returns are equal and is never spuriously
  negative; only the irrational square roots and the final divisions are evaluated in a local ``Decimal``
  context with precision 80 and ``ROUND_HALF_EVEN``, then every public numeric output is quantized to exactly
  18 fractional digits with ``ROUND_HALF_EVEN`` (signed zero normalized to positive).

It does NOT decide the 30-day gate, does NOT invoke the Stage-4 comparator, does NOT construct
``Stage4PaperSummary``, does NOT bind a backtest baseline, does NOT prove statistical significance, Sharpe
stability, profitability, edge, comparison readiness, live readiness, shadow readiness, Deribit readiness,
operational readiness, execution, orders, capital, margin, balance, scheduler, or PRDV4 Stage-4 completion.
It calls no wall-clock, runtime, service, execution, venue, scheduler, filesystem, network, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from enum import Enum
from fractions import Fraction

from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnBucket,
    PaperDailyReturnSeriesEvidence,
    PaperDailyReturnSeriesEvidenceStatus,
    paper_daily_return_series_evidence_digest,
)

_SCHEMA_VERSION = "paper-sharpe-evidence.v1"
_EVIDENCE_VERSION = "paper-sharpe-evidence.v1"
_EXPECTED_SERIES_SCHEMA_VERSION = "paper-daily-return-series-evidence.v1"
_CALENDAR = "UTC"
_BUCKET_FREQUENCY = "1d_utc"
_BUCKET_DURATION_NS = 86_400_000_000_000
_REQUIRED_CONSECUTIVE_BUCKET_COUNT = 30
_RETURN_BASIS = "normalized_paper_equity_index"
_RETURN_VALUE_KIND = "unitless_decimal_return"
_ANNUALIZATION_POLICY = "daily_utc_365_review_only"
_ANNUALIZATION_FACTOR = 365
_ANNUALIZATION_FORMULA = "paper_sharpe_daily * sqrt(365)"
_SERIES_PAPER_SHARPE_POLICY = "deferred_not_computed"
_TIMESTAMP_POLICY = "injected_deterministic_ns.v1"

# User-approved governance constants for this slice.
_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"
_RISK_FREE_POLICY = "constant_zero_daily_review_only"
_STDDEV_POLICY = "sample_stddev_n_minus_1.v1"
_ZERO_VARIANCE_POLICY = "exact_zero_variance_fail_closed.v1"
_NEAR_ZERO_EPSILON_POLICY = "none.v1"
_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_DECIMAL_INTERNAL_PRECISION = 80
_DECIMAL_QUANTUM = Decimal(1).scaleb(-_DECIMAL_SCALE)

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"stage4_comparator|compare_stage4|Stage4PaperSummary|capital|margin|balance|reservation|"
    r"real_account_equity|account_equity|real_equity)\w*"
    r"|crypto_core\.(?:service|execution|venue|runtime|orchestrator|temporal|session|data|portfolio)\b"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")
_CLOCK_TOKENS = (
    "wall_clock",
    "wall-clock",
    "wallclock",
    "datetime.now",
    "datetime.utcnow",
    "utcnow",
    "time.time_ns",
    "time.time",
    "perf_counter",
    "monotonic",
    "server_time",
    "exchange_time",
    "live_time",
    "real_time",
    "realtime",
    "system_time",
    "clock",
    "now()",
)


class PaperSharpeEvidenceError(RuntimeError):
    """Raised on malformed caller input, forbidden scope/clock tokens, or an unapproved risk-free policy."""


class PaperSharpeEvidenceStatus(str, Enum):
    """Paper Sharpe evidence status. READY means the Sharpe was deterministically computed, nothing more."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperSharpeEvidence:
    """Immutable, digest-bound deterministic paper Sharpe evidence (review/math only)."""

    schema_version: str
    evidence_version: str
    status: PaperSharpeEvidenceStatus
    ready: bool
    sharpe_evidence_id: str
    paper_id: str
    series_id: str
    methodology_id: str
    window_id: str
    correlation_id: str
    market_symbol: str
    expected_daily_return_series_digest: str
    daily_return_series_digest: str
    verified_daily_return_series_digest: str
    methodology_digest: str
    time_window_digest: str
    metrics_summary_digest: str
    calendar: str
    bucket_frequency: str
    bucket_duration_ns: int
    required_consecutive_bucket_count: int
    return_basis: str
    return_value_kind: str
    annualization_policy: str
    annualization_factor: int
    annualization_formula: str
    risk_free_policy_id: str
    risk_free_policy: str
    risk_free_daily_return: str
    stddev_policy: str
    zero_variance_policy: str
    near_zero_epsilon_policy: str
    decimal_policy: str
    decimal_scale: int
    decimal_rounding: str
    decimal_internal_precision: int
    bucket_count: int
    observation_count: int
    daily_return_count: int
    mean_excess_return: str
    sample_stddev_excess_return: str
    paper_sharpe_daily: str
    paper_sharpe_annualized: str
    sharpe_computed: bool
    stability_warning: bool
    minimum_window_only: bool
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    sharpe_evidence_digest: str
    paper_only: bool = True
    daily_return_series_evidence_consumed: bool = True
    paper_sharpe_evidence: bool = True
    return_series_constructed: bool = False
    statistical_significance_proven: bool = False
    sharpe_stable: bool = False
    paper_vs_backtest_comparison_ready: bool = False
    comparison_ready: bool = False
    stage4_comparator_invoked: bool = False
    thirty_day_gate_satisfied: bool = False
    thirty_day_gate_decided: bool = False
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    real_wall_clock_used: bool = False
    real_account_equity_used: bool = False
    real_capital_used: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return (
        type(value) is str
        and value.strip() != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_canonical_decimal_string(value: object) -> bool:
    if type(value) is not str or not _DECIMAL_PATTERN.fullmatch(value):
        return False
    if value == "-0":
        return False
    if "." not in value:
        return True
    return not value.endswith("0")


def _decimal_to_fraction(value: Decimal) -> Fraction:
    sign, digits, exponent = value.as_tuple()
    coefficient = int("".join(str(digit) for digit in digits)) if digits else 0
    if sign:
        coefficient = -coefficient
    if exponent >= 0:
        return Fraction(coefficient * (10**exponent), 1)
    return Fraction(coefficient, 10 ** (-exponent))


def _format_public_decimal(value: Decimal) -> str:
    """Quantize to exactly ``_DECIMAL_SCALE`` fractional digits with ROUND_HALF_EVEN; normalize signed zero."""

    quantized = value.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        quantized = Decimal(0).quantize(_DECIMAL_QUANTUM)
    return format(quantized, "f")


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperSharpeEvidenceError("paper_sharpe_evidence:metadata_malformed")
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperSharpeEvidenceError("paper_sharpe_evidence:metadata_malformed")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperSharpeEvidenceError("paper_sharpe_evidence:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _has_clock_token(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _CLOCK_TOKENS):
            return True
    return False


def _container_shape_failures(daily_return_series: PaperDailyReturnSeriesEvidence) -> list[str]:
    """Prove the exact upstream container shapes BEFORE any ``len`` / iteration / indexing of the consumed data.

    The digest boundary alone does not distinguish a ``tuple`` from an equal-content ``list``; a forged
    exact-typed series could carry a non-tuple ``daily_returns`` or ``buckets``. The Sharpe math depends only on
    ``daily_returns``, but both containers are shape-checked so a malformed upstream fails closed with a
    deterministic reason code (never a raw ``TypeError`` and never a silent collapse under a READY decision).
    """
    hard: list[str] = []
    buckets = daily_return_series.buckets
    if type(buckets) is not tuple:
        hard.append("paper_sharpe_evidence:buckets_container_malformed")
    elif not all(type(bucket) is PaperDailyReturnBucket for bucket in buckets):
        hard.append("paper_sharpe_evidence:bucket_type_malformed")
    daily_returns = daily_return_series.daily_returns
    if type(daily_returns) is not tuple:
        hard.append("paper_sharpe_evidence:daily_returns_container_malformed")
    elif not all(type(daily_return) is str for daily_return in daily_returns):
        hard.append("paper_sharpe_evidence:daily_return_malformed")
    return hard


def _series_hard_failures(
    daily_return_series: PaperDailyReturnSeriesEvidence,
    expected_daily_return_series_digest: str,
    risk_free_policy_id: str,
) -> list[str]:
    hard: list[str] = []
    try:
        recomputed = paper_daily_return_series_evidence_digest(daily_return_series)
    except Exception:  # noqa: BLE001 - public digest recompute failures fail closed at this boundary
        recomputed = None
    if (
        recomputed is None
        or not _is_hex64_string(daily_return_series.series_digest)
        or daily_return_series.series_digest != recomputed
        or daily_return_series.series_digest != expected_daily_return_series_digest
    ):
        hard.append("paper_sharpe_evidence:series_digest_mismatch")

    if daily_return_series.schema_version != _EXPECTED_SERIES_SCHEMA_VERSION:
        hard.append("paper_sharpe_evidence:series_schema_invalid")
    if (
        daily_return_series.status is not PaperDailyReturnSeriesEvidenceStatus.READY
        or daily_return_series.ready is not True
        or daily_return_series.reason_codes != ()
    ):
        hard.append("paper_sharpe_evidence:series_not_ready")

    expected_values = {
        "calendar": _CALENDAR,
        "bucket_frequency": _BUCKET_FREQUENCY,
        "bucket_duration_ns": _BUCKET_DURATION_NS,
        "required_consecutive_bucket_count": _REQUIRED_CONSECUTIVE_BUCKET_COUNT,
        "return_basis": _RETURN_BASIS,
        "return_value_kind": _RETURN_VALUE_KIND,
        "annualization_policy": _ANNUALIZATION_POLICY,
        "annualization_factor": _ANNUALIZATION_FACTOR,
        "paper_sharpe_policy": _SERIES_PAPER_SHARPE_POLICY,
        "timestamp_policy": _TIMESTAMP_POLICY,
    }
    for field_name, expected in expected_values.items():
        if getattr(daily_return_series, field_name) != expected:
            hard.append(f"paper_sharpe_evidence:series_{field_name}_mismatch")

    if (
        daily_return_series.paper_only is not True
        or daily_return_series.daily_return_series_evidence is not True
        or daily_return_series.methodology_snapshot_consumed is not True
        or daily_return_series.injected_deterministic_time_window_consumed is not True
        or daily_return_series.daily_utc_only is not True
        or daily_return_series.normalized_paper_equity_index is not True
        or daily_return_series.mark_to_market_required is not True
        or daily_return_series.realized_only_primary_series is not False
        or daily_return_series.return_series_computed is not True
        or daily_return_series.daily_returns_computed is not True
        or daily_return_series.sample_eligible is not True
        or daily_return_series.sharpe_computed is not False
        or daily_return_series.paper_sharpe_computed is not False
        or daily_return_series.thirty_day_gate_satisfied is not False
        or daily_return_series.thirty_day_gate_decided is not False
        or daily_return_series.comparison_ready is not False
        or daily_return_series.stage4_comparator_invoked is not False
        or daily_return_series.prdv4_stage4_complete is not False
        or daily_return_series.live_ready is not False
        or daily_return_series.shadow_ready is not False
        or daily_return_series.operational_readiness is not False
        or daily_return_series.deribit_ready is not False
        or daily_return_series.profitability_proven is not False
        or daily_return_series.edge_proven is not False
        or daily_return_series.production_execution is not False
        or daily_return_series.real_orders_enabled is not False
        or daily_return_series.real_money_enabled is not False
        or daily_return_series.real_capital_reserved is not False
        or daily_return_series.live_api_called is not False
        or daily_return_series.scheduler_enabled is not False
        or daily_return_series.auto_loop_enabled is not False
        or daily_return_series.connector_invoked is not False
        or daily_return_series.real_wall_clock_used is not False
        or daily_return_series.real_account_equity_used is not False
        or daily_return_series.real_capital_used is not False
    ):
        hard.append("paper_sharpe_evidence:series_unsafe_flags")

    if daily_return_series.risk_free_policy_id != _RISK_FREE_POLICY_ID:
        hard.append("paper_sharpe_evidence:series_risk_free_policy_mismatch")
    if daily_return_series.risk_free_policy_id != risk_free_policy_id:
        hard.append("paper_sharpe_evidence:risk_free_policy_id_series_mismatch")

    if (
        not _is_exact_int(daily_return_series.bucket_count)
        or daily_return_series.bucket_count < _REQUIRED_CONSECUTIVE_BUCKET_COUNT
    ):
        hard.append("paper_sharpe_evidence:insufficient_bucket_count")
    if (
        not _is_exact_int(daily_return_series.return_count)
        or daily_return_series.return_count < _REQUIRED_CONSECUTIVE_BUCKET_COUNT
    ):
        hard.append("paper_sharpe_evidence:insufficient_daily_return_count")
    if (
        type(daily_return_series.buckets) is tuple
        and len(daily_return_series.buckets) != daily_return_series.bucket_count
    ):
        hard.append("paper_sharpe_evidence:bucket_count_mismatch")
    if (
        type(daily_return_series.daily_returns) is tuple
        and len(daily_return_series.daily_returns) != daily_return_series.return_count
    ):
        hard.append("paper_sharpe_evidence:daily_return_count_mismatch")

    if (
        not _is_hex64_string(daily_return_series.methodology_digest)
        or not _is_hex64_string(daily_return_series.time_window_digest)
        or not _is_hex64_string(daily_return_series.metrics_summary_digest)
    ):
        hard.append("paper_sharpe_evidence:upstream_digest_anchor_invalid")

    policy_fields = (
        daily_return_series.series_id,
        daily_return_series.methodology_id,
        daily_return_series.window_id,
        daily_return_series.correlation_id,
        daily_return_series.market_symbol,
        daily_return_series.risk_free_policy_id,
    )
    if not all(_is_plain_non_empty_string(value) for value in policy_fields):
        hard.append("paper_sharpe_evidence:series_identity_or_policy_invalid")
    elif _has_scope_violation(*policy_fields) or _has_clock_token(*policy_fields):
        hard.append("paper_sharpe_evidence:series_scope_violation")
    return sorted(set(hard))


def _daily_return_failures(daily_returns: tuple[str, ...]) -> list[str]:
    for daily_return in daily_returns:
        if not _is_canonical_decimal_string(daily_return):
            return ["paper_sharpe_evidence:daily_return_noncanonical"]
    return []


def _compute_sharpe(daily_returns: tuple[str, ...]) -> tuple[dict[str, str], list[str]]:
    """Compute the deterministic Sharpe values from canonical daily returns under the approved policy.

    Returns ``(values, hard)``. ``values`` carries the four public decimal strings when ``hard`` is empty;
    on failure ``hard`` carries a deterministic reason and ``values`` is empty. The risk-free daily return is
    ``0`` (constant-zero policy), so the daily excess return equals the daily return. The mean and the sample
    variance are computed in exact rational arithmetic, so exact zero variance is detected exactly and the
    variance is never spuriously negative; only the square roots and final divisions use the local Decimal
    context.
    """

    excess: list[Fraction] = []
    for daily_return in daily_returns:
        if not _is_canonical_decimal_string(daily_return):
            return {}, ["paper_sharpe_evidence:daily_return_noncanonical"]
        excess.append(_decimal_to_fraction(Decimal(daily_return)))

    count = len(excess)
    mean = sum(excess, Fraction(0)) / count
    variance = sum(((value - mean) ** 2 for value in excess), Fraction(0)) / (count - 1)
    if variance == 0:
        return {}, ["paper_sharpe_evidence:zero_variance"]

    try:
        with localcontext() as ctx:
            ctx.prec = _DECIMAL_INTERNAL_PRECISION
            ctx.rounding = ROUND_HALF_EVEN
            mean_dec = Decimal(mean.numerator) / Decimal(mean.denominator)
            variance_dec = Decimal(variance.numerator) / Decimal(variance.denominator)
            stddev_dec = variance_dec.sqrt()
            if not stddev_dec.is_finite() or stddev_dec == 0:
                return {}, ["paper_sharpe_evidence:decimal_non_finite"]
            daily_sharpe_dec = mean_dec / stddev_dec
            annualized_dec = daily_sharpe_dec * Decimal(_ANNUALIZATION_FACTOR).sqrt()
            computed = (mean_dec, stddev_dec, daily_sharpe_dec, annualized_dec)
            if not all(value.is_finite() for value in computed):
                return {}, ["paper_sharpe_evidence:decimal_non_finite"]
            values = {
                "mean_excess_return": _format_public_decimal(mean_dec),
                "sample_stddev_excess_return": _format_public_decimal(stddev_dec),
                "paper_sharpe_daily": _format_public_decimal(daily_sharpe_dec),
                "paper_sharpe_annualized": _format_public_decimal(annualized_dec),
            }
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return {}, ["paper_sharpe_evidence:decimal_non_finite"]
    return values, []


def build_paper_sharpe_evidence(
    daily_return_series: PaperDailyReturnSeriesEvidence,
    *,
    expected_daily_return_series_digest: str,
    risk_free_policy_id: str,
    sharpe_evidence_id: str,
    paper_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSharpeEvidence:
    """Compute deterministic paper Sharpe evidence from a proven paper daily return series."""

    if type(daily_return_series) is not PaperDailyReturnSeriesEvidence:
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:series_malformed")
    if not _is_hex64_string(expected_daily_return_series_digest):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:expected_daily_return_series_digest_invalid")
    if not _is_plain_non_empty_string(risk_free_policy_id):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:risk_free_policy_id_invalid")
    if not _is_plain_non_empty_string(sharpe_evidence_id):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:sharpe_evidence_id_invalid")
    if not _is_plain_non_empty_string(paper_id):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:paper_id_invalid")
    if not _is_plain_non_empty_string(correlation_id):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(
        risk_free_policy_id, sharpe_evidence_id, paper_id, correlation_id, *_metadata_texts(metadata_pairs)
    ):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:scope_violation")
    if _has_clock_token(
        risk_free_policy_id, sharpe_evidence_id, paper_id, correlation_id, *_metadata_texts(metadata_pairs)
    ):
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:clock_token_forbidden")
    if risk_free_policy_id != _RISK_FREE_POLICY_ID:
        raise PaperSharpeEvidenceError("paper_sharpe_evidence:risk_free_policy_unapproved")

    # Prove exact container shapes BEFORE any len/iteration of the consumed data (fail closed, never a raw
    # TypeError, never a silent collapse under READY). The Sharpe math runs only over an exact tuple of
    # canonical daily-return strings.
    hard = [
        *_series_hard_failures(daily_return_series, expected_daily_return_series_digest, risk_free_policy_id),
        *_container_shape_failures(daily_return_series),
    ]
    if correlation_id != daily_return_series.correlation_id:
        hard.append("paper_sharpe_evidence:correlation_id_mismatch")

    raw_returns = daily_return_series.daily_returns
    daily_returns_safe = (
        raw_returns
        if type(raw_returns) is tuple and all(type(daily_return) is str for daily_return in raw_returns)
        else ()
    )

    values: dict[str, str] = {}
    if hard:
        hard.extend(_daily_return_failures(daily_returns_safe))
    else:
        values, compute_hard = _compute_sharpe(daily_returns_safe)
        hard.extend(compute_hard)

    if hard:
        status = PaperSharpeEvidenceStatus.REJECTED
        ready = False
        sharpe_computed = False
        reason_codes = tuple(sorted(set(hard)))
        mean_excess_return = ""
        sample_stddev_excess_return = ""
        paper_sharpe_daily = ""
        paper_sharpe_annualized = ""
        observation_count = 0
        stability_warning = False
        minimum_window_only = False
    else:
        status = PaperSharpeEvidenceStatus.READY
        ready = True
        sharpe_computed = True
        reason_codes = ()
        mean_excess_return = values["mean_excess_return"]
        sample_stddev_excess_return = values["sample_stddev_excess_return"]
        paper_sharpe_daily = values["paper_sharpe_daily"]
        paper_sharpe_annualized = values["paper_sharpe_annualized"]
        observation_count = len(daily_returns_safe)
        # A 30-day window is the documented MINIMUM; any window length carries a non-removable stability warning,
        # and a window pinned exactly at the minimum is additionally flagged as minimum-only.
        stability_warning = True
        minimum_window_only = observation_count == _REQUIRED_CONSECUTIVE_BUCKET_COUNT

    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "evidence_version": _EVIDENCE_VERSION,
        "status": status,
        "ready": ready,
        "sharpe_evidence_id": sharpe_evidence_id,
        "paper_id": paper_id,
        "series_id": daily_return_series.series_id if type(daily_return_series.series_id) is str else "",
        "methodology_id": daily_return_series.methodology_id if type(daily_return_series.methodology_id) is str else "",
        "window_id": daily_return_series.window_id if type(daily_return_series.window_id) is str else "",
        "correlation_id": correlation_id,
        "market_symbol": daily_return_series.market_symbol if type(daily_return_series.market_symbol) is str else "",
        "expected_daily_return_series_digest": expected_daily_return_series_digest,
        "daily_return_series_digest": daily_return_series.series_digest
        if type(daily_return_series.series_digest) is str
        else "",
        "verified_daily_return_series_digest": daily_return_series.series_digest
        if not hard and type(daily_return_series.series_digest) is str
        else "",
        "methodology_digest": daily_return_series.methodology_digest
        if type(daily_return_series.methodology_digest) is str
        else "",
        "time_window_digest": daily_return_series.time_window_digest
        if type(daily_return_series.time_window_digest) is str
        else "",
        "metrics_summary_digest": daily_return_series.metrics_summary_digest
        if type(daily_return_series.metrics_summary_digest) is str
        else "",
        "calendar": daily_return_series.calendar if type(daily_return_series.calendar) is str else "",
        "bucket_frequency": daily_return_series.bucket_frequency
        if type(daily_return_series.bucket_frequency) is str
        else "",
        "bucket_duration_ns": daily_return_series.bucket_duration_ns
        if _is_exact_int(daily_return_series.bucket_duration_ns)
        else 0,
        "required_consecutive_bucket_count": daily_return_series.required_consecutive_bucket_count
        if _is_exact_int(daily_return_series.required_consecutive_bucket_count)
        else 0,
        "return_basis": daily_return_series.return_basis if type(daily_return_series.return_basis) is str else "",
        "return_value_kind": daily_return_series.return_value_kind
        if type(daily_return_series.return_value_kind) is str
        else "",
        "annualization_policy": daily_return_series.annualization_policy
        if type(daily_return_series.annualization_policy) is str
        else "",
        "annualization_factor": daily_return_series.annualization_factor
        if _is_exact_int(daily_return_series.annualization_factor)
        else 0,
        "annualization_formula": _ANNUALIZATION_FORMULA,
        "risk_free_policy_id": risk_free_policy_id,
        "risk_free_policy": _RISK_FREE_POLICY,
        "risk_free_daily_return": _format_public_decimal(Decimal(0)),
        "stddev_policy": _STDDEV_POLICY,
        "zero_variance_policy": _ZERO_VARIANCE_POLICY,
        "near_zero_epsilon_policy": _NEAR_ZERO_EPSILON_POLICY,
        "decimal_policy": _DECIMAL_POLICY,
        "decimal_scale": _DECIMAL_SCALE,
        "decimal_rounding": _DECIMAL_ROUNDING,
        "decimal_internal_precision": _DECIMAL_INTERNAL_PRECISION,
        "bucket_count": daily_return_series.bucket_count if _is_exact_int(daily_return_series.bucket_count) else 0,
        "observation_count": observation_count,
        "daily_return_count": daily_return_series.return_count
        if _is_exact_int(daily_return_series.return_count)
        else 0,
        "mean_excess_return": mean_excess_return,
        "sample_stddev_excess_return": sample_stddev_excess_return,
        "paper_sharpe_daily": paper_sharpe_daily,
        "paper_sharpe_annualized": paper_sharpe_annualized,
        "sharpe_computed": sharpe_computed,
        "stability_warning": stability_warning,
        "minimum_window_only": minimum_window_only,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperSharpeEvidence(sharpe_evidence_digest="", **fields)  # type: ignore[arg-type]
    return _replace_evidence_digest(seed, paper_sharpe_evidence_digest(seed))


def _replace_evidence_digest(evidence: PaperSharpeEvidence, digest: str) -> PaperSharpeEvidence:
    fields = _evidence_fields(evidence)
    fields["sharpe_evidence_digest"] = digest
    return PaperSharpeEvidence(**fields)  # type: ignore[arg-type]


def _evidence_fields(evidence: PaperSharpeEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "evidence_version": evidence.evidence_version,
        "status": evidence.status,
        "ready": evidence.ready,
        "sharpe_evidence_id": evidence.sharpe_evidence_id,
        "paper_id": evidence.paper_id,
        "series_id": evidence.series_id,
        "methodology_id": evidence.methodology_id,
        "window_id": evidence.window_id,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_daily_return_series_digest": evidence.expected_daily_return_series_digest,
        "daily_return_series_digest": evidence.daily_return_series_digest,
        "verified_daily_return_series_digest": evidence.verified_daily_return_series_digest,
        "methodology_digest": evidence.methodology_digest,
        "time_window_digest": evidence.time_window_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "calendar": evidence.calendar,
        "bucket_frequency": evidence.bucket_frequency,
        "bucket_duration_ns": evidence.bucket_duration_ns,
        "required_consecutive_bucket_count": evidence.required_consecutive_bucket_count,
        "return_basis": evidence.return_basis,
        "return_value_kind": evidence.return_value_kind,
        "annualization_policy": evidence.annualization_policy,
        "annualization_factor": evidence.annualization_factor,
        "annualization_formula": evidence.annualization_formula,
        "risk_free_policy_id": evidence.risk_free_policy_id,
        "risk_free_policy": evidence.risk_free_policy,
        "risk_free_daily_return": evidence.risk_free_daily_return,
        "stddev_policy": evidence.stddev_policy,
        "zero_variance_policy": evidence.zero_variance_policy,
        "near_zero_epsilon_policy": evidence.near_zero_epsilon_policy,
        "decimal_policy": evidence.decimal_policy,
        "decimal_scale": evidence.decimal_scale,
        "decimal_rounding": evidence.decimal_rounding,
        "decimal_internal_precision": evidence.decimal_internal_precision,
        "bucket_count": evidence.bucket_count,
        "observation_count": evidence.observation_count,
        "daily_return_count": evidence.daily_return_count,
        "mean_excess_return": evidence.mean_excess_return,
        "sample_stddev_excess_return": evidence.sample_stddev_excess_return,
        "paper_sharpe_daily": evidence.paper_sharpe_daily,
        "paper_sharpe_annualized": evidence.paper_sharpe_annualized,
        "sharpe_computed": evidence.sharpe_computed,
        "stability_warning": evidence.stability_warning,
        "minimum_window_only": evidence.minimum_window_only,
        "reason_codes": evidence.reason_codes,
        "metadata": evidence.metadata,
    }


def _evidence_payload_from(evidence: PaperSharpeEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "evidence_version": evidence.evidence_version,
        "status": evidence.status.value,
        "ready": evidence.ready,
        "sharpe_evidence_id": evidence.sharpe_evidence_id,
        "paper_id": evidence.paper_id,
        "series_id": evidence.series_id,
        "methodology_id": evidence.methodology_id,
        "window_id": evidence.window_id,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_daily_return_series_digest": evidence.expected_daily_return_series_digest,
        "daily_return_series_digest": evidence.daily_return_series_digest,
        "verified_daily_return_series_digest": evidence.verified_daily_return_series_digest,
        "methodology_digest": evidence.methodology_digest,
        "time_window_digest": evidence.time_window_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "calendar": evidence.calendar,
        "bucket_frequency": evidence.bucket_frequency,
        "bucket_duration_ns": evidence.bucket_duration_ns,
        "required_consecutive_bucket_count": evidence.required_consecutive_bucket_count,
        "return_basis": evidence.return_basis,
        "return_value_kind": evidence.return_value_kind,
        "annualization_policy": evidence.annualization_policy,
        "annualization_factor": evidence.annualization_factor,
        "annualization_formula": evidence.annualization_formula,
        "risk_free_policy_id": evidence.risk_free_policy_id,
        "risk_free_policy": evidence.risk_free_policy,
        "risk_free_daily_return": evidence.risk_free_daily_return,
        "stddev_policy": evidence.stddev_policy,
        "zero_variance_policy": evidence.zero_variance_policy,
        "near_zero_epsilon_policy": evidence.near_zero_epsilon_policy,
        "decimal_policy": evidence.decimal_policy,
        "decimal_scale": evidence.decimal_scale,
        "decimal_rounding": evidence.decimal_rounding,
        "decimal_internal_precision": evidence.decimal_internal_precision,
        "bucket_count": evidence.bucket_count,
        "observation_count": evidence.observation_count,
        "daily_return_count": evidence.daily_return_count,
        "mean_excess_return": evidence.mean_excess_return,
        "sample_stddev_excess_return": evidence.sample_stddev_excess_return,
        "paper_sharpe_daily": evidence.paper_sharpe_daily,
        "paper_sharpe_annualized": evidence.paper_sharpe_annualized,
        "sharpe_computed": evidence.sharpe_computed,
        "stability_warning": evidence.stability_warning,
        "minimum_window_only": evidence.minimum_window_only,
        "reason_codes": list(evidence.reason_codes),
        "metadata": _serialize_metadata(evidence.metadata),
        "paper_only": evidence.paper_only,
        "daily_return_series_evidence_consumed": evidence.daily_return_series_evidence_consumed,
        "paper_sharpe_evidence": evidence.paper_sharpe_evidence,
        "return_series_constructed": evidence.return_series_constructed,
        "statistical_significance_proven": evidence.statistical_significance_proven,
        "sharpe_stable": evidence.sharpe_stable,
        "paper_vs_backtest_comparison_ready": evidence.paper_vs_backtest_comparison_ready,
        "comparison_ready": evidence.comparison_ready,
        "stage4_comparator_invoked": evidence.stage4_comparator_invoked,
        "thirty_day_gate_satisfied": evidence.thirty_day_gate_satisfied,
        "thirty_day_gate_decided": evidence.thirty_day_gate_decided,
        "prdv4_stage4_complete": evidence.prdv4_stage4_complete,
        "live_ready": evidence.live_ready,
        "shadow_ready": evidence.shadow_ready,
        "operational_readiness": evidence.operational_readiness,
        "deribit_ready": evidence.deribit_ready,
        "profitability_proven": evidence.profitability_proven,
        "edge_proven": evidence.edge_proven,
        "production_execution": evidence.production_execution,
        "real_orders_enabled": evidence.real_orders_enabled,
        "real_money_enabled": evidence.real_money_enabled,
        "real_capital_reserved": evidence.real_capital_reserved,
        "live_api_called": evidence.live_api_called,
        "scheduler_enabled": evidence.scheduler_enabled,
        "auto_loop_enabled": evidence.auto_loop_enabled,
        "connector_invoked": evidence.connector_invoked,
        "real_wall_clock_used": evidence.real_wall_clock_used,
        "real_account_equity_used": evidence.real_account_equity_used,
        "real_capital_used": evidence.real_capital_used,
    }


def paper_sharpe_evidence_to_dict(evidence: PaperSharpeEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for the paper Sharpe evidence, including its self-digest."""

    payload = _evidence_payload_from(evidence)
    payload["sharpe_evidence_digest"] = evidence.sharpe_evidence_digest
    return payload


def paper_sharpe_evidence_digest(evidence: PaperSharpeEvidence) -> str:
    """Recompute the canonical Sharpe-evidence digest, excluding only the self-digest field."""

    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperSharpeEvidence",
    "PaperSharpeEvidenceError",
    "PaperSharpeEvidenceStatus",
    "build_paper_sharpe_evidence",
    "paper_sharpe_evidence_digest",
    "paper_sharpe_evidence_to_dict",
]
