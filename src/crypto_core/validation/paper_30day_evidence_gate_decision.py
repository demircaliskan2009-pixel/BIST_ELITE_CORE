"""Paper 30-day evidence gate decision.

This validation artifact consumes a proven ``PaperDailyReturnSeriesEvidence`` and decides only whether the
deterministic paper daily return-series evidence satisfies the minimum ``>=30`` consecutive UTC daily-bucket
input gate (PRDV4 "Stage 4: Paper Trading" requires "Minimum 30 days"; the phase map scopes a ">=30-day"
gate). A longer valid contiguous window (31+ days) also satisfies the gate; the decision is taken over the
first 30 consecutive UTC daily buckets. The exact upstream container shapes (``buckets`` / ``daily_returns``
must be exact tuples of exact element types) are proven before any counting/indexing, so a forged exact-typed
upstream fails closed with a deterministic reason code rather than a raw ``TypeError`` or a silent collapse.
It is paper-only, deterministic, digest-bound, and fail-closed.

It does not compute Sharpe, does not invoke the Stage-4 comparator, does not construct ``Stage4PaperSummary``,
and does not prove profitability, edge, live readiness, shadow readiness, Deribit readiness, execution,
orders, capital, margin, balance, or scheduler behavior.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnBucket,
    PaperDailyReturnSeriesEvidence,
    PaperDailyReturnSeriesEvidenceStatus,
    paper_daily_return_series_evidence_digest,
)

_SCHEMA_VERSION = "paper-30day-evidence-gate-decision.v1"
_DECISION_VERSION = "paper-30day-evidence-gate-decision.v1"
_EXPECTED_SERIES_SCHEMA_VERSION = "paper-daily-return-series-evidence.v1"
_CALENDAR = "UTC"
_BUCKET_FREQUENCY = "1d_utc"
_BUCKET_DURATION_NS = 86_400_000_000_000
# Minimum (not exact) consecutive UTC daily buckets/returns required to satisfy the gate. PRDV4 §"Stage 4: Paper
# Trading" requires "Minimum 30 days" and the phase map (§10.4) scopes this as a deterministic ">=30-day" gate, so
# longer valid windows (31+ days) satisfy the gate; the decision is taken over the first 30 consecutive buckets.
_REQUIRED_CONSECUTIVE_BUCKET_COUNT = 30
_RETURN_BASIS = "normalized_paper_equity_index"
_RETURN_VALUE_KIND = "unitless_decimal_return"
_ANNUALIZATION_POLICY = "daily_utc_365_review_only"
_PAPER_SHARPE_POLICY = "deferred_not_computed"
_TIMESTAMP_POLICY = "injected_deterministic_ns.v1"

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


class PaperThirtyDayEvidenceGateDecisionError(RuntimeError):
    """Raised on malformed caller input or forbidden scope tokens."""


class PaperThirtyDayEvidenceGateDecisionStatus(str, Enum):
    """30-day evidence gate status. READY is evidence sufficiency only, not Stage-4 readiness."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperThirtyDayEvidenceGateDecision:
    """Immutable, digest-bound 30-day paper evidence gate decision."""

    schema_version: str
    decision_version: str
    status: PaperThirtyDayEvidenceGateDecisionStatus
    ready: bool
    gate_id: str
    series_id: str
    methodology_id: str
    window_id: str
    correlation_id: str
    market_symbol: str
    expected_series_digest: str
    series_digest: str
    methodology_digest: str
    time_window_digest: str
    metrics_summary_digest: str
    calendar: str
    bucket_frequency: str
    bucket_duration_ns: int
    required_consecutive_bucket_count: int
    bucket_count: int
    daily_return_count: int
    gate_minimum_consecutive_bucket_count: int
    gate_bucket_count_used: int
    gate_daily_return_count_used: int
    gate_used_first_bucket_id: str
    gate_used_last_bucket_id: str
    gate_used_first_bucket_start_ns: int
    gate_used_last_bucket_end_ns: int
    bucket_ids: tuple[str, ...]
    bucket_digests: tuple[str, ...]
    daily_returns: tuple[str, ...]
    first_bucket_id: str
    last_bucket_id: str
    first_bucket_start_ns: int
    last_bucket_end_ns: int
    window_duration_ns: int
    normalized_index_start: str
    normalized_index_end: str
    return_basis: str
    return_value_kind: str
    mtm_policy_id: str
    fee_policy_id: str
    funding_policy_id: str
    mark_policy_id: str
    exposure_policy_id: str
    liquidation_policy_id: str
    risk_free_policy_id: str
    timestamp_policy: str
    thirty_day_gate_satisfied: bool
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    decision_digest: str
    paper_only: bool = True
    daily_return_series_evidence_consumed: bool = True
    thirty_day_evidence_gate_decision: bool = True
    thirty_day_gate_decided: bool = True
    sharpe_computed: bool = False
    paper_sharpe_computed: bool = False
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


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:metadata_malformed")
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:metadata_malformed")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:metadata_malformed")
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


def _container_shape_failures(daily_return_series: PaperDailyReturnSeriesEvidence) -> list[str]:
    """Prove the exact upstream container shapes BEFORE any ``len`` / iteration / indexing / payload extraction.

    A forged-but-exact-typed ``PaperDailyReturnSeriesEvidence`` may carry a non-tuple ``buckets`` (e.g. ``None``
    or a ``list``) or a non-tuple ``daily_returns``; the digest boundary alone does not distinguish a ``tuple``
    from an equal-content ``list``. These must fail closed with a deterministic reason code (never a raw
    ``TypeError`` and never a silent collapse to an empty tuple under a READY decision).
    """
    hard: list[str] = []
    buckets = daily_return_series.buckets
    if type(buckets) is not tuple:
        hard.append("paper_30day_evidence_gate_decision:buckets_container_malformed")
    elif not all(type(bucket) is PaperDailyReturnBucket for bucket in buckets):
        hard.append("paper_30day_evidence_gate_decision:bucket_type_malformed")
    daily_returns = daily_return_series.daily_returns
    if type(daily_returns) is not tuple:
        hard.append("paper_30day_evidence_gate_decision:daily_returns_container_malformed")
    elif not all(type(daily_return) is str for daily_return in daily_returns):
        hard.append("paper_30day_evidence_gate_decision:daily_return_malformed")
    return hard


def _buckets_are_exact_tuple(daily_return_series: PaperDailyReturnSeriesEvidence) -> bool:
    buckets = daily_return_series.buckets
    return type(buckets) is tuple and all(type(bucket) is PaperDailyReturnBucket for bucket in buckets)


def _series_hard_failures(
    daily_return_series: PaperDailyReturnSeriesEvidence, expected_series_digest: str
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
        or daily_return_series.series_digest != expected_series_digest
    ):
        hard.append("paper_30day_evidence_gate_decision:series_digest_mismatch")

    if daily_return_series.schema_version != _EXPECTED_SERIES_SCHEMA_VERSION:
        hard.append("paper_30day_evidence_gate_decision:series_schema_invalid")
    if (
        daily_return_series.status is not PaperDailyReturnSeriesEvidenceStatus.READY
        or daily_return_series.ready is not True
        or daily_return_series.reason_codes != ()
    ):
        hard.append("paper_30day_evidence_gate_decision:series_not_ready")

    expected_values = {
        "calendar": _CALENDAR,
        "bucket_frequency": _BUCKET_FREQUENCY,
        "bucket_duration_ns": _BUCKET_DURATION_NS,
        "required_consecutive_bucket_count": _REQUIRED_CONSECUTIVE_BUCKET_COUNT,
        "return_basis": _RETURN_BASIS,
        "return_value_kind": _RETURN_VALUE_KIND,
        "annualization_policy": _ANNUALIZATION_POLICY,
        "paper_sharpe_policy": _PAPER_SHARPE_POLICY,
        "timestamp_policy": _TIMESTAMP_POLICY,
    }
    for field_name, expected in expected_values.items():
        if getattr(daily_return_series, field_name) != expected:
            hard.append(f"paper_30day_evidence_gate_decision:series_{field_name}_mismatch")

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
        hard.append("paper_30day_evidence_gate_decision:series_unsafe_flags")

    if (
        not _is_exact_int(daily_return_series.started_at_ns)
        or not _is_exact_int(daily_return_series.stopped_at_ns)
        or not _is_exact_int(daily_return_series.window_duration_ns)
        or daily_return_series.started_at_ns < 0
        or daily_return_series.stopped_at_ns <= daily_return_series.started_at_ns
        or daily_return_series.window_duration_ns
        != daily_return_series.stopped_at_ns - daily_return_series.started_at_ns
    ):
        hard.append("paper_30day_evidence_gate_decision:series_window_bounds_invalid")
    if daily_return_series.started_at_ns % _BUCKET_DURATION_NS != 0:
        hard.append("paper_30day_evidence_gate_decision:series_window_utc_alignment_invalid")
    if daily_return_series.stopped_at_ns % _BUCKET_DURATION_NS != 0:
        hard.append("paper_30day_evidence_gate_decision:series_window_utc_alignment_invalid")

    if (
        not _is_exact_int(daily_return_series.sample_observation_count)
        or daily_return_series.sample_observation_count < 1
    ):
        hard.append("paper_30day_evidence_gate_decision:series_sample_count_invalid")
    # Minimum (>=30), not exact: a longer valid contiguous UTC daily window also satisfies the gate.
    if (
        not _is_exact_int(daily_return_series.bucket_count)
        or daily_return_series.bucket_count < _REQUIRED_CONSECUTIVE_BUCKET_COUNT
    ):
        hard.append("paper_30day_evidence_gate_decision:insufficient_bucket_count")
    if (
        not _is_exact_int(daily_return_series.return_count)
        or daily_return_series.return_count < _REQUIRED_CONSECUTIVE_BUCKET_COUNT
    ):
        hard.append("paper_30day_evidence_gate_decision:insufficient_daily_return_count")
    # Count-vs-container coherence: only meaningful once the containers are exact tuples (shape is proven
    # separately by ``_container_shape_failures``); guard so a malformed container never raises here.
    if (
        type(daily_return_series.buckets) is tuple
        and len(daily_return_series.buckets) != daily_return_series.bucket_count
    ):
        hard.append("paper_30day_evidence_gate_decision:bucket_count_mismatch")
    if (
        type(daily_return_series.daily_returns) is tuple
        and len(daily_return_series.daily_returns) != daily_return_series.return_count
    ):
        hard.append("paper_30day_evidence_gate_decision:daily_return_count_mismatch")
    # The whole evidence window must be exactly ``bucket_count`` contiguous UTC days (not pinned to 30).
    if (
        not _is_exact_int(daily_return_series.bucket_count)
        or daily_return_series.window_duration_ns != daily_return_series.bucket_count * _BUCKET_DURATION_NS
    ):
        hard.append("paper_30day_evidence_gate_decision:window_duration_mismatch")

    policy_fields = (
        daily_return_series.series_id,
        daily_return_series.methodology_id,
        daily_return_series.window_id,
        daily_return_series.correlation_id,
        daily_return_series.market_symbol,
        daily_return_series.mtm_policy_id,
        daily_return_series.fee_policy_id,
        daily_return_series.funding_policy_id,
        daily_return_series.mark_policy_id,
        daily_return_series.exposure_policy_id,
        daily_return_series.liquidation_policy_id,
        daily_return_series.risk_free_policy_id,
    )
    if not all(_is_plain_non_empty_string(value) for value in policy_fields):
        hard.append("paper_30day_evidence_gate_decision:series_identity_or_policy_invalid")
    elif _has_scope_violation(*policy_fields) or _has_clock_token(*policy_fields):
        hard.append("paper_30day_evidence_gate_decision:series_scope_violation")

    if (
        not _is_hex64_string(daily_return_series.methodology_digest)
        or not _is_hex64_string(daily_return_series.time_window_digest)
        or not _is_hex64_string(daily_return_series.metrics_summary_digest)
    ):
        hard.append("paper_30day_evidence_gate_decision:upstream_digest_anchor_invalid")
    return sorted(set(hard))


def _bucket_hard_failures(daily_return_series: PaperDailyReturnSeriesEvidence) -> list[str]:
    hard: list[str] = []
    buckets = daily_return_series.buckets
    seen_ids: set[str] = set()
    seen_digests: set[str] = set()
    for index, bucket in enumerate(buckets):
        if type(bucket) is not PaperDailyReturnBucket:
            hard.append("paper_30day_evidence_gate_decision:bucket_malformed")
            continue
        if not _is_plain_non_empty_string(bucket.bucket_id):
            hard.append("paper_30day_evidence_gate_decision:bucket_id_invalid")
        elif bucket.bucket_id in seen_ids:
            hard.append("paper_30day_evidence_gate_decision:duplicate_bucket_id")
        else:
            seen_ids.add(bucket.bucket_id)
        if _has_scope_violation(bucket.bucket_id) or _has_clock_token(bucket.bucket_id):
            hard.append("paper_30day_evidence_gate_decision:bucket_id_scope_violation")
        if not _is_hex64_string(bucket.bucket_digest):
            hard.append("paper_30day_evidence_gate_decision:bucket_digest_invalid")
        else:
            if bucket.bucket_digest in seen_digests:
                hard.append("paper_30day_evidence_gate_decision:duplicate_bucket_digest")
            seen_digests.add(bucket.bucket_digest)
            if _bucket_digest(bucket) != bucket.bucket_digest:
                hard.append("paper_30day_evidence_gate_decision:bucket_digest_mismatch")
        if (
            not _is_exact_int(bucket.bucket_start_ns)
            or not _is_exact_int(bucket.bucket_end_ns)
            or bucket.bucket_start_ns < 0
            or bucket.bucket_end_ns <= bucket.bucket_start_ns
        ):
            hard.append("paper_30day_evidence_gate_decision:bucket_bounds_invalid")
            continue
        if bucket.bucket_end_ns - bucket.bucket_start_ns != _BUCKET_DURATION_NS:
            hard.append("paper_30day_evidence_gate_decision:bucket_duration_invalid")
        if bucket.bucket_start_ns % _BUCKET_DURATION_NS != 0 or bucket.bucket_end_ns % _BUCKET_DURATION_NS != 0:
            hard.append("paper_30day_evidence_gate_decision:bucket_utc_day_alignment_invalid")
        if index > 0 and type(buckets[index - 1]) is PaperDailyReturnBucket:
            if bucket.bucket_start_ns != buckets[index - 1].bucket_end_ns:
                hard.append("paper_30day_evidence_gate_decision:bucket_sequence_non_contiguous")
            if bucket.normalized_index_start != buckets[index - 1].normalized_index_end:
                hard.append("paper_30day_evidence_gate_decision:normalized_index_chain_mismatch")
        if not _is_canonical_decimal_string(bucket.normalized_index_start) or not _is_canonical_decimal_string(
            bucket.normalized_index_end
        ):
            hard.append("paper_30day_evidence_gate_decision:bucket_index_noncanonical")
    if buckets and type(buckets[0]) is PaperDailyReturnBucket:
        if buckets[0].bucket_start_ns != daily_return_series.started_at_ns:
            hard.append("paper_30day_evidence_gate_decision:bucket_window_start_mismatch")
        if buckets[0].normalized_index_start != daily_return_series.normalized_index_start:
            hard.append("paper_30day_evidence_gate_decision:normalized_index_start_mismatch")
    if buckets and type(buckets[-1]) is PaperDailyReturnBucket:
        if buckets[-1].bucket_end_ns != daily_return_series.stopped_at_ns:
            hard.append("paper_30day_evidence_gate_decision:bucket_window_end_mismatch")
        if buckets[-1].normalized_index_end != daily_return_series.normalized_index_end:
            hard.append("paper_30day_evidence_gate_decision:normalized_index_end_mismatch")
    if type(daily_return_series.daily_returns) is tuple:
        for daily_return in daily_return_series.daily_returns:
            if not _is_canonical_decimal_string(daily_return):
                hard.append("paper_30day_evidence_gate_decision:daily_return_noncanonical")
                break
    return sorted(set(hard))


def build_paper_30day_evidence_gate_decision(
    daily_return_series: PaperDailyReturnSeriesEvidence,
    *,
    expected_series_digest: str,
    gate_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperThirtyDayEvidenceGateDecision:
    """Decide whether a proven paper daily return series satisfies the deterministic 30-day input gate."""

    if type(daily_return_series) is not PaperDailyReturnSeriesEvidence:
        raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:series_malformed")
    if not _is_hex64_string(expected_series_digest):
        raise PaperThirtyDayEvidenceGateDecisionError(
            "paper_30day_evidence_gate_decision:expected_series_digest_invalid"
        )
    if not _is_plain_non_empty_string(gate_id):
        raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:gate_id_invalid")
    if not _is_plain_non_empty_string(correlation_id):
        raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(gate_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:scope_violation")
    if _has_clock_token(gate_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperThirtyDayEvidenceGateDecisionError("paper_30day_evidence_gate_decision:clock_token_forbidden")

    # Prove exact container shapes BEFORE any len/iteration/indexing/payload extraction (fail closed, never a
    # raw TypeError and never a silent collapse under READY). Bucket-level checks run only over an exact tuple of
    # exact buckets; a malformed container is already rejected by the shape failures above.
    hard = [
        *_series_hard_failures(daily_return_series, expected_series_digest),
        *_container_shape_failures(daily_return_series),
    ]
    if _buckets_are_exact_tuple(daily_return_series):
        hard.extend(_bucket_hard_failures(daily_return_series))
    if correlation_id != daily_return_series.correlation_id:
        hard.append("paper_30day_evidence_gate_decision:correlation_id_mismatch")

    # Deterministic decision window = the FIRST 30 consecutive UTC daily buckets of the validated (>=30-day)
    # series. The whole series is structurally validated above; the first 30 are the buckets the gate decision is
    # taken over. On any failure the used-window fields are empty/zero and the gate is not satisfied.
    raw_buckets = daily_return_series.buckets
    buckets = raw_buckets if type(raw_buckets) is tuple else ()
    if hard:
        status = PaperThirtyDayEvidenceGateDecisionStatus.REJECTED
        ready = False
        gate_satisfied = False
        reason_codes = tuple(sorted(set(hard)))
        bucket_count_used = 0
        return_count_used = 0
        used_first_bucket_id = ""
        used_last_bucket_id = ""
        used_first_bucket_start_ns = 0
        used_last_bucket_end_ns = 0
    else:
        status = PaperThirtyDayEvidenceGateDecisionStatus.READY
        ready = True
        gate_satisfied = True
        reason_codes = ()
        bucket_count_used = _REQUIRED_CONSECUTIVE_BUCKET_COUNT
        return_count_used = _REQUIRED_CONSECUTIVE_BUCKET_COUNT
        used_window = buckets[:_REQUIRED_CONSECUTIVE_BUCKET_COUNT]
        used_first_bucket_id = used_window[0].bucket_id
        used_last_bucket_id = used_window[-1].bucket_id
        used_first_bucket_start_ns = used_window[0].bucket_start_ns
        used_last_bucket_end_ns = used_window[-1].bucket_end_ns

    first_bucket = buckets[0] if buckets and type(buckets[0]) is PaperDailyReturnBucket else None
    last_bucket = buckets[-1] if buckets and type(buckets[-1]) is PaperDailyReturnBucket else None
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "decision_version": _DECISION_VERSION,
        "status": status,
        "ready": ready,
        "gate_id": gate_id,
        "series_id": daily_return_series.series_id if type(daily_return_series.series_id) is str else "",
        "methodology_id": daily_return_series.methodology_id if type(daily_return_series.methodology_id) is str else "",
        "window_id": daily_return_series.window_id if type(daily_return_series.window_id) is str else "",
        "correlation_id": correlation_id,
        "market_symbol": daily_return_series.market_symbol if type(daily_return_series.market_symbol) is str else "",
        "expected_series_digest": expected_series_digest,
        "series_digest": daily_return_series.series_digest if type(daily_return_series.series_digest) is str else "",
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
        "bucket_count": daily_return_series.bucket_count if _is_exact_int(daily_return_series.bucket_count) else 0,
        "daily_return_count": daily_return_series.return_count
        if _is_exact_int(daily_return_series.return_count)
        else 0,
        "gate_minimum_consecutive_bucket_count": _REQUIRED_CONSECUTIVE_BUCKET_COUNT,
        "gate_bucket_count_used": bucket_count_used,
        "gate_daily_return_count_used": return_count_used,
        "gate_used_first_bucket_id": used_first_bucket_id,
        "gate_used_last_bucket_id": used_last_bucket_id,
        "gate_used_first_bucket_start_ns": used_first_bucket_start_ns,
        "gate_used_last_bucket_end_ns": used_last_bucket_end_ns,
        "bucket_ids": tuple(bucket.bucket_id for bucket in buckets if type(bucket) is PaperDailyReturnBucket),
        "bucket_digests": tuple(bucket.bucket_digest for bucket in buckets if type(bucket) is PaperDailyReturnBucket),
        "daily_returns": daily_return_series.daily_returns
        if type(daily_return_series.daily_returns) is tuple
        and all(type(daily_return) is str for daily_return in daily_return_series.daily_returns)
        else (),
        "first_bucket_id": first_bucket.bucket_id if first_bucket is not None else "",
        "last_bucket_id": last_bucket.bucket_id if last_bucket is not None else "",
        "first_bucket_start_ns": first_bucket.bucket_start_ns if first_bucket is not None else 0,
        "last_bucket_end_ns": last_bucket.bucket_end_ns if last_bucket is not None else 0,
        "window_duration_ns": daily_return_series.window_duration_ns
        if _is_exact_int(daily_return_series.window_duration_ns)
        else 0,
        "normalized_index_start": daily_return_series.normalized_index_start
        if type(daily_return_series.normalized_index_start) is str
        else "",
        "normalized_index_end": daily_return_series.normalized_index_end
        if type(daily_return_series.normalized_index_end) is str
        else "",
        "return_basis": daily_return_series.return_basis if type(daily_return_series.return_basis) is str else "",
        "return_value_kind": daily_return_series.return_value_kind
        if type(daily_return_series.return_value_kind) is str
        else "",
        "mtm_policy_id": daily_return_series.mtm_policy_id if type(daily_return_series.mtm_policy_id) is str else "",
        "fee_policy_id": daily_return_series.fee_policy_id if type(daily_return_series.fee_policy_id) is str else "",
        "funding_policy_id": daily_return_series.funding_policy_id
        if type(daily_return_series.funding_policy_id) is str
        else "",
        "mark_policy_id": daily_return_series.mark_policy_id if type(daily_return_series.mark_policy_id) is str else "",
        "exposure_policy_id": daily_return_series.exposure_policy_id
        if type(daily_return_series.exposure_policy_id) is str
        else "",
        "liquidation_policy_id": daily_return_series.liquidation_policy_id
        if type(daily_return_series.liquidation_policy_id) is str
        else "",
        "risk_free_policy_id": daily_return_series.risk_free_policy_id
        if type(daily_return_series.risk_free_policy_id) is str
        else "",
        "timestamp_policy": daily_return_series.timestamp_policy
        if type(daily_return_series.timestamp_policy) is str
        else "",
        "thirty_day_gate_satisfied": gate_satisfied,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperThirtyDayEvidenceGateDecision(decision_digest="", **fields)  # type: ignore[arg-type]
    return _replace_decision_digest(seed, paper_30day_evidence_gate_decision_digest(seed))


def _replace_decision_digest(
    decision: PaperThirtyDayEvidenceGateDecision, digest: str
) -> PaperThirtyDayEvidenceGateDecision:
    fields = _decision_fields(decision)
    fields["decision_digest"] = digest
    return PaperThirtyDayEvidenceGateDecision(**fields)  # type: ignore[arg-type]


def _decision_fields(decision: PaperThirtyDayEvidenceGateDecision) -> dict[str, object]:
    return {
        "schema_version": decision.schema_version,
        "decision_version": decision.decision_version,
        "status": decision.status,
        "ready": decision.ready,
        "gate_id": decision.gate_id,
        "series_id": decision.series_id,
        "methodology_id": decision.methodology_id,
        "window_id": decision.window_id,
        "correlation_id": decision.correlation_id,
        "market_symbol": decision.market_symbol,
        "expected_series_digest": decision.expected_series_digest,
        "series_digest": decision.series_digest,
        "methodology_digest": decision.methodology_digest,
        "time_window_digest": decision.time_window_digest,
        "metrics_summary_digest": decision.metrics_summary_digest,
        "calendar": decision.calendar,
        "bucket_frequency": decision.bucket_frequency,
        "bucket_duration_ns": decision.bucket_duration_ns,
        "required_consecutive_bucket_count": decision.required_consecutive_bucket_count,
        "bucket_count": decision.bucket_count,
        "daily_return_count": decision.daily_return_count,
        "gate_minimum_consecutive_bucket_count": decision.gate_minimum_consecutive_bucket_count,
        "gate_bucket_count_used": decision.gate_bucket_count_used,
        "gate_daily_return_count_used": decision.gate_daily_return_count_used,
        "gate_used_first_bucket_id": decision.gate_used_first_bucket_id,
        "gate_used_last_bucket_id": decision.gate_used_last_bucket_id,
        "gate_used_first_bucket_start_ns": decision.gate_used_first_bucket_start_ns,
        "gate_used_last_bucket_end_ns": decision.gate_used_last_bucket_end_ns,
        "bucket_ids": decision.bucket_ids,
        "bucket_digests": decision.bucket_digests,
        "daily_returns": decision.daily_returns,
        "first_bucket_id": decision.first_bucket_id,
        "last_bucket_id": decision.last_bucket_id,
        "first_bucket_start_ns": decision.first_bucket_start_ns,
        "last_bucket_end_ns": decision.last_bucket_end_ns,
        "window_duration_ns": decision.window_duration_ns,
        "normalized_index_start": decision.normalized_index_start,
        "normalized_index_end": decision.normalized_index_end,
        "return_basis": decision.return_basis,
        "return_value_kind": decision.return_value_kind,
        "mtm_policy_id": decision.mtm_policy_id,
        "fee_policy_id": decision.fee_policy_id,
        "funding_policy_id": decision.funding_policy_id,
        "mark_policy_id": decision.mark_policy_id,
        "exposure_policy_id": decision.exposure_policy_id,
        "liquidation_policy_id": decision.liquidation_policy_id,
        "risk_free_policy_id": decision.risk_free_policy_id,
        "timestamp_policy": decision.timestamp_policy,
        "thirty_day_gate_satisfied": decision.thirty_day_gate_satisfied,
        "reason_codes": decision.reason_codes,
        "metadata": decision.metadata,
    }


def _decision_payload_from(decision: PaperThirtyDayEvidenceGateDecision) -> dict[str, object]:
    return {
        "schema_version": decision.schema_version,
        "decision_version": decision.decision_version,
        "status": decision.status.value,
        "ready": decision.ready,
        "gate_id": decision.gate_id,
        "series_id": decision.series_id,
        "methodology_id": decision.methodology_id,
        "window_id": decision.window_id,
        "correlation_id": decision.correlation_id,
        "market_symbol": decision.market_symbol,
        "expected_series_digest": decision.expected_series_digest,
        "series_digest": decision.series_digest,
        "methodology_digest": decision.methodology_digest,
        "time_window_digest": decision.time_window_digest,
        "metrics_summary_digest": decision.metrics_summary_digest,
        "calendar": decision.calendar,
        "bucket_frequency": decision.bucket_frequency,
        "bucket_duration_ns": decision.bucket_duration_ns,
        "required_consecutive_bucket_count": decision.required_consecutive_bucket_count,
        "bucket_count": decision.bucket_count,
        "daily_return_count": decision.daily_return_count,
        "gate_minimum_consecutive_bucket_count": decision.gate_minimum_consecutive_bucket_count,
        "gate_bucket_count_used": decision.gate_bucket_count_used,
        "gate_daily_return_count_used": decision.gate_daily_return_count_used,
        "gate_used_first_bucket_id": decision.gate_used_first_bucket_id,
        "gate_used_last_bucket_id": decision.gate_used_last_bucket_id,
        "gate_used_first_bucket_start_ns": decision.gate_used_first_bucket_start_ns,
        "gate_used_last_bucket_end_ns": decision.gate_used_last_bucket_end_ns,
        "bucket_ids": list(decision.bucket_ids),
        "bucket_digests": list(decision.bucket_digests),
        "daily_returns": list(decision.daily_returns),
        "first_bucket_id": decision.first_bucket_id,
        "last_bucket_id": decision.last_bucket_id,
        "first_bucket_start_ns": decision.first_bucket_start_ns,
        "last_bucket_end_ns": decision.last_bucket_end_ns,
        "window_duration_ns": decision.window_duration_ns,
        "normalized_index_start": decision.normalized_index_start,
        "normalized_index_end": decision.normalized_index_end,
        "return_basis": decision.return_basis,
        "return_value_kind": decision.return_value_kind,
        "mtm_policy_id": decision.mtm_policy_id,
        "fee_policy_id": decision.fee_policy_id,
        "funding_policy_id": decision.funding_policy_id,
        "mark_policy_id": decision.mark_policy_id,
        "exposure_policy_id": decision.exposure_policy_id,
        "liquidation_policy_id": decision.liquidation_policy_id,
        "risk_free_policy_id": decision.risk_free_policy_id,
        "timestamp_policy": decision.timestamp_policy,
        "thirty_day_gate_satisfied": decision.thirty_day_gate_satisfied,
        "reason_codes": list(decision.reason_codes),
        "metadata": _serialize_metadata(decision.metadata),
        "paper_only": decision.paper_only,
        "daily_return_series_evidence_consumed": decision.daily_return_series_evidence_consumed,
        "thirty_day_evidence_gate_decision": decision.thirty_day_evidence_gate_decision,
        "thirty_day_gate_decided": decision.thirty_day_gate_decided,
        "sharpe_computed": decision.sharpe_computed,
        "paper_sharpe_computed": decision.paper_sharpe_computed,
        "comparison_ready": decision.comparison_ready,
        "stage4_comparator_invoked": decision.stage4_comparator_invoked,
        "prdv4_stage4_complete": decision.prdv4_stage4_complete,
        "live_ready": decision.live_ready,
        "shadow_ready": decision.shadow_ready,
        "operational_readiness": decision.operational_readiness,
        "deribit_ready": decision.deribit_ready,
        "profitability_proven": decision.profitability_proven,
        "edge_proven": decision.edge_proven,
        "production_execution": decision.production_execution,
        "real_orders_enabled": decision.real_orders_enabled,
        "real_money_enabled": decision.real_money_enabled,
        "real_capital_reserved": decision.real_capital_reserved,
        "live_api_called": decision.live_api_called,
        "scheduler_enabled": decision.scheduler_enabled,
        "auto_loop_enabled": decision.auto_loop_enabled,
        "connector_invoked": decision.connector_invoked,
        "real_wall_clock_used": decision.real_wall_clock_used,
        "real_account_equity_used": decision.real_account_equity_used,
        "real_capital_used": decision.real_capital_used,
    }


def paper_30day_evidence_gate_decision_to_dict(
    decision: PaperThirtyDayEvidenceGateDecision,
) -> dict[str, object]:
    """Canonical JSON-ready mapping for the 30-day evidence gate decision, including its self-digest."""

    payload = _decision_payload_from(decision)
    payload["decision_digest"] = decision.decision_digest
    return payload


def paper_30day_evidence_gate_decision_digest(decision: PaperThirtyDayEvidenceGateDecision) -> str:
    """Recompute the canonical decision digest, excluding only the self-digest field."""

    return _canonical_digest(_decision_payload_from(decision))


__all__ = [
    "PaperThirtyDayEvidenceGateDecision",
    "PaperThirtyDayEvidenceGateDecisionError",
    "PaperThirtyDayEvidenceGateDecisionStatus",
    "build_paper_30day_evidence_gate_decision",
    "paper_30day_evidence_gate_decision_digest",
    "paper_30day_evidence_gate_decision_to_dict",
]
