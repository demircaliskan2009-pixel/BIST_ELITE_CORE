from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from crypto_core.venue.contracts import VenueId

PUBLIC_MARKET_DATA_ONLY_RUN_MODE = "PUBLIC_MARKET_DATA_ONLY"
_T = TypeVar("_T")


class PublicConnectorEnablementError(ValueError):
    """Raised when inert public connector enablement payloads are malformed."""


class PublicConnectorEnablementStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PublicConnectorEnablementRequest:
    venue_id: VenueId
    dialect_id: str
    operational_evidence_accepted: bool
    static_registry_verified: bool
    connector_enablement_status: PublicConnectorEnablementStatus
    reviewer_id: str
    reviewed_at_iso: str
    approved_run_mode: str
    evidence_refs: tuple[str, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicConnectorEnablementDecision:
    accepted: bool
    venue_id: VenueId | None
    dialect_id: str | None
    rejection_reasons: tuple[str, ...]


def evaluate_public_connector_enablement(request: object) -> PublicConnectorEnablementDecision:
    if not isinstance(request, PublicConnectorEnablementRequest):
        return PublicConnectorEnablementDecision(
            accepted=False,
            venue_id=None,
            dialect_id=None,
            rejection_reasons=("public_connector_enablement:malformed",),
        )

    reasons: list[str] = []
    venue = request.venue_id if isinstance(request.venue_id, VenueId) else None
    dialect_id = request.dialect_id if _provided_string(request.dialect_id) else None

    if venue is None or dialect_id is None:
        reasons.append("public_connector_enablement:malformed")
    if request.operational_evidence_accepted is not True:
        reasons.append("public_connector_enablement:operational_evidence_not_accepted")
    if request.static_registry_verified is not True:
        reasons.append("public_connector_enablement:static_registry_unverified")
    if not isinstance(request.connector_enablement_status, PublicConnectorEnablementStatus):
        reasons.append("public_connector_enablement:malformed")
    elif request.connector_enablement_status is PublicConnectorEnablementStatus.PENDING:
        reasons.append("public_connector_enablement:pending")
    elif request.connector_enablement_status is PublicConnectorEnablementStatus.REJECTED:
        reasons.append("public_connector_enablement:rejected")
    if not _provided_string(request.reviewer_id):
        reasons.append("public_connector_enablement:missing_reviewer")
    if not _provided_string(request.reviewed_at_iso):
        reasons.append("public_connector_enablement:missing_review_time")
    if request.approved_run_mode != PUBLIC_MARKET_DATA_ONLY_RUN_MODE:
        reasons.append("public_connector_enablement:invalid_run_mode")
    if not _provided_string_tuple(request.evidence_refs):
        reasons.append("public_connector_enablement:missing_evidence_ref")
    if not _strict_string_tuple_valid(request.rejection_reasons) or request.rejection_reasons:
        reasons.append("public_connector_enablement:preexisting_rejection")
        if _strict_string_tuple_valid(request.rejection_reasons):
            reasons.extend(request.rejection_reasons)

    rejection_reasons = tuple(dict.fromkeys(reasons))
    return PublicConnectorEnablementDecision(
        accepted=rejection_reasons == (),
        venue_id=venue,
        dialect_id=dialect_id,
        rejection_reasons=rejection_reasons,
    )


def public_connector_enablement_ready(decision: PublicConnectorEnablementDecision | None) -> bool:
    return (
        isinstance(decision, PublicConnectorEnablementDecision)
        and decision.accepted is True
        and decision.venue_id is not None
        and decision.dialect_id is not None
        and decision.rejection_reasons == ()
    )


def public_connector_enablement_request_to_dict(
    request: PublicConnectorEnablementRequest,
) -> dict[str, object]:
    return {
        "venue_id": request.venue_id.value,
        "dialect_id": request.dialect_id,
        "operational_evidence_accepted": request.operational_evidence_accepted,
        "static_registry_verified": request.static_registry_verified,
        "connector_enablement_status": request.connector_enablement_status.value,
        "reviewer_id": request.reviewer_id,
        "reviewed_at_iso": request.reviewed_at_iso,
        "approved_run_mode": request.approved_run_mode,
        "evidence_refs": list(request.evidence_refs),
        "rejection_reasons": list(request.rejection_reasons),
    }


def public_connector_enablement_request_from_dict(payload: object) -> PublicConnectorEnablementRequest:
    data = _mapping(payload, "public connector enablement request payload")
    return PublicConnectorEnablementRequest(
        venue_id=_venue_id(data.get("venue_id")),
        dialect_id=_string_field(data.get("dialect_id"), "dialect_id"),
        operational_evidence_accepted=_bool_field(
            data.get("operational_evidence_accepted"),
            "operational_evidence_accepted",
        ),
        static_registry_verified=_bool_field(data.get("static_registry_verified"), "static_registry_verified"),
        connector_enablement_status=_status(
            data.get("connector_enablement_status"),
            "connector_enablement_status",
        ),
        reviewer_id=_string_field(data.get("reviewer_id"), "reviewer_id"),
        reviewed_at_iso=_string_field(data.get("reviewed_at_iso"), "reviewed_at_iso"),
        approved_run_mode=_string_field(data.get("approved_run_mode"), "approved_run_mode"),
        evidence_refs=_string_tuple(data.get("evidence_refs"), "evidence_refs"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_connector_enablement_decision_to_dict(
    decision: PublicConnectorEnablementDecision,
) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "venue_id": None if decision.venue_id is None else decision.venue_id.value,
        "dialect_id": decision.dialect_id,
        "rejection_reasons": list(decision.rejection_reasons),
    }


def public_connector_enablement_decision_from_dict(payload: object) -> PublicConnectorEnablementDecision:
    data = _mapping(payload, "public connector enablement decision payload")
    venue_value = data.get("venue_id")
    return PublicConnectorEnablementDecision(
        accepted=_bool_field(data.get("accepted"), "accepted"),
        venue_id=None if venue_value is None else _venue_id(venue_value),
        dialect_id=_optional_string_field(data.get("dialect_id"), "dialect_id"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


def aggregate_public_connector_enablement_decisions(
    decisions: object,
) -> PublicConnectorEnablementDecision:
    if not isinstance(decisions, (tuple, list)) or not decisions:
        return PublicConnectorEnablementDecision(
            accepted=False,
            venue_id=None,
            dialect_id=None,
            rejection_reasons=("public_connector_enablement:malformed",),
        )

    reasons: list[str] = []
    accepted_flags: list[bool] = []
    venue_ids: list[VenueId] = []
    dialect_ids: list[str] = []
    for decision in decisions:
        if not isinstance(decision, PublicConnectorEnablementDecision):
            reasons.append("public_connector_enablement:malformed")
            continue
        accepted_flags.append(decision.accepted)
        reasons.extend(decision.rejection_reasons)
        if not decision.accepted and not decision.rejection_reasons:
            reasons.append("public_connector_enablement:malformed")
        if decision.venue_id is not None:
            venue_ids.append(decision.venue_id)
        if decision.dialect_id is not None:
            dialect_ids.append(decision.dialect_id)

    rejection_reasons = tuple(dict.fromkeys(reasons))
    return PublicConnectorEnablementDecision(
        accepted=rejection_reasons == () and len(accepted_flags) == len(decisions) and all(accepted_flags),
        venue_id=_single_or_none(venue_ids),
        dialect_id=_single_or_none(dialect_ids),
        rejection_reasons=rejection_reasons,
    )


def _mapping(payload: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise PublicConnectorEnablementError(f"{field_name} must be a mapping")
    return payload


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicConnectorEnablementError("venue_id is unsupported") from exc
    raise PublicConnectorEnablementError("venue_id is malformed")


def _status(value: object, field_name: str) -> PublicConnectorEnablementStatus:
    if isinstance(value, PublicConnectorEnablementStatus):
        return value
    if isinstance(value, str):
        try:
            return PublicConnectorEnablementStatus(value)
        except ValueError as exc:
            raise PublicConnectorEnablementError(f"{field_name} is unsupported") from exc
    raise PublicConnectorEnablementError(f"{field_name} is malformed")


def _string_field(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PublicConnectorEnablementError(f"{field_name} must be a string")
    return value


def _optional_string_field(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string_field(value, field_name)


def _bool_field(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicConnectorEnablementError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise PublicConnectorEnablementError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise PublicConnectorEnablementError(f"{field_name} must contain non-empty strings")
    return result


def _strict_string_tuple_valid(value: object) -> bool:
    if not isinstance(value, (tuple, list)):
        return False
    return all(isinstance(item, str) and bool(item) for item in value)


def _provided_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value != "PENDING"


def _provided_string_tuple(value: object) -> bool:
    if not isinstance(value, (tuple, list)):
        return False
    return any(_provided_string(item) for item in value)


def _single_or_none(items: list[_T]) -> _T | None:
    unique = tuple(dict.fromkeys(items))
    return unique[0] if len(unique) == 1 else None


__all__ = [
    "PUBLIC_MARKET_DATA_ONLY_RUN_MODE",
    "PublicConnectorEnablementDecision",
    "PublicConnectorEnablementError",
    "PublicConnectorEnablementRequest",
    "PublicConnectorEnablementStatus",
    "aggregate_public_connector_enablement_decisions",
    "evaluate_public_connector_enablement",
    "public_connector_enablement_decision_from_dict",
    "public_connector_enablement_decision_to_dict",
    "public_connector_enablement_ready",
    "public_connector_enablement_request_from_dict",
    "public_connector_enablement_request_to_dict",
]
