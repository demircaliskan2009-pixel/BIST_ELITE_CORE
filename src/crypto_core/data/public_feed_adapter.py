from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crypto_core.data.public_feed_connector import (
    PublicFeedConnectorPlan,
    evaluate_public_feed_connector_gate,
    public_feed_connector_plan_from_dict,
    public_feed_connector_plan_to_dict,
    public_feed_connector_ready,
)
from crypto_core.data.public_network_authorization import (
    PublicNetworkAuthorization,
    evaluate_public_network_authorization,
    public_network_authorization_from_dict,
    public_network_authorization_ready,
    public_network_authorization_to_dict,
)
from crypto_core.venue.contracts import PublicFeedType, VenueId


class PublicFeedAdapterError(ValueError):
    """Raised when inert public-feed adapter descriptor payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedAdapterDescriptor:
    adapter_id: str
    venue_id: VenueId
    supported_feed_types: tuple[PublicFeedType, ...]
    supported_symbols: tuple[str, ...]
    dialect_ids: tuple[str, ...]
    network_authorization: PublicNetworkAuthorization
    connector_plan: PublicFeedConnectorPlan
    enabled: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedAdapterReadiness:
    accepted: bool
    adapter_id: str | None
    venue_id: VenueId | None
    rejection_reasons: tuple[str, ...]
    network_authorized: bool
    connector_gate_ready: bool
    offline_only: bool


class PublicFeedAdapterProtocol(Protocol):
    def descriptor(self) -> PublicFeedAdapterDescriptor:
        pass

    def readiness(self, now_ns: int | None = None) -> PublicFeedAdapterReadiness:
        pass


def public_feed_adapter_descriptor_rejection_reasons(
    desc: object,
    *,
    now_ns: int | None = None,
) -> tuple[str, ...]:
    if desc is None:
        return ("public_feed_adapter:descriptor_missing",)
    if not isinstance(desc, PublicFeedAdapterDescriptor):
        return ("public_feed_adapter:descriptor_malformed",)

    reasons: list[str] = []
    if not _non_empty(desc.adapter_id):
        reasons.append("public_feed_adapter:descriptor_malformed")
    if not isinstance(desc.venue_id, VenueId):
        reasons.append("public_feed_adapter:descriptor_malformed")
    if not _feed_type_tuple_valid(desc.supported_feed_types, allow_empty=False):
        reasons.append("public_feed_adapter:feed_type_mismatch")
    if not _string_tuple_valid(desc.supported_symbols, allow_empty=False):
        reasons.append("public_feed_adapter:symbol_mismatch")
    if not _string_tuple_valid(desc.dialect_ids, allow_empty=False):
        reasons.append("public_feed_adapter:dialect_mismatch")
    if desc.enabled is not True:
        reasons.append("public_feed_adapter:disabled")
    reasons.extend(_string_reasons(desc.rejection_reasons, "public_feed_adapter:descriptor_malformed"))

    network_decision = evaluate_public_network_authorization(desc.network_authorization, now_ns=now_ns)
    if not public_network_authorization_ready(network_decision):
        reasons.append("public_feed_adapter:network_not_authorized")
        reasons.extend(network_decision.rejection_reasons)

    connector_decision = evaluate_public_feed_connector_gate(desc.connector_plan)
    if not public_feed_connector_ready(connector_decision):
        reasons.append("public_feed_adapter:connector_gate_not_ready")
        reasons.extend(connector_decision.rejection_reasons)

    reasons.extend(_identity_rejection_reasons(desc))
    return tuple(dict.fromkeys(reasons))


def evaluate_public_feed_adapter_readiness(
    desc: object,
    *,
    now_ns: int | None = None,
) -> PublicFeedAdapterReadiness:
    reasons = public_feed_adapter_descriptor_rejection_reasons(desc, now_ns=now_ns)
    if not isinstance(desc, PublicFeedAdapterDescriptor):
        return PublicFeedAdapterReadiness(
            accepted=False,
            adapter_id=None,
            venue_id=None,
            rejection_reasons=reasons,
            network_authorized=False,
            connector_gate_ready=False,
            offline_only=False,
        )

    network_decision = evaluate_public_network_authorization(desc.network_authorization, now_ns=now_ns)
    connector_decision = evaluate_public_feed_connector_gate(desc.connector_plan)
    network_authorized = public_network_authorization_ready(network_decision)
    connector_ready = public_feed_connector_ready(connector_decision)
    offline_only = connector_decision.offline_only
    return PublicFeedAdapterReadiness(
        accepted=reasons == () and network_authorized and connector_ready,
        adapter_id=desc.adapter_id,
        venue_id=desc.venue_id if isinstance(desc.venue_id, VenueId) else None,
        rejection_reasons=reasons,
        network_authorized=network_authorized,
        connector_gate_ready=connector_ready,
        offline_only=offline_only,
    )


def public_feed_adapter_ready(readiness: PublicFeedAdapterReadiness | None) -> bool:
    return (
        isinstance(readiness, PublicFeedAdapterReadiness)
        and readiness.accepted is True
        and readiness.network_authorized is True
        and readiness.connector_gate_ready is True
        and readiness.offline_only is True
        and readiness.rejection_reasons == ()
    )


def public_feed_adapter_descriptor_to_dict(desc: PublicFeedAdapterDescriptor) -> dict[str, object]:
    return {
        "adapter_id": desc.adapter_id,
        "venue_id": desc.venue_id.value,
        "supported_feed_types": [feed_type.value for feed_type in desc.supported_feed_types],
        "supported_symbols": list(desc.supported_symbols),
        "dialect_ids": list(desc.dialect_ids),
        "network_authorization": public_network_authorization_to_dict(desc.network_authorization),
        "connector_plan": public_feed_connector_plan_to_dict(desc.connector_plan),
        "enabled": desc.enabled,
        "rejection_reasons": list(desc.rejection_reasons),
    }


def public_feed_adapter_descriptor_from_dict(data: object) -> PublicFeedAdapterDescriptor:
    payload = _mapping(data, "public feed adapter descriptor payload")
    return PublicFeedAdapterDescriptor(
        adapter_id=_non_empty_string(payload.get("adapter_id"), "adapter_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        supported_feed_types=_feed_type_tuple(payload.get("supported_feed_types"), "supported_feed_types"),
        supported_symbols=_string_tuple(payload.get("supported_symbols"), "supported_symbols"),
        dialect_ids=_string_tuple(payload.get("dialect_ids"), "dialect_ids"),
        network_authorization=public_network_authorization_from_dict(payload.get("network_authorization")),
        connector_plan=public_feed_connector_plan_from_dict(payload.get("connector_plan")),
        enabled=_bool(payload.get("enabled"), "enabled"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_adapter_readiness_to_dict(readiness: PublicFeedAdapterReadiness) -> dict[str, object]:
    return {
        "accepted": readiness.accepted,
        "adapter_id": readiness.adapter_id,
        "venue_id": None if readiness.venue_id is None else readiness.venue_id.value,
        "rejection_reasons": list(readiness.rejection_reasons),
        "network_authorized": readiness.network_authorized,
        "connector_gate_ready": readiness.connector_gate_ready,
        "offline_only": readiness.offline_only,
    }


def public_feed_adapter_readiness_from_dict(data: object) -> PublicFeedAdapterReadiness:
    payload = _mapping(data, "public feed adapter readiness payload")
    return PublicFeedAdapterReadiness(
        accepted=_bool(payload.get("accepted"), "accepted"),
        adapter_id=_optional_non_empty_string(payload.get("adapter_id"), "adapter_id"),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        network_authorized=_bool(payload.get("network_authorized"), "network_authorized"),
        connector_gate_ready=_bool(payload.get("connector_gate_ready"), "connector_gate_ready"),
        offline_only=_bool(payload.get("offline_only"), "offline_only"),
    )


def _identity_rejection_reasons(desc: PublicFeedAdapterDescriptor) -> tuple[str, ...]:
    reasons: list[str] = []
    auth = desc.network_authorization
    plan = desc.connector_plan
    if isinstance(auth, PublicNetworkAuthorization):
        if auth.venue_id != desc.venue_id:
            reasons.append("public_feed_adapter:venue_mismatch")
        if any(symbol not in auth.allowed_symbols for symbol in desc.supported_symbols):
            reasons.append("public_feed_adapter:symbol_mismatch")
        if any(feed_type not in auth.allowed_feed_types for feed_type in desc.supported_feed_types):
            reasons.append("public_feed_adapter:feed_type_mismatch")
        if any(dialect_id not in auth.allowed_dialect_ids for dialect_id in desc.dialect_ids):
            reasons.append("public_feed_adapter:dialect_mismatch")
    else:
        reasons.append("public_feed_adapter:network_not_authorized")

    if isinstance(plan, PublicFeedConnectorPlan):
        if plan.venue_id != desc.venue_id:
            reasons.append("public_feed_adapter:venue_mismatch")
        if plan.symbol not in desc.supported_symbols:
            reasons.append("public_feed_adapter:symbol_mismatch")
        if plan.feed_type not in desc.supported_feed_types:
            reasons.append("public_feed_adapter:feed_type_mismatch")
        dialect_id = getattr(getattr(plan, "dialect", None), "dialect_id", None)
        if dialect_id not in desc.dialect_ids:
            reasons.append("public_feed_adapter:dialect_mismatch")
    else:
        reasons.append("public_feed_adapter:connector_gate_not_ready")
    return tuple(dict.fromkeys(reasons))


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedAdapterError(f"{name} must be a mapping")
    return data


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedAdapterError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedAdapterError(f"{field_name} must be a boolean")
    return value


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    reasons = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        return (fallback,)
    return reasons


def _string_tuple_valid(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, tuple | list):
        return False
    result = tuple(value)
    if not allow_empty and not result:
        return False
    return all(_non_empty(item) for item in result)


def _feed_type_tuple_valid(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, tuple | list):
        return False
    result = tuple(value)
    if not allow_empty and not result:
        return False
    return all(isinstance(item, PublicFeedType) for item in result)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedAdapterError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise PublicFeedAdapterError(f"{field_name} must contain non-empty strings")
    return result


def _feed_type_tuple(value: object, field_name: str) -> tuple[PublicFeedType, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedAdapterError(f"{field_name} must be a sequence")
    return tuple(_feed_type(item) for item in value)


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicFeedAdapterError("venue_id is unsupported") from exc
    raise PublicFeedAdapterError("venue_id is malformed")


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
            raise PublicFeedAdapterError("feed_type is unsupported") from exc
    raise PublicFeedAdapterError("feed_type is malformed")


__all__ = [
    "PublicFeedAdapterDescriptor",
    "PublicFeedAdapterError",
    "PublicFeedAdapterProtocol",
    "PublicFeedAdapterReadiness",
    "evaluate_public_feed_adapter_readiness",
    "public_feed_adapter_descriptor_from_dict",
    "public_feed_adapter_descriptor_rejection_reasons",
    "public_feed_adapter_descriptor_to_dict",
    "public_feed_adapter_readiness_from_dict",
    "public_feed_adapter_readiness_to_dict",
    "public_feed_adapter_ready",
]
