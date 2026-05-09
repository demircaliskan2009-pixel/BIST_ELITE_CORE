from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crypto_core.data.public_feed_adapter import (
    PublicFeedAdapterReadiness,
    public_feed_adapter_readiness_from_dict,
    public_feed_adapter_readiness_to_dict,
    public_feed_adapter_ready,
)
from crypto_core.data.public_feed_run_plan import (
    PublicFeedConnectorRunDecision,
    public_feed_run_decision_from_dict,
    public_feed_run_decision_ready,
    public_feed_run_decision_to_dict,
)
from crypto_core.data.public_network_authorization import (
    PublicNetworkAuthorizationDecision,
    public_network_authorization_decision_from_dict,
    public_network_authorization_decision_to_dict,
    public_network_authorization_ready,
)
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.operational_evidence_readiness import (
    OperationalEvidenceReadinessResult,
    operational_evidence_readiness_result_from_dict,
    operational_evidence_readiness_result_to_dict,
    operational_evidence_ready,
)


class DeribitPublicConnectorDesignError(ValueError):
    """Raised when inert Deribit public connector design payloads are malformed."""


class DeribitPublicConnectorDesignStatus(str, Enum):
    BLOCKED = "blocked"
    DESIGN_READY = "design_ready"


@dataclass(frozen=True)
class DeribitPublicConnectorDesignContract:
    contract_id: str
    venue_id: VenueId
    dialect_id: str
    feed_type: PublicFeedType
    instrument_name: str
    operational_evidence_result: OperationalEvidenceReadinessResult
    network_authorization_decision: PublicNetworkAuthorizationDecision
    adapter_readiness: PublicFeedAdapterReadiness
    run_decision: PublicFeedConnectorRunDecision
    required_event_types: tuple[str, ...]
    required_state_transitions: tuple[str, ...]
    required_fail_closed_conditions: tuple[str, ...]
    allowed_methods: tuple[str, ...]
    forbidden_methods: tuple[str, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeribitPublicConnectorDesignDecision:
    accepted: bool
    contract_id: str | None
    venue_id: VenueId | None
    dialect_id: str | None
    feed_type: PublicFeedType | None
    status: DeribitPublicConnectorDesignStatus
    rejection_reasons: tuple[str, ...]


DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES = (
    "snapshot",
    "delta",
    "gap",
    "resync_requested",
    "heartbeat_or_liveness",
)

DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES = (
    "DISCONNECTED",
    "SUBSCRIBING",
    "SNAPSHOT_PENDING",
    "STREAMING",
    "GAP_DETECTED",
    "RESYNC_REQUIRED",
    "HALTED",
)

DERIBIT_PUBLIC_CONNECTOR_ALLOWED_STATE_EDGES = (
    ("DISCONNECTED", "SUBSCRIBING"),
    ("SUBSCRIBING", "SNAPSHOT_PENDING"),
    ("SNAPSHOT_PENDING", "STREAMING"),
    ("STREAMING", "GAP_DETECTED"),
    ("GAP_DETECTED", "RESYNC_REQUIRED"),
    ("GAP_DETECTED", "HALTED"),
    ("RESYNC_REQUIRED", "SUBSCRIBING"),
    ("RESYNC_REQUIRED", "HALTED"),
)

DERIBIT_PUBLIC_CONNECTOR_PAPER_READY_STATES = ("STREAMING",)
DERIBIT_PUBLIC_CONNECTOR_TERMINAL_STATES = ("HALTED",)

DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS = (
    "connect",
    "start",
    "recv",
    "receive",
    "send",
    "subscribe",
    "place_order",
    "cancel_order",
)

DERIBIT_PUBLIC_CONNECTOR_RUNTIME_METHODS = (
    *DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS,
    "stop",
)


def deribit_public_connector_design_rejection_reasons(contract: object) -> tuple[str, ...]:
    if contract is None:
        return ("deribit_connector_design:contract_missing",)
    if not isinstance(contract, DeribitPublicConnectorDesignContract):
        return ("deribit_connector_design:contract_malformed",)

    reasons: list[str] = []
    if not _non_empty(contract.contract_id):
        reasons.append("deribit_connector_design:contract_malformed")
    if contract.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_connector_design:wrong_venue")
    if not _non_empty(contract.dialect_id):
        reasons.append("deribit_connector_design:contract_malformed")
    if not _non_empty(contract.instrument_name):
        reasons.append("deribit_connector_design:contract_malformed")
    if not isinstance(contract.feed_type, PublicFeedType):
        reasons.append("deribit_connector_design:contract_malformed")

    if not operational_evidence_ready(contract.operational_evidence_result):
        reasons.append("deribit_connector_design:operational_evidence_not_ready")
        if isinstance(contract.operational_evidence_result, OperationalEvidenceReadinessResult):
            reasons.extend(contract.operational_evidence_result.rejection_reasons)

    if not public_network_authorization_ready(contract.network_authorization_decision):
        reasons.append("deribit_connector_design:network_not_authorized")
        if isinstance(contract.network_authorization_decision, PublicNetworkAuthorizationDecision):
            reasons.extend(contract.network_authorization_decision.rejection_reasons)

    if not public_feed_adapter_ready(contract.adapter_readiness):
        reasons.append("deribit_connector_design:adapter_not_ready")
        if isinstance(contract.adapter_readiness, PublicFeedAdapterReadiness):
            reasons.extend(contract.adapter_readiness.rejection_reasons)

    if not public_feed_run_decision_ready(contract.run_decision):
        reasons.append("deribit_connector_design:run_not_ready")
        if isinstance(contract.run_decision, PublicFeedConnectorRunDecision):
            reasons.extend(contract.run_decision.rejection_reasons)

    reasons.extend(_identity_rejection_reasons(contract))
    reasons.extend(_required_item_reasons(contract.required_event_types, DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES))
    reasons.extend(
        _required_item_reasons(contract.required_state_transitions, DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES)
    )
    reasons.extend(_method_rejection_reasons(contract))
    if not _string_tuple_valid(contract.required_fail_closed_conditions, allow_empty=False):
        reasons.append("deribit_connector_design:contract_malformed")
    reasons.extend(_string_reasons(contract.rejection_reasons, "deribit_connector_design:contract_malformed"))
    return tuple(dict.fromkeys(reasons))


def evaluate_deribit_public_connector_design(contract: object) -> DeribitPublicConnectorDesignDecision:
    reasons = deribit_public_connector_design_rejection_reasons(contract)
    if not isinstance(contract, DeribitPublicConnectorDesignContract):
        return DeribitPublicConnectorDesignDecision(
            accepted=False,
            contract_id=None,
            venue_id=None,
            dialect_id=None,
            feed_type=None,
            status=DeribitPublicConnectorDesignStatus.BLOCKED,
            rejection_reasons=reasons,
        )

    accepted = reasons == ()
    return DeribitPublicConnectorDesignDecision(
        accepted=accepted,
        contract_id=contract.contract_id,
        venue_id=contract.venue_id if isinstance(contract.venue_id, VenueId) else None,
        dialect_id=contract.dialect_id,
        feed_type=contract.feed_type if isinstance(contract.feed_type, PublicFeedType) else None,
        status=DeribitPublicConnectorDesignStatus.DESIGN_READY
        if accepted
        else DeribitPublicConnectorDesignStatus.BLOCKED,
        rejection_reasons=reasons,
    )


def deribit_public_connector_design_ready(decision: DeribitPublicConnectorDesignDecision | None) -> bool:
    return (
        isinstance(decision, DeribitPublicConnectorDesignDecision)
        and decision.accepted is True
        and decision.status is DeribitPublicConnectorDesignStatus.DESIGN_READY
        and decision.rejection_reasons == ()
    )


def deribit_public_connector_design_contract_to_dict(
    contract: DeribitPublicConnectorDesignContract,
) -> dict[str, object]:
    return {
        "contract_id": contract.contract_id,
        "venue_id": contract.venue_id.value,
        "dialect_id": contract.dialect_id,
        "feed_type": contract.feed_type.value,
        "instrument_name": contract.instrument_name,
        "operational_evidence_result": operational_evidence_readiness_result_to_dict(
            contract.operational_evidence_result
        ),
        "network_authorization_decision": public_network_authorization_decision_to_dict(
            contract.network_authorization_decision
        ),
        "adapter_readiness": public_feed_adapter_readiness_to_dict(contract.adapter_readiness),
        "run_decision": public_feed_run_decision_to_dict(contract.run_decision),
        "required_event_types": list(contract.required_event_types),
        "required_state_transitions": list(contract.required_state_transitions),
        "required_fail_closed_conditions": list(contract.required_fail_closed_conditions),
        "allowed_methods": list(contract.allowed_methods),
        "forbidden_methods": list(contract.forbidden_methods),
        "rejection_reasons": list(contract.rejection_reasons),
    }


def deribit_public_connector_design_contract_from_dict(data: object) -> DeribitPublicConnectorDesignContract:
    payload = _mapping(data, "Deribit public connector design contract payload")
    return DeribitPublicConnectorDesignContract(
        contract_id=_non_empty_string(payload.get("contract_id"), "contract_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        dialect_id=_non_empty_string(payload.get("dialect_id"), "dialect_id"),
        feed_type=_feed_type(payload.get("feed_type")),
        instrument_name=_non_empty_string(payload.get("instrument_name"), "instrument_name"),
        operational_evidence_result=operational_evidence_readiness_result_from_dict(
            payload.get("operational_evidence_result")
        ),
        network_authorization_decision=public_network_authorization_decision_from_dict(
            payload.get("network_authorization_decision")
        ),
        adapter_readiness=public_feed_adapter_readiness_from_dict(payload.get("adapter_readiness")),
        run_decision=public_feed_run_decision_from_dict(payload.get("run_decision")),
        required_event_types=_string_tuple(payload.get("required_event_types"), "required_event_types"),
        required_state_transitions=_string_tuple(
            payload.get("required_state_transitions"),
            "required_state_transitions",
        ),
        required_fail_closed_conditions=_string_tuple(
            payload.get("required_fail_closed_conditions"),
            "required_fail_closed_conditions",
        ),
        allowed_methods=_string_tuple(payload.get("allowed_methods"), "allowed_methods"),
        forbidden_methods=_string_tuple(payload.get("forbidden_methods"), "forbidden_methods"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def deribit_public_connector_design_decision_to_dict(
    decision: DeribitPublicConnectorDesignDecision,
) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "contract_id": decision.contract_id,
        "venue_id": None if decision.venue_id is None else decision.venue_id.value,
        "dialect_id": decision.dialect_id,
        "feed_type": None if decision.feed_type is None else decision.feed_type.value,
        "status": decision.status.value,
        "rejection_reasons": list(decision.rejection_reasons),
    }


def deribit_public_connector_design_decision_from_dict(data: object) -> DeribitPublicConnectorDesignDecision:
    payload = _mapping(data, "Deribit public connector design decision payload")
    return DeribitPublicConnectorDesignDecision(
        accepted=_bool(payload.get("accepted"), "accepted"),
        contract_id=_optional_non_empty_string(payload.get("contract_id"), "contract_id"),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        dialect_id=_optional_non_empty_string(payload.get("dialect_id"), "dialect_id"),
        feed_type=_optional_feed_type(payload.get("feed_type")),
        status=_design_status(payload.get("status")),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _identity_rejection_reasons(contract: DeribitPublicConnectorDesignContract) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        isinstance(contract.operational_evidence_result, OperationalEvidenceReadinessResult)
        and contract.operational_evidence_result.venue_id is not None
        and contract.operational_evidence_result.venue_id is not contract.venue_id
    ):
        reasons.append("deribit_connector_design:wrong_venue")
    if (
        isinstance(contract.network_authorization_decision, PublicNetworkAuthorizationDecision)
        and contract.network_authorization_decision.venue_id is not None
        and contract.network_authorization_decision.venue_id is not contract.venue_id
    ):
        reasons.append("deribit_connector_design:network_not_authorized")
    if (
        isinstance(contract.adapter_readiness, PublicFeedAdapterReadiness)
        and contract.adapter_readiness.venue_id is not None
        and contract.adapter_readiness.venue_id is not contract.venue_id
    ):
        reasons.append("deribit_connector_design:adapter_not_ready")
    if isinstance(contract.run_decision, PublicFeedConnectorRunDecision):
        if contract.run_decision.venue_id is not None and contract.run_decision.venue_id is not contract.venue_id:
            reasons.append("deribit_connector_design:run_not_ready")
        if contract.run_decision.feed_type is not None and contract.run_decision.feed_type is not contract.feed_type:
            reasons.append("deribit_connector_design:run_not_ready")
    return tuple(dict.fromkeys(reasons))


def _required_item_reasons(value: object, required_items: tuple[str, ...]) -> tuple[str, ...]:
    if not _string_tuple_valid(value, allow_empty=False):
        return ("deribit_connector_design:contract_malformed",)
    provided = set(value)
    return tuple(
        "deribit_connector_design:required_event_missing"
        if item in DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES
        else "deribit_connector_design:state_transition_missing"
        for item in required_items
        if item not in provided
    )


def _method_rejection_reasons(contract: DeribitPublicConnectorDesignContract) -> tuple[str, ...]:
    if not _string_tuple_valid(contract.allowed_methods, allow_empty=True) or not _string_tuple_valid(
        contract.forbidden_methods,
        allow_empty=False,
    ):
        return ("deribit_connector_design:contract_malformed",)
    reasons: list[str] = []
    forbidden = set(contract.forbidden_methods)
    allowed = set(contract.allowed_methods)
    for method_name in DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS:
        if method_name not in forbidden:
            reasons.append("deribit_connector_design:forbidden_runtime_method")
    if allowed.intersection(DERIBIT_PUBLIC_CONNECTOR_RUNTIME_METHODS):
        reasons.append("deribit_connector_design:unsafe_allowed_method")
    return tuple(dict.fromkeys(reasons))


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise DeribitPublicConnectorDesignError(f"{name} must be a mapping")
    return data


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise DeribitPublicConnectorDesignError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise DeribitPublicConnectorDesignError(f"{field_name} must be a boolean")
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


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise DeribitPublicConnectorDesignError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise DeribitPublicConnectorDesignError(f"{field_name} must contain non-empty strings")
    return result


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise DeribitPublicConnectorDesignError("venue_id is unsupported") from exc
    raise DeribitPublicConnectorDesignError("venue_id is malformed")


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
            raise DeribitPublicConnectorDesignError("feed_type is unsupported") from exc
    raise DeribitPublicConnectorDesignError("feed_type is malformed")


def _optional_feed_type(value: object) -> PublicFeedType | None:
    if value is None:
        return None
    return _feed_type(value)


def _design_status(value: object) -> DeribitPublicConnectorDesignStatus:
    if isinstance(value, DeribitPublicConnectorDesignStatus):
        return value
    if isinstance(value, str):
        try:
            return DeribitPublicConnectorDesignStatus(value)
        except ValueError as exc:
            raise DeribitPublicConnectorDesignError("status is unsupported") from exc
    raise DeribitPublicConnectorDesignError("status is malformed")


__all__ = [
    "DERIBIT_PUBLIC_CONNECTOR_ALLOWED_STATE_EDGES",
    "DERIBIT_PUBLIC_CONNECTOR_PAPER_READY_STATES",
    "DERIBIT_PUBLIC_CONNECTOR_REQUIRED_EVENT_TYPES",
    "DERIBIT_PUBLIC_CONNECTOR_REQUIRED_FORBIDDEN_METHODS",
    "DERIBIT_PUBLIC_CONNECTOR_REQUIRED_STATES",
    "DERIBIT_PUBLIC_CONNECTOR_RUNTIME_METHODS",
    "DERIBIT_PUBLIC_CONNECTOR_TERMINAL_STATES",
    "DeribitPublicConnectorDesignContract",
    "DeribitPublicConnectorDesignDecision",
    "DeribitPublicConnectorDesignError",
    "DeribitPublicConnectorDesignStatus",
    "deribit_public_connector_design_contract_from_dict",
    "deribit_public_connector_design_contract_to_dict",
    "deribit_public_connector_design_decision_from_dict",
    "deribit_public_connector_design_decision_to_dict",
    "deribit_public_connector_design_ready",
    "deribit_public_connector_design_rejection_reasons",
    "evaluate_deribit_public_connector_design",
]
