from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crypto_core.data.public_feed_adapter import (
    PublicFeedAdapterDescriptor,
    PublicFeedAdapterReadiness,
    public_feed_adapter_descriptor_from_dict,
    public_feed_adapter_descriptor_to_dict,
    public_feed_adapter_readiness_from_dict,
    public_feed_adapter_readiness_to_dict,
    public_feed_adapter_ready,
)
from crypto_core.data.public_feed_connector import (
    PublicFeedConnectorGateDecision,
    public_feed_connector_gate_decision_from_dict,
    public_feed_connector_gate_decision_to_dict,
    public_feed_connector_ready,
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
from crypto_core.data.public_network_authorization import (
    PublicNetworkAuthorizationDecision,
    public_network_authorization_decision_from_dict,
    public_network_authorization_decision_to_dict,
    public_network_authorization_ready,
)
from crypto_core.venue.contracts import PublicFeedType, VenueId


class PublicFeedRunPlanError(ValueError):
    """Raised when inert public-feed run-plan payloads are malformed."""


class PublicFeedRunMode(str, Enum):
    DISABLED = "disabled"
    OFFLINE_REPLAY = "offline_replay"
    PUBLIC_NETWORK_AUTHORIZED_BUT_NOT_STARTED = "public_network_authorized_but_not_started"


@dataclass(frozen=True)
class PublicFeedConnectorRunPlan:
    run_id: str
    mode: PublicFeedRunMode
    adapter_descriptor: PublicFeedAdapterDescriptor
    adapter_readiness: PublicFeedAdapterReadiness
    network_authorization_decision: PublicNetworkAuthorizationDecision
    connector_gate: PublicFeedConnectorGateDecision
    subscription: PublicFeedSubscription
    policy: PublicFeedPolicy
    max_runtime_ns: int
    max_envelopes: int
    max_reconnects: int
    created_at_ns: int
    dry_run_only: bool
    network_start_forbidden: bool = True
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedConnectorRunDecision:
    accepted: bool
    run_id: str | None
    mode: PublicFeedRunMode | None
    venue_id: VenueId | None
    symbol: str | None
    canonical_symbol: str | None
    feed_type: PublicFeedType | None
    offline_only: bool
    network_start_forbidden: bool
    rejection_reasons: tuple[str, ...]


def public_feed_run_plan_rejection_reasons(plan: object) -> tuple[str, ...]:
    if plan is None:
        return ("public_run:plan_missing",)
    if not isinstance(plan, PublicFeedConnectorRunPlan):
        return ("public_run:plan_malformed",)

    reasons: list[str] = []
    if not _non_empty(plan.run_id):
        reasons.append("public_run:plan_malformed")
    if not isinstance(plan.mode, PublicFeedRunMode):
        reasons.append("public_run:plan_malformed")
    elif plan.mode is PublicFeedRunMode.DISABLED:
        reasons.append("public_run:disabled")
    elif (
        plan.mode is PublicFeedRunMode.PUBLIC_NETWORK_AUTHORIZED_BUT_NOT_STARTED
        and plan.network_start_forbidden is not True
    ):
        reasons.append("public_run:network_start_forbidden_required")

    if plan.dry_run_only is not True:
        reasons.append("public_run:dry_run_required")
    if not _positive_int(plan.max_runtime_ns) or not _positive_int(plan.max_envelopes):
        reasons.append("public_run:invalid_budget")
    if not _non_negative_int(plan.max_reconnects) or not _positive_int(plan.created_at_ns):
        reasons.append("public_run:invalid_budget")
    if not isinstance(plan.network_start_forbidden, bool):
        reasons.append("public_run:plan_malformed")

    reasons.extend(_adapter_readiness_reasons(plan))
    reasons.extend(_network_authorization_reasons(plan))
    reasons.extend(_connector_gate_reasons(plan))
    reasons.extend(_subscription_reasons(plan))
    reasons.extend(_policy_reasons(plan))
    reasons.extend(_identity_mismatch_reasons(plan))
    reasons.extend(_string_reasons(plan.rejection_reasons, "public_run:plan_malformed"))
    return tuple(dict.fromkeys(reasons))


def evaluate_public_feed_run_plan(plan: object) -> PublicFeedConnectorRunDecision:
    reasons = public_feed_run_plan_rejection_reasons(plan)
    if not isinstance(plan, PublicFeedConnectorRunPlan):
        return PublicFeedConnectorRunDecision(
            accepted=False,
            run_id=None,
            mode=None,
            venue_id=None,
            symbol=None,
            canonical_symbol=None,
            feed_type=None,
            offline_only=False,
            network_start_forbidden=True,
            rejection_reasons=reasons,
        )

    offline_only = plan.mode is PublicFeedRunMode.OFFLINE_REPLAY and plan.dry_run_only is True
    return PublicFeedConnectorRunDecision(
        accepted=reasons == (),
        run_id=plan.run_id,
        mode=plan.mode,
        venue_id=plan.subscription.venue_id if isinstance(plan.subscription, PublicFeedSubscription) else None,
        symbol=plan.subscription.symbol if isinstance(plan.subscription, PublicFeedSubscription) else None,
        canonical_symbol=(
            plan.subscription.canonical_symbol if isinstance(plan.subscription, PublicFeedSubscription) else None
        ),
        feed_type=plan.subscription.feed_type if isinstance(plan.subscription, PublicFeedSubscription) else None,
        offline_only=offline_only,
        network_start_forbidden=plan.network_start_forbidden is True,
        rejection_reasons=reasons,
    )


def public_feed_run_decision_ready(decision: PublicFeedConnectorRunDecision | None) -> bool:
    return (
        isinstance(decision, PublicFeedConnectorRunDecision)
        and decision.accepted is True
        and decision.network_start_forbidden is True
        and decision.rejection_reasons == ()
    )


def public_feed_run_plan_to_dict(plan: PublicFeedConnectorRunPlan) -> dict[str, object]:
    return {
        "run_id": plan.run_id,
        "mode": plan.mode.value,
        "adapter_descriptor": public_feed_adapter_descriptor_to_dict(plan.adapter_descriptor),
        "adapter_readiness": public_feed_adapter_readiness_to_dict(plan.adapter_readiness),
        "network_authorization_decision": public_network_authorization_decision_to_dict(
            plan.network_authorization_decision
        ),
        "connector_gate": public_feed_connector_gate_decision_to_dict(plan.connector_gate),
        "subscription": public_feed_subscription_to_dict(plan.subscription),
        "policy": public_feed_policy_to_dict(plan.policy),
        "max_runtime_ns": plan.max_runtime_ns,
        "max_envelopes": plan.max_envelopes,
        "max_reconnects": plan.max_reconnects,
        "created_at_ns": plan.created_at_ns,
        "dry_run_only": plan.dry_run_only,
        "network_start_forbidden": plan.network_start_forbidden,
        "rejection_reasons": list(plan.rejection_reasons),
    }


def public_feed_run_plan_from_dict(data: object) -> PublicFeedConnectorRunPlan:
    payload = _mapping(data, "public feed run plan payload")
    return PublicFeedConnectorRunPlan(
        run_id=_non_empty_string(payload.get("run_id"), "run_id"),
        mode=_mode(payload.get("mode")),
        adapter_descriptor=public_feed_adapter_descriptor_from_dict(payload.get("adapter_descriptor")),
        adapter_readiness=public_feed_adapter_readiness_from_dict(payload.get("adapter_readiness")),
        network_authorization_decision=public_network_authorization_decision_from_dict(
            payload.get("network_authorization_decision")
        ),
        connector_gate=public_feed_connector_gate_decision_from_dict(payload.get("connector_gate")),
        subscription=public_feed_subscription_from_dict(payload.get("subscription")),
        policy=public_feed_policy_from_dict(payload.get("policy")),
        max_runtime_ns=_positive_int_field(payload.get("max_runtime_ns"), "max_runtime_ns"),
        max_envelopes=_positive_int_field(payload.get("max_envelopes"), "max_envelopes"),
        max_reconnects=_non_negative_int_field(payload.get("max_reconnects"), "max_reconnects"),
        created_at_ns=_positive_int_field(payload.get("created_at_ns"), "created_at_ns"),
        dry_run_only=_bool(payload.get("dry_run_only"), "dry_run_only"),
        network_start_forbidden=_bool(payload.get("network_start_forbidden"), "network_start_forbidden"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_run_decision_to_dict(decision: PublicFeedConnectorRunDecision) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "run_id": decision.run_id,
        "mode": None if decision.mode is None else decision.mode.value,
        "venue_id": None if decision.venue_id is None else decision.venue_id.value,
        "symbol": decision.symbol,
        "canonical_symbol": decision.canonical_symbol,
        "feed_type": None if decision.feed_type is None else decision.feed_type.value,
        "offline_only": decision.offline_only,
        "network_start_forbidden": decision.network_start_forbidden,
        "rejection_reasons": list(decision.rejection_reasons),
    }


def public_feed_run_decision_from_dict(data: object) -> PublicFeedConnectorRunDecision:
    payload = _mapping(data, "public feed run decision payload")
    return PublicFeedConnectorRunDecision(
        accepted=_bool(payload.get("accepted"), "accepted"),
        run_id=_optional_non_empty_string(payload.get("run_id"), "run_id"),
        mode=_optional_mode(payload.get("mode")),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        symbol=_optional_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_optional_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_optional_feed_type(payload.get("feed_type")),
        offline_only=_bool(payload.get("offline_only"), "offline_only"),
        network_start_forbidden=_bool(payload.get("network_start_forbidden"), "network_start_forbidden"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _adapter_readiness_reasons(plan: PublicFeedConnectorRunPlan) -> tuple[str, ...]:
    if not isinstance(plan.adapter_descriptor, PublicFeedAdapterDescriptor):
        return ("public_run:adapter_not_ready",)
    if not isinstance(plan.adapter_readiness, PublicFeedAdapterReadiness):
        return ("public_run:adapter_not_ready",)
    reasons: list[str] = []
    if not public_feed_adapter_ready(plan.adapter_readiness):
        reasons.append("public_run:adapter_not_ready")
        reasons.extend(plan.adapter_readiness.rejection_reasons)
    if plan.adapter_readiness.adapter_id != plan.adapter_descriptor.adapter_id:
        reasons.append("public_run:adapter_not_ready")
    if plan.adapter_readiness.venue_id != plan.adapter_descriptor.venue_id:
        reasons.append("public_run:venue_mismatch")
    return tuple(dict.fromkeys(reasons))


def _network_authorization_reasons(plan: PublicFeedConnectorRunPlan) -> tuple[str, ...]:
    if not isinstance(plan.network_authorization_decision, PublicNetworkAuthorizationDecision):
        return ("public_run:network_not_authorized",)
    if public_network_authorization_ready(plan.network_authorization_decision):
        return ()
    return tuple(
        dict.fromkeys(
            (
                "public_run:network_not_authorized",
                *plan.network_authorization_decision.rejection_reasons,
            )
        )
    )


def _connector_gate_reasons(plan: PublicFeedConnectorRunPlan) -> tuple[str, ...]:
    if not isinstance(plan.connector_gate, PublicFeedConnectorGateDecision):
        return ("public_run:connector_gate_not_ready",)
    if public_feed_connector_ready(plan.connector_gate):
        return ()
    return tuple(dict.fromkeys(("public_run:connector_gate_not_ready", *plan.connector_gate.rejection_reasons)))


def _subscription_reasons(plan: PublicFeedConnectorRunPlan) -> tuple[str, ...]:
    if not isinstance(plan.subscription, PublicFeedSubscription):
        return ("public_run:subscription_missing",)
    subscription_reasons = validate_public_feed_subscription(plan.subscription)
    if not subscription_reasons:
        return ()
    return tuple(dict.fromkeys(("public_run:subscription_missing", *subscription_reasons)))


def _policy_reasons(plan: PublicFeedConnectorRunPlan) -> tuple[str, ...]:
    if not isinstance(plan.policy, PublicFeedPolicy):
        return ("public_run:policy_missing",)
    policy_reasons = public_feed_policy_rejection_reasons(plan.policy)
    if not policy_reasons:
        return ()
    return tuple(dict.fromkeys(("public_run:policy_missing", *policy_reasons)))


def _identity_mismatch_reasons(plan: PublicFeedConnectorRunPlan) -> tuple[str, ...]:
    reasons: list[str] = []
    subscription = plan.subscription
    policy = plan.policy
    connector_gate = plan.connector_gate
    descriptor = plan.adapter_descriptor
    network_decision = plan.network_authorization_decision

    if isinstance(subscription, PublicFeedSubscription):
        if isinstance(connector_gate, PublicFeedConnectorGateDecision):
            if connector_gate.venue_id != subscription.venue_id:
                reasons.append("public_run:venue_mismatch")
            if (
                connector_gate.symbol != subscription.symbol
                or connector_gate.canonical_symbol != subscription.canonical_symbol
            ):
                reasons.append("public_run:symbol_mismatch")
            if connector_gate.feed_type != subscription.feed_type:
                reasons.append("public_run:feed_type_mismatch")
        if isinstance(policy, PublicFeedPolicy):
            if policy.venue_id != subscription.venue_id:
                reasons.append("public_run:venue_mismatch")
            if policy.symbol != subscription.symbol or policy.canonical_symbol != subscription.canonical_symbol:
                reasons.append("public_run:symbol_mismatch")
            if policy.feed_type != subscription.feed_type:
                reasons.append("public_run:feed_type_mismatch")
        if isinstance(descriptor, PublicFeedAdapterDescriptor):
            if descriptor.venue_id != subscription.venue_id:
                reasons.append("public_run:venue_mismatch")
            if subscription.symbol not in descriptor.supported_symbols:
                reasons.append("public_run:symbol_mismatch")
            if subscription.feed_type not in descriptor.supported_feed_types:
                reasons.append("public_run:feed_type_mismatch")
        if (
            isinstance(network_decision, PublicNetworkAuthorizationDecision)
            and network_decision.venue_id != subscription.venue_id
        ):
            reasons.append("public_run:venue_mismatch")
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
        raise PublicFeedRunPlanError(f"{name} must be a mapping")
    return data


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedRunPlanError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedRunPlanError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int_field(value: object, field_name: str) -> int:
    if not _non_negative_int(value):
        raise PublicFeedRunPlanError(f"{field_name} must be a non-negative integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedRunPlanError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedRunPlanError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedRunPlanError(f"{field_name} must contain non-empty strings")
    return result


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicFeedRunPlanError("venue_id is unsupported") from exc
    raise PublicFeedRunPlanError("venue_id is malformed")


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
            raise PublicFeedRunPlanError("feed_type is unsupported") from exc
    raise PublicFeedRunPlanError("feed_type is malformed")


def _optional_feed_type(value: object) -> PublicFeedType | None:
    if value is None:
        return None
    return _feed_type(value)


def _mode(value: object) -> PublicFeedRunMode:
    if isinstance(value, PublicFeedRunMode):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedRunMode(value)
        except ValueError as exc:
            raise PublicFeedRunPlanError("mode is unsupported") from exc
    raise PublicFeedRunPlanError("mode is malformed")


def _optional_mode(value: object) -> PublicFeedRunMode | None:
    if value is None:
        return None
    return _mode(value)


__all__ = [
    "PublicFeedConnectorRunDecision",
    "PublicFeedConnectorRunPlan",
    "PublicFeedRunMode",
    "PublicFeedRunPlanError",
    "evaluate_public_feed_run_plan",
    "public_feed_run_decision_from_dict",
    "public_feed_run_decision_ready",
    "public_feed_run_decision_to_dict",
    "public_feed_run_plan_from_dict",
    "public_feed_run_plan_rejection_reasons",
    "public_feed_run_plan_to_dict",
]
