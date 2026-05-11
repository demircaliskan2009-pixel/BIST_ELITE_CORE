from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.venue.contracts import VenueId


class OfficialClaimReviewError(ValueError):
    """Raised when inert official claim-review payloads are malformed."""


class OfficialClaimReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class OfficialClaimReviewDecision:
    claim_id: str
    source_id: str
    venue_id: VenueId
    source_sha256: str
    official_url: str
    doc_section_or_anchor: str
    reviewer_id: str
    reviewed_at_iso: str
    review_status: OfficialClaimReviewStatus
    decision: OfficialClaimReviewStatus
    evidence_refs: tuple[str, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OfficialClaimReviewValidationResult:
    accepted: bool
    claim_id: str | None
    venue_id: VenueId | None
    review_status: OfficialClaimReviewStatus | None
    rejection_reasons: tuple[str, ...]


def validate_official_claim_review(decision: object) -> OfficialClaimReviewValidationResult:
    if not isinstance(decision, OfficialClaimReviewDecision):
        return OfficialClaimReviewValidationResult(
            accepted=False,
            claim_id=None,
            venue_id=None,
            review_status=None,
            rejection_reasons=("official_claim_review:malformed",),
        )

    reasons: list[str] = []
    if not _provided_string(decision.claim_id):
        reasons.append("official_claim_review:missing_claim_id")
    if not _provided_string(decision.source_id):
        reasons.append("official_claim_review:missing_source_id")
    if not isinstance(decision.venue_id, VenueId):
        reasons.append("official_claim_review:missing_venue_id")
    if not _provided_string(decision.official_url):
        reasons.append("official_claim_review:missing_url")
    if not _provided_string(decision.doc_section_or_anchor):
        reasons.append("official_claim_review:missing_section")
    if not _provided_string(decision.source_sha256):
        reasons.append("official_claim_review:missing_hash")
    elif not _valid_sha256_hex(decision.source_sha256):
        reasons.append("official_claim_review:invalid_hash")
    if not _provided_string(decision.reviewer_id):
        reasons.append("official_claim_review:missing_reviewer")
    if not _provided_string(decision.reviewed_at_iso):
        reasons.append("official_claim_review:missing_review_time")
    if not _provided_string_tuple(decision.evidence_refs):
        reasons.append("official_claim_review:missing_evidence_ref")
    if not _string_tuple_valid(decision.rejection_reasons, allow_empty=True) or decision.rejection_reasons:
        reasons.append("official_claim_review:preexisting_rejection")

    if not isinstance(decision.review_status, OfficialClaimReviewStatus) or not isinstance(
        decision.decision,
        OfficialClaimReviewStatus,
    ):
        reasons.append("official_claim_review:malformed")
    elif (
        decision.review_status is OfficialClaimReviewStatus.PENDING
        or decision.decision is OfficialClaimReviewStatus.PENDING
    ):
        reasons.append("official_claim_review:pending")
    elif (
        decision.review_status is OfficialClaimReviewStatus.REJECTED
        or decision.decision is OfficialClaimReviewStatus.REJECTED
    ):
        reasons.append("official_claim_review:rejected")

    rejection_reasons = tuple(dict.fromkeys(reasons))
    return OfficialClaimReviewValidationResult(
        accepted=rejection_reasons == (),
        claim_id=decision.claim_id if _provided_string(decision.claim_id) else None,
        venue_id=decision.venue_id if isinstance(decision.venue_id, VenueId) else None,
        review_status=decision.review_status if isinstance(decision.review_status, OfficialClaimReviewStatus) else None,
        rejection_reasons=rejection_reasons,
    )


def official_claim_review_ready(result: OfficialClaimReviewValidationResult | None) -> bool:
    return (
        isinstance(result, OfficialClaimReviewValidationResult)
        and result.accepted is True
        and result.review_status is OfficialClaimReviewStatus.APPROVED
        and result.rejection_reasons == ()
    )


def official_claim_review_decision_to_dict(decision: OfficialClaimReviewDecision) -> dict[str, object]:
    return {
        "claim_id": decision.claim_id,
        "source_id": decision.source_id,
        "venue_id": decision.venue_id.value,
        "source_sha256": decision.source_sha256,
        "official_url": decision.official_url,
        "doc_section_or_anchor": decision.doc_section_or_anchor,
        "reviewer_id": decision.reviewer_id,
        "reviewed_at_iso": decision.reviewed_at_iso,
        "review_status": decision.review_status.value,
        "decision": decision.decision.value,
        "evidence_refs": list(decision.evidence_refs),
        "rejection_reasons": list(decision.rejection_reasons),
    }


def official_claim_review_decision_from_dict(payload: object) -> OfficialClaimReviewDecision:
    data = _mapping(payload, "official claim-review decision payload")
    return OfficialClaimReviewDecision(
        claim_id=_string_field(data.get("claim_id"), "claim_id"),
        source_id=_string_field(data.get("source_id"), "source_id"),
        venue_id=_venue_id(data.get("venue_id")),
        source_sha256=_string_field(data.get("source_sha256"), "source_sha256"),
        official_url=_string_field(data.get("official_url"), "official_url"),
        doc_section_or_anchor=_string_field(data.get("doc_section_or_anchor"), "doc_section_or_anchor"),
        reviewer_id=_string_field(data.get("reviewer_id"), "reviewer_id"),
        reviewed_at_iso=_string_field(data.get("reviewed_at_iso"), "reviewed_at_iso"),
        review_status=_review_status(data.get("review_status"), "review_status"),
        decision=_review_status(data.get("decision"), "decision"),
        evidence_refs=_string_tuple(data.get("evidence_refs"), "evidence_refs"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


def official_claim_review_validation_result_to_dict(
    result: OfficialClaimReviewValidationResult,
) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "claim_id": result.claim_id,
        "venue_id": None if result.venue_id is None else result.venue_id.value,
        "review_status": None if result.review_status is None else result.review_status.value,
        "rejection_reasons": list(result.rejection_reasons),
    }


def official_claim_review_validation_result_from_dict(payload: object) -> OfficialClaimReviewValidationResult:
    data = _mapping(payload, "official claim-review validation result payload")
    venue_value = data.get("venue_id")
    status_value = data.get("review_status")
    return OfficialClaimReviewValidationResult(
        accepted=_bool_field(data.get("accepted"), "accepted"),
        claim_id=_optional_string_field(data.get("claim_id"), "claim_id"),
        venue_id=None if venue_value is None else _venue_id(venue_value),
        review_status=None if status_value is None else _review_status(status_value, "review_status"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


def aggregate_claim_review_results(results: object) -> OfficialClaimReviewValidationResult:
    if not isinstance(results, (tuple, list)) or not results:
        return OfficialClaimReviewValidationResult(
            accepted=False,
            claim_id="aggregate",
            venue_id=None,
            review_status=None,
            rejection_reasons=("official_claim_review:malformed",),
        )

    reasons: list[str] = []
    statuses: list[OfficialClaimReviewStatus] = []
    venue_ids: list[VenueId] = []
    for result in results:
        if not isinstance(result, OfficialClaimReviewValidationResult):
            reasons.append("official_claim_review:malformed")
            continue
        reasons.extend(result.rejection_reasons)
        if not result.accepted:
            if result.review_status is OfficialClaimReviewStatus.REJECTED:
                reasons.append("official_claim_review:rejected")
            elif result.review_status is OfficialClaimReviewStatus.PENDING:
                reasons.append("official_claim_review:pending")
            elif not result.rejection_reasons:
                reasons.append("official_claim_review:malformed")
        if result.review_status is not None:
            statuses.append(result.review_status)
        if result.venue_id is not None:
            venue_ids.append(result.venue_id)

    unique_reasons = tuple(dict.fromkeys(reasons))
    accepted = not unique_reasons and all(result.accepted for result in results)
    aggregate_status = _aggregate_status(statuses, accepted)
    aggregate_venue = _aggregate_venue(venue_ids)
    return OfficialClaimReviewValidationResult(
        accepted=accepted,
        claim_id="aggregate",
        venue_id=aggregate_venue,
        review_status=aggregate_status,
        rejection_reasons=unique_reasons,
    )


def _aggregate_status(
    statuses: list[OfficialClaimReviewStatus],
    accepted: bool,
) -> OfficialClaimReviewStatus | None:
    if accepted:
        return OfficialClaimReviewStatus.APPROVED
    if any(status is OfficialClaimReviewStatus.REJECTED for status in statuses):
        return OfficialClaimReviewStatus.REJECTED
    if any(status is OfficialClaimReviewStatus.PENDING for status in statuses):
        return OfficialClaimReviewStatus.PENDING
    return None


def _aggregate_venue(venue_ids: list[VenueId]) -> VenueId | None:
    unique = tuple(dict.fromkeys(venue_ids))
    return unique[0] if len(unique) == 1 else None


def _mapping(payload: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise OfficialClaimReviewError(f"{field_name} must be a mapping")
    return payload


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise OfficialClaimReviewError("venue_id is unsupported") from exc
    raise OfficialClaimReviewError("venue_id is malformed")


def _review_status(value: object, field_name: str) -> OfficialClaimReviewStatus:
    if isinstance(value, OfficialClaimReviewStatus):
        return value
    if isinstance(value, str):
        try:
            return OfficialClaimReviewStatus(value)
        except ValueError as exc:
            raise OfficialClaimReviewError(f"{field_name} is unsupported") from exc
    raise OfficialClaimReviewError(f"{field_name} is malformed")


def _provided_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value != "PENDING"


def _valid_sha256_hex(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value)


def _string_field(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise OfficialClaimReviewError(f"{field_name} must be a string")
    return value


def _optional_string_field(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string_field(value, field_name)


def _bool_field(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise OfficialClaimReviewError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise OfficialClaimReviewError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise OfficialClaimReviewError(f"{field_name} must contain non-empty strings")
    return result


def _string_tuple_valid(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, (tuple, list)):
        return False
    result = tuple(value)
    if not allow_empty and not result:
        return False
    return all(isinstance(item, str) and bool(item) for item in result)


def _provided_string_tuple(value: object) -> bool:
    if not isinstance(value, (tuple, list)):
        return False
    return any(_provided_string(item) for item in value)


__all__ = [
    "OfficialClaimReviewDecision",
    "OfficialClaimReviewError",
    "OfficialClaimReviewStatus",
    "OfficialClaimReviewValidationResult",
    "aggregate_claim_review_results",
    "official_claim_review_decision_from_dict",
    "official_claim_review_decision_to_dict",
    "official_claim_review_ready",
    "official_claim_review_validation_result_from_dict",
    "official_claim_review_validation_result_to_dict",
    "validate_official_claim_review",
]
