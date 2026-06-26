"""Paper return-series methodology snapshot.

This module defines the deterministic methodology evidence required before a later paper daily return-series
artifact can exist. It is methodology-only: it computes no returns, no Sharpe, no 30-day gate decision, no
Stage-4 comparator input, and no live/shadow/readiness state. The artifact is paper-only, immutable,
digest-bound, and intentionally carries explicit policy identifiers for mark-to-market, fees, funding, marks,
exposure, liquidation, and risk-free assumptions so later consumers can fail closed when any policy evidence is
missing or mismatched.

The snapshot uses 30 consecutive UTC calendar-day buckets for the later crypto 24/7 paper return-series path.
Timestamps and buckets are injected/deterministic data for later slices; this module imports no clock, runtime,
service, execution, venue, scheduler, or filesystem surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

_SCHEMA_VERSION = "paper-return-series-methodology.v1"
_METHODOLOGY_VERSION = "paper-return-series-methodology.v1"
_CALENDAR = "UTC"
_BUCKET_FREQUENCY = "1d_utc"
_BUCKET_DURATION_NS = 86_400_000_000_000
_REQUIRED_CONSECUTIVE_BUCKET_COUNT = 30
_RETURN_BASIS = "normalized_paper_equity_index"
_RETURN_VALUE_KIND = "unitless_decimal_return"
_NORMALIZED_INDEX_START = "1"
_MARK_TO_MARKET_REQUIRED = True
_REALIZED_ONLY_PRIMARY_SERIES = False
_ANNUALIZATION_POLICY = "daily_utc_365_review_only"
_ANNUALIZATION_FACTOR = 365
_PAPER_SHARPE_POLICY = "deferred_not_computed"
_MISSING_POLICY_INPUT_STATUS = "BLOCKED"
_SPARSE_WINDOW_STATUS = "BLOCKED"
_INSUFFICIENT_SAMPLE_STATUS = "BLOCKED"
_NO_TRADE_STATUS = "NOT_COMPUTABLE"
_ZERO_VARIANCE_STATUS = "NOT_COMPUTABLE"
_METHODOLOGY_MISMATCH_STATUS = "BLOCKED"

_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
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


class PaperReturnSeriesMethodologyError(RuntimeError):
    """Raised on malformed methodology inputs or forbidden scope tokens."""


class PaperReturnSeriesMethodologyStatus(str, Enum):
    """Methodology snapshot build status. READY is not a return-series, Sharpe, or gate verdict."""

    READY = "READY"


@dataclass(frozen=True)
class PaperReturnSeriesMethodology:
    """Immutable methodology snapshot for later deterministic paper daily return-series evidence."""

    schema_version: str
    methodology_version: str
    status: PaperReturnSeriesMethodologyStatus
    ready: bool
    methodology_id: str
    correlation_id: str
    calendar: str
    bucket_frequency: str
    bucket_duration_ns: int
    required_consecutive_bucket_count: int
    duration_sufficiency_assessed: bool
    sample_sufficiency_assessed: bool
    return_basis: str
    return_value_kind: str
    normalized_index_start: str
    mark_to_market_required: bool
    realized_only_primary_series: bool
    mtm_policy_id: str
    fee_policy_id: str
    funding_policy_id: str
    mark_policy_id: str
    exposure_policy_id: str
    liquidation_policy_id: str
    risk_free_policy_id: str
    fee_policy_required: bool
    funding_policy_required: bool
    mark_policy_required: bool
    exposure_policy_required: bool
    liquidation_policy_required: bool
    missing_policy_input_status: str
    sparse_window_status: str
    insufficient_sample_status: str
    no_trade_status: str
    zero_variance_status: str
    methodology_mismatch_status: str
    annualization_policy: str
    annualization_factor: int
    paper_sharpe_policy: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    methodology_digest: str
    paper_only: bool = True
    methodology_snapshot: bool = True
    daily_utc_only: bool = True
    normalized_paper_equity_index: bool = True
    real_account_equity_used: bool = False
    real_capital_used: bool = False
    return_series_computed: bool = False
    daily_returns_computed: bool = False
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


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value.strip() == ""
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise PaperReturnSeriesMethodologyError(f"paper_return_series_methodology:{field_name}_invalid")
    return value


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperReturnSeriesMethodologyError("paper_return_series_methodology:metadata_malformed")
    pairs: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperReturnSeriesMethodologyError("paper_return_series_methodology:metadata_malformed")
        pairs.append((key, value))
    return tuple(sorted(pairs))


def _normalize_reason_codes(reason_codes: object) -> tuple[str, ...]:
    if reason_codes is None:
        return ()
    if type(reason_codes) not in (tuple, list):
        raise PaperReturnSeriesMethodologyError("paper_return_series_methodology:reason_codes_malformed")
    values: list[str] = []
    for code in reason_codes:
        if type(code) is not str or code.strip() == "":
            raise PaperReturnSeriesMethodologyError("paper_return_series_methodology:reason_codes_malformed")
        values.append(code)
    return tuple(sorted(set(values)))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


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


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperReturnSeriesMethodologyError("paper_return_series_methodology:metadata_malformed")
        pairs.append([pair[0], pair[1]])
    return pairs


def build_paper_return_series_methodology(
    *,
    methodology_id: str,
    correlation_id: str,
    mtm_policy_id: str,
    fee_policy_id: str,
    funding_policy_id: str,
    mark_policy_id: str,
    exposure_policy_id: str,
    liquidation_policy_id: str,
    risk_free_policy_id: str,
    metadata: Mapping[str, str] | None = None,
    reason_codes: tuple[str, ...] | list[str] = (),
) -> PaperReturnSeriesMethodology:
    """Build a deterministic methodology-only snapshot for later paper daily return-series evidence."""

    methodology_id = _require_plain_non_empty_string(methodology_id, "methodology_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    policy_ids = (
        _require_plain_non_empty_string(mtm_policy_id, "mtm_policy_id"),
        _require_plain_non_empty_string(fee_policy_id, "fee_policy_id"),
        _require_plain_non_empty_string(funding_policy_id, "funding_policy_id"),
        _require_plain_non_empty_string(mark_policy_id, "mark_policy_id"),
        _require_plain_non_empty_string(exposure_policy_id, "exposure_policy_id"),
        _require_plain_non_empty_string(liquidation_policy_id, "liquidation_policy_id"),
        _require_plain_non_empty_string(risk_free_policy_id, "risk_free_policy_id"),
    )
    metadata_pairs = _normalize_metadata(metadata)
    reason_code_values = _normalize_reason_codes(reason_codes)
    scope_texts = (methodology_id, correlation_id, *policy_ids, *reason_code_values, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperReturnSeriesMethodologyError("paper_return_series_methodology:scope_violation")
    if _has_clock_token(*scope_texts):
        raise PaperReturnSeriesMethodologyError("paper_return_series_methodology:clock_token_forbidden")

    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "methodology_version": _METHODOLOGY_VERSION,
        "status": PaperReturnSeriesMethodologyStatus.READY,
        "ready": True,
        "methodology_id": methodology_id,
        "correlation_id": correlation_id,
        "calendar": _CALENDAR,
        "bucket_frequency": _BUCKET_FREQUENCY,
        "bucket_duration_ns": _BUCKET_DURATION_NS,
        "required_consecutive_bucket_count": _REQUIRED_CONSECUTIVE_BUCKET_COUNT,
        "duration_sufficiency_assessed": False,
        "sample_sufficiency_assessed": False,
        "return_basis": _RETURN_BASIS,
        "return_value_kind": _RETURN_VALUE_KIND,
        "normalized_index_start": _NORMALIZED_INDEX_START,
        "mark_to_market_required": _MARK_TO_MARKET_REQUIRED,
        "realized_only_primary_series": _REALIZED_ONLY_PRIMARY_SERIES,
        "mtm_policy_id": policy_ids[0],
        "fee_policy_id": policy_ids[1],
        "funding_policy_id": policy_ids[2],
        "mark_policy_id": policy_ids[3],
        "exposure_policy_id": policy_ids[4],
        "liquidation_policy_id": policy_ids[5],
        "risk_free_policy_id": policy_ids[6],
        "fee_policy_required": True,
        "funding_policy_required": True,
        "mark_policy_required": True,
        "exposure_policy_required": True,
        "liquidation_policy_required": True,
        "missing_policy_input_status": _MISSING_POLICY_INPUT_STATUS,
        "sparse_window_status": _SPARSE_WINDOW_STATUS,
        "insufficient_sample_status": _INSUFFICIENT_SAMPLE_STATUS,
        "no_trade_status": _NO_TRADE_STATUS,
        "zero_variance_status": _ZERO_VARIANCE_STATUS,
        "methodology_mismatch_status": _METHODOLOGY_MISMATCH_STATUS,
        "annualization_policy": _ANNUALIZATION_POLICY,
        "annualization_factor": _ANNUALIZATION_FACTOR,
        "paper_sharpe_policy": _PAPER_SHARPE_POLICY,
        "reason_codes": reason_code_values,
        "metadata": metadata_pairs,
    }
    seed = PaperReturnSeriesMethodology(methodology_digest="", **fields)  # type: ignore[arg-type]
    return _replace_methodology_digest(seed, paper_return_series_methodology_digest(seed))


def _replace_methodology_digest(methodology: PaperReturnSeriesMethodology, digest: str) -> PaperReturnSeriesMethodology:
    fields = _methodology_fields(methodology)
    fields["methodology_digest"] = digest
    return PaperReturnSeriesMethodology(**fields)  # type: ignore[arg-type]


def _methodology_fields(methodology: PaperReturnSeriesMethodology) -> dict[str, object]:
    return {
        "schema_version": methodology.schema_version,
        "methodology_version": methodology.methodology_version,
        "status": methodology.status,
        "ready": methodology.ready,
        "methodology_id": methodology.methodology_id,
        "correlation_id": methodology.correlation_id,
        "calendar": methodology.calendar,
        "bucket_frequency": methodology.bucket_frequency,
        "bucket_duration_ns": methodology.bucket_duration_ns,
        "required_consecutive_bucket_count": methodology.required_consecutive_bucket_count,
        "duration_sufficiency_assessed": methodology.duration_sufficiency_assessed,
        "sample_sufficiency_assessed": methodology.sample_sufficiency_assessed,
        "return_basis": methodology.return_basis,
        "return_value_kind": methodology.return_value_kind,
        "normalized_index_start": methodology.normalized_index_start,
        "mark_to_market_required": methodology.mark_to_market_required,
        "realized_only_primary_series": methodology.realized_only_primary_series,
        "mtm_policy_id": methodology.mtm_policy_id,
        "fee_policy_id": methodology.fee_policy_id,
        "funding_policy_id": methodology.funding_policy_id,
        "mark_policy_id": methodology.mark_policy_id,
        "exposure_policy_id": methodology.exposure_policy_id,
        "liquidation_policy_id": methodology.liquidation_policy_id,
        "risk_free_policy_id": methodology.risk_free_policy_id,
        "fee_policy_required": methodology.fee_policy_required,
        "funding_policy_required": methodology.funding_policy_required,
        "mark_policy_required": methodology.mark_policy_required,
        "exposure_policy_required": methodology.exposure_policy_required,
        "liquidation_policy_required": methodology.liquidation_policy_required,
        "missing_policy_input_status": methodology.missing_policy_input_status,
        "sparse_window_status": methodology.sparse_window_status,
        "insufficient_sample_status": methodology.insufficient_sample_status,
        "no_trade_status": methodology.no_trade_status,
        "zero_variance_status": methodology.zero_variance_status,
        "methodology_mismatch_status": methodology.methodology_mismatch_status,
        "annualization_policy": methodology.annualization_policy,
        "annualization_factor": methodology.annualization_factor,
        "paper_sharpe_policy": methodology.paper_sharpe_policy,
        "reason_codes": methodology.reason_codes,
        "metadata": methodology.metadata,
    }


def _methodology_payload_from(methodology: PaperReturnSeriesMethodology) -> dict[str, object]:
    return {
        "schema_version": methodology.schema_version,
        "methodology_version": methodology.methodology_version,
        "status": methodology.status.value,
        "ready": methodology.ready,
        "methodology_id": methodology.methodology_id,
        "correlation_id": methodology.correlation_id,
        "calendar": methodology.calendar,
        "bucket_frequency": methodology.bucket_frequency,
        "bucket_duration_ns": methodology.bucket_duration_ns,
        "required_consecutive_bucket_count": methodology.required_consecutive_bucket_count,
        "duration_sufficiency_assessed": methodology.duration_sufficiency_assessed,
        "sample_sufficiency_assessed": methodology.sample_sufficiency_assessed,
        "return_basis": methodology.return_basis,
        "return_value_kind": methodology.return_value_kind,
        "normalized_index_start": methodology.normalized_index_start,
        "mark_to_market_required": methodology.mark_to_market_required,
        "realized_only_primary_series": methodology.realized_only_primary_series,
        "mtm_policy_id": methodology.mtm_policy_id,
        "fee_policy_id": methodology.fee_policy_id,
        "funding_policy_id": methodology.funding_policy_id,
        "mark_policy_id": methodology.mark_policy_id,
        "exposure_policy_id": methodology.exposure_policy_id,
        "liquidation_policy_id": methodology.liquidation_policy_id,
        "risk_free_policy_id": methodology.risk_free_policy_id,
        "fee_policy_required": methodology.fee_policy_required,
        "funding_policy_required": methodology.funding_policy_required,
        "mark_policy_required": methodology.mark_policy_required,
        "exposure_policy_required": methodology.exposure_policy_required,
        "liquidation_policy_required": methodology.liquidation_policy_required,
        "missing_policy_input_status": methodology.missing_policy_input_status,
        "sparse_window_status": methodology.sparse_window_status,
        "insufficient_sample_status": methodology.insufficient_sample_status,
        "no_trade_status": methodology.no_trade_status,
        "zero_variance_status": methodology.zero_variance_status,
        "methodology_mismatch_status": methodology.methodology_mismatch_status,
        "annualization_policy": methodology.annualization_policy,
        "annualization_factor": methodology.annualization_factor,
        "paper_sharpe_policy": methodology.paper_sharpe_policy,
        "reason_codes": list(methodology.reason_codes),
        "metadata": _serialize_metadata(methodology.metadata),
        "paper_only": methodology.paper_only,
        "methodology_snapshot": methodology.methodology_snapshot,
        "daily_utc_only": methodology.daily_utc_only,
        "normalized_paper_equity_index": methodology.normalized_paper_equity_index,
        "real_account_equity_used": methodology.real_account_equity_used,
        "real_capital_used": methodology.real_capital_used,
        "return_series_computed": methodology.return_series_computed,
        "daily_returns_computed": methodology.daily_returns_computed,
        "sharpe_computed": methodology.sharpe_computed,
        "paper_sharpe_computed": methodology.paper_sharpe_computed,
        "thirty_day_gate_satisfied": methodology.thirty_day_gate_satisfied,
        "thirty_day_gate_decided": methodology.thirty_day_gate_decided,
        "comparison_ready": methodology.comparison_ready,
        "stage4_comparator_invoked": methodology.stage4_comparator_invoked,
        "prdv4_stage4_complete": methodology.prdv4_stage4_complete,
        "live_ready": methodology.live_ready,
        "shadow_ready": methodology.shadow_ready,
        "operational_readiness": methodology.operational_readiness,
        "deribit_ready": methodology.deribit_ready,
        "profitability_proven": methodology.profitability_proven,
        "edge_proven": methodology.edge_proven,
        "production_execution": methodology.production_execution,
        "real_orders_enabled": methodology.real_orders_enabled,
        "real_money_enabled": methodology.real_money_enabled,
        "real_capital_reserved": methodology.real_capital_reserved,
        "live_api_called": methodology.live_api_called,
        "scheduler_enabled": methodology.scheduler_enabled,
        "auto_loop_enabled": methodology.auto_loop_enabled,
        "connector_invoked": methodology.connector_invoked,
        "real_wall_clock_used": methodology.real_wall_clock_used,
        "timestamp_origin_proven": methodology.timestamp_origin_proven,
    }


def paper_return_series_methodology_to_dict(methodology: PaperReturnSeriesMethodology) -> dict[str, object]:
    """Canonical JSON-ready mapping for the methodology snapshot, including its self-digest."""

    payload = _methodology_payload_from(methodology)
    payload["methodology_digest"] = methodology.methodology_digest
    return payload


def paper_return_series_methodology_digest(methodology: PaperReturnSeriesMethodology) -> str:
    """Recompute the canonical methodology digest, excluding the self-digest field."""

    return _canonical_digest(_methodology_payload_from(methodology))


__all__ = [
    "PaperReturnSeriesMethodology",
    "PaperReturnSeriesMethodologyError",
    "PaperReturnSeriesMethodologyStatus",
    "build_paper_return_series_methodology",
    "paper_return_series_methodology_digest",
    "paper_return_series_methodology_to_dict",
]
