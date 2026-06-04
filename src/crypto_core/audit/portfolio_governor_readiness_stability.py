"""Paper governor readiness stability gate.

A deterministic, fail-closed governance gate over the readiness status-transition history: it answers
not merely "is the latest verdict READY" but "is the latest READY *stable enough* under an explicit
paper-only policy". A flapping READY->BLOCKED->READY sequence is not treated as safe without a policy
that explicitly allows it. This advances risk-bounded paper governance — without live execution,
persistence, scheduler, venue, route, order intent, or controller wiring.

Consumes a ``PaperGovernorReadinessTransitionTrace`` directly, or a ``PaperGovernorReadinessRecordStore``
/ ordered records (validated and summarized through ``trace_paper_governor_readiness_transitions``).

Design rules:
  - Reuse, don't duplicate: store/record sources are snapshotted once and validated + summarized via
    the transition trace (which replays through a fresh store); no append/store/replay logic is
    reimplemented and the single-snapshot rule from PR #233 is preserved.
  - Tail inspection needs ordered records: ``min_ready_tail_records > 1`` and ``max_recent_transitions``
    require the ordered records. A bare transition trace does not expose them, so those checks fail
    closed (the verdict is never STABLE_READY when stability cannot be verified). A directly-supplied
    trace is re-verified against its own recomputed ``transition_digest`` before it is trusted.
  - Fail closed: an empty chain or a latest status that is not READY is NOT_READY; an invalid policy,
    a tampered trace, or a broken/malformed/duplicate/tampered record source is rejected.
  - Deterministic + immutable: identical input + policy yields an identical decision (incl. digest).
  - PAPER ONLY: no order intent, live route, venue execution, scheduler, persistence, or execution field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from crypto_core.audit.portfolio_governor_readiness import PaperGovernorReadinessStatus
from crypto_core.audit.portfolio_governor_readiness_record import PaperGovernorReadinessRecord
from crypto_core.audit.portfolio_governor_readiness_record_store import PaperGovernorReadinessRecordStore
from crypto_core.audit.portfolio_governor_readiness_transition import (
    PaperGovernorReadinessStatusTransition,
    PaperGovernorReadinessTransitionTrace,
    trace_paper_governor_readiness_transitions,
)

_STABILITY_SCHEMA_VERSION = "paper-governor-readiness-stability.v1"
_TRANSITION_SCHEMA_VERSION = "paper-governor-readiness-transition-trace.v1"
_READY = PaperGovernorReadinessStatus.READY
_BLOCKED_STATUS_VALUE = PaperGovernorReadinessStatus.BLOCKED.value

_EMPTY_CHAIN = "stability:empty_chain"
_LATEST_NOT_READY = "stability:latest_not_ready"
_INSUFFICIENT_READY_TAIL = "stability:insufficient_ready_tail"
_READY_TAIL_UNVERIFIABLE = "stability:ready_tail_unverifiable"
_TOO_MANY_TOTAL_TRANSITIONS = "stability:too_many_total_transitions"
_TOO_MANY_RECENT_TRANSITIONS = "stability:too_many_recent_transitions"
_RECENT_TRANSITIONS_UNVERIFIABLE = "stability:recent_transitions_unverifiable"
_HISTORICAL_BLOCKED = "stability:historical_blocked_records"


class PaperGovernorReadinessStabilityError(RuntimeError):
    """Raised when a stability source is malformed, a trace is tampered, or the policy is invalid."""


class PaperGovernorReadinessStabilityStatus(str, Enum):
    """Deterministic paper-governor readiness stability verdict. Never an order/live action."""

    STABLE_READY = "stable_ready"
    NOT_READY = "not_ready"
    UNSTABLE = "unstable"


@dataclass(frozen=True)
class PaperGovernorReadinessStabilityPolicy:
    """Explicit, deterministic stability policy. Caps None = sub-check not applied. PAPER ONLY."""

    min_ready_tail_records: int = 1
    max_total_transitions: int | None = None
    max_recent_transitions: int | None = None
    blocked_status_blocks_stability: bool = True


_DEFAULT_POLICY = PaperGovernorReadinessStabilityPolicy()


@dataclass(frozen=True)
class PaperGovernorReadinessStability:
    """Deterministic, immutable paper-governor readiness stability decision. PAPER ONLY."""

    schema_version: str
    stability_status: PaperGovernorReadinessStabilityStatus
    stable_ready: bool
    latest_status: PaperGovernorReadinessStatus | None
    latest_ready: bool
    entry_count: int
    transition_count: int
    status_counts: tuple[tuple[str, int], ...]
    head_record_digest: str | None
    transition_digest: str
    min_ready_tail_records: int
    max_total_transitions: int | None
    max_recent_transitions: int | None
    blocked_status_blocks_stability: bool
    block_reasons: tuple[str, ...]
    replay_digest: str
    stability_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 1


def _is_optional_non_negative_int(value: object) -> bool:
    return value is None or (not isinstance(value, bool) and isinstance(value, int) and value >= 0)


def _validate_policy(policy: PaperGovernorReadinessStabilityPolicy) -> None:
    if not isinstance(policy, PaperGovernorReadinessStabilityPolicy):
        raise PaperGovernorReadinessStabilityError("stability:policy_malformed")
    if not _is_positive_int(policy.min_ready_tail_records):
        raise PaperGovernorReadinessStabilityError("stability:min_ready_tail_records_invalid")
    if not _is_optional_non_negative_int(policy.max_total_transitions):
        raise PaperGovernorReadinessStabilityError("stability:max_total_transitions_invalid")
    if not _is_optional_non_negative_int(policy.max_recent_transitions):
        raise PaperGovernorReadinessStabilityError("stability:max_recent_transitions_invalid")
    if not isinstance(policy.blocked_status_blocks_stability, bool):
        raise PaperGovernorReadinessStabilityError("stability:policy_flag_invalid")


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


def _expected_transition_digest(trace: PaperGovernorReadinessTransitionTrace) -> str:
    # Mirror of the transition-trace digest payload. Recomputed here only to verify a directly-supplied
    # trace has not been tampered with before this fail-closed gate trusts its summary fields. A real
    # trace keeps this in lockstep (asserted by the tests).
    payload: dict[str, object] = {
        "schema_version": _TRANSITION_SCHEMA_VERSION,
        "entry_count": trace.entry_count,
        "head_record_digest": trace.head_record_digest,
        "first_status": trace.first_status.value if trace.first_status is not None else None,
        "latest_status": trace.latest_status.value if trace.latest_status is not None else None,
        "latest_ready": trace.latest_ready,
        "status_counts": [[status, count] for status, count in trace.status_counts],
        "transition_count": trace.transition_count,
        "transitions": _serialize_transitions(trace.transitions),
        "replay_digest": trace.replay_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return _canonical_digest(payload)


def _snapshot_records(source: object) -> tuple[PaperGovernorReadinessRecord, ...]:
    if isinstance(source, PaperGovernorReadinessRecordStore):
        return source.snapshot()
    if isinstance(source, (tuple, list)):
        return tuple(source)
    raise PaperGovernorReadinessStabilityError("stability:source_malformed")


def _trace_and_records(
    source: object,
) -> tuple[PaperGovernorReadinessTransitionTrace, tuple[PaperGovernorReadinessRecord, ...] | None]:
    if isinstance(source, PaperGovernorReadinessTransitionTrace):
        trace = source
        # The trace digest hard-codes the schema version, so the schema_version field must be checked
        # explicitly — otherwise a future/mismatched schema_version would slip past the digest check.
        if trace.schema_version != _TRANSITION_SCHEMA_VERSION:
            raise PaperGovernorReadinessStabilityError("stability:trace_schema_version_unexpected")
        if not (trace.paper_only is True and trace.real_orders_enabled is False and trace.real_money_enabled is False):
            raise PaperGovernorReadinessStabilityError("stability:non_paper_trace_rejected")
        if not isinstance(trace.transition_digest, str) or trace.transition_digest != _expected_transition_digest(
            trace
        ):
            raise PaperGovernorReadinessStabilityError("stability:transition_digest_mismatch")
        return trace, None
    # Snapshot store/record sources once and validate + summarize that SAME snapshot through the trace.
    records = _snapshot_records(source)
    trace = trace_paper_governor_readiness_transitions(records)
    return trace, records


def _ready_tail_satisfied(records: tuple[PaperGovernorReadinessRecord, ...], tail: int) -> bool:
    if len(records) < tail:
        return False
    return all(record.status is _READY for record in records[len(records) - tail :])


def _recent_transition_count(records: tuple[PaperGovernorReadinessRecord, ...], window_boundaries: int) -> int:
    # Status changes among the last ``window_boundaries`` record adjacencies (boundary i is between
    # records[i] and records[i+1]); for an all-READY tail this is 0.
    boundary_count = len(records) - 1
    if boundary_count <= 0:
        return 0
    start = max(0, boundary_count - window_boundaries)
    return sum(1 for i in range(start, boundary_count) if records[i].status is not records[i + 1].status)


def evaluate_paper_governor_readiness_stability(
    source: PaperGovernorReadinessTransitionTrace
    | PaperGovernorReadinessRecordStore
    | tuple[PaperGovernorReadinessRecord, ...]
    | list[PaperGovernorReadinessRecord],
    *,
    policy: PaperGovernorReadinessStabilityPolicy = _DEFAULT_POLICY,
) -> PaperGovernorReadinessStability:
    """Evaluate paper-governor readiness stability over the readiness history under ``policy``.

    Returns ``STABLE_READY`` only when the latest verdict is READY and every applicable stability check
    passes; ``NOT_READY`` when the chain is empty or the latest verdict is not READY; ``UNSTABLE`` when
    the latest is READY but a stability check fails or cannot be verified (e.g. a tail/recent check on a
    bare trace that lacks ordered records). An invalid policy, a tampered trace, or a malformed/broken/
    duplicate/tampered record source fails closed. The decision is deterministic and immutable; no order
    intent or live wiring is produced.
    """
    _validate_policy(policy)
    trace, records = _trace_and_records(source)

    latest_status = trace.latest_status
    reasons: list[str] = []

    if trace.entry_count == 0:
        status = PaperGovernorReadinessStabilityStatus.NOT_READY
        reasons.append(_EMPTY_CHAIN)
    elif latest_status is not _READY or not trace.latest_ready:
        status = PaperGovernorReadinessStabilityStatus.NOT_READY
        reasons.append(_LATEST_NOT_READY)
    else:
        if policy.min_ready_tail_records > 1:
            if records is None:
                reasons.append(_READY_TAIL_UNVERIFIABLE)
            elif not _ready_tail_satisfied(records, policy.min_ready_tail_records):
                reasons.append(_INSUFFICIENT_READY_TAIL)
        if policy.max_recent_transitions is not None:
            if records is None:
                reasons.append(_RECENT_TRANSITIONS_UNVERIFIABLE)
            elif _recent_transition_count(records, policy.min_ready_tail_records) > policy.max_recent_transitions:
                reasons.append(_TOO_MANY_RECENT_TRANSITIONS)
        if policy.max_total_transitions is not None and trace.transition_count > policy.max_total_transitions:
            reasons.append(_TOO_MANY_TOTAL_TRANSITIONS)
        if policy.blocked_status_blocks_stability and dict(trace.status_counts).get(_BLOCKED_STATUS_VALUE, 0) > 0:
            reasons.append(_HISTORICAL_BLOCKED)
        status = (
            PaperGovernorReadinessStabilityStatus.STABLE_READY
            if not reasons
            else PaperGovernorReadinessStabilityStatus.UNSTABLE
        )

    block_reasons = tuple(sorted(set(reasons)))
    stable_ready = status is PaperGovernorReadinessStabilityStatus.STABLE_READY

    stability_payload: dict[str, object] = {
        "schema_version": _STABILITY_SCHEMA_VERSION,
        "stability_status": status.value,
        "stable_ready": stable_ready,
        "latest_status": latest_status.value if latest_status is not None else None,
        "latest_ready": trace.latest_ready,
        "entry_count": trace.entry_count,
        "transition_count": trace.transition_count,
        "status_counts": [[name, count] for name, count in trace.status_counts],
        "head_record_digest": trace.head_record_digest,
        "transition_digest": trace.transition_digest,
        "min_ready_tail_records": policy.min_ready_tail_records,
        "max_total_transitions": policy.max_total_transitions,
        "max_recent_transitions": policy.max_recent_transitions,
        "blocked_status_blocks_stability": policy.blocked_status_blocks_stability,
        "block_reasons": list(block_reasons),
        "replay_digest": trace.replay_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PaperGovernorReadinessStability(
        schema_version=_STABILITY_SCHEMA_VERSION,
        stability_status=status,
        stable_ready=stable_ready,
        latest_status=latest_status,
        latest_ready=trace.latest_ready,
        entry_count=trace.entry_count,
        transition_count=trace.transition_count,
        status_counts=trace.status_counts,
        head_record_digest=trace.head_record_digest,
        transition_digest=trace.transition_digest,
        min_ready_tail_records=policy.min_ready_tail_records,
        max_total_transitions=policy.max_total_transitions,
        max_recent_transitions=policy.max_recent_transitions,
        blocked_status_blocks_stability=policy.blocked_status_blocks_stability,
        block_reasons=block_reasons,
        replay_digest=trace.replay_digest,
        stability_digest=_canonical_digest(stability_payload),
    )


def paper_governor_readiness_stability_to_dict(
    stability: PaperGovernorReadinessStability,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a readiness stability decision (deterministic shape)."""
    return {
        "schema_version": stability.schema_version,
        "stability_status": stability.stability_status.value,
        "stable_ready": stability.stable_ready,
        "latest_status": stability.latest_status.value if stability.latest_status is not None else None,
        "latest_ready": stability.latest_ready,
        "entry_count": stability.entry_count,
        "transition_count": stability.transition_count,
        "status_counts": [[name, count] for name, count in stability.status_counts],
        "head_record_digest": stability.head_record_digest,
        "transition_digest": stability.transition_digest,
        "min_ready_tail_records": stability.min_ready_tail_records,
        "max_total_transitions": stability.max_total_transitions,
        "max_recent_transitions": stability.max_recent_transitions,
        "blocked_status_blocks_stability": stability.blocked_status_blocks_stability,
        "block_reasons": list(stability.block_reasons),
        "replay_digest": stability.replay_digest,
        "stability_digest": stability.stability_digest,
        "paper_only": stability.paper_only,
        "real_orders_enabled": stability.real_orders_enabled,
        "real_money_enabled": stability.real_money_enabled,
    }


__all__ = [
    "PaperGovernorReadinessStability",
    "PaperGovernorReadinessStabilityError",
    "PaperGovernorReadinessStabilityPolicy",
    "PaperGovernorReadinessStabilityStatus",
    "evaluate_paper_governor_readiness_stability",
    "paper_governor_readiness_stability_to_dict",
]
