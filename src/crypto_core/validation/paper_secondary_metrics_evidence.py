"""Deterministic, digest-bound paper secondary-metrics evidence (SM-4, secondary-metrics chain).

This validation artifact aggregates a set of merged SM-3 ``TradeRecordEvidence`` observations against the
merged SM-2 ``SecondaryMetricsPolicy`` thresholds and reports whether the computed hit-rate, fill-rate, and
slippage clear the governance-approved floors/ceiling. Every metric is recomputed here from the raw record
fields with ``Fraction`` intermediates and quantized to scale-18 ``Decimal`` — carried record values are
never trusted as the metric. The policy self-digest and each record self-digest are re-proven via their
public serializers before any field is read.

Threshold enforcement is performed EXPLICITLY here (``computed_metric`` vs ``approved_threshold``); it does
NOT rely on ``compare_stage4`` — this module neither imports nor calls the comparator. ``METRICS_READY``
means only that a trusted evidence set cleared the approved thresholds; it is NOT edge, profitability,
authoritative PnL, Stage-4 completion, machine-time provenance, secondary-metric enforcement wired into the
Stage-4 pipeline, or live/shadow/Deribit/operational readiness. ``INSUFFICIENT_EVIDENCE`` (decided episodes
below the approved minimum) and ``METRICS_REJECTED`` (trust failure or a threshold breach) are both valid
non-READY outcomes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import Enum
from fractions import Fraction

from crypto_core.validation.secondary_metrics_policy import (
    SecondaryMetricsPolicy,
    SecondaryMetricsPolicyStatus,
    secondary_metrics_policy_digest,
)
from crypto_core.validation.trade_record_evidence import (
    TradeRecordEvidence,
    TradeRecordEvidenceStatus,
    trade_record_evidence_digest,
)

_SCHEMA_VERSION = "paper-secondary-metrics-evidence.v1"
_EVIDENCE_VERSION = "paper-secondary-metrics-evidence.v1"
_REASON_PREFIX = "paper_secondary_metrics_evidence"

_EXPECTED_POLICY_SCHEMA_VERSION = "secondary-metrics-policy.v1"
_EXPECTED_RECORD_SCHEMA_VERSION = "trade-record-evidence.v1"

_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_fraction_intermediates.v1"
_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_DECIMAL_INTERNAL_PRECISION = 80
_DECIMAL_QUANTUM = Decimal(1).scaleb(-_DECIMAL_SCALE)
_HIT_RATE_OPERATOR = ">="
_FILL_RATE_OPERATOR = ">="
_SLIPPAGE_OPERATOR = "<="

# Bounds the aggregated record set so every scale-18 sum quantization stays inside the precision-80 context.
_MAX_RECORDS = 100_000

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

_POLICY_TRUE_FLAGS = ("paper_only", "policy_only")
_POLICY_FALSE_FLAGS = (
    "secondary_metrics_enforced",
    "trade_records_consumed",
    "episodes_consumed",
    "fills_consumed",
    "pnl_consumed",
    "comparator_invoked",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "private_api_ready",
    "live_api_called",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "edge_proven",
    "profitability_proven",
)
_RECORD_TRUE_FLAGS = ("paper_only", "record_only")
_RECORD_FALSE_FLAGS = (
    "execution_authorized",
    "order_created",
    "order_routed",
    "real_fill_created",
    "position_mutated",
    "pnl_authoritative",
    "secondary_metrics_enforced",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "edge_proven",
    "profitability_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
)

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


class PaperSecondaryMetricsEvidenceError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed policy/records/ids/metadata/tokens)."""


class PaperSecondaryMetricsEvidenceStatus(str, Enum):
    """SM-4 status. METRICS_READY is threshold-clearance evidence only, never enforcement/edge/completion."""

    METRICS_READY = "METRICS_READY"
    METRICS_REJECTED = "METRICS_REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperSecondaryMetricsEvidence:
    """Immutable, digest-bound paper secondary-metrics evidence over merged SM-3 records + SM-2 policy.

    ``status=METRICS_READY`` only when the policy and every record re-prove their digests, the set is
    trusted and coherent, decided episodes meet the approved minimum, and the recomputed hit-rate /
    fill-rate / slippage clear the approved thresholds (compared in ``Fraction`` before quantization).
    ``INSUFFICIENT_EVIDENCE`` and ``METRICS_REJECTED`` are valid non-READY outcomes. Thresholds are
    enforced HERE, not by ``compare_stage4``. READY is never edge/profitability/PnL-authority/completion/
    readiness.
    """

    schema_version: str
    evidence_version: str
    status: PaperSecondaryMetricsEvidenceStatus
    ready: bool
    evidence_id: str
    correlation_id: str
    policy_id: str
    verified_policy_digest: str
    record_count: int
    decided_episode_count: int
    positive_pnl_episode_count: int
    filled_episode_count: int
    intended_quantity_sum: str
    filled_quantity_sum: str
    hit_rate: str | None
    fill_rate_by_quantity: str | None
    fill_rate_by_episode: str | None
    average_slippage_bps: str | None
    approved_hit_rate_floor: str | None
    approved_fill_rate_floor: str | None
    approved_slippage_ceiling_bps: str | None
    approved_min_decided_episode_count: int | None
    hit_rate_operator: str
    fill_rate_operator: str
    slippage_operator: str
    hit_rate_satisfied: bool
    fill_rate_satisfied: bool
    slippage_satisfied: bool
    sufficient_evidence: bool
    thresholds_cleared: bool
    decimal_policy: str
    decimal_scale: int
    decimal_rounding: str
    decimal_internal_precision: int
    record_digests: tuple[str, ...]
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    evidence_digest: str
    paper_only: bool = True
    evidence_only: bool = True
    thresholds_enforced_here_not_by_comparator: bool = True
    comparator_invoked: bool = False
    secondary_metrics_enforced: bool = False
    stage4_completion_decided: bool = False
    prdv4_stage4_complete: bool = False
    machine_time_origin_proven: bool = False
    pnl_authoritative: bool = False
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
    production_execution: bool = False


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


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperSecondaryMetricsEvidenceError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSecondaryMetricsEvidenceError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperSecondaryMetricsEvidenceError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperSecondaryMetricsEvidenceError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperSecondaryMetricsEvidenceError(_reason("metadata_malformed"))
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


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _flag_failures(
    artifact: object, true_flags: tuple[str, ...], false_flags: tuple[str, ...], reason_code: str
) -> list[str]:
    if any(getattr(artifact, flag) is not True for flag in true_flags) or any(
        getattr(artifact, flag) is not False for flag in false_flags
    ):
        return [_reason(reason_code)]
    return []


def _recomputed_digest_or_none(compute: object, artifact: object) -> str | None:
    try:
        return compute(artifact)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return None


def _policy_failures(policy: SecondaryMetricsPolicy) -> list[str]:
    """Trust boundary for the merged SM-2 policy (digest / schema / status / readiness / safe flags)."""

    hard: list[str] = []
    recomputed = _recomputed_digest_or_none(secondary_metrics_policy_digest, policy)
    if recomputed is None or not _is_hex64_string(policy.policy_digest) or policy.policy_digest != recomputed:
        hard.append(_reason("policy_digest_mismatch"))
    if policy.schema_version != _EXPECTED_POLICY_SCHEMA_VERSION:
        hard.append(_reason("policy_schema_invalid"))
    if (
        policy.status is not SecondaryMetricsPolicyStatus.POLICY_READY
        or policy.ready is not True
        or policy.secondary_metrics_policy_ready is not True
        or policy.reason_codes != ()
    ):
        hard.append(_reason("policy_not_ready"))
    hard.extend(_flag_failures(policy, _POLICY_TRUE_FLAGS, _POLICY_FALSE_FLAGS, "policy_unsafe_flags"))
    return hard


def _record_failures(record: TradeRecordEvidence, policy_id: str) -> list[str]:
    """Trust boundary for one merged SM-3 record (digest / schema / status / policy binding / safe flags)."""

    hard: list[str] = []
    recomputed = _recomputed_digest_or_none(trade_record_evidence_digest, record)
    if recomputed is None or not _is_hex64_string(record.record_digest) or record.record_digest != recomputed:
        hard.append(_reason("record_digest_mismatch"))
    if record.schema_version != _EXPECTED_RECORD_SCHEMA_VERSION:
        hard.append(_reason("record_schema_invalid"))
    if (
        record.status is not TradeRecordEvidenceStatus.RECORD_READY
        or record.ready is not True
        or record.reason_codes != ()
    ):
        hard.append(_reason("record_not_ready"))
    if record.policy_id != policy_id:
        hard.append(_reason("record_policy_id_mismatch"))
    hard.extend(_flag_failures(record, _RECORD_TRUE_FLAGS, _RECORD_FALSE_FLAGS, "record_unsafe_flags"))
    return hard


def _fraction_from_scale18(value: str) -> Fraction:
    return Fraction(Decimal(value))


def _format_fraction_scale18(value: Fraction) -> str:
    with localcontext() as context:
        context.prec = _DECIMAL_INTERNAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        as_decimal = Decimal(value.numerator) / Decimal(value.denominator)
        quantized = as_decimal.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        quantized = Decimal(0).quantize(_DECIMAL_QUANTUM)
    return format(quantized, "f")


def _format_decimal_scale18(value: Decimal) -> str:
    quantized = value.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        quantized = Decimal(0).quantize(_DECIMAL_QUANTUM)
    return format(quantized, "f")


@dataclass(frozen=True)
class _Metrics:
    decided: int
    positive: int
    filled: int
    intended_sum: Decimal
    filled_sum: Decimal
    hit_rate: Fraction | None
    fill_rate_qty: Fraction
    fill_rate_ep: Fraction
    avg_slippage: Fraction | None


def _compute_metrics(records: tuple[TradeRecordEvidence, ...]) -> _Metrics:
    decided = sum(1 for record in records if record.decided_episode)
    positive = sum(1 for record in records if record.hit_flag)
    filled = sum(1 for record in records if record.fill_flag)
    intended_sum = sum((Decimal(record.intended_quantity) for record in records), Decimal(0))
    filled_sum = sum((Decimal(record.filled_quantity) for record in records), Decimal(0))
    slippage_values = [Decimal(record.slippage_bps) for record in records if record.slippage_bps is not None]

    hit_rate = Fraction(positive, decided) if decided > 0 else None
    fill_rate_qty = Fraction(filled_sum) / Fraction(intended_sum) if intended_sum > 0 else Fraction(0)
    fill_rate_ep = Fraction(filled, len(records))
    avg_slippage = (
        sum((Fraction(value) for value in slippage_values), Fraction(0)) / len(slippage_values)
        if slippage_values
        else None
    )
    return _Metrics(
        decided=decided,
        positive=positive,
        filled=filled,
        intended_sum=intended_sum,
        filled_sum=filled_sum,
        hit_rate=hit_rate,
        fill_rate_qty=fill_rate_qty,
        fill_rate_ep=fill_rate_ep,
        avg_slippage=avg_slippage,
    )


def build_paper_secondary_metrics_evidence(
    policy: SecondaryMetricsPolicy,
    records: Sequence[TradeRecordEvidence],
    *,
    evidence_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSecondaryMetricsEvidence:
    """Aggregate merged SM-3 records against the merged SM-2 policy and report threshold clearance.

    The policy and every record re-prove their self-digest; thresholds are compared in ``Fraction`` before
    quantization. Wrong-typed inputs, malformed ids/metadata, or forbidden BIST/live/order/scheduler/clock
    tokens raise ``PaperSecondaryMetricsEvidenceError``. Trust/coherence failures and threshold breaches map
    to ``METRICS_REJECTED``; too few decided episodes map to ``INSUFFICIENT_EVIDENCE``.
    """

    if type(policy) is not SecondaryMetricsPolicy:
        raise PaperSecondaryMetricsEvidenceError(_reason("policy_malformed"))
    if type(records) not in (tuple, list):
        raise PaperSecondaryMetricsEvidenceError(_reason("records_malformed"))
    record_tuple = tuple(records)
    if len(record_tuple) == 0:
        raise PaperSecondaryMetricsEvidenceError(_reason("records_empty"))
    if len(record_tuple) > _MAX_RECORDS:
        raise PaperSecondaryMetricsEvidenceError(_reason("records_too_many"))
    if any(type(record) is not TradeRecordEvidence for record in record_tuple):
        raise PaperSecondaryMetricsEvidenceError(_reason("record_malformed"))
    evidence_id = _require_plain_non_empty_string(evidence_id, "evidence_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (evidence_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperSecondaryMetricsEvidenceError(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperSecondaryMetricsEvidenceError(_reason("clock_token_forbidden"))

    hard: list[str] = []
    hard.extend(_policy_failures(policy))

    policy_id = policy.policy_id if _is_plain_non_empty_string(policy.policy_id) else ""
    for record in record_tuple:
        hard.extend(_record_failures(record, policy_id))

    record_ids = [record.record_id for record in record_tuple]
    record_digests = [record.record_digest for record in record_tuple]
    if len(set(record_ids)) != len(record_ids):
        hard.append(_reason("duplicate_record_id"))
    if len(set(record_digests)) != len(record_digests):
        hard.append(_reason("duplicate_record_digest"))

    verified_policy_digest = policy.policy_digest if _is_hex64_string(policy.policy_digest) else ""
    sorted_digests = tuple(sorted(set(record_digests))) if all(_is_hex64_string(d) for d in record_digests) else ()

    approved_hit = policy.approved_hit_rate_floor
    approved_fill = policy.approved_fill_rate_floor
    approved_slippage = policy.approved_slippage_ceiling_bps
    approved_min = policy.approved_min_decided_episode_count

    # Metric computation is only trustworthy once the set is trusted; on any hard failure we emit a REJECTED
    # record with zeroed metrics rather than compute over untrusted inputs.
    if hard:
        metrics: _Metrics | None = None
    else:
        metrics = _compute_metrics(record_tuple)

    hit_rate_str: str | None = None
    fill_rate_qty_str: str | None = None
    fill_rate_ep_str: str | None = None
    avg_slippage_str: str | None = None
    intended_sum_str = ""
    filled_sum_str = ""
    decided_count = 0
    positive_count = 0
    filled_count = 0
    hit_ok = False
    fill_ok = False
    slippage_ok = False
    sufficient = False
    thresholds_cleared = False

    if metrics is not None:
        decided_count = metrics.decided
        positive_count = metrics.positive
        filled_count = metrics.filled
        intended_sum_str = _format_decimal_scale18(metrics.intended_sum)
        filled_sum_str = _format_decimal_scale18(metrics.filled_sum)
        fill_rate_qty_str = _format_fraction_scale18(metrics.fill_rate_qty)
        fill_rate_ep_str = _format_fraction_scale18(metrics.fill_rate_ep)
        if metrics.hit_rate is not None:
            hit_rate_str = _format_fraction_scale18(metrics.hit_rate)
        if metrics.avg_slippage is not None:
            avg_slippage_str = _format_fraction_scale18(metrics.avg_slippage)

        hit_floor = _fraction_from_scale18(approved_hit)  # type: ignore[arg-type]
        fill_floor = _fraction_from_scale18(approved_fill)  # type: ignore[arg-type]
        slippage_ceiling = _fraction_from_scale18(approved_slippage)  # type: ignore[arg-type]

        sufficient = decided_count >= approved_min  # type: ignore[operator]
        hit_ok = metrics.hit_rate is not None and metrics.hit_rate >= hit_floor
        fill_ok = metrics.fill_rate_qty >= fill_floor and metrics.fill_rate_ep >= fill_floor
        slippage_ok = metrics.avg_slippage is None or metrics.avg_slippage <= slippage_ceiling

    if hard:
        status = PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
        reason_codes = _sorted_unique(hard)
    elif not sufficient:
        status = PaperSecondaryMetricsEvidenceStatus.INSUFFICIENT_EVIDENCE
        reason_codes = (_reason("insufficient_decided_episodes"),)
    else:
        threshold_failures: list[str] = []
        if not hit_ok:
            threshold_failures.append(_reason("hit_rate_below_floor"))
        if not fill_ok:
            threshold_failures.append(_reason("fill_rate_below_floor"))
        if not slippage_ok:
            threshold_failures.append(_reason("slippage_above_ceiling"))
        if threshold_failures:
            status = PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
            reason_codes = _sorted_unique(threshold_failures)
        else:
            status = PaperSecondaryMetricsEvidenceStatus.METRICS_READY
            reason_codes = ()
            thresholds_cleared = True

    ready = status is PaperSecondaryMetricsEvidenceStatus.METRICS_READY

    evidence_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "evidence_version": _EVIDENCE_VERSION,
        "status": status,
        "ready": ready,
        "evidence_id": evidence_id,
        "correlation_id": correlation_id,
        "policy_id": policy_id,
        "verified_policy_digest": verified_policy_digest,
        "record_count": len(record_tuple),
        "decided_episode_count": decided_count,
        "positive_pnl_episode_count": positive_count,
        "filled_episode_count": filled_count,
        "intended_quantity_sum": intended_sum_str,
        "filled_quantity_sum": filled_sum_str,
        "hit_rate": hit_rate_str,
        "fill_rate_by_quantity": fill_rate_qty_str,
        "fill_rate_by_episode": fill_rate_ep_str,
        "average_slippage_bps": avg_slippage_str,
        "approved_hit_rate_floor": approved_hit,
        "approved_fill_rate_floor": approved_fill,
        "approved_slippage_ceiling_bps": approved_slippage,
        "approved_min_decided_episode_count": approved_min,
        "hit_rate_operator": _HIT_RATE_OPERATOR,
        "fill_rate_operator": _FILL_RATE_OPERATOR,
        "slippage_operator": _SLIPPAGE_OPERATOR,
        "hit_rate_satisfied": hit_ok and not hard and sufficient,
        "fill_rate_satisfied": fill_ok and not hard and sufficient,
        "slippage_satisfied": slippage_ok and not hard and sufficient,
        "sufficient_evidence": sufficient and not hard,
        "thresholds_cleared": thresholds_cleared,
        "decimal_policy": _DECIMAL_POLICY,
        "decimal_scale": _DECIMAL_SCALE,
        "decimal_rounding": _DECIMAL_ROUNDING,
        "decimal_internal_precision": _DECIMAL_INTERNAL_PRECISION,
        "record_digests": sorted_digests,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperSecondaryMetricsEvidence(evidence_digest="", **evidence_fields)  # type: ignore[arg-type]
    return _replace_evidence_digest(seed, paper_secondary_metrics_evidence_digest(seed))


def _replace_evidence_digest(evidence: PaperSecondaryMetricsEvidence, digest: str) -> PaperSecondaryMetricsEvidence:
    values = {
        field.name: getattr(evidence, field.name) for field in fields(evidence) if field.name != "evidence_digest"
    }
    values["evidence_digest"] = digest
    return PaperSecondaryMetricsEvidence(**values)  # type: ignore[arg-type]


def _evidence_payload_from(evidence: PaperSecondaryMetricsEvidence) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(evidence):
        if field.name == "evidence_digest":
            continue
        value = getattr(evidence, field.name)
        if field.name == "status":
            payload[field.name] = value.value if isinstance(value, PaperSecondaryMetricsEvidenceStatus) else value
        elif field.name == "reason_codes":
            payload[field.name] = list(evidence.reason_codes)
        elif field.name == "record_digests":
            payload[field.name] = list(evidence.record_digests)
        elif field.name == "metadata":
            payload[field.name] = _serialize_metadata(evidence.metadata)
        else:
            payload[field.name] = value
    return payload


def paper_secondary_metrics_evidence_to_dict(evidence: PaperSecondaryMetricsEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for the SM-4 evidence, including its self-digest."""

    payload = _evidence_payload_from(evidence)
    payload["evidence_digest"] = evidence.evidence_digest
    return payload


def paper_secondary_metrics_evidence_digest(evidence: PaperSecondaryMetricsEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only the self-digest field."""

    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperSecondaryMetricsEvidence",
    "PaperSecondaryMetricsEvidenceError",
    "PaperSecondaryMetricsEvidenceStatus",
    "build_paper_secondary_metrics_evidence",
    "paper_secondary_metrics_evidence_digest",
    "paper_secondary_metrics_evidence_to_dict",
]
