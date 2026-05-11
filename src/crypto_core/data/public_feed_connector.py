from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crypto_core.data.public_feed_dialect import (
    PublicFeedDialectSpec,
    public_feed_dialect_connector_ready,
    public_feed_dialect_rejection_reasons,
    public_feed_dialect_spec_from_dict,
    public_feed_dialect_spec_to_dict,
)
from crypto_core.data.public_feed_policy import (
    PublicFeedPolicy,
    public_feed_policy_from_dict,
    public_feed_policy_rejection_reasons,
    public_feed_policy_to_dict,
)
from crypto_core.data.public_feed_source import (
    PublicFeedSubscription,
    public_feed_subscription_from_dict,
    public_feed_subscription_to_dict,
    validate_public_feed_subscription,
)
from crypto_core.venue.contracts import PublicFeedType, VenueId


class PublicFeedConnectorError(ValueError):
    """Raised when inert public-feed connector payloads are malformed."""


class PublicFeedConnectorMode(str, Enum):
    DISABLED = "disabled"
    OFFLINE_SIMULATED = "offline_simulated"
    REALTIME_DISABLED = "realtime_disabled"


@dataclass(frozen=True)
class PublicFeedConnectorPlan:
    connector_id: str
    mode: PublicFeedConnectorMode
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    dialect: PublicFeedDialectSpec
    subscription: PublicFeedSubscription
    policy: PublicFeedPolicy
    created_at_ns: int
    require_verified_dialect: bool
    require_subscription_enabled: bool
    require_policy_valid: bool
    network_enabled: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedConnectorGateDecision:
    accepted: bool
    connector_id: str | None
    mode: PublicFeedConnectorMode | None
    venue_id: VenueId | None
    symbol: str | None
    canonical_symbol: str | None
    feed_type: PublicFeedType | None
    rejection_reasons: tuple[str, ...]
    connector_ready: bool
    offline_only: bool


def public_feed_connector_plan_rejection_reasons(plan: object) -> tuple[str, ...]:
    if plan is None:
        return ("public_connector:plan_missing",)
    if not isinstance(plan, PublicFeedConnectorPlan):
        return ("public_connector:plan_malformed",)

    reasons: list[str] = []
    if not _non_empty(plan.connector_id):
        reasons.append("public_connector:plan_malformed")
    if not isinstance(plan.mode, PublicFeedConnectorMode):
        reasons.append("public_connector:plan_malformed")
    elif plan.mode is PublicFeedConnectorMode.DISABLED:
        reasons.append("public_connector:disabled")
    elif plan.mode is PublicFeedConnectorMode.REALTIME_DISABLED:
        reasons.append("public_connector:realtime_disabled")
    if not isinstance(plan.venue_id, VenueId):
        reasons.append("public_connector:plan_malformed")
    if not _non_empty(plan.symbol) or not _non_empty(plan.canonical_symbol):
        reasons.append("public_connector:symbol_mismatch")
    if not isinstance(plan.feed_type, PublicFeedType):
        reasons.append("public_connector:plan_malformed")
    if not _positive_int(plan.created_at_ns):
        reasons.append("public_connector:plan_malformed")
    for field_name in (
        "require_verified_dialect",
        "require_subscription_enabled",
        "require_policy_valid",
        "network_enabled",
    ):
        if not isinstance(getattr(plan, field_name), bool):
            reasons.append("public_connector:plan_malformed")
    if plan.network_enabled is True:
        reasons.append("public_connector:network_forbidden")

    reasons.extend(_string_reasons(plan.rejection_reasons, "public_connector:plan_malformed"))
    reasons.extend(_dialect_reasons(plan))
    reasons.extend(_subscription_reasons(plan))
    reasons.extend(_policy_reasons(plan))
    reasons.extend(_identity_mismatch_reasons(plan))
    return tuple(dict.fromkeys(reasons))


def evaluate_public_feed_connector_gate(plan: object) -> PublicFeedConnectorGateDecision:
    reasons = public_feed_connector_plan_rejection_reasons(plan)
    if not isinstance(plan, PublicFeedConnectorPlan):
        return PublicFeedConnectorGateDecision(
            accepted=False,
            connector_id=None,
            mode=None,
            venue_id=None,
            symbol=None,
            canonical_symbol=None,
            feed_type=None,
            rejection_reasons=reasons,
            connector_ready=False,
            offline_only=False,
        )

    offline_only = plan.mode is PublicFeedConnectorMode.OFFLINE_SIMULATED and plan.network_enabled is False
    accepted = reasons == () and offline_only
    return PublicFeedConnectorGateDecision(
        accepted=accepted,
        connector_id=plan.connector_id,
        mode=plan.mode,
        venue_id=plan.venue_id,
        symbol=plan.symbol,
        canonical_symbol=plan.canonical_symbol,
        feed_type=plan.feed_type,
        rejection_reasons=reasons,
        connector_ready=accepted,
        offline_only=offline_only,
    )


def public_feed_connector_ready(decision: PublicFeedConnectorGateDecision | None) -> bool:
    return (
        isinstance(decision, PublicFeedConnectorGateDecision)
        and decision.accepted is True
        and decision.connector_ready is True
        and decision.offline_only is True
        and decision.rejection_reasons == ()
    )


def public_feed_connector_plan_to_dict(plan: PublicFeedConnectorPlan) -> dict[str, object]:
    return {
        "connector_id": plan.connector_id,
        "mode": plan.mode.value,
        "venue_id": plan.venue_id.value,
        "symbol": plan.symbol,
        "canonical_symbol": plan.canonical_symbol,
        "feed_type": plan.feed_type.value,
        "dialect": public_feed_dialect_spec_to_dict(plan.dialect),
        "subscription": public_feed_subscription_to_dict(plan.subscription),
        "policy": public_feed_policy_to_dict(plan.policy),
        "created_at_ns": plan.created_at_ns,
        "require_verified_dialect": plan.require_verified_dialect,
        "require_subscription_enabled": plan.require_subscription_enabled,
        "require_policy_valid": plan.require_policy_valid,
        "network_enabled": plan.network_enabled,
        "rejection_reasons": list(plan.rejection_reasons),
    }


def public_feed_connector_plan_from_dict(data: object) -> PublicFeedConnectorPlan:
    payload = _mapping(data, "public feed connector plan payload")
    return PublicFeedConnectorPlan(
        connector_id=_non_empty_string(payload.get("connector_id"), "connector_id"),
        mode=_mode(payload.get("mode")),
        venue_id=_venue_id(payload.get("venue_id")),
        symbol=_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_feed_type(payload.get("feed_type")),
        dialect=public_feed_dialect_spec_from_dict(payload.get("dialect")),
        subscription=public_feed_subscription_from_dict(payload.get("subscription")),
        policy=public_feed_policy_from_dict(payload.get("policy")),
        created_at_ns=_positive_int_field(payload.get("created_at_ns"), "created_at_ns"),
        require_verified_dialect=_bool(payload.get("require_verified_dialect"), "require_verified_dialect"),
        require_subscription_enabled=_bool(
            payload.get("require_subscription_enabled"),
            "require_subscription_enabled",
        ),
        require_policy_valid=_bool(payload.get("require_policy_valid"), "require_policy_valid"),
        network_enabled=_bool(payload.get("network_enabled"), "network_enabled"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_connector_gate_decision_to_dict(
    decision: PublicFeedConnectorGateDecision,
) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "connector_id": decision.connector_id,
        "mode": None if decision.mode is None else decision.mode.value,
        "venue_id": None if decision.venue_id is None else decision.venue_id.value,
        "symbol": decision.symbol,
        "canonical_symbol": decision.canonical_symbol,
        "feed_type": None if decision.feed_type is None else decision.feed_type.value,
        "rejection_reasons": list(decision.rejection_reasons),
        "connector_ready": decision.connector_ready,
        "offline_only": decision.offline_only,
    }


def public_feed_connector_gate_decision_from_dict(data: object) -> PublicFeedConnectorGateDecision:
    payload = _mapping(data, "public feed connector gate decision payload")
    return PublicFeedConnectorGateDecision(
        accepted=_bool(payload.get("accepted"), "accepted"),
        connector_id=_optional_non_empty_string(payload.get("connector_id"), "connector_id"),
        mode=_optional_mode(payload.get("mode")),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        symbol=_optional_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_optional_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_optional_feed_type(payload.get("feed_type")),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        connector_ready=_bool(payload.get("connector_ready"), "connector_ready"),
        offline_only=_bool(payload.get("offline_only"), "offline_only"),
    )


def _dialect_reasons(plan: PublicFeedConnectorPlan) -> tuple[str, ...]:
    if not isinstance(plan.dialect, PublicFeedDialectSpec):
        return ("public_connector:dialect_missing",)
    reasons: list[str] = []
    dialect_reasons = public_feed_dialect_rejection_reasons(plan.dialect)
    if plan.require_verified_dialect and not public_feed_dialect_connector_ready(plan.dialect):
        reasons.append("public_connector:dialect_not_ready")
    if not plan.dialect.supports_delta_stream:
        reasons.append("public_feed_dialect:delta_stream_unsupported")
    reasons.extend(dialect_reasons)
    return tuple(dict.fromkeys(reasons))


def _subscription_reasons(plan: PublicFeedConnectorPlan) -> tuple[str, ...]:
    if not isinstance(plan.subscription, PublicFeedSubscription):
        return ("public_connector:subscription_missing",)
    reasons: list[str] = []
    subscription_reasons = validate_public_feed_subscription(plan.subscription)
    if plan.require_subscription_enabled and not plan.subscription.enabled:
        reasons.append("public_connector:subscription_disabled")
    if subscription_reasons:
        if "public_feed_source:subscription_disabled" in subscription_reasons:
            reasons.append("public_connector:subscription_disabled")
        reasons.append("public_connector:subscription_rejected")
        reasons.extend(subscription_reasons)
    return tuple(dict.fromkeys(reasons))


def _policy_reasons(plan: PublicFeedConnectorPlan) -> tuple[str, ...]:
    if not isinstance(plan.policy, PublicFeedPolicy):
        return ("public_connector:policy_missing",)
    policy_reasons = public_feed_policy_rejection_reasons(plan.policy)
    if plan.require_policy_valid and policy_reasons:
        return tuple(dict.fromkeys(("public_connector:policy_rejected", *policy_reasons)))
    return tuple(policy_reasons)


def _identity_mismatch_reasons(plan: PublicFeedConnectorPlan) -> tuple[str, ...]:
    reasons: list[str] = []
    identities = (plan.dialect, plan.subscription, plan.policy)
    for item in identities:
        if hasattr(item, "venue_id") and item.venue_id != plan.venue_id:
            reasons.append("public_connector:venue_mismatch")
        if hasattr(item, "symbol") and item.symbol != plan.symbol:
            reasons.append("public_connector:symbol_mismatch")
        if hasattr(item, "canonical_symbol") and item.canonical_symbol != plan.canonical_symbol:
            reasons.append("public_connector:symbol_mismatch")
        if hasattr(item, "feed_type") and item.feed_type != plan.feed_type:
            reasons.append("public_connector:feed_type_mismatch")
    return tuple(dict.fromkeys(reasons))


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    reasons = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        return (fallback,)
    return reasons


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedConnectorError(f"{name} must be a mapping")
    return data


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedConnectorError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedConnectorError(f"{field_name} must be a positive integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedConnectorError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedConnectorError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedConnectorError(f"{field_name} must contain non-empty strings")
    return result


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicFeedConnectorError("venue_id is unsupported") from exc
    raise PublicFeedConnectorError("venue_id is malformed")


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
            raise PublicFeedConnectorError("feed_type is unsupported") from exc
    raise PublicFeedConnectorError("feed_type is malformed")


def _optional_feed_type(value: object) -> PublicFeedType | None:
    if value is None:
        return None
    return _feed_type(value)


def _mode(value: object) -> PublicFeedConnectorMode:
    if isinstance(value, PublicFeedConnectorMode):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedConnectorMode(value)
        except ValueError as exc:
            raise PublicFeedConnectorError("mode is unsupported") from exc
    raise PublicFeedConnectorError("mode is malformed")


def _optional_mode(value: object) -> PublicFeedConnectorMode | None:
    if value is None:
        return None
    return _mode(value)


__all__ = [
    "PublicFeedConnectorError",
    "PublicFeedConnectorGateDecision",
    "PublicFeedConnectorMode",
    "PublicFeedConnectorPlan",
    "evaluate_public_feed_connector_gate",
    "public_feed_connector_gate_decision_from_dict",
    "public_feed_connector_gate_decision_to_dict",
    "public_feed_connector_plan_from_dict",
    "public_feed_connector_plan_rejection_reasons",
    "public_feed_connector_plan_to_dict",
    "public_feed_connector_ready",
]
