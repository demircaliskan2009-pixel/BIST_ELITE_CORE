"""Paper governor readiness status-transition view.

Traces how the paper-governor readiness *status* changes across the append-only readiness-record
chain (e.g. READY->BLOCKED, BLOCKED->READY, READY->OVER_BUDGET) into a deterministic, immutable
forensic view. This advances governor-readiness auditability — without persistence, live execution,
scheduler, venue, route, order intent, or controller wiring.

Design rules:
  - Reuse, don't duplicate: chain + per-record integrity validation and the summary fields come from
    ``replay_paper_governor_readiness_records`` (which re-validates by replaying through a fresh
    store). The ordered records — needed for adjacent transitions, which the replay summary does not
    expose — are read back from the (now-validated) store/records source. No append/store validation
    logic is reimplemented and chain validation is never weakened.
  - Status-change only: a transition is emitted only between two adjacent records whose status
    differs (the smallest useful status-transition surface); equal-status adjacents are not
    transitions but are still counted in ``status_counts``/``entry_count``.
  - Fail closed: a non-store/non-record source, or any broken-chain / duplicate / tampered record, is
    rejected with ``PaperGovernorReadinessRecordReplayError`` through the reused validation.
  - Deterministic + immutable: identical input yields an identical view (including ``transition_digest``).
  - PAPER ONLY: no order intent, live route, venue execution, scheduler, persistence, or execution field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from crypto_core.audit.portfolio_governor_readiness import PaperGovernorReadinessStatus
from crypto_core.audit.portfolio_governor_readiness_record import PaperGovernorReadinessRecord
from crypto_core.audit.portfolio_governor_readiness_record_replay import (
    PaperGovernorReadinessRecordReplayError,
    replay_paper_governor_readiness_records,
)
from crypto_core.audit.portfolio_governor_readiness_record_store import PaperGovernorReadinessRecordStore

_TRANSITION_SCHEMA_VERSION = "paper-governor-readiness-transition-trace.v1"


@dataclass(frozen=True)
class PaperGovernorReadinessStatusTransition:
    """A single status change between two adjacent readiness records. PAPER ONLY."""

    transition_index: int
    from_status: PaperGovernorReadinessStatus
    to_status: PaperGovernorReadinessStatus
    from_record_digest: str
    to_record_digest: str
    from_readiness_digest: str
    to_readiness_digest: str
    from_block_reasons: tuple[str, ...]
    to_block_reasons: tuple[str, ...]
    from_blocker_summary: tuple[str, ...]
    to_blocker_summary: tuple[str, ...]


@dataclass(frozen=True)
class PaperGovernorReadinessTransitionTrace:
    """Deterministic, immutable readiness status-transition forensic view. PAPER ONLY."""

    schema_version: str
    entry_count: int
    head_record_digest: str | None
    first_status: PaperGovernorReadinessStatus | None
    latest_status: PaperGovernorReadinessStatus | None
    latest_ready: bool
    status_counts: tuple[tuple[str, int], ...]
    transition_count: int
    transitions: tuple[PaperGovernorReadinessStatusTransition, ...]
    replay_digest: str
    transition_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot_records(source: object) -> tuple[PaperGovernorReadinessRecord, ...]:
    # Capture a single immutable snapshot of the source. The SAME snapshot is then used for both
    # replay validation and transition emission, so a mutating list/store (or a subclass returning a
    # different second snapshot) cannot make the transitions disagree with the validated summary.
    if isinstance(source, PaperGovernorReadinessRecordStore):
        return source.snapshot()
    if isinstance(source, (tuple, list)):
        return tuple(source)
    raise PaperGovernorReadinessRecordReplayError("paper_governor_readiness_record_replay:source_malformed")


def _serialize_transitions(
    transitions: tuple[PaperGovernorReadinessStatusTransition, ...],
) -> list[list[object]]:
    return [
        [
            transition.transition_index,
            transition.from_status.value,
            transition.to_status.value,
            transition.from_record_digest,
            transition.to_record_digest,
            transition.from_readiness_digest,
            transition.to_readiness_digest,
            list(transition.from_block_reasons),
            list(transition.to_block_reasons),
            list(transition.from_blocker_summary),
            list(transition.to_blocker_summary),
        ]
        for transition in transitions
    ]


def trace_paper_governor_readiness_transitions(
    source: PaperGovernorReadinessRecordStore
    | tuple[PaperGovernorReadinessRecord, ...]
    | list[PaperGovernorReadinessRecord],
) -> PaperGovernorReadinessTransitionTrace:
    """Trace readiness status transitions across a readiness-record chain (store or ordered records).

    The source is snapshotted once; that same immutable snapshot is validated (and its summary fields
    produced) by reusing ``replay_paper_governor_readiness_records`` and is also the set from which one
    transition per adjacent status change is emitted, in append order — so the transitions can never
    disagree with the validated summary. A malformed source or broken/duplicate/tampered record fails
    closed through that reused validation. The result is deterministic and immutable; no order intent
    or live wiring is produced.
    """
    # Snapshot the source once, then use that SAME immutable tuple for both replay validation and
    # transition emission (so the two cannot disagree if the source mutates or re-snapshots).
    records = _snapshot_records(source)
    replay = replay_paper_governor_readiness_records(records)

    transitions: list[PaperGovernorReadinessStatusTransition] = []
    for previous, current in zip(records, records[1:], strict=False):
        if previous.status is current.status:
            continue
        transitions.append(
            PaperGovernorReadinessStatusTransition(
                transition_index=len(transitions),
                from_status=previous.status,
                to_status=current.status,
                from_record_digest=previous.record_digest,
                to_record_digest=current.record_digest,
                from_readiness_digest=previous.readiness_digest,
                to_readiness_digest=current.readiness_digest,
                from_block_reasons=previous.block_reasons,
                to_block_reasons=current.block_reasons,
                from_blocker_summary=previous.blocker_summary,
                to_blocker_summary=current.blocker_summary,
            )
        )
    transitions_tuple = tuple(transitions)

    first_status = records[0].status if records else None

    transition_payload: dict[str, object] = {
        "schema_version": _TRANSITION_SCHEMA_VERSION,
        "entry_count": replay.entry_count,
        "head_record_digest": replay.head_record_digest,
        "first_status": first_status.value if first_status is not None else None,
        "latest_status": replay.latest_status.value if replay.latest_status is not None else None,
        "latest_ready": replay.latest_ready,
        "status_counts": [[status, count] for status, count in replay.status_counts],
        "transition_count": len(transitions_tuple),
        "transitions": _serialize_transitions(transitions_tuple),
        "replay_digest": replay.replay_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PaperGovernorReadinessTransitionTrace(
        schema_version=_TRANSITION_SCHEMA_VERSION,
        entry_count=replay.entry_count,
        head_record_digest=replay.head_record_digest,
        first_status=first_status,
        latest_status=replay.latest_status,
        latest_ready=replay.latest_ready,
        status_counts=replay.status_counts,
        transition_count=len(transitions_tuple),
        transitions=transitions_tuple,
        replay_digest=replay.replay_digest,
        transition_digest=_canonical_digest(transition_payload),
    )


def paper_governor_readiness_transition_trace_to_dict(
    trace: PaperGovernorReadinessTransitionTrace,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a readiness transition trace (deterministic shape)."""

    def _transition(transition: PaperGovernorReadinessStatusTransition) -> dict[str, object]:
        return {
            "transition_index": transition.transition_index,
            "from_status": transition.from_status.value,
            "to_status": transition.to_status.value,
            "from_record_digest": transition.from_record_digest,
            "to_record_digest": transition.to_record_digest,
            "from_readiness_digest": transition.from_readiness_digest,
            "to_readiness_digest": transition.to_readiness_digest,
            "from_block_reasons": list(transition.from_block_reasons),
            "to_block_reasons": list(transition.to_block_reasons),
            "from_blocker_summary": list(transition.from_blocker_summary),
            "to_blocker_summary": list(transition.to_blocker_summary),
        }

    return {
        "schema_version": trace.schema_version,
        "entry_count": trace.entry_count,
        "head_record_digest": trace.head_record_digest,
        "first_status": trace.first_status.value if trace.first_status is not None else None,
        "latest_status": trace.latest_status.value if trace.latest_status is not None else None,
        "latest_ready": trace.latest_ready,
        "status_counts": [[status, count] for status, count in trace.status_counts],
        "transition_count": trace.transition_count,
        "transitions": [_transition(transition) for transition in trace.transitions],
        "replay_digest": trace.replay_digest,
        "transition_digest": trace.transition_digest,
        "paper_only": trace.paper_only,
        "real_orders_enabled": trace.real_orders_enabled,
        "real_money_enabled": trace.real_money_enabled,
    }


__all__ = [
    "PaperGovernorReadinessStatusTransition",
    "PaperGovernorReadinessTransitionTrace",
    "paper_governor_readiness_transition_trace_to_dict",
    "trace_paper_governor_readiness_transitions",
]
