"""Paper governor readiness record replay / current-decision view.

Replays the append-only ``PaperGovernorReadinessRecordStore`` (or an ordered tuple/list of
``PaperGovernorReadinessRecord``) into a deterministic, immutable current-decision view: the latest
readiness verdict (status / ready / digests), per-status record counts, the current block reasons and
blocker summary, the latest exposure caps and totals, and the latest record's provenance evidence.
This advances auditability and decision forensics — without persistence, live execution, scheduler,
venue, route, order intent, or controller wiring.

Design rules:
  - Reuse, don't duplicate: the append-only chain and per-record integrity are re-validated by
    replaying the records through a fresh ``PaperGovernorReadinessRecordStore`` — no append/store
    validation logic is reimplemented here.
  - Latest appended record = the current readiness decision.
  - Fail closed: a non-store/non-record source, or any broken-chain / duplicate / tampered record, is
    rejected with ``PaperGovernorReadinessRecordReplayError``.
  - Deterministic + immutable: identical input yields an identical view (including ``replay_digest``).
  - PAPER ONLY: no order intent, live route, venue execution, scheduler, persistence, or execution field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from crypto_core.audit.decision_ledger import DecisionEvidenceRef
from crypto_core.audit.portfolio_governor_readiness import PaperGovernorReadinessStatus
from crypto_core.audit.portfolio_governor_readiness_record import PaperGovernorReadinessRecord
from crypto_core.audit.portfolio_governor_readiness_record_store import (
    PaperGovernorReadinessRecordStore,
    PaperGovernorReadinessRecordStoreError,
)

_REPLAY_SCHEMA_VERSION = "paper-governor-readiness-record-replay.v1"


class PaperGovernorReadinessRecordReplayError(RuntimeError):
    """Raised when a readiness-record replay source is malformed or its chain is broken/tampered."""


@dataclass(frozen=True)
class PaperGovernorReadinessRecordReplay:
    """Deterministic, immutable current-decision view over the readiness-record chain. PAPER ONLY."""

    schema_version: str
    entry_count: int
    head_record_digest: str | None
    latest_record_digest: str | None
    latest_status: PaperGovernorReadinessStatus | None
    latest_ready: bool
    latest_readiness_digest: str | None
    status_counts: tuple[tuple[str, int], ...]
    current_block_reasons: tuple[str, ...]
    current_blocker_summary: tuple[str, ...]
    latest_max_current_active_weight: float | None
    latest_max_current_active_notional: float | None
    latest_total_active_weight: float
    latest_total_active_notional: float
    latest_evidence_refs: tuple[DecisionEvidenceRef, ...]
    replay_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coerce_records(source: object) -> tuple[PaperGovernorReadinessRecord, ...]:
    if isinstance(source, PaperGovernorReadinessRecordStore):
        return source.snapshot()
    if isinstance(source, (tuple, list)):
        records = tuple(source)
        for record in records:
            if not isinstance(record, PaperGovernorReadinessRecord):
                raise PaperGovernorReadinessRecordReplayError("paper_governor_readiness_record_replay:record_malformed")
        return records
    raise PaperGovernorReadinessRecordReplayError("paper_governor_readiness_record_replay:source_malformed")


def _serialize_evidence_refs(refs: tuple[DecisionEvidenceRef, ...]) -> list[list[object]]:
    return [[ref.source_type, ref.digest, ref.source_id] for ref in refs]


def replay_paper_governor_readiness_records(
    source: PaperGovernorReadinessRecordStore
    | tuple[PaperGovernorReadinessRecord, ...]
    | list[PaperGovernorReadinessRecord],
) -> PaperGovernorReadinessRecordReplay:
    """Replay a readiness-record chain (store or ordered records) into a current-decision view.

    The append-only chain and per-record integrity are independently re-validated by replaying the
    records through a fresh ``PaperGovernorReadinessRecordStore`` (first ``previous_record_digest`` is
    None, each next references the prior ``record_digest``, no duplicate digests, every record
    self-consistent). Any breach fails closed with ``PaperGovernorReadinessRecordReplayError``. The
    latest appended record is the current decision. The view is deterministic and immutable; no order
    intent or live wiring is produced.
    """
    records = _coerce_records(source)

    # Independently re-validate the append-only chain + record integrity by replaying through a fresh
    # store. This reuses the canonical append validation; no chain logic is duplicated here.
    store = PaperGovernorReadinessRecordStore()
    try:
        for record in records:
            store.append(record)
    except PaperGovernorReadinessRecordStoreError as exc:
        raise PaperGovernorReadinessRecordReplayError(
            f"paper_governor_readiness_record_replay:chain_invalid:{exc}"
        ) from exc
    validated = store.snapshot()

    counts = dict.fromkeys(PaperGovernorReadinessStatus, 0)
    for record in validated:
        counts[record.status] += 1
    status_counts = tuple(sorted((status.value, counts[status]) for status in counts))

    if validated:
        latest = validated[-1]
        head_record_digest: str | None = latest.record_digest
        latest_record_digest: str | None = latest.record_digest
        latest_status: PaperGovernorReadinessStatus | None = latest.status
        latest_ready = latest.ready
        latest_readiness_digest: str | None = latest.readiness_digest
        current_block_reasons = latest.block_reasons
        current_blocker_summary = latest.blocker_summary
        latest_max_weight = latest.max_current_active_weight
        latest_max_notional = latest.max_current_active_notional
        latest_total_weight = latest.total_active_weight
        latest_total_notional = latest.total_active_notional
        latest_evidence_refs = latest.evidence_refs
    else:
        head_record_digest = None
        latest_record_digest = None
        latest_status = None
        latest_ready = False
        latest_readiness_digest = None
        current_block_reasons = ()
        current_blocker_summary = ()
        latest_max_weight = None
        latest_max_notional = None
        latest_total_weight = 0.0
        latest_total_notional = 0.0
        latest_evidence_refs = ()

    replay_payload: dict[str, object] = {
        "schema_version": _REPLAY_SCHEMA_VERSION,
        "entry_count": len(validated),
        "head_record_digest": head_record_digest,
        "latest_record_digest": latest_record_digest,
        "latest_status": latest_status.value if latest_status is not None else None,
        "latest_ready": latest_ready,
        "latest_readiness_digest": latest_readiness_digest,
        "status_counts": [[status, count] for status, count in status_counts],
        "current_block_reasons": list(current_block_reasons),
        "current_blocker_summary": list(current_blocker_summary),
        "latest_max_current_active_weight": latest_max_weight,
        "latest_max_current_active_notional": latest_max_notional,
        "latest_total_active_weight": latest_total_weight,
        "latest_total_active_notional": latest_total_notional,
        "latest_evidence_refs": _serialize_evidence_refs(latest_evidence_refs),
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PaperGovernorReadinessRecordReplay(
        schema_version=_REPLAY_SCHEMA_VERSION,
        entry_count=len(validated),
        head_record_digest=head_record_digest,
        latest_record_digest=latest_record_digest,
        latest_status=latest_status,
        latest_ready=latest_ready,
        latest_readiness_digest=latest_readiness_digest,
        status_counts=status_counts,
        current_block_reasons=current_block_reasons,
        current_blocker_summary=current_blocker_summary,
        latest_max_current_active_weight=latest_max_weight,
        latest_max_current_active_notional=latest_max_notional,
        latest_total_active_weight=latest_total_weight,
        latest_total_active_notional=latest_total_notional,
        latest_evidence_refs=latest_evidence_refs,
        replay_digest=_canonical_digest(replay_payload),
    )


def paper_governor_readiness_record_replay_to_dict(
    replay: PaperGovernorReadinessRecordReplay,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a readiness-record replay view (deterministic shape)."""
    return {
        "schema_version": replay.schema_version,
        "entry_count": replay.entry_count,
        "head_record_digest": replay.head_record_digest,
        "latest_record_digest": replay.latest_record_digest,
        "latest_status": replay.latest_status.value if replay.latest_status is not None else None,
        "latest_ready": replay.latest_ready,
        "latest_readiness_digest": replay.latest_readiness_digest,
        "status_counts": [[status, count] for status, count in replay.status_counts],
        "current_block_reasons": list(replay.current_block_reasons),
        "current_blocker_summary": list(replay.current_blocker_summary),
        "latest_max_current_active_weight": replay.latest_max_current_active_weight,
        "latest_max_current_active_notional": replay.latest_max_current_active_notional,
        "latest_total_active_weight": replay.latest_total_active_weight,
        "latest_total_active_notional": replay.latest_total_active_notional,
        "latest_evidence_refs": [
            {"source_type": ref.source_type, "digest": ref.digest, "source_id": ref.source_id}
            for ref in replay.latest_evidence_refs
        ],
        "replay_digest": replay.replay_digest,
        "paper_only": replay.paper_only,
        "real_orders_enabled": replay.real_orders_enabled,
        "real_money_enabled": replay.real_money_enabled,
    }


__all__ = [
    "PaperGovernorReadinessRecordReplay",
    "PaperGovernorReadinessRecordReplayError",
    "paper_governor_readiness_record_replay_to_dict",
    "replay_paper_governor_readiness_records",
]
