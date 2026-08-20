"""Deterministic paper daily return-series evidence.

This validation artifact consumes a proven ``PaperReturnSeriesMethodology`` and a proven
``PaperDeterministicTimeWindowEvidence``, then computes an ordered daily UTC return series from caller-supplied
normalized paper equity index bucket endpoints. It is paper-only, deterministic, digest-bound, and fail-closed.

It does not compute Sharpe, does not decide the 30-day gate, does not invoke the Stage-4 comparator, and does not
construct ``Stage4PaperSummary``. Bucket timestamps and index values are injected evidence data; this module calls
no wall-clock, runtime, service, execution, venue, scheduler, filesystem, network, or random surface.

Recomputing the carried methodology digest proves only that the methodology object is internally self-consistent;
it does not prove the object could have been produced by the public methodology builder. This module therefore
also replays the producer's public-builder contract locally: its forbidden-scope/clock text semantics, its fixed
contract values, and the canonical reason-code/metadata output shape it is able to emit. It never mutates the
producer and never imports producer-private helpers.

The replay is applied at two deliberately different strengths, because the two text surfaces have different
owners. The nine methodology identity/policy carriers must satisfy BOTH this module's own text policy and the
producer policy, so producer-permitted values this module already refused stay refused. Methodology reason codes
and metadata are producer-owned OUTPUT containers that this module never governed, so the producer policy alone
decides whether their text is emittable: the daily-series generic policy is deliberately not applied there, and
anything the public builder can canonically emit stays accepted - including padded/control-character text and a
sorted metadata tuple that repeats a key, which a Mapping whose ``items()`` repeats a key produces.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from fractions import Fraction

from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.paper_return_series_methodology import (
    PaperReturnSeriesMethodology,
    PaperReturnSeriesMethodologyStatus,
    paper_return_series_methodology_digest,
)

_SCHEMA_VERSION = "paper-daily-return-series-evidence.v1"
_SERIES_VERSION = "paper-daily-return-series.v1"
_EXPECTED_METHODOLOGY_SCHEMA_VERSION = "paper-return-series-methodology.v1"
_EXPECTED_METHODOLOGY_VERSION = "paper-return-series-methodology.v1"
_EXPECTED_METHODOLOGY_MISSING_POLICY_INPUT_STATUS = "BLOCKED"
_EXPECTED_METHODOLOGY_SPARSE_WINDOW_STATUS = "BLOCKED"
_EXPECTED_METHODOLOGY_INSUFFICIENT_SAMPLE_STATUS = "BLOCKED"
_EXPECTED_METHODOLOGY_NO_TRADE_STATUS = "NOT_COMPUTABLE"
_EXPECTED_METHODOLOGY_ZERO_VARIANCE_STATUS = "NOT_COMPUTABLE"
_EXPECTED_METHODOLOGY_MISMATCH_STATUS = "BLOCKED"
_EXPECTED_TIME_WINDOW_SCHEMA_VERSION = "paper-deterministic-time-window-evidence.v1"
_CALENDAR = "UTC"
_BUCKET_FREQUENCY = "1d_utc"
_BUCKET_DURATION_NS = 86_400_000_000_000
_REQUIRED_CONSECUTIVE_BUCKET_COUNT = 30
_RETURN_BASIS = "normalized_paper_equity_index"
_NORMALIZED_INDEX_START = "1"
_RETURN_VALUE_KIND = "unitless_decimal_return"
_PAPER_SHARPE_POLICY = "deferred_not_computed"
_ANNUALIZATION_POLICY = "daily_utc_365_review_only"
_ANNUALIZATION_FACTOR = 365
_TIMESTAMP_POLICY = "injected_deterministic_ns.v1"
_VERDICT_CANDIDATE = "PAPER_STAGE4_CANDIDATE"

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

# Producer-parity replay surface. These mirror the public methodology producer's own text policy so this
# consumer can prove that methodology-owned text could have been emitted by
# ``build_paper_return_series_methodology``. They are deliberately SEPARATE from the daily-series generic
# policy above and never replace it: identity/policy carriers must satisfy both policies, while
# producer-owned reason-code and metadata text is governed by the producer policy alone.
_PRODUCER_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_PRODUCER_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|"
    r"readiness|service|capital|equity|margin|balance|reservation|real_money|paper_adapter|"
    r"stage4_comparator|compare_stage4|Stage4PaperSummary)\w*"
    r"|crypto_core\.(?:service|execution|venue|runtime|orchestrator|temporal|session|data|portfolio)\b"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_PRODUCER_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")
_PRODUCER_CLOCK_TOKENS = (
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

# Fixed methodology contract values the public producer pins for every emitted snapshot.
_EXPECTED_METHODOLOGY_TEXT_VALUES: dict[str, str] = {
    "schema_version": _EXPECTED_METHODOLOGY_SCHEMA_VERSION,
    "methodology_version": _EXPECTED_METHODOLOGY_VERSION,
    "calendar": _CALENDAR,
    "bucket_frequency": _BUCKET_FREQUENCY,
    "return_basis": _RETURN_BASIS,
    "normalized_index_start": _NORMALIZED_INDEX_START,
    "return_value_kind": _RETURN_VALUE_KIND,
    "annualization_policy": _ANNUALIZATION_POLICY,
    "paper_sharpe_policy": _PAPER_SHARPE_POLICY,
    "missing_policy_input_status": _EXPECTED_METHODOLOGY_MISSING_POLICY_INPUT_STATUS,
    "sparse_window_status": _EXPECTED_METHODOLOGY_SPARSE_WINDOW_STATUS,
    "insufficient_sample_status": _EXPECTED_METHODOLOGY_INSUFFICIENT_SAMPLE_STATUS,
    "no_trade_status": _EXPECTED_METHODOLOGY_NO_TRADE_STATUS,
    "zero_variance_status": _EXPECTED_METHODOLOGY_ZERO_VARIANCE_STATUS,
    "methodology_mismatch_status": _EXPECTED_METHODOLOGY_MISMATCH_STATUS,
}
_EXPECTED_METHODOLOGY_INT_VALUES: dict[str, int] = {
    "bucket_duration_ns": _BUCKET_DURATION_NS,
    "required_consecutive_bucket_count": _REQUIRED_CONSECUTIVE_BUCKET_COUNT,
    "annualization_factor": _ANNUALIZATION_FACTOR,
}
_EXPECTED_METHODOLOGY_BOOL_VALUES: dict[str, bool] = {
    "duration_sufficiency_assessed": False,
    "sample_sufficiency_assessed": False,
    "fee_policy_required": True,
    "funding_policy_required": True,
    "mark_policy_required": True,
    "exposure_policy_required": True,
    "liquidation_policy_required": True,
}


class PaperDailyReturnSeriesEvidenceError(RuntimeError):
    """Raised on malformed caller input or forbidden scope tokens."""


class PaperDailyReturnSeriesEvidenceStatus(str, Enum):
    """Daily return-series evidence status. READY is not a Sharpe, 30-day gate, or Stage-4 verdict."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperDailyReturnBucket:
    """One deterministic UTC daily normalized-index bucket supplied as evidence input."""

    bucket_id: str
    bucket_start_ns: int
    bucket_end_ns: int
    normalized_index_start: str
    normalized_index_end: str
    bucket_digest: str


@dataclass(frozen=True)
class PaperDailyReturnSeriesEvidence:
    """Immutable, digest-bound deterministic paper daily return-series evidence."""

    schema_version: str
    series_version: str
    status: PaperDailyReturnSeriesEvidenceStatus
    ready: bool
    series_id: str
    methodology_id: str
    window_id: str
    correlation_id: str
    market_symbol: str
    expected_methodology_digest: str
    methodology_digest: str
    expected_time_window_digest: str
    time_window_digest: str
    metrics_summary_digest: str
    calendar: str
    bucket_frequency: str
    bucket_duration_ns: int
    required_consecutive_bucket_count: int
    duration_sufficiency_assessed: bool
    sample_sufficiency_assessed: bool
    return_basis: str
    return_value_kind: str
    annualization_policy: str
    annualization_factor: int
    paper_sharpe_policy: str
    mtm_policy_id: str
    fee_policy_id: str
    funding_policy_id: str
    mark_policy_id: str
    exposure_policy_id: str
    liquidation_policy_id: str
    risk_free_policy_id: str
    timestamp_policy: str
    started_at_ns: int
    stopped_at_ns: int
    window_duration_ns: int
    sample_observation_count: int
    sample_eligible: bool
    bucket_count: int
    return_count: int
    normalized_index_start: str
    normalized_index_end: str
    daily_returns: tuple[str, ...]
    buckets: tuple[PaperDailyReturnBucket, ...]
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    series_digest: str
    paper_only: bool = True
    daily_return_series_evidence: bool = True
    methodology_snapshot_consumed: bool = True
    injected_deterministic_time_window_consumed: bool = True
    daily_utc_only: bool = True
    normalized_paper_equity_index: bool = True
    mark_to_market_required: bool = True
    realized_only_primary_series: bool = False
    real_account_equity_used: bool = False
    real_capital_used: bool = False
    return_series_computed: bool = True
    daily_returns_computed: bool = True
    sharpe_computed: bool = False
    paper_sharpe_computed: bool = False
    thirty_day_gate_satisfied: bool = False
    thirty_day_gate_decided: bool = False
    comparison_ready: bool = False
    stage4_comparator_invoked: bool = False
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
    timestamp_origin_proven: bool = False


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


def _eq_plain_str(value: object, expected: str) -> bool:
    return type(value) is str and value == expected


def _eq_exact_int(value: object, expected: int) -> bool:
    return _is_exact_int(value) and value == expected


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _parse_decimal(value: object) -> Decimal | None:
    if type(value) is not str or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _render_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _canonical_decimal(value: object) -> Decimal | None:
    parsed = _parse_decimal(value)
    if parsed is None or _render_decimal(parsed) != value:
        return None
    return parsed


def _decimal_to_fraction(value: Decimal) -> Fraction:
    sign, digits, exponent = value.as_tuple()
    coefficient = int("".join(str(digit) for digit in digits)) if digits else 0
    if sign:
        coefficient = -coefficient
    if exponent >= 0:
        return Fraction(coefficient * (10**exponent), 1)
    return Fraction(coefficient, 10 ** (-exponent))


def _finite_decimal_string(value: Fraction) -> str | None:
    denominator = value.denominator
    twos = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    fives = 0
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return None

    scale = max(twos, fives)
    scaled_numerator = value.numerator * (2 ** (scale - twos)) * (5 ** (scale - fives))
    if scaled_numerator == 0:
        return "0"
    sign = "-" if scaled_numerator < 0 else ""
    digits = str(abs(scaled_numerator))
    if scale == 0:
        return f"{sign}{digits}"
    if len(digits) <= scale:
        rendered = f"{sign}0.{('0' * (scale - len(digits)))}{digits}"
    else:
        rendered = f"{sign}{digits[:-scale]}.{digits[-scale:]}"
    rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _compute_daily_return(start_index: Decimal, end_index: Decimal) -> str | None:
    start = _decimal_to_fraction(start_index)
    end = _decimal_to_fraction(end_index)
    if start <= 0:
        return None
    return _finite_decimal_string((end - start) / start)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:metadata_malformed")
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:metadata_malformed")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


def _bucket_payload_from(bucket: PaperDailyReturnBucket) -> dict[str, object]:
    return {
        "bucket_id": bucket.bucket_id,
        "bucket_start_ns": bucket.bucket_start_ns,
        "bucket_end_ns": bucket.bucket_end_ns,
        "normalized_index_start": bucket.normalized_index_start,
        "normalized_index_end": bucket.normalized_index_end,
    }


def _bucket_digest(bucket: PaperDailyReturnBucket) -> str:
    return _canonical_digest(_bucket_payload_from(bucket))


def _serialize_bucket(bucket: PaperDailyReturnBucket) -> dict[str, object]:
    payload = _bucket_payload_from(bucket)
    payload["bucket_digest"] = bucket.bucket_digest
    return payload


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


def _producer_has_scope_violation(*texts: object) -> bool:
    """Replay the public methodology producer's forbidden-scope semantics on methodology-owned text."""

    for text in texts:
        if type(text) is not str or text == "":
            continue
        if _PRODUCER_BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _PRODUCER_SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _PRODUCER_FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _producer_has_clock_token(*texts: object) -> bool:
    """Replay the public methodology producer's clock-token semantics on methodology-owned text."""

    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _PRODUCER_CLOCK_TOKENS):
            return True
    return False


def _producer_methodology_text_rejected(*texts: object) -> bool:
    """Producer policy alone. Authoritative for producer-OWNED output text (reason codes and metadata)."""

    return _producer_has_scope_violation(*texts) or _producer_has_clock_token(*texts)


def _methodology_identity_text_rejected(*texts: object) -> bool:
    """Identity/policy carriers must satisfy BOTH this module's own text policy and the producer policy."""

    return _has_scope_violation(*texts) or _has_clock_token(*texts) or _producer_methodology_text_rejected(*texts)


def _producer_canonical_reason_codes(reason_codes: object) -> tuple[str, ...] | None:
    """Return producer-canonical reason codes, or ``None`` when the public builder could not emit them."""

    if type(reason_codes) is not tuple:
        return None
    codes: list[str] = []
    for code in reason_codes:
        if type(code) is not str or code.strip() == "":
            return None
        codes.append(code)
    if codes != sorted(set(codes)):
        return None
    return tuple(codes)


def _producer_canonical_metadata(metadata: object) -> tuple[tuple[str, str], ...] | None:
    """Return producer-canonical metadata pairs, or ``None`` when the public builder could not emit them."""

    if type(metadata) is not tuple:
        return None
    pairs: list[tuple[str, str]] = []
    for pair in metadata:
        if type(pair) is not tuple or len(pair) != 2:
            return None
        key, value = pair
        if type(key) is not str or type(value) is not str:
            return None
        pairs.append((key, value))
    # The producer sorts whatever ``Mapping.items()`` yields and never enforces key uniqueness, so a
    # canonical producer-emitted tuple may legitimately repeat a key. Only the ordering is canonical.
    if pairs != sorted(pairs):
        return None
    return tuple(pairs)


def _methodology_container_failures(methodology: PaperReturnSeriesMethodology) -> list[str]:
    """Fail closed on methodology reason-code/metadata state the public builder could not have emitted."""

    failures: list[str] = []
    texts: list[str] = []

    reason_codes = _producer_canonical_reason_codes(methodology.reason_codes)
    if reason_codes is None:
        failures.append("paper_daily_return_series_evidence:methodology_reason_codes_noncanonical")
    else:
        texts.extend(reason_codes)

    metadata = _producer_canonical_metadata(methodology.metadata)
    if metadata is None:
        failures.append("paper_daily_return_series_evidence:methodology_metadata_noncanonical")
    else:
        texts.extend(text for pair in metadata for text in pair)

    if _producer_methodology_text_rejected(*texts):
        failures.append("paper_daily_return_series_evidence:methodology_scope_violation")
    return failures


def _methodology_hard_failures(
    methodology: PaperReturnSeriesMethodology, expected_methodology_digest: str
) -> list[str]:
    hard: list[str] = []
    try:
        recomputed = paper_return_series_methodology_digest(methodology)
    except Exception:  # noqa: BLE001 - digest recompute failures fail closed at this boundary
        recomputed = None
    if (
        recomputed is None
        or not _is_hex64_string(methodology.methodology_digest)
        or methodology.methodology_digest != recomputed
        or methodology.methodology_digest != expected_methodology_digest
    ):
        hard.append("paper_daily_return_series_evidence:methodology_digest_mismatch")

    for field_name, expected_text in _EXPECTED_METHODOLOGY_TEXT_VALUES.items():
        if not _eq_plain_str(getattr(methodology, field_name), expected_text):
            hard.append(f"paper_daily_return_series_evidence:methodology_{field_name}_mismatch")
    for field_name, expected_int in _EXPECTED_METHODOLOGY_INT_VALUES.items():
        if not _eq_exact_int(getattr(methodology, field_name), expected_int):
            hard.append(f"paper_daily_return_series_evidence:methodology_{field_name}_mismatch")
    for field_name, expected_flag in _EXPECTED_METHODOLOGY_BOOL_VALUES.items():
        if getattr(methodology, field_name) is not expected_flag:
            hard.append(f"paper_daily_return_series_evidence:methodology_{field_name}_mismatch")

    if methodology.status is not PaperReturnSeriesMethodologyStatus.READY or methodology.ready is not True:
        hard.append("paper_daily_return_series_evidence:methodology_not_ready")
    if methodology.mark_to_market_required is not True or methodology.realized_only_primary_series is not False:
        hard.append("paper_daily_return_series_evidence:methodology_mtm_policy_mismatch")
    if (
        methodology.paper_only is not True
        or methodology.methodology_snapshot is not True
        or methodology.daily_utc_only is not True
        or methodology.normalized_paper_equity_index is not True
        or methodology.real_account_equity_used is not False
        or methodology.real_capital_used is not False
        or methodology.return_series_computed is not False
        or methodology.daily_returns_computed is not False
        or methodology.sharpe_computed is not False
        or methodology.paper_sharpe_computed is not False
        or methodology.thirty_day_gate_satisfied is not False
        or methodology.thirty_day_gate_decided is not False
        or methodology.comparison_ready is not False
        or methodology.stage4_comparator_invoked is not False
        or methodology.prdv4_stage4_complete is not False
        or methodology.live_ready is not False
        or methodology.shadow_ready is not False
        or methodology.operational_readiness is not False
        or methodology.deribit_ready is not False
        or methodology.profitability_proven is not False
        or methodology.edge_proven is not False
        or methodology.production_execution is not False
        or methodology.real_orders_enabled is not False
        or methodology.real_money_enabled is not False
        or methodology.real_capital_reserved is not False
        or methodology.live_api_called is not False
        or methodology.scheduler_enabled is not False
        or methodology.auto_loop_enabled is not False
        or methodology.connector_invoked is not False
        or methodology.real_wall_clock_used is not False
        or methodology.timestamp_origin_proven is not False
    ):
        hard.append("paper_daily_return_series_evidence:methodology_unsafe_flags")

    policy_ids = (
        methodology.methodology_id,
        methodology.correlation_id,
        methodology.mtm_policy_id,
        methodology.fee_policy_id,
        methodology.funding_policy_id,
        methodology.mark_policy_id,
        methodology.exposure_policy_id,
        methodology.liquidation_policy_id,
        methodology.risk_free_policy_id,
    )
    if not all(_is_plain_non_empty_string(value) for value in policy_ids):
        hard.append("paper_daily_return_series_evidence:methodology_policy_id_invalid")
    elif _methodology_identity_text_rejected(*policy_ids):
        hard.append("paper_daily_return_series_evidence:methodology_scope_violation")
    hard.extend(_methodology_container_failures(methodology))
    return hard


def _window_hard_failures(
    time_window: PaperDeterministicTimeWindowEvidence,
    expected_time_window_digest: str,
    methodology: PaperReturnSeriesMethodology,
) -> list[str]:
    hard: list[str] = []
    try:
        recomputed = paper_deterministic_time_window_evidence_digest(time_window)
    except Exception:  # noqa: BLE001 - digest recompute failures fail closed at this boundary
        recomputed = None
    if (
        recomputed is None
        or not _is_hex64_string(time_window.time_window_digest)
        or time_window.time_window_digest != recomputed
        or time_window.time_window_digest != expected_time_window_digest
    ):
        hard.append("paper_daily_return_series_evidence:time_window_digest_mismatch")

    if time_window.schema_version != _EXPECTED_TIME_WINDOW_SCHEMA_VERSION:
        hard.append("paper_daily_return_series_evidence:time_window_schema_invalid")
    if time_window.status is not PaperDeterministicTimeWindowEvidenceStatus.READY or time_window.ready is not True:
        hard.append("paper_daily_return_series_evidence:time_window_not_ready")
    if time_window.methodology_id != methodology.methodology_id:
        hard.append("paper_daily_return_series_evidence:methodology_id_mismatch")
    if time_window.timestamp_policy != _TIMESTAMP_POLICY:
        hard.append("paper_daily_return_series_evidence:timestamp_policy_mismatch")
    if (
        not _is_exact_int(time_window.started_at_ns)
        or not _is_exact_int(time_window.stopped_at_ns)
        or not _is_exact_int(time_window.window_duration_ns)
        or time_window.started_at_ns < 0
        or time_window.stopped_at_ns <= time_window.started_at_ns
        or time_window.window_duration_ns != time_window.stopped_at_ns - time_window.started_at_ns
    ):
        hard.append("paper_daily_return_series_evidence:time_window_bounds_invalid")
    if (
        time_window.sample_eligible is not True
        or not _is_exact_int(time_window.sample_observation_count)
        or time_window.sample_observation_count < 1
        or time_window.summary_ready is not True
        or time_window.summary_readiness_verdict != _VERDICT_CANDIDATE
        or time_window.reason_codes != ()
    ):
        hard.append("paper_daily_return_series_evidence:time_window_not_sample_eligible")
    if (
        time_window.paper_only is not True
        or time_window.injected_deterministic_time_window is not True
        or time_window.prdv4_stage4_complete is not False
        or time_window.live_ready is not False
        or time_window.shadow_ready is not False
        or time_window.profitability_proven is not False
        or time_window.edge_proven is not False
        or time_window.production_execution is not False
        or time_window.real_orders_enabled is not False
        or time_window.real_money_enabled is not False
        or time_window.real_capital_reserved is not False
        or time_window.live_api_called is not False
        or time_window.scheduler_enabled is not False
        or time_window.auto_loop_enabled is not False
        or time_window.connector_invoked is not False
        or time_window.deribit_ready is not False
        or time_window.operational_readiness is not False
        or time_window.sharpe_computed is not False
        or time_window.return_series_computed is not False
        or time_window.thirty_day_gate_satisfied is not False
        or time_window.stage4_comparator_invoked is not False
        or time_window.real_wall_clock_used is not False
        or time_window.timestamp_origin_proven is not False
    ):
        hard.append("paper_daily_return_series_evidence:time_window_unsafe_flags")
    if not _is_plain_non_empty_string(time_window.market_symbol):
        hard.append("paper_daily_return_series_evidence:market_symbol_invalid")
    return hard


def _normalize_buckets(daily_buckets: object) -> tuple[PaperDailyReturnBucket, ...]:
    if not isinstance(daily_buckets, Sequence) or isinstance(daily_buckets, (str, bytes, bytearray)):
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:buckets_malformed")
    buckets: list[PaperDailyReturnBucket] = []
    for bucket in daily_buckets:
        if type(bucket) is not PaperDailyReturnBucket:
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:bucket_malformed")
        if not _is_plain_non_empty_string(bucket.bucket_id):
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:bucket_id_invalid")
        if not _is_exact_int(bucket.bucket_start_ns) or not _is_exact_int(bucket.bucket_end_ns):
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:bucket_timestamp_invalid")
        if type(bucket.normalized_index_start) is not str or type(bucket.normalized_index_end) is not str:
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:bucket_index_invalid")
        if type(bucket.bucket_digest) is not str:
            raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:bucket_digest_invalid")
        buckets.append(bucket)
    return tuple(buckets)


def _bucket_hard_failures(
    buckets: tuple[PaperDailyReturnBucket, ...],
    time_window: PaperDeterministicTimeWindowEvidence,
    methodology: PaperReturnSeriesMethodology,
) -> tuple[list[str], tuple[str, ...], str, str]:
    hard: list[str] = []
    returns: list[str] = []
    parsed_pairs: list[tuple[Decimal, Decimal]] = []
    if not buckets:
        return ["paper_daily_return_series_evidence:buckets_empty"], (), "", ""

    if (
        _is_exact_int(time_window.started_at_ns)
        and _is_exact_int(time_window.stopped_at_ns)
        and (
            time_window.started_at_ns % _BUCKET_DURATION_NS != 0 or time_window.stopped_at_ns % _BUCKET_DURATION_NS != 0
        )
    ):
        hard.append("paper_daily_return_series_evidence:time_window_utc_day_alignment_invalid")

    seen_bucket_ids: set[str] = set()
    seen_bucket_digests: set[str] = set()
    for index, bucket in enumerate(buckets):
        if bucket.bucket_id in seen_bucket_ids:
            hard.append("paper_daily_return_series_evidence:duplicate_bucket_id")
        seen_bucket_ids.add(bucket.bucket_id)
        if _has_scope_violation(bucket.bucket_id) or _has_clock_token(bucket.bucket_id):
            hard.append("paper_daily_return_series_evidence:bucket_id_scope_violation")
        if not _is_hex64_string(bucket.bucket_digest):
            hard.append("paper_daily_return_series_evidence:bucket_digest_invalid")
        else:
            if bucket.bucket_digest in seen_bucket_digests:
                hard.append("paper_daily_return_series_evidence:duplicate_bucket_digest")
            seen_bucket_digests.add(bucket.bucket_digest)
            if _bucket_digest(bucket) != bucket.bucket_digest:
                hard.append("paper_daily_return_series_evidence:bucket_digest_mismatch")
        if bucket.bucket_start_ns < 0 or bucket.bucket_end_ns <= bucket.bucket_start_ns:
            hard.append("paper_daily_return_series_evidence:bucket_bounds_invalid")
        if bucket.bucket_end_ns - bucket.bucket_start_ns != _BUCKET_DURATION_NS:
            hard.append("paper_daily_return_series_evidence:bucket_duration_invalid")
        if bucket.bucket_start_ns % _BUCKET_DURATION_NS != 0 or bucket.bucket_end_ns % _BUCKET_DURATION_NS != 0:
            hard.append("paper_daily_return_series_evidence:bucket_utc_day_alignment_invalid")
        if index > 0 and bucket.bucket_start_ns != buckets[index - 1].bucket_end_ns:
            hard.append("paper_daily_return_series_evidence:bucket_sequence_non_contiguous")
        start_index = _canonical_decimal(bucket.normalized_index_start)
        end_index = _canonical_decimal(bucket.normalized_index_end)
        if start_index is None or end_index is None:
            hard.append("paper_daily_return_series_evidence:bucket_index_noncanonical")
            continue
        if start_index <= 0 or end_index <= 0:
            hard.append("paper_daily_return_series_evidence:bucket_index_nonpositive")
        parsed_pairs.append((start_index, end_index))

    methodology_start = _canonical_decimal(methodology.normalized_index_start)
    if methodology_start is None:
        hard.append("paper_daily_return_series_evidence:methodology_normalized_index_start_invalid")
    elif parsed_pairs and parsed_pairs[0][0] != methodology_start:
        hard.append("paper_daily_return_series_evidence:normalized_index_start_mismatch")

    if buckets[0].bucket_start_ns != time_window.started_at_ns:
        hard.append("paper_daily_return_series_evidence:bucket_window_start_mismatch")
    if buckets[-1].bucket_end_ns != time_window.stopped_at_ns:
        hard.append("paper_daily_return_series_evidence:bucket_window_end_mismatch")
    if len(buckets) * _BUCKET_DURATION_NS != time_window.window_duration_ns:
        hard.append("paper_daily_return_series_evidence:bucket_window_duration_mismatch")
    if len(parsed_pairs) == len(buckets):
        for index in range(1, len(parsed_pairs)):
            if parsed_pairs[index - 1][1] != parsed_pairs[index][0]:
                hard.append("paper_daily_return_series_evidence:normalized_index_chain_mismatch")
        if not hard:
            for start_index, end_index in parsed_pairs:
                daily_return = _compute_daily_return(start_index, end_index)
                if daily_return is None:
                    hard.append("paper_daily_return_series_evidence:return_non_terminating")
                    break
                returns.append(daily_return)

    if hard:
        return sorted(set(hard)), (), buckets[0].normalized_index_start, buckets[-1].normalized_index_end
    return [], tuple(returns), buckets[0].normalized_index_start, buckets[-1].normalized_index_end


def build_paper_daily_return_series_evidence(
    methodology: PaperReturnSeriesMethodology,
    time_window: PaperDeterministicTimeWindowEvidence,
    *,
    expected_methodology_digest: str,
    expected_time_window_digest: str,
    series_id: str,
    correlation_id: str,
    daily_buckets: Sequence[PaperDailyReturnBucket],
    metadata: Mapping[str, str] | None = None,
) -> PaperDailyReturnSeriesEvidence:
    """Build deterministic daily return-series evidence from normalized paper equity index buckets."""

    if type(methodology) is not PaperReturnSeriesMethodology:
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:methodology_malformed")
    if type(time_window) is not PaperDeterministicTimeWindowEvidence:
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:time_window_malformed")
    if not _is_hex64_string(expected_methodology_digest):
        raise PaperDailyReturnSeriesEvidenceError(
            "paper_daily_return_series_evidence:expected_methodology_digest_invalid"
        )
    if not _is_hex64_string(expected_time_window_digest):
        raise PaperDailyReturnSeriesEvidenceError(
            "paper_daily_return_series_evidence:expected_time_window_digest_invalid"
        )
    if not _is_plain_non_empty_string(series_id):
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:series_id_invalid")
    if not _is_plain_non_empty_string(correlation_id):
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:correlation_id_invalid")

    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(series_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:scope_violation")
    if _has_clock_token(series_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperDailyReturnSeriesEvidenceError("paper_daily_return_series_evidence:clock_token_forbidden")
    buckets = _normalize_buckets(daily_buckets)

    hard = [
        *_methodology_hard_failures(methodology, expected_methodology_digest),
        *_window_hard_failures(time_window, expected_time_window_digest, methodology),
    ]
    bucket_failures, daily_returns, first_index, last_index = _bucket_hard_failures(buckets, time_window, methodology)
    hard.extend(bucket_failures)

    if correlation_id != methodology.correlation_id or correlation_id != time_window.correlation_id:
        hard.append("paper_daily_return_series_evidence:correlation_id_mismatch")

    if hard:
        status = PaperDailyReturnSeriesEvidenceStatus.REJECTED
        ready = False
        reason_codes = tuple(sorted(set(hard)))
        daily_returns = ()
        return_count = 0
    else:
        status = PaperDailyReturnSeriesEvidenceStatus.READY
        ready = True
        reason_codes = ()
        return_count = len(daily_returns)

    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "series_version": _SERIES_VERSION,
        "status": status,
        "ready": ready,
        "series_id": series_id,
        "methodology_id": methodology.methodology_id,
        "window_id": time_window.window_id,
        "correlation_id": correlation_id,
        "market_symbol": time_window.market_symbol if type(time_window.market_symbol) is str else "",
        "expected_methodology_digest": expected_methodology_digest,
        "methodology_digest": methodology.methodology_digest if type(methodology.methodology_digest) is str else "",
        "expected_time_window_digest": expected_time_window_digest,
        "time_window_digest": time_window.time_window_digest if type(time_window.time_window_digest) is str else "",
        "metrics_summary_digest": time_window.metrics_summary_digest
        if type(time_window.metrics_summary_digest) is str
        else "",
        "calendar": methodology.calendar if type(methodology.calendar) is str else "",
        "bucket_frequency": methodology.bucket_frequency if type(methodology.bucket_frequency) is str else "",
        "bucket_duration_ns": methodology.bucket_duration_ns if _is_exact_int(methodology.bucket_duration_ns) else 0,
        "required_consecutive_bucket_count": methodology.required_consecutive_bucket_count
        if _is_exact_int(methodology.required_consecutive_bucket_count)
        else 0,
        "duration_sufficiency_assessed": False,
        "sample_sufficiency_assessed": False,
        "return_basis": methodology.return_basis if type(methodology.return_basis) is str else "",
        "return_value_kind": methodology.return_value_kind if type(methodology.return_value_kind) is str else "",
        "annualization_policy": methodology.annualization_policy
        if type(methodology.annualization_policy) is str
        else "",
        "annualization_factor": methodology.annualization_factor
        if _is_exact_int(methodology.annualization_factor)
        else 0,
        "paper_sharpe_policy": methodology.paper_sharpe_policy if type(methodology.paper_sharpe_policy) is str else "",
        "mtm_policy_id": methodology.mtm_policy_id if type(methodology.mtm_policy_id) is str else "",
        "fee_policy_id": methodology.fee_policy_id if type(methodology.fee_policy_id) is str else "",
        "funding_policy_id": methodology.funding_policy_id if type(methodology.funding_policy_id) is str else "",
        "mark_policy_id": methodology.mark_policy_id if type(methodology.mark_policy_id) is str else "",
        "exposure_policy_id": methodology.exposure_policy_id if type(methodology.exposure_policy_id) is str else "",
        "liquidation_policy_id": methodology.liquidation_policy_id
        if type(methodology.liquidation_policy_id) is str
        else "",
        "risk_free_policy_id": methodology.risk_free_policy_id if type(methodology.risk_free_policy_id) is str else "",
        "timestamp_policy": time_window.timestamp_policy if type(time_window.timestamp_policy) is str else "",
        "started_at_ns": time_window.started_at_ns if _is_exact_int(time_window.started_at_ns) else 0,
        "stopped_at_ns": time_window.stopped_at_ns if _is_exact_int(time_window.stopped_at_ns) else 0,
        "window_duration_ns": time_window.window_duration_ns if _is_exact_int(time_window.window_duration_ns) else 0,
        "sample_observation_count": time_window.sample_observation_count
        if _is_exact_int(time_window.sample_observation_count)
        else 0,
        "sample_eligible": time_window.sample_eligible if type(time_window.sample_eligible) is bool else False,
        "bucket_count": len(buckets),
        "return_count": return_count,
        "normalized_index_start": first_index,
        "normalized_index_end": last_index,
        "daily_returns": daily_returns,
        "buckets": buckets,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
        "return_series_computed": ready,
        "daily_returns_computed": ready,
    }
    seed = PaperDailyReturnSeriesEvidence(series_digest="", **fields)  # type: ignore[arg-type]
    return _replace_series_digest(seed, paper_daily_return_series_evidence_digest(seed))


def _replace_series_digest(evidence: PaperDailyReturnSeriesEvidence, digest: str) -> PaperDailyReturnSeriesEvidence:
    fields = _series_fields(evidence)
    fields["series_digest"] = digest
    return PaperDailyReturnSeriesEvidence(**fields)  # type: ignore[arg-type]


def _series_fields(evidence: PaperDailyReturnSeriesEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "series_version": evidence.series_version,
        "status": evidence.status,
        "ready": evidence.ready,
        "series_id": evidence.series_id,
        "methodology_id": evidence.methodology_id,
        "window_id": evidence.window_id,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_methodology_digest": evidence.expected_methodology_digest,
        "methodology_digest": evidence.methodology_digest,
        "expected_time_window_digest": evidence.expected_time_window_digest,
        "time_window_digest": evidence.time_window_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "calendar": evidence.calendar,
        "bucket_frequency": evidence.bucket_frequency,
        "bucket_duration_ns": evidence.bucket_duration_ns,
        "required_consecutive_bucket_count": evidence.required_consecutive_bucket_count,
        "duration_sufficiency_assessed": evidence.duration_sufficiency_assessed,
        "sample_sufficiency_assessed": evidence.sample_sufficiency_assessed,
        "return_basis": evidence.return_basis,
        "return_value_kind": evidence.return_value_kind,
        "annualization_policy": evidence.annualization_policy,
        "annualization_factor": evidence.annualization_factor,
        "paper_sharpe_policy": evidence.paper_sharpe_policy,
        "mtm_policy_id": evidence.mtm_policy_id,
        "fee_policy_id": evidence.fee_policy_id,
        "funding_policy_id": evidence.funding_policy_id,
        "mark_policy_id": evidence.mark_policy_id,
        "exposure_policy_id": evidence.exposure_policy_id,
        "liquidation_policy_id": evidence.liquidation_policy_id,
        "risk_free_policy_id": evidence.risk_free_policy_id,
        "timestamp_policy": evidence.timestamp_policy,
        "started_at_ns": evidence.started_at_ns,
        "stopped_at_ns": evidence.stopped_at_ns,
        "window_duration_ns": evidence.window_duration_ns,
        "sample_observation_count": evidence.sample_observation_count,
        "sample_eligible": evidence.sample_eligible,
        "bucket_count": evidence.bucket_count,
        "return_count": evidence.return_count,
        "normalized_index_start": evidence.normalized_index_start,
        "normalized_index_end": evidence.normalized_index_end,
        "daily_returns": evidence.daily_returns,
        "buckets": evidence.buckets,
        "reason_codes": evidence.reason_codes,
        "metadata": evidence.metadata,
        "return_series_computed": evidence.return_series_computed,
        "daily_returns_computed": evidence.daily_returns_computed,
    }


def _series_payload_from(evidence: PaperDailyReturnSeriesEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "series_version": evidence.series_version,
        "status": evidence.status.value,
        "ready": evidence.ready,
        "series_id": evidence.series_id,
        "methodology_id": evidence.methodology_id,
        "window_id": evidence.window_id,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_methodology_digest": evidence.expected_methodology_digest,
        "methodology_digest": evidence.methodology_digest,
        "expected_time_window_digest": evidence.expected_time_window_digest,
        "time_window_digest": evidence.time_window_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "calendar": evidence.calendar,
        "bucket_frequency": evidence.bucket_frequency,
        "bucket_duration_ns": evidence.bucket_duration_ns,
        "required_consecutive_bucket_count": evidence.required_consecutive_bucket_count,
        "duration_sufficiency_assessed": evidence.duration_sufficiency_assessed,
        "sample_sufficiency_assessed": evidence.sample_sufficiency_assessed,
        "return_basis": evidence.return_basis,
        "return_value_kind": evidence.return_value_kind,
        "annualization_policy": evidence.annualization_policy,
        "annualization_factor": evidence.annualization_factor,
        "paper_sharpe_policy": evidence.paper_sharpe_policy,
        "mtm_policy_id": evidence.mtm_policy_id,
        "fee_policy_id": evidence.fee_policy_id,
        "funding_policy_id": evidence.funding_policy_id,
        "mark_policy_id": evidence.mark_policy_id,
        "exposure_policy_id": evidence.exposure_policy_id,
        "liquidation_policy_id": evidence.liquidation_policy_id,
        "risk_free_policy_id": evidence.risk_free_policy_id,
        "timestamp_policy": evidence.timestamp_policy,
        "started_at_ns": evidence.started_at_ns,
        "stopped_at_ns": evidence.stopped_at_ns,
        "window_duration_ns": evidence.window_duration_ns,
        "sample_observation_count": evidence.sample_observation_count,
        "sample_eligible": evidence.sample_eligible,
        "bucket_count": evidence.bucket_count,
        "return_count": evidence.return_count,
        "normalized_index_start": evidence.normalized_index_start,
        "normalized_index_end": evidence.normalized_index_end,
        "daily_returns": list(evidence.daily_returns),
        "buckets": [_serialize_bucket(bucket) for bucket in evidence.buckets],
        "reason_codes": list(evidence.reason_codes),
        "metadata": _serialize_metadata(evidence.metadata),
        "paper_only": evidence.paper_only,
        "daily_return_series_evidence": evidence.daily_return_series_evidence,
        "methodology_snapshot_consumed": evidence.methodology_snapshot_consumed,
        "injected_deterministic_time_window_consumed": evidence.injected_deterministic_time_window_consumed,
        "daily_utc_only": evidence.daily_utc_only,
        "normalized_paper_equity_index": evidence.normalized_paper_equity_index,
        "mark_to_market_required": evidence.mark_to_market_required,
        "realized_only_primary_series": evidence.realized_only_primary_series,
        "real_account_equity_used": evidence.real_account_equity_used,
        "real_capital_used": evidence.real_capital_used,
        "return_series_computed": evidence.return_series_computed,
        "daily_returns_computed": evidence.daily_returns_computed,
        "sharpe_computed": evidence.sharpe_computed,
        "paper_sharpe_computed": evidence.paper_sharpe_computed,
        "thirty_day_gate_satisfied": evidence.thirty_day_gate_satisfied,
        "thirty_day_gate_decided": evidence.thirty_day_gate_decided,
        "comparison_ready": evidence.comparison_ready,
        "stage4_comparator_invoked": evidence.stage4_comparator_invoked,
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
        "timestamp_origin_proven": evidence.timestamp_origin_proven,
    }


def paper_daily_return_series_evidence_to_dict(evidence: PaperDailyReturnSeriesEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for the daily return-series evidence, including its self-digest."""

    payload = _series_payload_from(evidence)
    payload["series_digest"] = evidence.series_digest
    return payload


def paper_daily_return_series_evidence_digest(evidence: PaperDailyReturnSeriesEvidence) -> str:
    """Recompute the canonical series digest, excluding the self-digest field."""

    return _canonical_digest(_series_payload_from(evidence))


__all__ = [
    "PaperDailyReturnBucket",
    "PaperDailyReturnSeriesEvidence",
    "PaperDailyReturnSeriesEvidenceError",
    "PaperDailyReturnSeriesEvidenceStatus",
    "build_paper_daily_return_series_evidence",
    "paper_daily_return_series_evidence_digest",
    "paper_daily_return_series_evidence_to_dict",
]
