from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.market_data_journal import (
    PublicMarketDataReplayResult,
    build_journal_entry_from_public_event,
    public_market_data_replay_cursor_from_dict,
    public_market_data_replay_cursor_to_dict,
    replay_cursor_ready,
    replay_journal_entries,
)
from crypto_core.data.public_data_readiness import (
    PublicDataReadinessInput,
    PublicDataReadinessSnapshot,
    build_public_data_readiness_snapshot,
    public_data_readiness_snapshot_from_dict,
    public_data_readiness_snapshot_to_dict,
    public_data_ready_for_paper,
)
from crypto_core.data.public_feed_policy import (
    PublicFeedPolicy,
    public_feed_policy_from_dict,
    public_feed_policy_to_dict,
)
from crypto_core.data.public_feed_source import (
    PublicFeedBatch,
    PublicFeedBatchValidationResult,
    PublicFeedSubscription,
    public_feed_batch_ready,
    public_feed_batch_validation_result_from_dict,
    public_feed_batch_validation_result_to_dict,
    public_feed_subscription_from_dict,
    public_feed_subscription_to_dict,
    validate_public_feed_batch,
)
from crypto_core.venue.contracts import PublicFeedHealth, PublicMarketDataEvent


class PublicFeedIngestError(ValueError):
    """Raised when offline public-feed ingest payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedIngestPlan:
    plan_id: str
    policy: PublicFeedPolicy
    subscription: PublicFeedSubscription
    max_receive_lag_ns: int
    require_batch_ready: bool
    require_replay_ready: bool
    require_public_data_ready: bool


@dataclass(frozen=True)
class PublicFeedIngestResult:
    accepted: bool
    batch_validation: PublicFeedBatchValidationResult
    replay_result: PublicMarketDataReplayResult
    readiness_snapshot: PublicDataReadinessSnapshot
    journal_entry_count: int
    rejection_reasons: tuple[str, ...]


def ingest_public_feed_events(
    plan: PublicFeedIngestPlan,
    batch: PublicFeedBatch,
    events: tuple[PublicMarketDataEvent, ...],
    *,
    now_ns: int | None = None,
) -> PublicFeedIngestResult:
    plan_reasons = list(_plan_rejection_reasons(plan))
    batch_validation = validate_public_feed_batch(
        batch,
        max_receive_lag_ns=plan.max_receive_lag_ns if isinstance(plan, PublicFeedIngestPlan) else None,
        now_ns=now_ns,
    )
    event_reasons = list(_event_alignment_rejection_reasons(events, batch))

    journal_entries = ()
    if not event_reasons:
        journal_entries = tuple(
            build_journal_entry_from_public_event(event, entry_id=envelope.envelope_id)
            for event, envelope in zip(events, batch.envelopes, strict=True)
        )

    replay_result = replay_journal_entries(journal_entries)
    readiness_snapshot = _build_readiness_snapshot(plan, batch_validation, replay_result, now_ns=now_ns)

    reasons: list[str] = []
    reasons.extend(plan_reasons)
    if plan.require_batch_ready and not public_feed_batch_ready(batch_validation):
        reasons.append("public_feed_ingest:batch_not_ready")
        reasons.extend(batch_validation.rejection_reasons)
    reasons.extend(event_reasons)
    if plan.require_replay_ready and not _replay_result_ready(replay_result):
        reasons.append("public_feed_ingest:replay_not_ready")
        reasons.extend(replay_result.rejection_reasons)
    if plan.require_public_data_ready and not public_data_ready_for_paper(readiness_snapshot):
        reasons.append("public_feed_ingest:public_data_not_ready")
        reasons.extend(readiness_snapshot.rejection_reasons)

    normalized_reasons = tuple(dict.fromkeys(reasons))
    return PublicFeedIngestResult(
        accepted=normalized_reasons == (),
        batch_validation=batch_validation,
        replay_result=replay_result,
        readiness_snapshot=readiness_snapshot,
        journal_entry_count=len(journal_entries),
        rejection_reasons=normalized_reasons,
    )


def public_feed_ingest_result_ready(result: PublicFeedIngestResult | None) -> bool:
    return (
        isinstance(result, PublicFeedIngestResult)
        and result.accepted is True
        and result.rejection_reasons == ()
        and public_feed_batch_ready(result.batch_validation)
        and _replay_result_ready(result.replay_result)
        and public_data_ready_for_paper(result.readiness_snapshot)
    )


def public_feed_ingest_plan_to_dict(plan: PublicFeedIngestPlan) -> dict[str, object]:
    return {
        "plan_id": plan.plan_id,
        "policy": public_feed_policy_to_dict(plan.policy),
        "subscription": public_feed_subscription_to_dict(plan.subscription),
        "max_receive_lag_ns": plan.max_receive_lag_ns,
        "require_batch_ready": plan.require_batch_ready,
        "require_replay_ready": plan.require_replay_ready,
        "require_public_data_ready": plan.require_public_data_ready,
    }


def public_feed_ingest_plan_from_dict(data: object) -> PublicFeedIngestPlan:
    payload = _mapping(data, "public feed ingest plan payload")
    return PublicFeedIngestPlan(
        plan_id=_non_empty_string(payload.get("plan_id"), "plan_id"),
        policy=public_feed_policy_from_dict(payload.get("policy")),
        subscription=public_feed_subscription_from_dict(payload.get("subscription")),
        max_receive_lag_ns=_positive_int_field(payload.get("max_receive_lag_ns"), "max_receive_lag_ns"),
        require_batch_ready=_bool(payload.get("require_batch_ready"), "require_batch_ready"),
        require_replay_ready=_bool(payload.get("require_replay_ready"), "require_replay_ready"),
        require_public_data_ready=_bool(payload.get("require_public_data_ready"), "require_public_data_ready"),
    )


def public_feed_ingest_result_to_dict(result: PublicFeedIngestResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "batch_validation": public_feed_batch_validation_result_to_dict(result.batch_validation),
        "replay_result": _replay_result_to_dict(result.replay_result),
        "readiness_snapshot": public_data_readiness_snapshot_to_dict(result.readiness_snapshot),
        "journal_entry_count": result.journal_entry_count,
        "rejection_reasons": list(result.rejection_reasons),
    }


def public_feed_ingest_result_from_dict(data: object) -> PublicFeedIngestResult:
    payload = _mapping(data, "public feed ingest result payload")
    return PublicFeedIngestResult(
        accepted=_bool(payload.get("accepted"), "accepted"),
        batch_validation=public_feed_batch_validation_result_from_dict(payload.get("batch_validation")),
        replay_result=_replay_result_from_dict(payload.get("replay_result")),
        readiness_snapshot=public_data_readiness_snapshot_from_dict(payload.get("readiness_snapshot")),
        journal_entry_count=_non_negative_int_field(payload.get("journal_entry_count"), "journal_entry_count"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _plan_rejection_reasons(plan: object) -> tuple[str, ...]:
    if not isinstance(plan, PublicFeedIngestPlan):
        return ("public_feed_ingest:plan_malformed",)
    reasons: list[str] = []
    if not _non_empty(plan.plan_id):
        reasons.append("public_feed_ingest:plan_id_missing")
    if not isinstance(plan.policy, PublicFeedPolicy):
        reasons.append("public_feed_ingest:policy_malformed")
    if not isinstance(plan.subscription, PublicFeedSubscription):
        reasons.append("public_feed_ingest:subscription_malformed")
    if not _positive_int(plan.max_receive_lag_ns):
        reasons.append("public_feed_ingest:invalid_receive_lag")
    for field_name in ("require_batch_ready", "require_replay_ready", "require_public_data_ready"):
        if not isinstance(getattr(plan, field_name), bool):
            reasons.append("public_feed_ingest:plan_malformed")
    return tuple(dict.fromkeys(reasons))


def _event_alignment_rejection_reasons(
    events: object,
    batch: PublicFeedBatch,
) -> tuple[str, ...]:
    if not isinstance(events, tuple) or not events:
        return ("public_feed_ingest:events_empty",)
    if not isinstance(batch, PublicFeedBatch):
        return ("public_feed_ingest:batch_malformed",)

    reasons: list[str] = []
    if len(events) != len(batch.envelopes):
        reasons.append("public_feed_ingest:event_envelope_count_mismatch")
    for index, event in enumerate(events):
        if not isinstance(event, PublicMarketDataEvent):
            reasons.append("public_feed_ingest:event_malformed")
            continue
        if index >= len(batch.envelopes):
            continue
        envelope = batch.envelopes[index]
        if event.sequence_id != envelope.sequence_id:
            reasons.append("public_feed_ingest:event_sequence_mismatch")
        if event.payload_hash != envelope.payload_hash:
            reasons.append("public_feed_ingest:event_hash_mismatch")
        if event.raw_payload_ref != envelope.raw_payload_ref:
            reasons.append("public_feed_ingest:event_payload_ref_mismatch")
        if (
            event.venue_id != envelope.venue_id
            or event.symbol != envelope.symbol
            or event.canonical_symbol != envelope.canonical_symbol
            or event.feed_type != envelope.feed_type
        ):
            reasons.append("public_feed_ingest:event_envelope_identity_mismatch")
    return tuple(dict.fromkeys(reasons))


def _build_readiness_snapshot(
    plan: PublicFeedIngestPlan,
    batch_validation: PublicFeedBatchValidationResult,
    replay_result: PublicMarketDataReplayResult,
    *,
    now_ns: int | None,
) -> PublicDataReadinessSnapshot:
    health = PublicFeedHealth(
        venue_id=plan.policy.venue_id,
        feed_type=plan.policy.feed_type,
        symbol=plan.policy.symbol,
        healthy=public_feed_batch_ready(batch_validation),
        stale=batch_validation.stale_detected,
        last_event_time_ns=batch_validation.last_event_time_ns or 1,
        last_receive_time_ns=now_ns
        if isinstance(now_ns, int) and now_ns > 0
        else (batch_validation.last_event_time_ns or 1),
        gap_detected=batch_validation.gap_detected,
        resync_required=batch_validation.resync_required,
        rejection_reasons=batch_validation.rejection_reasons,
    )
    return build_public_data_readiness_snapshot(
        PublicDataReadinessInput(
            policy=plan.policy,
            health=health,
            replay_cursor=replay_result.cursor,
            replay_result=replay_result,
            order_book_state=None,
            order_book_result=None,
            now_ns=now_ns,
        )
    )


def _replay_result_ready(result: PublicMarketDataReplayResult) -> bool:
    return (
        isinstance(result, PublicMarketDataReplayResult)
        and result.applied is True
        and result.rejection_reasons == ()
        and replay_cursor_ready(result.cursor)
        and result.gap_detected is False
        and result.resync_required is False
    )


def _replay_result_to_dict(result: PublicMarketDataReplayResult) -> dict[str, object]:
    return {
        "applied": result.applied,
        "cursor": None if result.cursor is None else public_market_data_replay_cursor_to_dict(result.cursor),
        "rejection_reasons": list(result.rejection_reasons),
        "gap_detected": result.gap_detected,
        "stale_detected": result.stale_detected,
        "resync_required": result.resync_required,
    }


def _replay_result_from_dict(data: object) -> PublicMarketDataReplayResult:
    payload = _mapping(data, "public market data replay result payload")
    cursor_payload = payload.get("cursor")
    return PublicMarketDataReplayResult(
        applied=_bool(payload.get("applied"), "applied"),
        cursor=None if cursor_payload is None else public_market_data_replay_cursor_from_dict(cursor_payload),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        gap_detected=_bool(payload.get("gap_detected"), "gap_detected"),
        stale_detected=_bool(payload.get("stale_detected"), "stale_detected"),
        resync_required=_bool(payload.get("resync_required"), "resync_required"),
    )


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedIngestError(f"{name} must be a mapping")
    return data


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedIngestError(f"{field_name} must be a non-empty string")
    return value


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedIngestError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int_field(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PublicFeedIngestError(f"{field_name} must be a non-negative integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedIngestError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedIngestError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedIngestError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "PublicFeedIngestError",
    "PublicFeedIngestPlan",
    "PublicFeedIngestResult",
    "ingest_public_feed_events",
    "public_feed_ingest_plan_from_dict",
    "public_feed_ingest_plan_to_dict",
    "public_feed_ingest_result_from_dict",
    "public_feed_ingest_result_ready",
    "public_feed_ingest_result_to_dict",
]
