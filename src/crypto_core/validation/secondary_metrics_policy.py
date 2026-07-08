"""Secondary metrics policy artifact for the SM-2 policy-only slice.

This module pins the governance-owned secondary-metric policy structure for later SM evidence artifacts.
It consumes no episodes, fills, PnL, comparator output, runtime state, live state, or external facts. A READY
policy proves only that the supplied threshold metadata and model reference are digest-bound and approved;
it never proves that secondary metrics have been computed or enforced.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import Enum

_SCHEMA_VERSION = "secondary-metrics-policy.v1"
_POLICY_VERSION = "secondary-metrics-policy.v1"
_HIT_RATE_DEFINITION = "realized_pnl_positive_episode_over_decided_episodes.v1"
_FILL_RATE_DEFINITION = "filled_quantity_over_intended_quantity_and_filled_episode_ratio.v1"
_SLIPPAGE_DEFINITION = "signed_bps_vs_expected_fill_reference_price.v1"
_EXPECTED_FILL_MODEL_REFERENCE = "crypto_core.execution.fill_pricer.FillPricer.mid_plus_half_spread_plus_size_impact.v1"
_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_fraction_intermediates.v1"
_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_REASON_PREFIX = "secondary_metrics_policy"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Exactly _DECIMAL_SCALE (18) fractional digits are mandatory: a looser pattern would let the same
# approved number ("0.5" vs "0.500000000000000000") produce different digest-bound encodings.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{18}$")
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"stage4_comparator|compare_stage4|Stage4PaperSummary|Stage4BacktestBaseline|capital|margin|balance|"
    r"reservation|real_account_equity|account_equity|real_equity)\w*"
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


class SecondaryMetricsPolicyError(RuntimeError):
    """Raised on malformed caller input for the SM-2 policy artifact."""


class SecondaryMetricsPolicyStatus(str, Enum):
    """SM-2 policy status. READY is policy readiness only, never metric enforcement."""

    POLICY_READY = "POLICY_READY"
    POLICY_REJECTED = "POLICY_REJECTED"


@dataclass(frozen=True)
class SecondaryMetricsPolicy:
    """Immutable, digest-bound secondary-metrics policy snapshot.

    The policy may be READY only when human/controller approval metadata and caller-supplied approved
    thresholds are present and well-formed. It does not consume records or enforce metrics.
    """

    schema_version: str
    policy_version: str
    status: SecondaryMetricsPolicyStatus
    ready: bool
    policy_id: str
    correlation_id: str
    hit_rate_definition: str
    fill_rate_definition: str
    slippage_definition: str
    expected_fill_model_reference: str
    expected_fill_model_parameters_digest: str
    decimal_policy: str
    decimal_scale: int
    decimal_rounding: str
    fraction_intermediates_required: bool
    approved_hit_rate_floor: str | None
    approved_fill_rate_floor: str | None
    approved_slippage_ceiling_bps: str | None
    approved_min_decided_episode_count: int | None
    approval_reference: str | None
    approval_digest: str | None
    thresholds_approved: bool
    secondary_metrics_policy_ready: bool
    secondary_metrics_enforced: bool
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    policy_digest: str
    paper_only: bool = True
    policy_only: bool = True
    trade_records_consumed: bool = False
    episodes_consumed: bool = False
    fills_consumed: bool = False
    pnl_consumed: bool = False
    comparator_invoked: bool = False
    stage4_completion_decided: bool = False
    prdv4_stage4_complete: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


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


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise SecondaryMetricsPolicyError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise SecondaryMetricsPolicyError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise SecondaryMetricsPolicyError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise SecondaryMetricsPolicyError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise SecondaryMetricsPolicyError(_reason("metadata_malformed"))
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


def _has_bist_token(*texts: object) -> bool:
    return any(type(text) is str and text != "" and _BIST_PATTERN.search(text) for text in texts)


def _has_clock_token(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _CLOCK_TOKENS):
            return True
    return False


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _parse_decimal_string(value: object) -> Decimal | None:
    if type(value) is not str or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _threshold_decimal_failures(
    *,
    value: object,
    missing_code: str,
    lower_bound: Decimal,
    upper_bound: Decimal | None = None,
) -> tuple[Decimal | None, list[str]]:
    if value is None:
        return None, [_reason(missing_code)]
    parsed = _parse_decimal_string(value)
    if parsed is None or (type(value) is str and value.startswith("-")):
        return None, [_reason("approved_value_invalid")]
    if parsed < lower_bound or (upper_bound is not None and parsed > upper_bound):
        return parsed, [_reason("approved_value_invalid")]
    return parsed, []


def _min_count_failures(value: object) -> list[str]:
    if value is None:
        return [_reason("approved_min_decided_episode_count_missing")]
    if not _is_exact_int(value) or value < 1:
        return [_reason("approved_value_invalid")]
    return []


def _definition_failures(
    *,
    hit_rate_definition: object,
    fill_rate_definition: object,
    slippage_definition: object,
    expected_fill_model_reference: object,
    expected_fill_model_parameters_digest: object,
    decimal_policy: object,
    decimal_scale: object,
    decimal_rounding: object,
    fraction_intermediates_required: object,
) -> list[str]:
    hard: list[str] = []
    if (
        hit_rate_definition != _HIT_RATE_DEFINITION
        or fill_rate_definition != _FILL_RATE_DEFINITION
        or slippage_definition != _SLIPPAGE_DEFINITION
    ):
        hard.append(_reason("definition_mismatch"))
    if expected_fill_model_reference != _EXPECTED_FILL_MODEL_REFERENCE:
        hard.append(_reason("expected_fill_model_reference_invalid"))
    if not _is_hex64_string(expected_fill_model_parameters_digest):
        hard.append(_reason("expected_fill_model_parameters_digest_invalid"))
    if (
        decimal_policy != _DECIMAL_POLICY
        or decimal_scale != _DECIMAL_SCALE
        or decimal_rounding != _DECIMAL_ROUNDING
        or fraction_intermediates_required is not True
    ):
        hard.append(_reason("decimal_policy_mismatch"))
    return hard


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def build_secondary_metrics_policy(
    *,
    policy_id: str,
    correlation_id: str,
    expected_fill_model_parameters_digest: str | None = None,
    approved_hit_rate_floor: str | None = None,
    approved_fill_rate_floor: str | None = None,
    approved_slippage_ceiling_bps: str | None = None,
    approved_min_decided_episode_count: int | None = None,
    approval_reference: str | None = None,
    approval_digest: str | None = None,
    thresholds_approved: bool = False,
    hit_rate_definition: str = _HIT_RATE_DEFINITION,
    fill_rate_definition: str = _FILL_RATE_DEFINITION,
    slippage_definition: str = _SLIPPAGE_DEFINITION,
    expected_fill_model_reference: str = _EXPECTED_FILL_MODEL_REFERENCE,
    decimal_policy: str = _DECIMAL_POLICY,
    decimal_scale: int = _DECIMAL_SCALE,
    decimal_rounding: str = _DECIMAL_ROUNDING,
    fraction_intermediates_required: bool = True,
    metadata: Mapping[str, str] | None = None,
) -> SecondaryMetricsPolicy:
    """Build a deterministic policy-only SM-2 artifact.

    Governance-owned numeric values are accepted only when explicitly supplied with approval metadata.
    Missing or unapproved values produce ``POLICY_REJECTED`` rather than defaults.
    """

    policy_id = _require_plain_non_empty_string(policy_id, "policy_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    if type(thresholds_approved) is not bool:
        raise SecondaryMetricsPolicyError(_reason("thresholds_approved_invalid"))

    metadata_pairs = _normalize_metadata(metadata)
    hard: list[str] = []

    if thresholds_approved is not True:
        hard.append(_reason("thresholds_not_approved"))

    _, failures = _threshold_decimal_failures(
        value=approved_hit_rate_floor,
        missing_code="approved_hit_rate_floor_missing",
        lower_bound=Decimal(0),
        upper_bound=Decimal(1),
    )
    hard.extend(failures)
    _, failures = _threshold_decimal_failures(
        value=approved_fill_rate_floor,
        missing_code="approved_fill_rate_floor_missing",
        lower_bound=Decimal(0),
        upper_bound=Decimal(1),
    )
    hard.extend(failures)
    _, failures = _threshold_decimal_failures(
        value=approved_slippage_ceiling_bps,
        missing_code="approved_slippage_ceiling_missing",
        lower_bound=Decimal(0),
    )
    hard.extend(failures)
    hard.extend(_min_count_failures(approved_min_decided_episode_count))

    if not _is_plain_non_empty_string(approval_reference):
        hard.append(_reason("approval_reference_missing"))
    if not _is_hex64_string(approval_digest):
        hard.append(_reason("approval_digest_invalid"))

    hard.extend(
        _definition_failures(
            hit_rate_definition=hit_rate_definition,
            fill_rate_definition=fill_rate_definition,
            slippage_definition=slippage_definition,
            expected_fill_model_reference=expected_fill_model_reference,
            expected_fill_model_parameters_digest=expected_fill_model_parameters_digest,
            decimal_policy=decimal_policy,
            decimal_scale=decimal_scale,
            decimal_rounding=decimal_rounding,
            fraction_intermediates_required=fraction_intermediates_required,
        )
    )

    scope_texts = (
        policy_id,
        correlation_id,
        approval_reference,
        approved_hit_rate_floor,
        approved_fill_rate_floor,
        approved_slippage_ceiling_bps,
        *_metadata_texts(metadata_pairs),
    )
    if _has_bist_token(*scope_texts):
        hard.append(_reason("bist_token_forbidden"))
    if _has_clock_token(*scope_texts):
        hard.append(_reason("clock_token_forbidden"))
    if _has_scope_violation(*scope_texts):
        hard.append(_reason("scope_violation"))

    reason_codes = _sorted_unique(hard)
    status = SecondaryMetricsPolicyStatus.POLICY_REJECTED if reason_codes else SecondaryMetricsPolicyStatus.POLICY_READY
    ready = status is SecondaryMetricsPolicyStatus.POLICY_READY

    policy_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "policy_version": _POLICY_VERSION,
        "status": status,
        "ready": ready,
        "policy_id": policy_id,
        "correlation_id": correlation_id,
        "hit_rate_definition": hit_rate_definition,
        "fill_rate_definition": fill_rate_definition,
        "slippage_definition": slippage_definition,
        "expected_fill_model_reference": expected_fill_model_reference,
        "expected_fill_model_parameters_digest": expected_fill_model_parameters_digest,
        "decimal_policy": decimal_policy,
        "decimal_scale": decimal_scale,
        "decimal_rounding": decimal_rounding,
        "fraction_intermediates_required": fraction_intermediates_required,
        "approved_hit_rate_floor": approved_hit_rate_floor,
        "approved_fill_rate_floor": approved_fill_rate_floor,
        "approved_slippage_ceiling_bps": approved_slippage_ceiling_bps,
        "approved_min_decided_episode_count": approved_min_decided_episode_count,
        "approval_reference": approval_reference,
        "approval_digest": approval_digest,
        "thresholds_approved": thresholds_approved,
        "secondary_metrics_policy_ready": ready,
        "secondary_metrics_enforced": False,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = SecondaryMetricsPolicy(policy_digest="", **policy_fields)  # type: ignore[arg-type]
    return _replace_policy_digest(seed, secondary_metrics_policy_digest(seed))


def _replace_policy_digest(policy: SecondaryMetricsPolicy, digest: str) -> SecondaryMetricsPolicy:
    values = _policy_fields(policy)
    values["policy_digest"] = digest
    return SecondaryMetricsPolicy(**values)  # type: ignore[arg-type]


def _policy_fields(policy: SecondaryMetricsPolicy) -> dict[str, object]:
    return {field.name: getattr(policy, field.name) for field in fields(policy) if field.name != "policy_digest"}


def _policy_payload_from(policy: SecondaryMetricsPolicy) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(policy):
        if field.name == "policy_digest":
            continue
        value = getattr(policy, field.name)
        if field.name == "status":
            payload[field.name] = value.value if isinstance(value, SecondaryMetricsPolicyStatus) else value
        elif field.name == "reason_codes":
            payload[field.name] = list(policy.reason_codes)
        elif field.name == "metadata":
            payload[field.name] = _serialize_metadata(policy.metadata)
        else:
            payload[field.name] = value
    return payload


def secondary_metrics_policy_to_dict(policy: SecondaryMetricsPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping for the SM-2 policy, including its self-digest."""

    payload = _policy_payload_from(policy)
    payload["policy_digest"] = policy.policy_digest
    return payload


def secondary_metrics_policy_digest(policy: SecondaryMetricsPolicy) -> str:
    """Recompute the canonical policy digest, excluding only the self-digest field."""

    return _canonical_digest(_policy_payload_from(policy))


__all__ = [
    "SecondaryMetricsPolicy",
    "SecondaryMetricsPolicyError",
    "SecondaryMetricsPolicyStatus",
    "build_secondary_metrics_policy",
    "secondary_metrics_policy_digest",
    "secondary_metrics_policy_to_dict",
]
