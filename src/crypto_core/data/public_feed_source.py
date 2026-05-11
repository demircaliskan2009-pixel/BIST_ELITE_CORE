from __future__ import annotations

from dataclasses import dataclass

from crypto_core.venue.contracts import PublicFeedType, VenueId


class PublicFeedSourceError(ValueError):
    """Raised when inert public-feed source payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedSubscription:
    subscription_id: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    depth: int
    enabled: bool
    created_at_ns: int


@dataclass(frozen=True)
class RawPublicFeedEnvelope:
    envelope_id: str
    subscription_id: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    event_time_ns: int
    receive_time_ns: int
    sequence_id: int
    payload_hash: str
    raw_payload_ref: str
    normalized: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedBatch:
    batch_id: str
    subscription: PublicFeedSubscription
    envelopes: tuple[RawPublicFeedEnvelope, ...]
    created_at_ns: int
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedBatchValidationResult:
    accepted: bool
    batch_id: str | None
    envelope_count: int
    first_sequence_id: int | None
    last_sequence_id: int | None
    first_event_time_ns: int | None
    last_event_time_ns: int | None
    rejection_reasons: tuple[str, ...]
    gap_detected: bool
    stale_detected: bool
    resync_required: bool


def validate_public_feed_subscription(subscription: object) -> tuple[str, ...]:
    if not isinstance(subscription, PublicFeedSubscription):
        return ("public_feed_source:subscription_malformed",)

    reasons: list[str] = []
    if not _non_empty(subscription.subscription_id):
        reasons.append("public_feed_source:subscription_id_missing")
    if not isinstance(subscription.venue_id, VenueId):
        reasons.append("public_feed_source:venue_missing")
    if not _non_empty(subscription.symbol) or not _non_empty(subscription.canonical_symbol):
        reasons.append("public_feed_source:symbol_missing")
    if not isinstance(subscription.feed_type, PublicFeedType):
        reasons.append("public_feed_source:feed_type_missing")
    if not _positive_int(subscription.depth):
        reasons.append("public_feed_source:invalid_depth")
    if not isinstance(subscription.enabled, bool):
        reasons.append("public_feed_source:subscription_malformed")
    elif not subscription.enabled:
        reasons.append("public_feed_source:subscription_disabled")
    if not _positive_int(subscription.created_at_ns):
        reasons.append("public_feed_source:invalid_created_at")
    return tuple(dict.fromkeys(reasons))


def validate_raw_public_feed_envelope(
    envelope: object,
    subscription: PublicFeedSubscription,
) -> tuple[str, ...]:
    if not isinstance(envelope, RawPublicFeedEnvelope):
        return ("public_feed_source:envelope_malformed",)

    reasons: list[str] = []
    if not _non_empty(envelope.envelope_id):
        reasons.append("public_feed_source:envelope_id_missing")
    if not _non_empty(envelope.subscription_id):
        reasons.append("public_feed_source:subscription_id_missing")
    elif isinstance(subscription, PublicFeedSubscription) and envelope.subscription_id != subscription.subscription_id:
        reasons.append("public_feed_source:subscription_mismatch")
    if not isinstance(envelope.venue_id, VenueId):
        reasons.append("public_feed_source:venue_missing")
    elif isinstance(subscription, PublicFeedSubscription) and envelope.venue_id != subscription.venue_id:
        reasons.append("public_feed_source:venue_mismatch")
    if not _non_empty(envelope.symbol) or not _non_empty(envelope.canonical_symbol):
        reasons.append("public_feed_source:symbol_missing")
    elif isinstance(subscription, PublicFeedSubscription) and (
        envelope.symbol != subscription.symbol or envelope.canonical_symbol != subscription.canonical_symbol
    ):
        reasons.append("public_feed_source:symbol_mismatch")
    if not isinstance(envelope.feed_type, PublicFeedType):
        reasons.append("public_feed_source:feed_type_missing")
    elif isinstance(subscription, PublicFeedSubscription) and envelope.feed_type != subscription.feed_type:
        reasons.append("public_feed_source:feed_type_mismatch")
    if not _positive_int(envelope.event_time_ns) or not _positive_int(envelope.receive_time_ns):
        reasons.append("public_feed_source:invalid_timestamps")
    elif envelope.receive_time_ns < envelope.event_time_ns:
        reasons.append("public_feed_source:receive_before_event")
    if not _non_negative_int(envelope.sequence_id):
        reasons.append("public_feed_source:invalid_sequence")
    if not _non_empty(envelope.payload_hash):
        reasons.append("public_feed_source:payload_hash_missing")
    if not _non_empty(envelope.raw_payload_ref):
        reasons.append("public_feed_source:raw_payload_ref_missing")
    if not isinstance(envelope.normalized, bool):
        reasons.append("public_feed_source:envelope_malformed")
    elif not envelope.normalized:
        reasons.append("public_feed_source:not_normalized")
    reasons.extend(_string_reasons(envelope.rejection_reasons, "public_feed_source:envelope_rejected"))
    return tuple(dict.fromkeys(reasons))


def validate_public_feed_batch(
    batch: object,
    *,
    max_receive_lag_ns: int | None = None,
    now_ns: int | None = None,
) -> PublicFeedBatchValidationResult:
    if not isinstance(batch, PublicFeedBatch):
        return _batch_result(
            batch_id=None,
            envelopes=(),
            reasons=("public_feed_source:batch_malformed",),
            stale_detected=False,
        )

    reasons: list[str] = []
    if not _non_empty(batch.batch_id):
        reasons.append("public_feed_source:batch_id_missing")
    if not _positive_int(batch.created_at_ns):
        reasons.append("public_feed_source:invalid_created_at")
    reasons.extend(validate_public_feed_subscription(batch.subscription))
    reasons.extend(_string_reasons(batch.rejection_reasons, "public_feed_source:batch_rejected"))
    if not isinstance(batch.envelopes, tuple) or not batch.envelopes:
        reasons.append("public_feed_source:batch_empty")
        return _batch_result(
            batch_id=batch.batch_id if _non_empty(batch.batch_id) else None, envelopes=(), reasons=reasons
        )
    if max_receive_lag_ns is not None and not _positive_int(max_receive_lag_ns):
        reasons.append("public_feed_source:invalid_receive_lag")
    if now_ns is not None and not _positive_int(now_ns):
        reasons.append("public_feed_source:invalid_receive_lag")

    envelope_ids: set[str] = set()
    sequence_ids: set[int] = set()
    previous_sequence_id: int | None = None
    previous_event_time_ns: int | None = None
    stale_detected = False
    for envelope in batch.envelopes:
        reasons.extend(validate_raw_public_feed_envelope(envelope, batch.subscription))
        if not isinstance(envelope, RawPublicFeedEnvelope):
            continue
        if envelope.envelope_id in envelope_ids:
            reasons.append("public_feed_source:duplicate_envelope_id")
        envelope_ids.add(envelope.envelope_id)
        if envelope.sequence_id in sequence_ids:
            reasons.append("public_feed_source:duplicate_sequence_id")
        sequence_ids.add(envelope.sequence_id)
        if previous_sequence_id is not None and envelope.sequence_id <= previous_sequence_id:
            reasons.append("public_feed_source:sequence_not_monotonic")
        if previous_event_time_ns is not None and envelope.event_time_ns <= previous_event_time_ns:
            reasons.append("public_feed_source:event_time_not_monotonic")
        if _positive_int(max_receive_lag_ns) and _positive_int(now_ns):
            receive_lag = now_ns - envelope.receive_time_ns
            if receive_lag > max_receive_lag_ns:
                stale_detected = True
                reasons.append("public_feed_source:receive_lag_exceeded")
        previous_sequence_id = envelope.sequence_id
        previous_event_time_ns = envelope.event_time_ns

    normalized_reasons = tuple(dict.fromkeys(reasons))
    return _batch_result(
        batch_id=batch.batch_id if _non_empty(batch.batch_id) else None,
        envelopes=batch.envelopes,
        reasons=normalized_reasons,
        gap_detected=any(reason in _GAP_REASONS for reason in normalized_reasons),
        stale_detected=stale_detected,
        resync_required=bool(normalized_reasons),
    )


def public_feed_batch_ready(result: PublicFeedBatchValidationResult | None) -> bool:
    return (
        isinstance(result, PublicFeedBatchValidationResult)
        and result.accepted is True
        and result.rejection_reasons == ()
        and result.gap_detected is False
        and result.resync_required is False
    )


def public_feed_subscription_to_dict(subscription: PublicFeedSubscription) -> dict[str, object]:
    return {
        "subscription_id": subscription.subscription_id,
        "venue_id": subscription.venue_id.value,
        "symbol": subscription.symbol,
        "canonical_symbol": subscription.canonical_symbol,
        "feed_type": subscription.feed_type.value,
        "depth": subscription.depth,
        "enabled": subscription.enabled,
        "created_at_ns": subscription.created_at_ns,
    }


def public_feed_subscription_from_dict(data: object) -> PublicFeedSubscription:
    payload = _mapping(data, "public feed subscription payload")
    return PublicFeedSubscription(
        subscription_id=_non_empty_string(payload.get("subscription_id"), "subscription_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        symbol=_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_feed_type(payload.get("feed_type")),
        depth=_positive_int_field(payload.get("depth"), "depth"),
        enabled=_bool(payload.get("enabled"), "enabled"),
        created_at_ns=_positive_int_field(payload.get("created_at_ns"), "created_at_ns"),
    )


def raw_public_feed_envelope_to_dict(envelope: RawPublicFeedEnvelope) -> dict[str, object]:
    return {
        "envelope_id": envelope.envelope_id,
        "subscription_id": envelope.subscription_id,
        "venue_id": envelope.venue_id.value,
        "symbol": envelope.symbol,
        "canonical_symbol": envelope.canonical_symbol,
        "feed_type": envelope.feed_type.value,
        "event_time_ns": envelope.event_time_ns,
        "receive_time_ns": envelope.receive_time_ns,
        "sequence_id": envelope.sequence_id,
        "payload_hash": envelope.payload_hash,
        "raw_payload_ref": envelope.raw_payload_ref,
        "normalized": envelope.normalized,
        "rejection_reasons": list(envelope.rejection_reasons),
    }


def raw_public_feed_envelope_from_dict(data: object) -> RawPublicFeedEnvelope:
    payload = _mapping(data, "raw public feed envelope payload")
    return RawPublicFeedEnvelope(
        envelope_id=_non_empty_string(payload.get("envelope_id"), "envelope_id"),
        subscription_id=_non_empty_string(payload.get("subscription_id"), "subscription_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        symbol=_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_feed_type(payload.get("feed_type")),
        event_time_ns=_positive_int_field(payload.get("event_time_ns"), "event_time_ns"),
        receive_time_ns=_positive_int_field(payload.get("receive_time_ns"), "receive_time_ns"),
        sequence_id=_non_negative_int_field(payload.get("sequence_id"), "sequence_id"),
        payload_hash=_non_empty_string(payload.get("payload_hash"), "payload_hash"),
        raw_payload_ref=_non_empty_string(payload.get("raw_payload_ref"), "raw_payload_ref"),
        normalized=_bool(payload.get("normalized"), "normalized"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_batch_to_dict(batch: PublicFeedBatch) -> dict[str, object]:
    return {
        "batch_id": batch.batch_id,
        "subscription": public_feed_subscription_to_dict(batch.subscription),
        "envelopes": [raw_public_feed_envelope_to_dict(envelope) for envelope in batch.envelopes],
        "created_at_ns": batch.created_at_ns,
        "rejection_reasons": list(batch.rejection_reasons),
    }


def public_feed_batch_from_dict(data: object) -> PublicFeedBatch:
    payload = _mapping(data, "public feed batch payload")
    return PublicFeedBatch(
        batch_id=_non_empty_string(payload.get("batch_id"), "batch_id"),
        subscription=public_feed_subscription_from_dict(payload.get("subscription")),
        envelopes=tuple(raw_public_feed_envelope_from_dict(item) for item in _sequence(payload.get("envelopes"))),
        created_at_ns=_positive_int_field(payload.get("created_at_ns"), "created_at_ns"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_batch_validation_result_to_dict(result: PublicFeedBatchValidationResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "batch_id": result.batch_id,
        "envelope_count": result.envelope_count,
        "first_sequence_id": result.first_sequence_id,
        "last_sequence_id": result.last_sequence_id,
        "first_event_time_ns": result.first_event_time_ns,
        "last_event_time_ns": result.last_event_time_ns,
        "rejection_reasons": list(result.rejection_reasons),
        "gap_detected": result.gap_detected,
        "stale_detected": result.stale_detected,
        "resync_required": result.resync_required,
    }


def public_feed_batch_validation_result_from_dict(data: object) -> PublicFeedBatchValidationResult:
    payload = _mapping(data, "public feed batch validation result payload")
    return PublicFeedBatchValidationResult(
        accepted=_bool(payload.get("accepted"), "accepted"),
        batch_id=_optional_non_empty_string(payload.get("batch_id"), "batch_id"),
        envelope_count=_non_negative_int_field(payload.get("envelope_count"), "envelope_count"),
        first_sequence_id=_optional_non_negative_int(payload.get("first_sequence_id"), "first_sequence_id"),
        last_sequence_id=_optional_non_negative_int(payload.get("last_sequence_id"), "last_sequence_id"),
        first_event_time_ns=_optional_positive_int(payload.get("first_event_time_ns"), "first_event_time_ns"),
        last_event_time_ns=_optional_positive_int(payload.get("last_event_time_ns"), "last_event_time_ns"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        gap_detected=_bool(payload.get("gap_detected"), "gap_detected"),
        stale_detected=_bool(payload.get("stale_detected"), "stale_detected"),
        resync_required=_bool(payload.get("resync_required"), "resync_required"),
    )


_GAP_REASONS = frozenset(
    {
        "public_feed_source:duplicate_sequence_id",
        "public_feed_source:sequence_not_monotonic",
        "public_feed_source:event_time_not_monotonic",
    }
)


def _batch_result(
    *,
    batch_id: str | None,
    envelopes: tuple[RawPublicFeedEnvelope, ...],
    reasons: tuple[str, ...] | list[str],
    gap_detected: bool = False,
    stale_detected: bool = False,
    resync_required: bool | None = None,
) -> PublicFeedBatchValidationResult:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return PublicFeedBatchValidationResult(
        accepted=normalized_reasons == (),
        batch_id=batch_id,
        envelope_count=len(envelopes),
        first_sequence_id=envelopes[0].sequence_id if envelopes else None,
        last_sequence_id=envelopes[-1].sequence_id if envelopes else None,
        first_event_time_ns=envelopes[0].event_time_ns if envelopes else None,
        last_event_time_ns=envelopes[-1].event_time_ns if envelopes else None,
        rejection_reasons=normalized_reasons,
        gap_detected=gap_detected,
        stale_detected=stale_detected,
        resync_required=bool(normalized_reasons) if resync_required is None else resync_required,
    )


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    reasons = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        return (fallback,)
    return reasons


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedSourceError(f"{name} must be a mapping")
    return data


def _sequence(data: object) -> tuple[object, ...]:
    if not isinstance(data, tuple | list):
        raise PublicFeedSourceError("payload field must be a sequence")
    return tuple(data)


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicFeedSourceError("venue_id is unsupported") from exc
    raise PublicFeedSourceError("venue_id is malformed")


def _feed_type(value: object) -> PublicFeedType:
    if isinstance(value, PublicFeedType):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedType(value)
        except ValueError as exc:
            raise PublicFeedSourceError("feed_type is unsupported") from exc
    raise PublicFeedSourceError("feed_type is malformed")


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedSourceError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedSourceError(f"{field_name} must be a positive integer")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int_field(value, field_name)


def _non_negative_int_field(value: object, field_name: str) -> int:
    if not _non_negative_int(value):
        raise PublicFeedSourceError(f"{field_name} must be a non-negative integer")
    return value


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _non_negative_int_field(value, field_name)


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedSourceError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedSourceError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedSourceError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "PublicFeedBatch",
    "PublicFeedBatchValidationResult",
    "PublicFeedSourceError",
    "PublicFeedSubscription",
    "RawPublicFeedEnvelope",
    "public_feed_batch_from_dict",
    "public_feed_batch_ready",
    "public_feed_batch_to_dict",
    "public_feed_batch_validation_result_from_dict",
    "public_feed_batch_validation_result_to_dict",
    "public_feed_subscription_from_dict",
    "public_feed_subscription_to_dict",
    "raw_public_feed_envelope_from_dict",
    "raw_public_feed_envelope_to_dict",
    "validate_public_feed_batch",
    "validate_public_feed_subscription",
    "validate_raw_public_feed_envelope",
]
