"""Deterministic, digest-bound paper trade-record evidence (SM-3, secondary-metrics chain).

This validation artifact is a SANITIZED PAPER-TRADE OBSERVATION record, never an execution artifact.
It consumes only caller-supplied primitive fields (ids + scale-18 ``Decimal`` strings + one ``decided``
flag) describing a single already-simulated paper episode; it never touches an execution engine, order
router, fill simulator, ledger, wall clock, network, filesystem, scheduler, or any live/private surface,
and it imports no such module.

A ``RECORD_READY`` record proves only that the supplied observation is well-formed, in-range, scope-clean,
and internally coherent, and that its derived ``hit_flag`` / ``fill_flag`` / ``slippage_bps`` were recomputed
from the raw quantities/prices (never trusted from the caller). It does NOT prove edge, profitability,
authoritative PnL, secondary-metric enforcement, Stage-4 completion, machine-time provenance, or
live/shadow/Deribit/operational readiness. Later ``PaperSecondaryMetricsEvidence`` (SM-4) aggregates a set of
these records against the merged ``SecondaryMetricsPolicy`` (SM-2) thresholds; this module computes no
aggregate metric and enforces no threshold.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import Enum

_SCHEMA_VERSION = "trade-record-evidence.v1"
_RECORD_VERSION = "trade-record-evidence.v1"
_REASON_PREFIX = "trade_record_evidence"
_SLIPPAGE_DEFINITION = "signed_bps_vs_expected_fill_reference_price.v1"
_HIT_DEFINITION = "realized_pnl_positive_and_decided_episode.v1"
_FILL_DEFINITION = "filled_quantity_positive_episode.v1"
_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_fraction_intermediates.v1"
_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_DECIMAL_INTERNAL_PRECISION = 80

_BPS_PER_UNIT = Decimal(10_000)

# Exactly _DECIMAL_SCALE (18) fractional digits are mandatory; a looser pattern would let the same number
# carry multiple digest-bound encodings (mirrors SM-2 ``SecondaryMetricsPolicy`` scale-18 policy).
_SCALE18_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{18}$")
_NEGATIVE_ZERO_SCALE18 = "-0.000000000000000000"
# Hard cap on a consumed scale-18 string length. Bounded magnitude keeps every scale-18 quantization inside
# the precision-80 Decimal context, so an oversize value fails closed deterministically instead of raising.
_MAX_SCALE18_LENGTH = 60
# Magnitude bounds for positive quantities/prices and the absolute PnL: outside [1e-18, 1e18] the derived
# slippage quantization could exceed the precision-80 context. Deterministic rejection, never an exception.
_MIN_POSITIVE_DECIMAL = Decimal("1E-18")
_MAX_ABS_DECIMAL = Decimal("1E+18")
_DECIMAL_QUANTUM = Decimal(1).scaleb(-_DECIMAL_SCALE)

_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"capital|margin|balance|reservation|real_account_equity|account_equity|real_equity)\w*"
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


class TradeRecordEvidenceError(RuntimeError):
    """Raised on malformed caller input for the SM-3 trade-record artifact."""


class TradeRecordEvidenceStatus(str, Enum):
    """SM-3 record status. RECORD_READY is observation well-formedness only, never enforcement/edge."""

    RECORD_READY = "RECORD_READY"
    RECORD_REJECTED = "RECORD_REJECTED"


@dataclass(frozen=True)
class TradeRecordEvidence:
    """Immutable, digest-bound sanitized paper-trade observation record.

    ``status=RECORD_READY`` only when ids are safe and scope-clean, every numeric field is a canonical
    scale-18 string within range, ``filled_quantity <= intended_quantity``, the realized fill price is
    present exactly when ``filled_quantity > 0``, and the derived ``hit_flag`` / ``fill_flag`` /
    ``slippage_bps`` recomputed here match the record. It reports one observation only — no aggregate metric,
    no threshold, no enforcement, no edge/profitability/PnL-authority/readiness/completion claim.
    """

    schema_version: str
    record_version: str
    status: TradeRecordEvidenceStatus
    ready: bool
    record_id: str
    correlation_id: str
    sleeve_id: str
    policy_id: str
    episode_id: str
    strategy_id: str
    decision_id: str
    hit_rate_definition: str
    fill_rate_definition: str
    slippage_definition: str
    intended_quantity: str
    filled_quantity: str
    expected_fill_price: str
    realized_fill_price: str | None
    realized_pnl: str
    slippage_bps: str | None
    decided_episode: bool
    hit_flag: bool
    fill_flag: bool
    decimal_policy: str
    decimal_scale: int
    decimal_rounding: str
    decimal_internal_precision: int
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    record_digest: str
    paper_only: bool = True
    record_only: bool = True
    execution_authorized: bool = False
    order_created: bool = False
    order_routed: bool = False
    real_fill_created: bool = False
    position_mutated: bool = False
    pnl_authoritative: bool = False
    secondary_metrics_enforced: bool = False
    stage4_completion_decided: bool = False
    prdv4_stage4_complete: bool = False
    machine_time_origin_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False


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


def _is_exact_bool(value: object) -> bool:
    return type(value) is bool


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise TradeRecordEvidenceError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _parse_scale18(value: object) -> Decimal | None:
    if (
        type(value) is not str
        or len(value) > _MAX_SCALE18_LENGTH
        or value == _NEGATIVE_ZERO_SCALE18
        or not _SCALE18_PATTERN.fullmatch(value)
    ):
        return None
    parsed = Decimal(value)
    return parsed if parsed.is_finite() else None


def _format_scale18(value: Decimal) -> str:
    quantized = value.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        quantized = Decimal(0).quantize(_DECIMAL_QUANTUM)
    return format(quantized, "f")


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise TradeRecordEvidenceError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise TradeRecordEvidenceError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise TradeRecordEvidenceError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise TradeRecordEvidenceError(_reason("metadata_malformed"))
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


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _positive_in_bounds(value: Decimal) -> bool:
    return _MIN_POSITIVE_DECIMAL <= value <= _MAX_ABS_DECIMAL


def _quantity_price_failures(
    *,
    intended: Decimal | None,
    filled: Decimal | None,
    expected_price: Decimal | None,
    realized_price_raw: object,
    realized_pnl: Decimal | None,
) -> tuple[list[str], Decimal | None]:
    """Validate the numeric block and return (failures, realized_fill_price_decimal_or_None)."""

    hard: list[str] = []
    if intended is None or not _positive_in_bounds(intended):
        hard.append(_reason("intended_quantity_invalid"))
    if filled is None or filled < 0 or filled > _MAX_ABS_DECIMAL:
        hard.append(_reason("filled_quantity_invalid"))
    if expected_price is None or not _positive_in_bounds(expected_price):
        hard.append(_reason("expected_fill_price_invalid"))
    if realized_pnl is None or abs(realized_pnl) > _MAX_ABS_DECIMAL:
        hard.append(_reason("realized_pnl_invalid"))
    if intended is not None and filled is not None and filled > intended:
        hard.append(_reason("filled_exceeds_intended"))

    realized_price: Decimal | None = None
    is_filled = filled is not None and filled > 0
    if is_filled:
        realized_price = _parse_scale18(realized_price_raw)
        if realized_price is None or not _positive_in_bounds(realized_price):
            hard.append(_reason("realized_fill_price_invalid"))
            realized_price = None
    elif realized_price_raw is not None:
        # An unfilled episode must not carry a realized fill price — otherwise slippage is ambiguous.
        hard.append(_reason("realized_fill_price_present_without_fill"))
    return hard, realized_price


def _derive_slippage_bps(expected_price: Decimal, realized_price: Decimal) -> str:
    with localcontext() as context:
        context.prec = _DECIMAL_INTERNAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        ratio = (realized_price - expected_price) / expected_price
        return _format_scale18(ratio * _BPS_PER_UNIT)


def build_trade_record_evidence(
    *,
    record_id: str,
    correlation_id: str,
    sleeve_id: str,
    policy_id: str,
    episode_id: str,
    strategy_id: str,
    decision_id: str,
    intended_quantity: str,
    filled_quantity: str,
    expected_fill_price: str,
    realized_pnl: str,
    decided_episode: bool,
    realized_fill_price: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> TradeRecordEvidence:
    """Build a deterministic SM-3 trade-record observation.

    ``hit_flag`` / ``fill_flag`` / ``slippage_bps`` are RECOMPUTED from the raw quantities/prices and never
    accepted from the caller. Wrong-typed ids/metadata or forbidden BIST/live/order/scheduler/clock tokens
    raise ``TradeRecordEvidenceError``; every well-formedness/range/coherence failure maps to
    ``status=RECORD_REJECTED`` with deterministic reason codes.
    """

    record_id = _require_plain_non_empty_string(record_id, "record_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    sleeve_id = _require_plain_non_empty_string(sleeve_id, "sleeve_id")
    policy_id = _require_plain_non_empty_string(policy_id, "policy_id")
    episode_id = _require_plain_non_empty_string(episode_id, "episode_id")
    strategy_id = _require_plain_non_empty_string(strategy_id, "strategy_id")
    decision_id = _require_plain_non_empty_string(decision_id, "decision_id")
    if not _is_exact_bool(decided_episode):
        raise TradeRecordEvidenceError(_reason("decided_episode_invalid"))
    metadata_pairs = _normalize_metadata(metadata)

    scope_texts = (
        record_id,
        correlation_id,
        sleeve_id,
        policy_id,
        episode_id,
        strategy_id,
        decision_id,
        *_metadata_texts(metadata_pairs),
    )
    if _has_bist_token(*scope_texts):
        raise TradeRecordEvidenceError(_reason("bist_token_forbidden"))
    if _has_clock_token(*scope_texts):
        raise TradeRecordEvidenceError(_reason("clock_token_forbidden"))
    if _has_scope_violation(*scope_texts):
        raise TradeRecordEvidenceError(_reason("scope_violation"))

    intended = _parse_scale18(intended_quantity)
    filled = _parse_scale18(filled_quantity)
    expected_price = _parse_scale18(expected_fill_price)
    pnl = _parse_scale18(realized_pnl)

    hard, realized_price = _quantity_price_failures(
        intended=intended,
        filled=filled,
        expected_price=expected_price,
        realized_price_raw=realized_fill_price,
        realized_pnl=pnl,
    )

    fill_flag = filled is not None and filled > 0
    hit_flag = decided_episode and pnl is not None and pnl > 0
    slippage_bps: str | None = None
    if not hard and fill_flag and expected_price is not None and realized_price is not None:
        slippage_bps = _derive_slippage_bps(expected_price, realized_price)

    reason_codes = _sorted_unique(hard)
    status = TradeRecordEvidenceStatus.RECORD_REJECTED if reason_codes else TradeRecordEvidenceStatus.RECORD_READY
    ready = status is TradeRecordEvidenceStatus.RECORD_READY

    record_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "record_version": _RECORD_VERSION,
        "status": status,
        "ready": ready,
        "record_id": record_id,
        "correlation_id": correlation_id,
        "sleeve_id": sleeve_id,
        "policy_id": policy_id,
        "episode_id": episode_id,
        "strategy_id": strategy_id,
        "decision_id": decision_id,
        "hit_rate_definition": _HIT_DEFINITION,
        "fill_rate_definition": _FILL_DEFINITION,
        "slippage_definition": _SLIPPAGE_DEFINITION,
        "intended_quantity": intended_quantity if type(intended_quantity) is str else "",
        "filled_quantity": filled_quantity if type(filled_quantity) is str else "",
        "expected_fill_price": expected_fill_price if type(expected_fill_price) is str else "",
        "realized_fill_price": realized_fill_price if realized_price is not None else None,
        "realized_pnl": realized_pnl if type(realized_pnl) is str else "",
        "slippage_bps": slippage_bps,
        "decided_episode": decided_episode,
        "hit_flag": hit_flag if not reason_codes else False,
        "fill_flag": fill_flag if not reason_codes else False,
        "decimal_policy": _DECIMAL_POLICY,
        "decimal_scale": _DECIMAL_SCALE,
        "decimal_rounding": _DECIMAL_ROUNDING,
        "decimal_internal_precision": _DECIMAL_INTERNAL_PRECISION,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = TradeRecordEvidence(record_digest="", **record_fields)  # type: ignore[arg-type]
    return _replace_record_digest(seed, trade_record_evidence_digest(seed))


def _replace_record_digest(record: TradeRecordEvidence, digest: str) -> TradeRecordEvidence:
    values = {field.name: getattr(record, field.name) for field in fields(record) if field.name != "record_digest"}
    values["record_digest"] = digest
    return TradeRecordEvidence(**values)  # type: ignore[arg-type]


def _record_payload_from(record: TradeRecordEvidence) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(record):
        if field.name == "record_digest":
            continue
        value = getattr(record, field.name)
        if field.name == "status":
            payload[field.name] = value.value if isinstance(value, TradeRecordEvidenceStatus) else value
        elif field.name == "reason_codes":
            payload[field.name] = list(record.reason_codes)
        elif field.name == "metadata":
            payload[field.name] = _serialize_metadata(record.metadata)
        else:
            payload[field.name] = value
    return payload


def trade_record_evidence_to_dict(record: TradeRecordEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for the SM-3 record, including its self-digest."""

    payload = _record_payload_from(record)
    payload["record_digest"] = record.record_digest
    return payload


def trade_record_evidence_digest(record: TradeRecordEvidence) -> str:
    """Recompute the canonical record digest, excluding only the self-digest field."""

    return _canonical_digest(_record_payload_from(record))


__all__ = [
    "TradeRecordEvidence",
    "TradeRecordEvidenceError",
    "TradeRecordEvidenceStatus",
    "build_trade_record_evidence",
    "trade_record_evidence_digest",
    "trade_record_evidence_to_dict",
]
