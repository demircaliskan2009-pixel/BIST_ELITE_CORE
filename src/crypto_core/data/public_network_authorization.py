from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from crypto_core.venue.contracts import PublicFeedType, VenueId

PUBLIC_NETWORK_AUTHORIZATION_SCHEMA_VERSION = 1


class PublicNetworkAuthorizationError(ValueError):
    """Raised when inert public-network authorization payloads are malformed."""


class PublicNetworkAuthorizationStatus(str, Enum):
    MISSING = "missing"
    REJECTED = "rejected"
    AUTHORIZED = "authorized"


@dataclass(frozen=True)
class PublicNetworkAuthorization:
    authorization_id: str
    schema_version: int
    status: PublicNetworkAuthorizationStatus
    venue_id: VenueId
    allowed_symbols: tuple[str, ...]
    allowed_feed_types: tuple[PublicFeedType, ...]
    allowed_dialect_ids: tuple[str, ...]
    max_connections: int
    max_subscriptions: int
    max_messages_per_second: float
    max_snapshot_requests_per_minute: int
    approved_by: str
    approved_at_ns: int
    expires_at_ns: int
    official_doc_bundle_id: str
    verification_result_ids: tuple[str, ...]
    region_review_reference: str
    data_tos_review_reference: str
    network_allowed: bool
    private_api_forbidden: bool
    credentials_forbidden: bool
    live_trading_forbidden: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicNetworkAuthorizationDecision:
    accepted: bool
    authorization_id: str | None
    venue_id: VenueId | None
    rejection_reasons: tuple[str, ...]
    expires_at_ns: int | None


def public_network_authorization_rejection_reasons(
    auth: object,
    *,
    now_ns: int | None = None,
) -> tuple[str, ...]:
    if auth is None:
        return ("public_network:authorization_missing",)
    if not isinstance(auth, PublicNetworkAuthorization):
        return ("public_network:authorization_malformed",)

    reasons: list[str] = []
    if not _non_empty(auth.authorization_id):
        reasons.append("public_network:authorization_malformed")
    if auth.schema_version != PUBLIC_NETWORK_AUTHORIZATION_SCHEMA_VERSION:
        reasons.append("public_network:authorization_malformed")
    if not isinstance(auth.status, PublicNetworkAuthorizationStatus):
        reasons.append("public_network:authorization_malformed")
    elif auth.status is not PublicNetworkAuthorizationStatus.AUTHORIZED:
        reasons.append("public_network:not_allowed")
    if not isinstance(auth.venue_id, VenueId):
        reasons.append("public_network:authorization_malformed")
    if not _string_tuple_valid(auth.allowed_symbols, allow_empty=False):
        reasons.append("public_network:symbols_missing")
    if not _feed_type_tuple_valid(auth.allowed_feed_types, allow_empty=False):
        reasons.append("public_network:feeds_missing")
    if not _string_tuple_valid(auth.allowed_dialect_ids, allow_empty=False):
        reasons.append("public_network:dialects_missing")
    if (
        not _positive_int(auth.max_connections)
        or not _positive_int(auth.max_subscriptions)
        or not _positive_float(auth.max_messages_per_second)
        or not _positive_int(auth.max_snapshot_requests_per_minute)
    ):
        reasons.append("public_network:invalid_budget")
    if not _non_empty(auth.approved_by) or not _positive_int(auth.approved_at_ns):
        reasons.append("public_network:approval_missing")
    if not _positive_int(auth.expires_at_ns) or (
        _positive_int(auth.approved_at_ns) and auth.expires_at_ns <= auth.approved_at_ns
    ):
        reasons.append("public_network:expired")
    if _positive_int(now_ns) and _positive_int(auth.expires_at_ns) and now_ns > auth.expires_at_ns:
        reasons.append("public_network:expired")
    elif now_ns is not None and not _positive_int(now_ns):
        reasons.append("public_network:authorization_malformed")
    if not _non_empty(auth.official_doc_bundle_id) or not _string_tuple_valid(
        auth.verification_result_ids,
        allow_empty=False,
    ):
        reasons.append("public_network:official_docs_missing")
    if not _non_empty(auth.region_review_reference):
        reasons.append("public_network:region_review_missing")
    if not _non_empty(auth.data_tos_review_reference):
        reasons.append("public_network:data_tos_review_missing")
    if auth.network_allowed is not True:
        reasons.append("public_network:not_allowed")
    if auth.private_api_forbidden is not True:
        reasons.append("public_network:private_api_not_forbidden")
    if auth.credentials_forbidden is not True:
        reasons.append("public_network:credentials_not_forbidden")
    if auth.live_trading_forbidden is not True:
        reasons.append("public_network:live_trading_not_forbidden")
    reasons.extend(_string_reasons(auth.rejection_reasons, "public_network:authorization_malformed"))
    return tuple(dict.fromkeys(reasons))


def evaluate_public_network_authorization(
    auth: object,
    *,
    now_ns: int | None = None,
) -> PublicNetworkAuthorizationDecision:
    reasons = public_network_authorization_rejection_reasons(auth, now_ns=now_ns)
    if not isinstance(auth, PublicNetworkAuthorization):
        return PublicNetworkAuthorizationDecision(
            accepted=False,
            authorization_id=None,
            venue_id=None,
            rejection_reasons=reasons,
            expires_at_ns=None,
        )
    return PublicNetworkAuthorizationDecision(
        accepted=reasons == (),
        authorization_id=auth.authorization_id,
        venue_id=auth.venue_id if isinstance(auth.venue_id, VenueId) else None,
        rejection_reasons=reasons,
        expires_at_ns=auth.expires_at_ns if _positive_int(auth.expires_at_ns) else None,
    )


def public_network_authorization_ready(decision: PublicNetworkAuthorizationDecision | None) -> bool:
    return (
        isinstance(decision, PublicNetworkAuthorizationDecision)
        and decision.accepted is True
        and decision.rejection_reasons == ()
    )


def public_network_authorization_to_dict(auth: PublicNetworkAuthorization) -> dict[str, object]:
    return {
        "authorization_id": auth.authorization_id,
        "schema_version": auth.schema_version,
        "status": auth.status.value,
        "venue_id": auth.venue_id.value,
        "allowed_symbols": list(auth.allowed_symbols),
        "allowed_feed_types": [feed_type.value for feed_type in auth.allowed_feed_types],
        "allowed_dialect_ids": list(auth.allowed_dialect_ids),
        "max_connections": auth.max_connections,
        "max_subscriptions": auth.max_subscriptions,
        "max_messages_per_second": auth.max_messages_per_second,
        "max_snapshot_requests_per_minute": auth.max_snapshot_requests_per_minute,
        "approved_by": auth.approved_by,
        "approved_at_ns": auth.approved_at_ns,
        "expires_at_ns": auth.expires_at_ns,
        "official_doc_bundle_id": auth.official_doc_bundle_id,
        "verification_result_ids": list(auth.verification_result_ids),
        "region_review_reference": auth.region_review_reference,
        "data_tos_review_reference": auth.data_tos_review_reference,
        "network_allowed": auth.network_allowed,
        "private_api_forbidden": auth.private_api_forbidden,
        "credentials_forbidden": auth.credentials_forbidden,
        "live_trading_forbidden": auth.live_trading_forbidden,
        "rejection_reasons": list(auth.rejection_reasons),
    }


def public_network_authorization_from_dict(data: object) -> PublicNetworkAuthorization:
    payload = _mapping(data, "public network authorization payload")
    return PublicNetworkAuthorization(
        authorization_id=_non_empty_string(payload.get("authorization_id"), "authorization_id"),
        schema_version=_positive_int_field(payload.get("schema_version"), "schema_version"),
        status=_status(payload.get("status")),
        venue_id=_venue_id(payload.get("venue_id")),
        allowed_symbols=_string_tuple(payload.get("allowed_symbols"), "allowed_symbols"),
        allowed_feed_types=_feed_type_tuple(payload.get("allowed_feed_types"), "allowed_feed_types"),
        allowed_dialect_ids=_string_tuple(payload.get("allowed_dialect_ids"), "allowed_dialect_ids"),
        max_connections=_positive_int_field(payload.get("max_connections"), "max_connections"),
        max_subscriptions=_positive_int_field(payload.get("max_subscriptions"), "max_subscriptions"),
        max_messages_per_second=_positive_float_field(
            payload.get("max_messages_per_second"),
            "max_messages_per_second",
        ),
        max_snapshot_requests_per_minute=_positive_int_field(
            payload.get("max_snapshot_requests_per_minute"),
            "max_snapshot_requests_per_minute",
        ),
        approved_by=_non_empty_string(payload.get("approved_by"), "approved_by"),
        approved_at_ns=_positive_int_field(payload.get("approved_at_ns"), "approved_at_ns"),
        expires_at_ns=_positive_int_field(payload.get("expires_at_ns"), "expires_at_ns"),
        official_doc_bundle_id=_non_empty_string(
            payload.get("official_doc_bundle_id"),
            "official_doc_bundle_id",
        ),
        verification_result_ids=_string_tuple(payload.get("verification_result_ids"), "verification_result_ids"),
        region_review_reference=_non_empty_string(
            payload.get("region_review_reference"),
            "region_review_reference",
        ),
        data_tos_review_reference=_non_empty_string(
            payload.get("data_tos_review_reference"),
            "data_tos_review_reference",
        ),
        network_allowed=_bool(payload.get("network_allowed"), "network_allowed"),
        private_api_forbidden=_bool(payload.get("private_api_forbidden"), "private_api_forbidden"),
        credentials_forbidden=_bool(payload.get("credentials_forbidden"), "credentials_forbidden"),
        live_trading_forbidden=_bool(payload.get("live_trading_forbidden"), "live_trading_forbidden"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_network_authorization_decision_to_dict(
    decision: PublicNetworkAuthorizationDecision,
) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "authorization_id": decision.authorization_id,
        "venue_id": None if decision.venue_id is None else decision.venue_id.value,
        "rejection_reasons": list(decision.rejection_reasons),
        "expires_at_ns": decision.expires_at_ns,
    }


def public_network_authorization_decision_from_dict(data: object) -> PublicNetworkAuthorizationDecision:
    payload = _mapping(data, "public network authorization decision payload")
    return PublicNetworkAuthorizationDecision(
        accepted=_bool(payload.get("accepted"), "accepted"),
        authorization_id=_optional_non_empty_string(payload.get("authorization_id"), "authorization_id"),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        expires_at_ns=_optional_positive_int(payload.get("expires_at_ns"), "expires_at_ns"),
    )


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicNetworkAuthorizationError(f"{name} must be a mapping")
    return data


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_float(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicNetworkAuthorizationError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicNetworkAuthorizationError(f"{field_name} must be a positive integer")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int_field(value, field_name)


def _positive_float_field(value: object, field_name: str) -> float:
    if not _positive_float(value):
        raise PublicNetworkAuthorizationError(f"{field_name} must be a positive finite number")
    return float(value)


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicNetworkAuthorizationError(f"{field_name} must be a boolean")
    return value


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


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    reasons = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        return (fallback,)
    return reasons


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicNetworkAuthorizationError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise PublicNetworkAuthorizationError(f"{field_name} must contain non-empty strings")
    return result


def _feed_type_tuple(value: object, field_name: str) -> tuple[PublicFeedType, ...]:
    if not isinstance(value, tuple | list):
        raise PublicNetworkAuthorizationError(f"{field_name} must be a sequence")
    return tuple(_feed_type(item) for item in value)


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicNetworkAuthorizationError("venue_id is unsupported") from exc
    raise PublicNetworkAuthorizationError("venue_id is malformed")


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
            raise PublicNetworkAuthorizationError("feed_type is unsupported") from exc
    raise PublicNetworkAuthorizationError("feed_type is malformed")


def _status(value: object) -> PublicNetworkAuthorizationStatus:
    if isinstance(value, PublicNetworkAuthorizationStatus):
        return value
    if isinstance(value, str):
        try:
            return PublicNetworkAuthorizationStatus(value)
        except ValueError as exc:
            raise PublicNetworkAuthorizationError("status is unsupported") from exc
    raise PublicNetworkAuthorizationError("status is malformed")


__all__ = [
    "PUBLIC_NETWORK_AUTHORIZATION_SCHEMA_VERSION",
    "PublicNetworkAuthorization",
    "PublicNetworkAuthorizationDecision",
    "PublicNetworkAuthorizationError",
    "PublicNetworkAuthorizationStatus",
    "evaluate_public_network_authorization",
    "public_network_authorization_decision_from_dict",
    "public_network_authorization_decision_to_dict",
    "public_network_authorization_from_dict",
    "public_network_authorization_ready",
    "public_network_authorization_rejection_reasons",
    "public_network_authorization_to_dict",
]
