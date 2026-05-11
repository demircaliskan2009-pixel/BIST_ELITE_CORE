from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crypto_core.venue.contracts import InstrumentType, PublicFeedType, VenueId


class PublicFeedDialectError(ValueError):
    """Raised when inert public feed dialect payloads are malformed."""


class FeedSequenceModel(str, Enum):
    UNKNOWN = "unknown"
    MONOTONIC = "monotonic"
    PREV_FINAL_RANGE = "prev_final_range"
    SNAPSHOT_DELTA_RANGE = "snapshot_delta_range"


class FeedChecksumModel(str, Enum):
    NONE = "none"
    UNKNOWN = "unknown"
    VENUE_SPECIFIC = "venue_specific"


class FeedDialectVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED_FROM_OFFICIAL_DOCS = "verified_from_official_docs"


@dataclass(frozen=True)
class PublicFeedDialectSpec:
    dialect_id: str
    venue_id: VenueId
    feed_type: PublicFeedType
    instrument_type: InstrumentType
    verification_status: FeedDialectVerificationStatus
    official_doc_refs: tuple[str, ...]
    requires_rest_snapshot: bool
    supports_delta_stream: bool
    supports_checksum: bool
    sequence_model: FeedSequenceModel
    checksum_model: FeedChecksumModel
    requires_heartbeat: bool
    requires_ping_pong: bool
    supports_resync: bool
    max_gap_tolerance: int
    max_staleness_ns: int
    max_receive_lag_ns: int
    enabled_for_connector: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedResyncPlan:
    accepted: bool
    resync_required: bool
    reason: str
    venue_id: VenueId | None
    feed_type: PublicFeedType | None
    symbol: str | None
    requires_rest_snapshot: bool
    discard_buffer: bool
    reset_sequence: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PublicFeedDialectGateDecision:
    accepted: bool
    connector_allowed: bool
    rejection_reasons: tuple[str, ...]
    resync_required: bool


def public_feed_dialect_rejection_reasons(spec: object) -> tuple[str, ...]:
    if spec is None:
        return ("public_feed_dialect:spec_missing",)
    if not isinstance(spec, PublicFeedDialectSpec):
        return ("public_feed_dialect:spec_malformed",)

    reasons: list[str] = []
    if not _non_empty(spec.dialect_id):
        reasons.append("public_feed_dialect:dialect_id_missing")
    if not isinstance(spec.venue_id, VenueId):
        reasons.append("public_feed_dialect:venue_missing")
    if not isinstance(spec.feed_type, PublicFeedType):
        reasons.append("public_feed_dialect:feed_type_missing")
    if not isinstance(spec.instrument_type, InstrumentType):
        reasons.append("public_feed_dialect:instrument_type_missing")
    if not isinstance(spec.verification_status, FeedDialectVerificationStatus):
        reasons.append("public_feed_dialect:verification_status_malformed")
    elif spec.verification_status is FeedDialectVerificationStatus.UNVERIFIED:
        reasons.append("public_feed_dialect:unverified")
    elif not spec.official_doc_refs:
        reasons.append("public_feed_dialect:official_docs_missing")
    reasons.extend(_string_tuple_shape_reasons(spec.official_doc_refs, "public_feed_dialect:official_docs_malformed"))

    for field_name in (
        "requires_rest_snapshot",
        "supports_delta_stream",
        "supports_checksum",
        "requires_heartbeat",
        "requires_ping_pong",
        "supports_resync",
        "enabled_for_connector",
    ):
        if not isinstance(getattr(spec, field_name), bool):
            reasons.append("public_feed_dialect:spec_malformed")

    if not isinstance(spec.sequence_model, FeedSequenceModel):
        reasons.append("public_feed_dialect:sequence_model_missing")
    elif spec.supports_delta_stream and spec.sequence_model is FeedSequenceModel.UNKNOWN:
        reasons.append("public_feed_dialect:sequence_model_unknown")

    if not isinstance(spec.checksum_model, FeedChecksumModel):
        reasons.append("public_feed_dialect:checksum_model_missing")
    elif spec.supports_checksum and spec.checksum_model in {FeedChecksumModel.UNKNOWN, FeedChecksumModel.NONE}:
        reasons.append("public_feed_dialect:checksum_model_unknown")

    if (
        spec.enabled_for_connector
        and spec.verification_status is not FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
    ):
        reasons.append("public_feed_dialect:connector_unverified")
    if not _non_negative_int(spec.max_gap_tolerance):
        reasons.append("public_feed_dialect:invalid_gap_tolerance")
    if not _positive_int(spec.max_staleness_ns):
        reasons.append("public_feed_dialect:invalid_staleness")
    if not _positive_int(spec.max_receive_lag_ns):
        reasons.append("public_feed_dialect:invalid_receive_lag")

    reasons.extend(_string_reasons(spec.rejection_reasons, "public_feed_dialect:rejection_reasons_malformed"))
    return tuple(dict.fromkeys(reasons))


def public_feed_dialect_connector_ready(spec: object) -> bool:
    return (
        isinstance(spec, PublicFeedDialectSpec)
        and spec.enabled_for_connector is True
        and spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
        and spec.supports_delta_stream is True
        and public_feed_dialect_rejection_reasons(spec) == ()
    )


def evaluate_public_feed_dialect_gate(spec: object) -> PublicFeedDialectGateDecision:
    reasons = list(public_feed_dialect_rejection_reasons(spec))
    connector_allowed = public_feed_dialect_connector_ready(spec)
    if isinstance(spec, PublicFeedDialectSpec):
        if not spec.enabled_for_connector:
            reasons.append("public_feed_dialect:connector_disabled")
        if not spec.supports_delta_stream:
            reasons.append("public_feed_dialect:delta_stream_unsupported")
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return PublicFeedDialectGateDecision(
        accepted=connector_allowed and normalized_reasons == (),
        connector_allowed=connector_allowed,
        rejection_reasons=normalized_reasons,
        resync_required=False,
    )


def build_public_feed_resync_plan(
    spec: object,
    *,
    symbol: str | None = None,
    gap_detected: bool = False,
    stale_detected: bool = False,
    checksum_failed: bool = False,
) -> PublicFeedResyncPlan:
    reasons = list(public_feed_dialect_rejection_reasons(spec))
    if not isinstance(spec, PublicFeedDialectSpec):
        return _resync_plan(
            accepted=False,
            resync_required=gap_detected or stale_detected or checksum_failed,
            reason="public_feed_dialect:spec_malformed",
            spec=None,
            symbol=symbol,
            reasons=reasons,
        )

    trigger_reason = _resync_reason(
        gap_detected=gap_detected,
        stale_detected=stale_detected,
        checksum_failed=checksum_failed,
    )
    resync_required = trigger_reason != "public_feed_dialect:no_resync_required"
    if checksum_failed and not spec.supports_checksum:
        reasons.append("public_feed_dialect:checksum_unsupported")
    if resync_required and not spec.supports_resync:
        reasons.append("public_feed_dialect:resync_unsupported")

    normalized_reasons = tuple(dict.fromkeys(reasons))
    return _resync_plan(
        accepted=normalized_reasons == (),
        resync_required=resync_required,
        reason=trigger_reason,
        spec=spec,
        symbol=symbol,
        reasons=normalized_reasons,
    )


def public_feed_dialect_spec_to_dict(spec: PublicFeedDialectSpec) -> dict[str, object]:
    return {
        "dialect_id": spec.dialect_id,
        "venue_id": spec.venue_id.value,
        "feed_type": spec.feed_type.value,
        "instrument_type": spec.instrument_type.value,
        "verification_status": spec.verification_status.value,
        "official_doc_refs": list(spec.official_doc_refs),
        "requires_rest_snapshot": spec.requires_rest_snapshot,
        "supports_delta_stream": spec.supports_delta_stream,
        "supports_checksum": spec.supports_checksum,
        "sequence_model": spec.sequence_model.value,
        "checksum_model": spec.checksum_model.value,
        "requires_heartbeat": spec.requires_heartbeat,
        "requires_ping_pong": spec.requires_ping_pong,
        "supports_resync": spec.supports_resync,
        "max_gap_tolerance": spec.max_gap_tolerance,
        "max_staleness_ns": spec.max_staleness_ns,
        "max_receive_lag_ns": spec.max_receive_lag_ns,
        "enabled_for_connector": spec.enabled_for_connector,
        "rejection_reasons": list(spec.rejection_reasons),
    }


def public_feed_dialect_spec_from_dict(data: object) -> PublicFeedDialectSpec:
    payload = _mapping(data, "public feed dialect spec payload")
    return PublicFeedDialectSpec(
        dialect_id=_non_empty_string(payload.get("dialect_id"), "dialect_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        feed_type=_feed_type(payload.get("feed_type")),
        instrument_type=_instrument_type(payload.get("instrument_type")),
        verification_status=_verification_status(payload.get("verification_status")),
        official_doc_refs=_string_tuple(payload.get("official_doc_refs", ()), "official_doc_refs"),
        requires_rest_snapshot=_bool(payload.get("requires_rest_snapshot"), "requires_rest_snapshot"),
        supports_delta_stream=_bool(payload.get("supports_delta_stream"), "supports_delta_stream"),
        supports_checksum=_bool(payload.get("supports_checksum"), "supports_checksum"),
        sequence_model=_sequence_model(payload.get("sequence_model")),
        checksum_model=_checksum_model(payload.get("checksum_model")),
        requires_heartbeat=_bool(payload.get("requires_heartbeat"), "requires_heartbeat"),
        requires_ping_pong=_bool(payload.get("requires_ping_pong"), "requires_ping_pong"),
        supports_resync=_bool(payload.get("supports_resync"), "supports_resync"),
        max_gap_tolerance=_non_negative_int_field(payload.get("max_gap_tolerance"), "max_gap_tolerance"),
        max_staleness_ns=_positive_int_field(payload.get("max_staleness_ns"), "max_staleness_ns"),
        max_receive_lag_ns=_positive_int_field(payload.get("max_receive_lag_ns"), "max_receive_lag_ns"),
        enabled_for_connector=_bool(payload.get("enabled_for_connector"), "enabled_for_connector"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_resync_plan_to_dict(plan: PublicFeedResyncPlan) -> dict[str, object]:
    return {
        "accepted": plan.accepted,
        "resync_required": plan.resync_required,
        "reason": plan.reason,
        "venue_id": None if plan.venue_id is None else plan.venue_id.value,
        "feed_type": None if plan.feed_type is None else plan.feed_type.value,
        "symbol": plan.symbol,
        "requires_rest_snapshot": plan.requires_rest_snapshot,
        "discard_buffer": plan.discard_buffer,
        "reset_sequence": plan.reset_sequence,
        "rejection_reasons": list(plan.rejection_reasons),
    }


def public_feed_resync_plan_from_dict(data: object) -> PublicFeedResyncPlan:
    payload = _mapping(data, "public feed resync plan payload")
    return PublicFeedResyncPlan(
        accepted=_bool(payload.get("accepted"), "accepted"),
        resync_required=_bool(payload.get("resync_required"), "resync_required"),
        reason=_non_empty_string(payload.get("reason"), "reason"),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        feed_type=_optional_feed_type(payload.get("feed_type")),
        symbol=_optional_non_empty_string(payload.get("symbol"), "symbol"),
        requires_rest_snapshot=_bool(payload.get("requires_rest_snapshot"), "requires_rest_snapshot"),
        discard_buffer=_bool(payload.get("discard_buffer"), "discard_buffer"),
        reset_sequence=_bool(payload.get("reset_sequence"), "reset_sequence"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_dialect_gate_decision_to_dict(decision: PublicFeedDialectGateDecision) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "connector_allowed": decision.connector_allowed,
        "rejection_reasons": list(decision.rejection_reasons),
        "resync_required": decision.resync_required,
    }


def public_feed_dialect_gate_decision_from_dict(data: object) -> PublicFeedDialectGateDecision:
    payload = _mapping(data, "public feed dialect gate decision payload")
    return PublicFeedDialectGateDecision(
        accepted=_bool(payload.get("accepted"), "accepted"),
        connector_allowed=_bool(payload.get("connector_allowed"), "connector_allowed"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        resync_required=_bool(payload.get("resync_required"), "resync_required"),
    )


def _resync_plan(
    *,
    accepted: bool,
    resync_required: bool,
    reason: str,
    spec: PublicFeedDialectSpec | None,
    symbol: str | None,
    reasons: tuple[str, ...] | list[str],
) -> PublicFeedResyncPlan:
    return PublicFeedResyncPlan(
        accepted=accepted,
        resync_required=resync_required,
        reason=reason,
        venue_id=None if spec is None else spec.venue_id,
        feed_type=None if spec is None else spec.feed_type,
        symbol=symbol,
        requires_rest_snapshot=bool(spec.requires_rest_snapshot) if spec is not None and resync_required else False,
        discard_buffer=resync_required,
        reset_sequence=resync_required,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


def _resync_reason(*, gap_detected: bool, stale_detected: bool, checksum_failed: bool) -> str:
    if gap_detected:
        return "public_feed_dialect:gap_detected"
    if checksum_failed:
        return "public_feed_dialect:checksum_failed"
    if stale_detected:
        return "public_feed_dialect:stale_detected"
    return "public_feed_dialect:no_resync_required"


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    reasons = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        return (fallback,)
    return reasons


def _string_tuple_shape_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    if any(not isinstance(reason, str) or not reason for reason in value):
        return (fallback,)
    return ()


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedDialectError(f"{name} must be a mapping")
    return data


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicFeedDialectError("venue_id is unsupported") from exc
    raise PublicFeedDialectError("venue_id is malformed")


def _optional_venue_id(value: object) -> VenueId | None:
    if value is None:
        return None
    return _venue_id(value)


def _feed_type(value: object) -> PublicFeedType:
    if isinstance(value, PublicFeedType):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedType(value)
        except ValueError as exc:
            raise PublicFeedDialectError("feed_type is unsupported") from exc
    raise PublicFeedDialectError("feed_type is malformed")


def _optional_feed_type(value: object) -> PublicFeedType | None:
    if value is None:
        return None
    return _feed_type(value)


def _instrument_type(value: object) -> InstrumentType:
    if isinstance(value, InstrumentType):
        return value
    if isinstance(value, str):
        try:
            return InstrumentType(value)
        except ValueError as exc:
            raise PublicFeedDialectError("instrument_type is unsupported") from exc
    raise PublicFeedDialectError("instrument_type is malformed")


def _verification_status(value: object) -> FeedDialectVerificationStatus:
    if isinstance(value, FeedDialectVerificationStatus):
        return value
    if isinstance(value, str):
        try:
            return FeedDialectVerificationStatus(value)
        except ValueError as exc:
            raise PublicFeedDialectError("verification_status is unsupported") from exc
    raise PublicFeedDialectError("verification_status is malformed")


def _sequence_model(value: object) -> FeedSequenceModel:
    if isinstance(value, FeedSequenceModel):
        return value
    if isinstance(value, str):
        try:
            return FeedSequenceModel(value)
        except ValueError as exc:
            raise PublicFeedDialectError("sequence_model is unsupported") from exc
    raise PublicFeedDialectError("sequence_model is malformed")


def _checksum_model(value: object) -> FeedChecksumModel:
    if isinstance(value, FeedChecksumModel):
        return value
    if isinstance(value, str):
        try:
            return FeedChecksumModel(value)
        except ValueError as exc:
            raise PublicFeedDialectError("checksum_model is unsupported") from exc
    raise PublicFeedDialectError("checksum_model is malformed")


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedDialectError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedDialectError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int_field(value: object, field_name: str) -> int:
    if not _non_negative_int(value):
        raise PublicFeedDialectError(f"{field_name} must be a non-negative integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedDialectError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedDialectError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedDialectError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "FeedChecksumModel",
    "FeedDialectVerificationStatus",
    "FeedSequenceModel",
    "PublicFeedDialectError",
    "PublicFeedDialectGateDecision",
    "PublicFeedDialectSpec",
    "PublicFeedResyncPlan",
    "build_public_feed_resync_plan",
    "evaluate_public_feed_dialect_gate",
    "public_feed_dialect_connector_ready",
    "public_feed_dialect_gate_decision_from_dict",
    "public_feed_dialect_gate_decision_to_dict",
    "public_feed_dialect_rejection_reasons",
    "public_feed_dialect_spec_from_dict",
    "public_feed_dialect_spec_to_dict",
    "public_feed_resync_plan_from_dict",
    "public_feed_resync_plan_to_dict",
]
