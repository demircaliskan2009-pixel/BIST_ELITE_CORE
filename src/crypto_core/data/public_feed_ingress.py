from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.public_feed_run_plan import (
    PublicFeedConnectorRunDecision,
    public_feed_run_decision_from_dict,
    public_feed_run_decision_ready,
    public_feed_run_decision_to_dict,
)
from crypto_core.data.public_feed_source import (
    PublicFeedSubscription,
    RawPublicFeedEnvelope,
    public_feed_subscription_from_dict,
    public_feed_subscription_to_dict,
    raw_public_feed_envelope_from_dict,
    raw_public_feed_envelope_to_dict,
    validate_raw_public_feed_envelope,
)
from crypto_core.venue.contracts import PublicFeedType, VenueId


class PublicFeedIngressError(ValueError):
    """Raised when offline public-feed ingress payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedIngressPacket:
    packet_id: str
    run_decision: PublicFeedConnectorRunDecision
    subscription: PublicFeedSubscription
    envelope: RawPublicFeedEnvelope
    received_at_ns: int
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedIngressDecision:
    accepted: bool
    packet_id: str | None
    envelope_id: str | None
    venue_id: VenueId | None
    symbol: str | None
    canonical_symbol: str | None
    feed_type: PublicFeedType | None
    sequence_id: int | None
    rejection_reasons: tuple[str, ...]


def public_feed_ingress_packet_rejection_reasons(packet: object) -> tuple[str, ...]:
    if packet is None:
        return ("public_ingress:packet_missing",)
    if not isinstance(packet, PublicFeedIngressPacket):
        return ("public_ingress:packet_malformed",)

    reasons: list[str] = []
    if not _non_empty(packet.packet_id):
        reasons.append("public_ingress:packet_malformed")
    if not isinstance(packet.run_decision, PublicFeedConnectorRunDecision) or not public_feed_run_decision_ready(
        packet.run_decision
    ):
        reasons.append("public_ingress:run_not_ready")
        if isinstance(packet.run_decision, PublicFeedConnectorRunDecision):
            reasons.extend(packet.run_decision.rejection_reasons)
    if not isinstance(packet.subscription, PublicFeedSubscription):
        reasons.append("public_ingress:subscription_missing")
    if not isinstance(packet.envelope, RawPublicFeedEnvelope):
        reasons.append("public_ingress:envelope_missing")
    if not _positive_int(packet.received_at_ns):
        reasons.append("public_ingress:invalid_received_at")
    elif isinstance(packet.envelope, RawPublicFeedEnvelope) and packet.received_at_ns < packet.envelope.receive_time_ns:
        reasons.append("public_ingress:invalid_received_at")

    reasons.extend(_identity_mismatch_reasons(packet))
    reasons.extend(_envelope_reasons(packet))
    reasons.extend(_string_reasons(packet.rejection_reasons, "public_ingress:packet_malformed"))
    return tuple(dict.fromkeys(reasons))


def evaluate_public_feed_ingress_packet(packet: object) -> PublicFeedIngressDecision:
    reasons = public_feed_ingress_packet_rejection_reasons(packet)
    if not isinstance(packet, PublicFeedIngressPacket):
        return PublicFeedIngressDecision(
            accepted=False,
            packet_id=None,
            envelope_id=None,
            venue_id=None,
            symbol=None,
            canonical_symbol=None,
            feed_type=None,
            sequence_id=None,
            rejection_reasons=reasons,
        )
    envelope = packet.envelope
    return PublicFeedIngressDecision(
        accepted=reasons == (),
        packet_id=packet.packet_id,
        envelope_id=envelope.envelope_id if isinstance(envelope, RawPublicFeedEnvelope) else None,
        venue_id=envelope.venue_id if isinstance(envelope, RawPublicFeedEnvelope) else None,
        symbol=envelope.symbol if isinstance(envelope, RawPublicFeedEnvelope) else None,
        canonical_symbol=envelope.canonical_symbol if isinstance(envelope, RawPublicFeedEnvelope) else None,
        feed_type=envelope.feed_type if isinstance(envelope, RawPublicFeedEnvelope) else None,
        sequence_id=envelope.sequence_id if isinstance(envelope, RawPublicFeedEnvelope) else None,
        rejection_reasons=reasons,
    )


def public_feed_ingress_decision_ready(decision: PublicFeedIngressDecision | None) -> bool:
    return (
        isinstance(decision, PublicFeedIngressDecision)
        and decision.accepted is True
        and decision.rejection_reasons == ()
    )


def public_feed_ingress_packet_to_dict(packet: PublicFeedIngressPacket) -> dict[str, object]:
    return {
        "packet_id": packet.packet_id,
        "run_decision": public_feed_run_decision_to_dict(packet.run_decision),
        "subscription": public_feed_subscription_to_dict(packet.subscription),
        "envelope": raw_public_feed_envelope_to_dict(packet.envelope),
        "received_at_ns": packet.received_at_ns,
        "rejection_reasons": list(packet.rejection_reasons),
    }


def public_feed_ingress_packet_from_dict(data: object) -> PublicFeedIngressPacket:
    payload = _mapping(data, "public feed ingress packet payload")
    return PublicFeedIngressPacket(
        packet_id=_non_empty_string(payload.get("packet_id"), "packet_id"),
        run_decision=public_feed_run_decision_from_dict(payload.get("run_decision")),
        subscription=public_feed_subscription_from_dict(payload.get("subscription")),
        envelope=raw_public_feed_envelope_from_dict(payload.get("envelope")),
        received_at_ns=_positive_int_field(payload.get("received_at_ns"), "received_at_ns"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_ingress_decision_to_dict(decision: PublicFeedIngressDecision) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "packet_id": decision.packet_id,
        "envelope_id": decision.envelope_id,
        "venue_id": None if decision.venue_id is None else decision.venue_id.value,
        "symbol": decision.symbol,
        "canonical_symbol": decision.canonical_symbol,
        "feed_type": None if decision.feed_type is None else decision.feed_type.value,
        "sequence_id": decision.sequence_id,
        "rejection_reasons": list(decision.rejection_reasons),
    }


def public_feed_ingress_decision_from_dict(data: object) -> PublicFeedIngressDecision:
    payload = _mapping(data, "public feed ingress decision payload")
    return PublicFeedIngressDecision(
        accepted=_bool(payload.get("accepted"), "accepted"),
        packet_id=_optional_non_empty_string(payload.get("packet_id"), "packet_id"),
        envelope_id=_optional_non_empty_string(payload.get("envelope_id"), "envelope_id"),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        symbol=_optional_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_optional_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_optional_feed_type(payload.get("feed_type")),
        sequence_id=_optional_non_negative_int(payload.get("sequence_id"), "sequence_id"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _identity_mismatch_reasons(packet: PublicFeedIngressPacket) -> tuple[str, ...]:
    reasons: list[str] = []
    run = packet.run_decision
    subscription = packet.subscription
    envelope = packet.envelope
    if isinstance(run, PublicFeedConnectorRunDecision) and isinstance(subscription, PublicFeedSubscription):
        if run.venue_id != subscription.venue_id:
            reasons.append("public_ingress:venue_mismatch")
        if run.symbol != subscription.symbol or run.canonical_symbol != subscription.canonical_symbol:
            reasons.append("public_ingress:symbol_mismatch")
        if run.feed_type != subscription.feed_type:
            reasons.append("public_ingress:feed_type_mismatch")
    if isinstance(envelope, RawPublicFeedEnvelope) and isinstance(subscription, PublicFeedSubscription):
        if envelope.venue_id != subscription.venue_id:
            reasons.append("public_ingress:venue_mismatch")
        if envelope.symbol != subscription.symbol or envelope.canonical_symbol != subscription.canonical_symbol:
            reasons.append("public_ingress:symbol_mismatch")
        if envelope.feed_type != subscription.feed_type:
            reasons.append("public_ingress:feed_type_mismatch")
    if isinstance(run, PublicFeedConnectorRunDecision) and isinstance(envelope, RawPublicFeedEnvelope):
        if run.venue_id != envelope.venue_id:
            reasons.append("public_ingress:venue_mismatch")
        if run.symbol != envelope.symbol or run.canonical_symbol != envelope.canonical_symbol:
            reasons.append("public_ingress:symbol_mismatch")
        if run.feed_type != envelope.feed_type:
            reasons.append("public_ingress:feed_type_mismatch")
    return tuple(dict.fromkeys(reasons))


def _envelope_reasons(packet: PublicFeedIngressPacket) -> tuple[str, ...]:
    if not isinstance(packet.envelope, RawPublicFeedEnvelope) or not isinstance(
        packet.subscription, PublicFeedSubscription
    ):
        return ()
    envelope_reasons = validate_raw_public_feed_envelope(packet.envelope, packet.subscription)
    if not envelope_reasons:
        return ()
    return tuple(dict.fromkeys(("public_ingress:envelope_rejected", *envelope_reasons)))


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    reasons = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        return (fallback,)
    return reasons


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedIngressError(f"{name} must be a mapping")
    return data


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedIngressError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedIngressError(f"{field_name} must be a positive integer")
    return value


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not _non_negative_int(value):
        raise PublicFeedIngressError(f"{field_name} must be a non-negative integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedIngressError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedIngressError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedIngressError(f"{field_name} must contain non-empty strings")
    return result


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicFeedIngressError("venue_id is unsupported") from exc
    raise PublicFeedIngressError("venue_id is malformed")


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
            raise PublicFeedIngressError("feed_type is unsupported") from exc
    raise PublicFeedIngressError("feed_type is malformed")


def _optional_feed_type(value: object) -> PublicFeedType | None:
    if value is None:
        return None
    return _feed_type(value)


__all__ = [
    "PublicFeedIngressDecision",
    "PublicFeedIngressError",
    "PublicFeedIngressPacket",
    "evaluate_public_feed_ingress_packet",
    "public_feed_ingress_decision_from_dict",
    "public_feed_ingress_decision_ready",
    "public_feed_ingress_decision_to_dict",
    "public_feed_ingress_packet_from_dict",
    "public_feed_ingress_packet_rejection_reasons",
    "public_feed_ingress_packet_to_dict",
]
