"""Paper governor readiness decision audit record.

Projects a validated ``PaperGovernorReadiness`` verdict into a deterministic,
immutable, audit-recordable paper-governor readiness record. This is a projection
only: no persistence, controller wiring, scheduler, venue, route, order intent,
or live/private execution path is created.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from crypto_core.audit.decision_ledger import DecisionEvidenceRef
from crypto_core.audit.portfolio_governor_readiness import (
    PaperGovernorReadiness,
    PaperGovernorReadinessStatus,
)

_READINESS_RECORD_SCHEMA_VERSION = "paper-governor-readiness-record.v1"
_READINESS_SCHEMA_VERSION = "paper-governor-readiness.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

_EVIDENCE_SOURCE_READINESS = "paper_governor_readiness"
_EVIDENCE_SOURCE_LIFECYCLE = "portfolio_governor_lifecycle"
_EVIDENCE_SOURCE_REPLAY = "portfolio_governor_ledger_replay"
_EVIDENCE_SOURCE_HEAD = "portfolio_governor_ledger_head"
_BLOCKED_PLANS_PRESENT = "paper_governor_readiness:blocked_plans_present"


class PaperGovernorReadinessRecordError(RuntimeError):
    """Raised when a readiness record projection input is malformed or tampered."""


@dataclass(frozen=True)
class PaperGovernorReadinessRecord:
    """Deterministic paper-only audit record for a readiness verdict."""

    record_schema_version: str
    status: PaperGovernorReadinessStatus
    ready: bool
    head_digest: str | None
    entry_count: int
    active_count: int
    blocked_count: int
    total_active_weight: float
    total_active_notional: float
    max_current_active_weight: float | None
    max_current_active_notional: float | None
    blocked_plans_block_readiness: bool
    block_reasons: tuple[str, ...]
    blocker_summary: tuple[str, ...]
    replay_digest: str
    lifecycle_digest: str
    readiness_digest: str
    evidence_refs: tuple[DecisionEvidenceRef, ...]
    correlation_id: str | None
    previous_record_digest: str | None
    record_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_hex_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _optional_sha256_hex_digest(value: object) -> bool:
    return value is None or _sha256_hex_digest(value)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _is_non_negative_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _is_non_negative_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _optional_non_negative_finite(value: object) -> bool:
    return value is None or _is_non_negative_finite(value)


def _stable_string_tuple(values: object) -> bool:
    return (
        isinstance(values, tuple)
        and all(_non_empty_str(value) for value in values)
        and values == tuple(sorted(set(values)))
    )


def _expected_readiness_digest(readiness: PaperGovernorReadiness) -> str:
    payload: dict[str, object] = {
        "schema_version": _READINESS_SCHEMA_VERSION,
        "status": readiness.status.value,
        "head_digest": readiness.head_digest,
        "entry_count": readiness.entry_count,
        "active_count": readiness.active_count,
        "blocked_count": readiness.blocked_count,
        "total_active_weight": readiness.total_active_weight,
        "total_active_notional": readiness.total_active_notional,
        "max_current_active_weight": readiness.max_current_active_weight,
        "max_current_active_notional": readiness.max_current_active_notional,
        "blocked_plans_block_readiness": readiness.blocked_plans_block_readiness,
        "block_reasons": list(readiness.block_reasons),
        "blocker_summary": list(readiness.blocker_summary),
        "replay_digest": readiness.replay_digest,
        "lifecycle_digest": readiness.lifecycle_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return _canonical_digest(payload)


def _validate_readiness(readiness: object) -> PaperGovernorReadiness:
    if not isinstance(readiness, PaperGovernorReadiness):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:readiness_malformed")
    if readiness.schema_version != _READINESS_SCHEMA_VERSION:
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:schema_version_unexpected")
    if not isinstance(readiness.status, PaperGovernorReadinessStatus):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:status_malformed")
    if not isinstance(readiness.ready, bool) or readiness.ready != (
        readiness.status is PaperGovernorReadinessStatus.READY
    ):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:ready_status_mismatch")
    if not (
        readiness.paper_only is True
        and readiness.real_orders_enabled is False
        and readiness.real_money_enabled is False
    ):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:non_paper_readiness_rejected")
    if not (
        _sha256_hex_digest(readiness.readiness_digest)
        and _sha256_hex_digest(readiness.replay_digest)
        and _sha256_hex_digest(readiness.lifecycle_digest)
        and _optional_sha256_hex_digest(readiness.head_digest)
    ):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:digest_invalid")
    if readiness.readiness_digest != _expected_readiness_digest(readiness):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:readiness_digest_mismatch")
    if not (
        _is_non_negative_int(readiness.entry_count)
        and _is_non_negative_int(readiness.active_count)
        and _is_non_negative_int(readiness.blocked_count)
        and readiness.active_count <= readiness.entry_count
        and readiness.blocked_count <= readiness.entry_count
    ):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:counts_invalid")
    if not (
        _is_non_negative_finite(readiness.total_active_weight)
        and _is_non_negative_finite(readiness.total_active_notional)
        and _optional_non_negative_finite(readiness.max_current_active_weight)
        and _optional_non_negative_finite(readiness.max_current_active_notional)
    ):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:exposure_invalid")
    if readiness.active_count == 0 and (readiness.total_active_weight != 0.0 or readiness.total_active_notional != 0.0):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:exposure_count_mismatch")
    if not isinstance(readiness.blocked_plans_block_readiness, bool):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:policy_flag_invalid")
    if not _stable_string_tuple(readiness.block_reasons):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:block_reasons_invalid")
    if not _stable_string_tuple(readiness.blocker_summary):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:blocker_summary_invalid")
    if readiness.status is PaperGovernorReadinessStatus.READY and readiness.block_reasons:
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:ready_with_block_reasons")
    if readiness.status is not PaperGovernorReadinessStatus.READY and not readiness.block_reasons:
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:blocked_without_reason")
    expected_status = (
        PaperGovernorReadinessStatus.READY
        if not readiness.block_reasons
        else PaperGovernorReadinessStatus.BLOCKED
        if _BLOCKED_PLANS_PRESENT in readiness.block_reasons
        else PaperGovernorReadinessStatus.OVER_BUDGET
    )
    if readiness.status is not expected_status:
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:status_reason_mismatch")
    if readiness.blocked_plans_block_readiness and readiness.blocked_count > 0:
        if _BLOCKED_PLANS_PRESENT not in readiness.block_reasons:
            raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:blocked_reason_missing")
    return readiness


def _build_evidence_refs(readiness: PaperGovernorReadiness) -> tuple[DecisionEvidenceRef, ...]:
    refs: list[DecisionEvidenceRef] = [
        DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_READINESS, digest=readiness.readiness_digest),
        DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_LIFECYCLE, digest=readiness.lifecycle_digest),
        DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_REPLAY, digest=readiness.replay_digest),
    ]
    if readiness.head_digest is not None:
        refs.append(DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_HEAD, digest=readiness.head_digest))
    return tuple(refs)


def build_paper_governor_readiness_record(
    readiness: PaperGovernorReadiness,
    *,
    correlation_id: str | None = None,
    previous_record_digest: str | None = None,
) -> PaperGovernorReadinessRecord:
    """Project a validated readiness verdict into an audit-recordable immutable object."""
    validated = _validate_readiness(readiness)
    if correlation_id is not None and not _non_empty_str(correlation_id):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:correlation_id_invalid")
    if previous_record_digest is not None and not _sha256_hex_digest(previous_record_digest):
        raise PaperGovernorReadinessRecordError("paper_governor_readiness_record:previous_record_digest_invalid")

    evidence_refs = _build_evidence_refs(validated)
    record_payload: dict[str, object] = {
        "record_schema_version": _READINESS_RECORD_SCHEMA_VERSION,
        "status": validated.status.value,
        "ready": validated.ready,
        "head_digest": validated.head_digest,
        "entry_count": validated.entry_count,
        "active_count": validated.active_count,
        "blocked_count": validated.blocked_count,
        "total_active_weight": validated.total_active_weight,
        "total_active_notional": validated.total_active_notional,
        "max_current_active_weight": validated.max_current_active_weight,
        "max_current_active_notional": validated.max_current_active_notional,
        "blocked_plans_block_readiness": validated.blocked_plans_block_readiness,
        "block_reasons": list(validated.block_reasons),
        "blocker_summary": list(validated.blocker_summary),
        "replay_digest": validated.replay_digest,
        "lifecycle_digest": validated.lifecycle_digest,
        "readiness_digest": validated.readiness_digest,
        "evidence_refs": [[ref.source_type, ref.digest, ref.source_id] for ref in evidence_refs],
        "correlation_id": correlation_id,
        "previous_record_digest": previous_record_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PaperGovernorReadinessRecord(
        record_schema_version=_READINESS_RECORD_SCHEMA_VERSION,
        status=validated.status,
        ready=validated.ready,
        head_digest=validated.head_digest,
        entry_count=validated.entry_count,
        active_count=validated.active_count,
        blocked_count=validated.blocked_count,
        total_active_weight=validated.total_active_weight,
        total_active_notional=validated.total_active_notional,
        max_current_active_weight=validated.max_current_active_weight,
        max_current_active_notional=validated.max_current_active_notional,
        blocked_plans_block_readiness=validated.blocked_plans_block_readiness,
        block_reasons=validated.block_reasons,
        blocker_summary=validated.blocker_summary,
        replay_digest=validated.replay_digest,
        lifecycle_digest=validated.lifecycle_digest,
        readiness_digest=validated.readiness_digest,
        evidence_refs=evidence_refs,
        correlation_id=correlation_id,
        previous_record_digest=previous_record_digest,
        record_digest=_canonical_digest(record_payload),
    )


def paper_governor_readiness_record_to_dict(record: PaperGovernorReadinessRecord) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper-governor readiness audit record."""
    return {
        "record_schema_version": record.record_schema_version,
        "status": record.status.value,
        "ready": record.ready,
        "head_digest": record.head_digest,
        "entry_count": record.entry_count,
        "active_count": record.active_count,
        "blocked_count": record.blocked_count,
        "total_active_weight": record.total_active_weight,
        "total_active_notional": record.total_active_notional,
        "max_current_active_weight": record.max_current_active_weight,
        "max_current_active_notional": record.max_current_active_notional,
        "blocked_plans_block_readiness": record.blocked_plans_block_readiness,
        "block_reasons": list(record.block_reasons),
        "blocker_summary": list(record.blocker_summary),
        "replay_digest": record.replay_digest,
        "lifecycle_digest": record.lifecycle_digest,
        "readiness_digest": record.readiness_digest,
        "evidence_refs": [
            {"source_type": ref.source_type, "digest": ref.digest, "source_id": ref.source_id}
            for ref in record.evidence_refs
        ],
        "correlation_id": record.correlation_id,
        "previous_record_digest": record.previous_record_digest,
        "record_digest": record.record_digest,
        "paper_only": record.paper_only,
        "real_orders_enabled": record.real_orders_enabled,
        "real_money_enabled": record.real_money_enabled,
    }


__all__ = [
    "PaperGovernorReadinessRecord",
    "PaperGovernorReadinessRecordError",
    "build_paper_governor_readiness_record",
    "paper_governor_readiness_record_to_dict",
]
