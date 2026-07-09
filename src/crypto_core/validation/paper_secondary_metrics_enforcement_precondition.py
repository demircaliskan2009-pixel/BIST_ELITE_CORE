"""Validation-only secondary-metrics enforcement precondition bridge.

This artifact binds the merged SM-2 ``SecondaryMetricsPolicy``, SM-4
``PaperSecondaryMetricsEvidence``, and PR #327
``PaperSecondaryMetricsSubstrateReconciliation`` into one deterministic
precondition that later SM-5/SM-6 artifacts can require. It re-proves every
consumed self-digest, rechecks the SM-4 metrics against the SM-2 approved
thresholds, and requires the #327 reconciliation to be ``RECONCILED``.

It does not implement SM-5 or SM-6, does not call the Stage-4 comparator, does
not update any completion decision, and does not claim Stage-4 completion,
runtime readiness, live/shadow readiness, real fills, orders, or capital
authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_secondary_metrics_evidence import (
    PaperSecondaryMetricsEvidence,
    PaperSecondaryMetricsEvidenceStatus,
    paper_secondary_metrics_evidence_digest,
)
from crypto_core.validation.paper_secondary_metrics_substrate_reconciliation import (
    PaperSecondaryMetricsSubstrateReconciliation,
    PaperSecondaryMetricsSubstrateReconciliationStatus,
    paper_secondary_metrics_substrate_reconciliation_digest,
)
from crypto_core.validation.secondary_metrics_policy import (
    SecondaryMetricsPolicy,
    SecondaryMetricsPolicyStatus,
    secondary_metrics_policy_digest,
)

_SCHEMA_VERSION = "paper-secondary-metrics-enforcement-precondition.v1"
_PRECONDITION_VERSION = "paper-secondary-metrics-enforcement-precondition.v1"
_REASON_PREFIX = "paper_secondary_metrics_enforcement_precondition"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_SCALE18_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{18}$")
_NEGATIVE_ZERO_SCALE18 = "-0.000000000000000000"
_MAX_SCALE18_LENGTH = 60

_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"\b(?:live|private|order_router|real_order|scheduler|deribit_ready|shadow|capital_mutation|"
    r"stage4_complete|sm5_enabled|sm6_enabled)\b",
    re.IGNORECASE,
)
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
_METRICS_TRUE_FLAGS = ("paper_only", "evidence_only", "thresholds_enforced_here_not_by_comparator")
_METRICS_FALSE_FLAGS = (
    "comparator_invoked",
    "secondary_metrics_enforced",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "pnl_authoritative",
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
    "production_execution",
)
_RECONCILIATION_TRUE_FLAGS = ("paper_only", "validation_only")
_RECONCILIATION_FALSE_FLAGS = (
    "live_ready",
    "shadow_ready",
    "connector_ready",
    "orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "stage4_complete",
    "sm5_enabled",
    "sm6_enabled",
)


class PaperSecondaryMetricsEnforcementPreconditionError(RuntimeError):
    """Raised on malformed caller input for the secondary-metrics precondition bridge."""


class PaperSecondaryMetricsEnforcementPreconditionStatus(str, Enum):
    """Precondition status. READY is bridge readiness only, never SM-5/SM-6 or Stage-4 completion."""

    PRECONDITION_READY = "PRECONDITION_READY"
    PRECONDITION_REJECTED = "PRECONDITION_REJECTED"


@dataclass(frozen=True)
class PaperSecondaryMetricsEnforcementPrecondition:
    """Immutable, digest-bound validation bridge over SM-2, SM-4, and #327 reconciliation."""

    schema_version: str
    precondition_version: str
    status: PaperSecondaryMetricsEnforcementPreconditionStatus
    ready: bool
    precondition_id: str
    correlation_id: str
    policy_id: str
    market_symbol: str
    policy_digest: str
    metrics_evidence_digest: str
    reconciliation_digest: str
    approved_hit_rate_floor: str | None
    computed_hit_rate: str | None
    hit_rate_passed: bool
    approved_fill_rate_floor: str | None
    computed_fill_rate_by_quantity: str | None
    computed_fill_rate_by_episode: str | None
    fill_rate_by_quantity_passed: bool
    fill_rate_by_episode_passed: bool
    fill_rate_passed: bool
    approved_slippage_ceiling_bps: str | None
    computed_slippage_bps: str | None
    slippage_passed: bool
    approved_min_decided_episode_count: int | None
    computed_decided_episode_count: int
    min_decided_episode_count_passed: bool
    metrics_record_count: int
    reconciled_record_count: int
    reconciled_episode_count: int
    record_digests: tuple[str, ...]
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    precondition_digest: str
    paper_only: bool = True
    validation_only: bool = True
    live_ready: bool = False
    shadow_ready: bool = False
    connector_ready: bool = False
    orders_enabled: bool = False
    real_fills_used: bool = False
    authoritative_pnl: bool = False
    capital_mutation_enabled: bool = False
    scheduler_enabled: bool = False
    stage4_complete: bool = False
    sm5_enabled: bool = False
    sm6_enabled: bool = False


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


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _require_hex64(value: object, field_name: str) -> str:
    if not _is_hex64_string(value):
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("metadata_malformed"))
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
        if _BIST_PATTERN.search(text) or _FORBIDDEN_PATTERN.search(text):
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


def _recomputed_digest_or_none(compute: object, artifact: object) -> str | None:
    try:
        return compute(artifact)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection
        return None


def _parse_scale18(value: object) -> Decimal | None:
    if (
        type(value) is not str
        or len(value) > _MAX_SCALE18_LENGTH
        or value == _NEGATIVE_ZERO_SCALE18
        or not _SCALE18_PATTERN.fullmatch(value)
    ):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _flag_failure(artifact: object, true_flags: tuple[str, ...], false_flags: tuple[str, ...]) -> bool:
    return any(getattr(artifact, flag) is not True for flag in true_flags) or any(
        getattr(artifact, flag) is not False for flag in false_flags
    )


def _digest_reproof_failed(*, artifact: object, carried_digest: object, expected_digest: str, compute: object) -> bool:
    recomputed = _recomputed_digest_or_none(compute, artifact)
    return recomputed is None or carried_digest != recomputed or carried_digest != expected_digest


def _threshold_flags(
    policy: SecondaryMetricsPolicy,
    metrics_evidence: PaperSecondaryMetricsEvidence,
) -> tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool]:
    hit_floor = _parse_scale18(policy.approved_hit_rate_floor)
    fill_floor = _parse_scale18(policy.approved_fill_rate_floor)
    slippage_ceiling = _parse_scale18(policy.approved_slippage_ceiling_bps)
    hit_rate = _parse_scale18(metrics_evidence.hit_rate)
    fill_quantity = _parse_scale18(metrics_evidence.fill_rate_by_quantity)
    fill_episode = _parse_scale18(metrics_evidence.fill_rate_by_episode)
    slippage = _parse_scale18(metrics_evidence.average_slippage_bps)

    hit_passed = hit_floor is not None and hit_rate is not None and hit_rate >= hit_floor
    fill_quantity_passed = fill_floor is not None and fill_quantity is not None and fill_quantity >= fill_floor
    fill_episode_passed = fill_floor is not None and fill_episode is not None and fill_episode >= fill_floor
    fill_passed = fill_quantity_passed and fill_episode_passed
    slippage_passed = slippage_ceiling is not None and (
        metrics_evidence.average_slippage_bps is None or (slippage is not None and slippage <= slippage_ceiling)
    )
    min_decided_passed = (
        _is_exact_int(policy.approved_min_decided_episode_count)
        and _is_exact_int(metrics_evidence.decided_episode_count)
        and metrics_evidence.decided_episode_count >= policy.approved_min_decided_episode_count
    )
    snapshot_matches = (
        metrics_evidence.approved_hit_rate_floor == policy.approved_hit_rate_floor
        and metrics_evidence.approved_fill_rate_floor == policy.approved_fill_rate_floor
        and metrics_evidence.approved_slippage_ceiling_bps == policy.approved_slippage_ceiling_bps
        and metrics_evidence.approved_min_decided_episode_count == policy.approved_min_decided_episode_count
    )
    boolean_snapshot_matches = (
        metrics_evidence.hit_rate_satisfied is hit_passed
        and metrics_evidence.fill_rate_satisfied is fill_passed
        and metrics_evidence.slippage_satisfied is slippage_passed
        and metrics_evidence.sufficient_evidence is min_decided_passed
        and metrics_evidence.thresholds_cleared
        is (hit_passed and fill_passed and slippage_passed and min_decided_passed)
    )
    return (
        hit_passed,
        fill_quantity_passed,
        fill_episode_passed,
        fill_passed,
        slippage_passed,
        min_decided_passed,
        snapshot_matches,
        boolean_snapshot_matches,
        hit_passed and fill_passed and slippage_passed and min_decided_passed,
    )


def _record_set_matches(
    metrics_evidence: PaperSecondaryMetricsEvidence,
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
) -> bool:
    metrics_digests = metrics_evidence.record_digests if type(metrics_evidence.record_digests) is tuple else ()
    reconciliation_digests = (
        reconciliation.reconciled_record_digests if type(reconciliation.reconciled_record_digests) is tuple else ()
    )
    return (
        metrics_digests == reconciliation_digests
        and len(metrics_digests) == metrics_evidence.record_count
        and len(reconciliation_digests) == reconciliation.episode_count
        and metrics_evidence.record_count == reconciliation.episode_count
        and metrics_evidence.filled_episode_count == reconciliation.filled_episode_count
        and metrics_evidence.positive_pnl_episode_count == reconciliation.positive_pnl_episode_count
    )


def build_paper_secondary_metrics_enforcement_precondition(
    policy: SecondaryMetricsPolicy,
    metrics_evidence: PaperSecondaryMetricsEvidence,
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
    *,
    precondition_id: str,
    correlation_id: str,
    expected_policy_digest: str,
    expected_metrics_evidence_digest: str,
    expected_reconciliation_digest: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSecondaryMetricsEnforcementPrecondition:
    """Build a validation-only bridge required before later SM-5/SM-6 can consume secondary metrics."""

    if type(policy) is not SecondaryMetricsPolicy:
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("policy_malformed"))
    if type(metrics_evidence) is not PaperSecondaryMetricsEvidence:
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("metrics_evidence_malformed"))
    if type(reconciliation) is not PaperSecondaryMetricsSubstrateReconciliation:
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("reconciliation_malformed"))
    precondition_id = _require_plain_non_empty_string(precondition_id, "precondition_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    expected_policy_digest = _require_hex64(expected_policy_digest, "expected_policy_digest")
    expected_metrics_evidence_digest = _require_hex64(
        expected_metrics_evidence_digest, "expected_metrics_evidence_digest"
    )
    expected_reconciliation_digest = _require_hex64(expected_reconciliation_digest, "expected_reconciliation_digest")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (precondition_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperSecondaryMetricsEnforcementPreconditionError(_reason("clock_token_forbidden"))

    hard: list[str] = []

    if _digest_reproof_failed(
        artifact=policy,
        carried_digest=policy.policy_digest,
        expected_digest=expected_policy_digest,
        compute=secondary_metrics_policy_digest,
    ):
        hard.append(_reason("policy_digest_mismatch"))
    if _digest_reproof_failed(
        artifact=metrics_evidence,
        carried_digest=metrics_evidence.evidence_digest,
        expected_digest=expected_metrics_evidence_digest,
        compute=paper_secondary_metrics_evidence_digest,
    ):
        hard.append(_reason("metrics_evidence_digest_mismatch"))
    if _digest_reproof_failed(
        artifact=reconciliation,
        carried_digest=reconciliation.reconciliation_digest,
        expected_digest=expected_reconciliation_digest,
        compute=paper_secondary_metrics_substrate_reconciliation_digest,
    ):
        hard.append(_reason("reconciliation_digest_mismatch"))

    if (
        policy.status is not SecondaryMetricsPolicyStatus.POLICY_READY
        or policy.ready is not True
        or policy.reason_codes
    ):
        hard.append(_reason("policy_not_ready"))
    if (
        metrics_evidence.status is not PaperSecondaryMetricsEvidenceStatus.METRICS_READY
        or metrics_evidence.ready is not True
        or metrics_evidence.reason_codes
    ):
        hard.append(_reason("metrics_evidence_not_ready"))
    if (
        reconciliation.status is not PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED
        or reconciliation.ready is not True
        or reconciliation.reason_codes
    ):
        hard.append(_reason("reconciliation_not_ready"))

    if (
        metrics_evidence.policy_id != policy.policy_id
        or metrics_evidence.verified_policy_digest != policy.policy_digest
    ):
        hard.append(_reason("metrics_evidence_policy_mismatch"))
    if reconciliation.policy_id != policy.policy_id or reconciliation.verified_policy_digest != policy.policy_digest:
        hard.append(_reason("reconciliation_policy_mismatch"))
    if reconciliation.verified_metrics_evidence_digest != metrics_evidence.evidence_digest:
        hard.append(_reason("reconciliation_metrics_evidence_mismatch"))
    if (
        policy.correlation_id != correlation_id
        or metrics_evidence.correlation_id != correlation_id
        or reconciliation.correlation_id != correlation_id
    ):
        hard.append(_reason("correlation_id_mismatch"))
    if not _record_set_matches(metrics_evidence, reconciliation):
        hard.append(_reason("record_set_mismatch"))

    (
        hit_passed,
        fill_quantity_passed,
        fill_episode_passed,
        fill_passed,
        slippage_passed,
        min_decided_passed,
        snapshot_matches,
        boolean_snapshot_matches,
        thresholds_cleared,
    ) = _threshold_flags(policy, metrics_evidence)
    if not hit_passed:
        hard.append(_reason("hit_rate_floor_not_met"))
    if not fill_passed:
        hard.append(_reason("fill_rate_floor_not_met"))
    if not slippage_passed:
        hard.append(_reason("slippage_ceiling_exceeded"))
    if not min_decided_passed:
        hard.append(_reason("min_decided_episode_count_not_met"))
    if not snapshot_matches or not boolean_snapshot_matches:
        hard.append(_reason("threshold_snapshot_mismatch"))

    if (
        _flag_failure(policy, _POLICY_TRUE_FLAGS, _POLICY_FALSE_FLAGS)
        or _flag_failure(metrics_evidence, _METRICS_TRUE_FLAGS, _METRICS_FALSE_FLAGS)
        or _flag_failure(reconciliation, _RECONCILIATION_TRUE_FLAGS, _RECONCILIATION_FALSE_FLAGS)
    ):
        hard.append(_reason("unsafe_flags"))

    reason_codes = _sorted_unique(hard)
    status = (
        PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
        if reason_codes
        else PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_READY
    )
    ready = status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_READY
    if ready and not thresholds_cleared:
        # Unreachable under the reason-code checks above; kept as a defensive fail-closed guard.
        status = PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
        ready = False
        reason_codes = (_reason("threshold_snapshot_mismatch"),)

    metrics_record_digests = metrics_evidence.record_digests if type(metrics_evidence.record_digests) is tuple else ()
    reconciliation_record_digests = (
        reconciliation.reconciled_record_digests if type(reconciliation.reconciled_record_digests) is tuple else ()
    )

    precondition_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "precondition_version": _PRECONDITION_VERSION,
        "status": status,
        "ready": ready,
        "precondition_id": precondition_id,
        "correlation_id": correlation_id,
        "policy_id": policy.policy_id,
        "market_symbol": reconciliation.market_symbol,
        "policy_digest": policy.policy_digest if _is_hex64_string(policy.policy_digest) else "",
        "metrics_evidence_digest": metrics_evidence.evidence_digest
        if _is_hex64_string(metrics_evidence.evidence_digest)
        else "",
        "reconciliation_digest": reconciliation.reconciliation_digest
        if _is_hex64_string(reconciliation.reconciliation_digest)
        else "",
        "approved_hit_rate_floor": policy.approved_hit_rate_floor,
        "computed_hit_rate": metrics_evidence.hit_rate,
        "hit_rate_passed": hit_passed,
        "approved_fill_rate_floor": policy.approved_fill_rate_floor,
        "computed_fill_rate_by_quantity": metrics_evidence.fill_rate_by_quantity,
        "computed_fill_rate_by_episode": metrics_evidence.fill_rate_by_episode,
        "fill_rate_by_quantity_passed": fill_quantity_passed,
        "fill_rate_by_episode_passed": fill_episode_passed,
        "fill_rate_passed": fill_passed,
        "approved_slippage_ceiling_bps": policy.approved_slippage_ceiling_bps,
        "computed_slippage_bps": metrics_evidence.average_slippage_bps,
        "slippage_passed": slippage_passed,
        "approved_min_decided_episode_count": policy.approved_min_decided_episode_count,
        "computed_decided_episode_count": metrics_evidence.decided_episode_count
        if _is_exact_int(metrics_evidence.decided_episode_count)
        else 0,
        "min_decided_episode_count_passed": min_decided_passed,
        "metrics_record_count": metrics_evidence.record_count if _is_exact_int(metrics_evidence.record_count) else 0,
        "reconciled_record_count": len(reconciliation_record_digests),
        "reconciled_episode_count": reconciliation.episode_count if _is_exact_int(reconciliation.episode_count) else 0,
        "record_digests": metrics_record_digests,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperSecondaryMetricsEnforcementPrecondition(precondition_digest="", **precondition_fields)  # type: ignore[arg-type]
    return _replace_precondition_digest(seed, paper_secondary_metrics_enforcement_precondition_digest(seed))


def _replace_precondition_digest(
    precondition: PaperSecondaryMetricsEnforcementPrecondition, digest: str
) -> PaperSecondaryMetricsEnforcementPrecondition:
    values = {
        field.name: getattr(precondition, field.name)
        for field in fields(precondition)
        if field.name != "precondition_digest"
    }
    values["precondition_digest"] = digest
    return PaperSecondaryMetricsEnforcementPrecondition(**values)  # type: ignore[arg-type]


def _precondition_payload_from(precondition: PaperSecondaryMetricsEnforcementPrecondition) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(precondition):
        if field.name == "precondition_digest":
            continue
        value = getattr(precondition, field.name)
        if field.name == "status":
            payload[field.name] = (
                value.value if isinstance(value, PaperSecondaryMetricsEnforcementPreconditionStatus) else value
            )
        elif field.name == "reason_codes":
            payload[field.name] = list(precondition.reason_codes)
        elif field.name == "record_digests":
            payload[field.name] = list(precondition.record_digests)
        elif field.name == "metadata":
            payload[field.name] = _serialize_metadata(precondition.metadata)
        else:
            payload[field.name] = value
    return payload


def paper_secondary_metrics_enforcement_precondition_to_dict(
    precondition: PaperSecondaryMetricsEnforcementPrecondition,
) -> dict[str, object]:
    """Canonical JSON-ready mapping for the precondition, including its self-digest."""

    payload = _precondition_payload_from(precondition)
    payload["precondition_digest"] = precondition.precondition_digest
    return payload


def paper_secondary_metrics_enforcement_precondition_digest(
    precondition: PaperSecondaryMetricsEnforcementPrecondition,
) -> str:
    """Recompute the canonical precondition digest, excluding only the self-digest field."""

    return _canonical_digest(_precondition_payload_from(precondition))


__all__ = [
    "PaperSecondaryMetricsEnforcementPrecondition",
    "PaperSecondaryMetricsEnforcementPreconditionError",
    "PaperSecondaryMetricsEnforcementPreconditionStatus",
    "build_paper_secondary_metrics_enforcement_precondition",
    "paper_secondary_metrics_enforcement_precondition_digest",
    "paper_secondary_metrics_enforcement_precondition_to_dict",
]
