"""Append-only paper governor readiness record store.

In-memory, append-only, deterministically-chained repository for
``PaperGovernorReadinessRecord`` objects. This is an audit/read model only: no
disk persistence, controller wiring, scheduler, venue, route, order intent, or
live/private execution path is created.
"""

from __future__ import annotations

import hashlib
import json
import math

from crypto_core.audit.decision_ledger import DecisionEvidenceRef
from crypto_core.audit.portfolio_governor_readiness import PaperGovernorReadinessStatus
from crypto_core.audit.portfolio_governor_readiness_record import PaperGovernorReadinessRecord

_READINESS_RECORD_SCHEMA_VERSION = "paper-governor-readiness-record.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")
_BLOCKED_PLANS_PRESENT = "paper_governor_readiness:blocked_plans_present"

_EVIDENCE_SOURCE_READINESS = "paper_governor_readiness"
_EVIDENCE_SOURCE_LIFECYCLE = "portfolio_governor_lifecycle"
_EVIDENCE_SOURCE_REPLAY = "portfolio_governor_ledger_replay"
_EVIDENCE_SOURCE_HEAD = "portfolio_governor_ledger_head"


class PaperGovernorReadinessRecordStoreError(RuntimeError):
    """Raised when a readiness record is malformed, tampered, or breaks the append chain."""


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _sha256_hex_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _optional_sha256_hex_digest(value: object) -> bool:
    return value is None or _sha256_hex_digest(value)


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


def _expected_evidence_sources(record: PaperGovernorReadinessRecord) -> tuple[str, ...]:
    sources = (_EVIDENCE_SOURCE_READINESS, _EVIDENCE_SOURCE_LIFECYCLE, _EVIDENCE_SOURCE_REPLAY)
    if record.head_digest is not None:
        return (*sources, _EVIDENCE_SOURCE_HEAD)
    return sources


def _expected_evidence_digests(record: PaperGovernorReadinessRecord) -> tuple[str, ...]:
    digests = (record.readiness_digest, record.lifecycle_digest, record.replay_digest)
    if record.head_digest is not None:
        return (*digests, record.head_digest)
    return digests


def _expected_record_digest(record: PaperGovernorReadinessRecord) -> str:
    """Mirror ``build_paper_governor_readiness_record`` digest payload for tamper checks."""
    payload: dict[str, object] = {
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
        "evidence_refs": [[ref.source_type, ref.digest, ref.source_id] for ref in record.evidence_refs],
        "correlation_id": record.correlation_id,
        "previous_record_digest": record.previous_record_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return _canonical_digest(payload)


def _validate_evidence_refs(record: PaperGovernorReadinessRecord) -> None:
    if not isinstance(record.evidence_refs, tuple) or not record.evidence_refs:
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:evidence_refs_missing")
    expected_sources = _expected_evidence_sources(record)
    expected_digests = _expected_evidence_digests(record)
    if tuple(ref.source_type for ref in record.evidence_refs) != expected_sources:
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:evidence_refs_unexpected")
    if tuple(ref.digest for ref in record.evidence_refs) != expected_digests:
        raise PaperGovernorReadinessRecordStoreError(
            "paper_governor_readiness_record_store:evidence_ref_digest_mismatch"
        )
    for ref in record.evidence_refs:
        if not isinstance(ref, DecisionEvidenceRef):
            raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:evidence_ref_malformed")
        if ref.source_id is not None or ref.metadata is not None:
            raise PaperGovernorReadinessRecordStoreError(
                "paper_governor_readiness_record_store:evidence_ref_noncanonical"
            )
        if not _sha256_hex_digest(ref.digest):
            raise PaperGovernorReadinessRecordStoreError(
                "paper_governor_readiness_record_store:evidence_ref_digest_invalid"
            )


def _validate_status_coherence(record: PaperGovernorReadinessRecord) -> None:
    if record.status is PaperGovernorReadinessStatus.READY and record.block_reasons:
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:ready_with_block_reasons")
    if record.status is not PaperGovernorReadinessStatus.READY and not record.block_reasons:
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:blocked_without_reason")
    expected_status = (
        PaperGovernorReadinessStatus.READY
        if not record.block_reasons
        else PaperGovernorReadinessStatus.BLOCKED
        if _BLOCKED_PLANS_PRESENT in record.block_reasons
        else PaperGovernorReadinessStatus.OVER_BUDGET
    )
    if record.status is not expected_status:
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:status_reason_mismatch")
    if record.ready != (record.status is PaperGovernorReadinessStatus.READY):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:ready_status_mismatch")
    if record.blocked_plans_block_readiness and record.blocked_count > 0:
        if _BLOCKED_PLANS_PRESENT not in record.block_reasons:
            raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:blocked_reason_missing")


def _validate_record(record: object) -> PaperGovernorReadinessRecord:
    if not isinstance(record, PaperGovernorReadinessRecord):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:record_malformed")
    if record.record_schema_version != _READINESS_RECORD_SCHEMA_VERSION:
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:schema_version_unexpected")
    if not isinstance(record.status, PaperGovernorReadinessStatus) or not isinstance(record.ready, bool):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:status_malformed")
    if not (record.paper_only is True and record.real_orders_enabled is False and record.real_money_enabled is False):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:non_paper_record_rejected")
    if record.correlation_id is not None and not _non_empty_str(record.correlation_id):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:correlation_id_invalid")
    if not (
        _sha256_hex_digest(record.record_digest)
        and _sha256_hex_digest(record.readiness_digest)
        and _sha256_hex_digest(record.replay_digest)
        and _sha256_hex_digest(record.lifecycle_digest)
        and _optional_sha256_hex_digest(record.head_digest)
        and _optional_sha256_hex_digest(record.previous_record_digest)
    ):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:digest_invalid")
    if not (
        _is_non_negative_int(record.entry_count)
        and _is_non_negative_int(record.active_count)
        and _is_non_negative_int(record.blocked_count)
        and record.active_count <= record.entry_count
        and record.blocked_count <= record.entry_count
    ):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:counts_invalid")
    if not (
        _is_non_negative_finite(record.total_active_weight)
        and _is_non_negative_finite(record.total_active_notional)
        and _optional_non_negative_finite(record.max_current_active_weight)
        and _optional_non_negative_finite(record.max_current_active_notional)
    ):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:exposure_invalid")
    if record.active_count == 0 and (record.total_active_weight != 0.0 or record.total_active_notional != 0.0):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:exposure_count_mismatch")
    if not isinstance(record.blocked_plans_block_readiness, bool):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:policy_flag_invalid")
    if not _stable_string_tuple(record.block_reasons):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:block_reasons_invalid")
    if not _stable_string_tuple(record.blocker_summary):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:blocker_summary_invalid")

    _validate_status_coherence(record)
    _validate_evidence_refs(record)
    if record.record_digest != _expected_record_digest(record):
        raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:record_digest_mismatch")
    return record


class PaperGovernorReadinessRecordStore:
    """Append-only, deterministically-chained in-memory store of readiness records."""

    def __init__(self) -> None:
        self._records: list[PaperGovernorReadinessRecord] = []
        self._by_record_digest: dict[str, PaperGovernorReadinessRecord] = {}

    def __len__(self) -> int:
        return len(self._records)

    def append(self, record: PaperGovernorReadinessRecord) -> PaperGovernorReadinessRecord:
        """Validate and append one record, enforcing the append-only chain."""
        validated = _validate_record(record)
        if validated.record_digest in self._by_record_digest:
            raise PaperGovernorReadinessRecordStoreError(
                "paper_governor_readiness_record_store:duplicate_record_digest"
            )
        if not self._records:
            if validated.previous_record_digest is not None:
                raise PaperGovernorReadinessRecordStoreError(
                    "paper_governor_readiness_record_store:first_record_previous_digest_must_be_none"
                )
        elif validated.previous_record_digest != self._records[-1].record_digest:
            raise PaperGovernorReadinessRecordStoreError(
                "paper_governor_readiness_record_store:previous_record_digest_mismatch"
            )
        self._records.append(validated)
        self._by_record_digest[validated.record_digest] = validated
        return validated

    def snapshot(self) -> tuple[PaperGovernorReadinessRecord, ...]:
        """Full ordered readiness-record snapshot as an immutable tuple."""
        return tuple(self._records)

    def head_digest(self) -> str | None:
        """``record_digest`` of the most recent record, or ``None`` when empty."""
        return self._records[-1].record_digest if self._records else None

    def get_by_record_digest(self, record_digest: str) -> PaperGovernorReadinessRecord | None:
        """Return the record for this digest, or ``None``. Fail closed on malformed queries."""
        if not _sha256_hex_digest(record_digest):
            raise PaperGovernorReadinessRecordStoreError(
                "paper_governor_readiness_record_store:record_digest_query_invalid"
            )
        return self._by_record_digest.get(record_digest)

    def find_by_readiness_digest(self, readiness_digest: str) -> tuple[PaperGovernorReadinessRecord, ...]:
        """Return records for this readiness digest in append order."""
        if not _sha256_hex_digest(readiness_digest):
            raise PaperGovernorReadinessRecordStoreError(
                "paper_governor_readiness_record_store:readiness_digest_query_invalid"
            )
        return tuple(record for record in self._records if record.readiness_digest == readiness_digest)

    def find_by_status(self, status: PaperGovernorReadinessStatus) -> tuple[PaperGovernorReadinessRecord, ...]:
        """Return records for this readiness status in append order."""
        if not isinstance(status, PaperGovernorReadinessStatus):
            raise PaperGovernorReadinessRecordStoreError("paper_governor_readiness_record_store:status_query_invalid")
        return tuple(record for record in self._records if record.status is status)


__all__ = [
    "PaperGovernorReadinessRecordStore",
    "PaperGovernorReadinessRecordStoreError",
]
