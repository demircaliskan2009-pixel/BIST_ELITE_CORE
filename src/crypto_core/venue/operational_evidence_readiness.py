from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.dialect_evidence import PublicFeedDialectVerificationResult
from crypto_core.venue.official_claim_reviews import (
    OfficialClaimReviewValidationResult,
    official_claim_review_validation_result_from_dict,
    official_claim_review_validation_result_to_dict,
)
from crypto_core.venue.official_evidence_packages import (
    OfficialEvidencePackage,
    official_evidence_package_rejection_reasons,
)
from crypto_core.venue.official_source_snapshots import (
    OfficialSourceSnapshotValidationResult,
    official_source_snapshot_result_to_dict,
)


class OperationalEvidenceReadinessError(ValueError):
    """Raised when operational evidence readiness payloads are malformed."""


class OperationalEvidenceReadinessStatus(str, Enum):
    BLOCKED = "blocked"
    READY = "ready"


class OperationalPolicyApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class OperationalEvidenceReadinessRequirement:
    requirement_id: str
    field_name: str
    satisfied: bool
    evidence_refs: tuple[str, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationalEvidenceReadinessResult:
    accepted: bool
    venue_id: VenueId | None
    dialect_id: str | None
    feed_type: PublicFeedType | None
    status: OperationalEvidenceReadinessStatus
    requirements: tuple[OperationalEvidenceReadinessRequirement, ...]
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class OperationalPolicyApproval:
    policy_id: str
    venue_id: VenueId
    policy_status: OperationalPolicyApprovalStatus
    reviewer_id: str
    reviewed_at_iso: str
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationalEvidenceAcceptanceInput:
    venue_id: VenueId
    source_snapshot_results: tuple[OfficialSourceSnapshotValidationResult, ...]
    claim_review_results: tuple[OfficialClaimReviewValidationResult, ...]
    policy_approvals: tuple[OperationalPolicyApproval, ...]
    static_registry_verified: bool
    connector_enablement_requested: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationalEvidenceAcceptanceResult:
    accepted: bool
    venue_id: VenueId | None
    rejection_reasons: tuple[str, ...]


OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS = (
    "real_official_urls_present",
    "reproducible_content_hashes_present",
    "retrieval_timestamps_present",
    "manual_review_approved",
    "sequence_model_verified",
    "snapshot_delta_resync_verified",
    "checksum_decision_verified",
    "rate_limits_verified",
    "staleness_budget_verified",
    "receive_lag_budget_verified",
    "heartbeat_or_ping_pong_verified",
    "testnet_prod_difference_reviewed",
    "regional_access_reviewed",
    "static_registry_not_enabled",
    "connector_ready_dialects_empty",
)


OPERATIONAL_EVIDENCE_ACCEPTANCE_REQUIRED_POLICY_IDS = (
    "checksum_decision",
    "liveness_policy",
    "staleness_budget",
    "receive_lag_budget",
    "testnet_prod_review",
    "regional_legal_access_review",
    "separate_connector_enablement",
)


_REQUIREMENT_REJECTION_BY_FIELD = {
    "real_official_urls_present": "operational_evidence:comparison_only_not_evidence",
    "reproducible_content_hashes_present": "operational_evidence:content_hash_missing",
    "retrieval_timestamps_present": "operational_evidence:retrieval_timestamp_missing",
    "manual_review_approved": "operational_evidence:manual_review_missing",
    "sequence_model_verified": "operational_evidence:sequence_unknown",
    "snapshot_delta_resync_verified": "operational_evidence:resync_unknown",
    "checksum_decision_verified": "operational_evidence:checksum_decision_missing",
    "rate_limits_verified": "operational_evidence:rate_limits_unknown",
    "staleness_budget_verified": "operational_evidence:staleness_unknown",
    "receive_lag_budget_verified": "operational_evidence:receive_lag_unknown",
    "heartbeat_or_ping_pong_verified": "operational_evidence:heartbeat_unknown",
    "testnet_prod_difference_reviewed": "operational_evidence:testnet_prod_unknown",
    "regional_access_reviewed": "operational_evidence:regional_access_unknown",
    "static_registry_not_enabled": "operational_evidence:registry_enabled_forbidden",
    "connector_ready_dialects_empty": "operational_evidence:registry_enabled_forbidden",
}


_POLICY_REJECTION_BY_ID = {
    "checksum_decision": "operational_policy:checksum_decision_missing",
    "liveness_policy": "operational_policy:liveness_policy_missing",
    "staleness_budget": "operational_policy:staleness_budget_missing",
    "receive_lag_budget": "operational_policy:receive_lag_budget_missing",
    "testnet_prod_review": "operational_policy:testnet_prod_review_missing",
    "regional_legal_access_review": "operational_policy:regional_legal_access_review_missing",
    "separate_connector_enablement": "operational_policy:separate_connector_enablement_required",
}


_CONTENT_HASH_UNAVAILABLE_PREFIX = "CONTENT_HASH_UNAVAILABLE"
_PLACEHOLDER_URL_MARKERS = ("docs.example.test", "example.com", "example.test")


def evaluate_operational_public_connector_evidence(
    *,
    venue_id: object,
    dialect_id: object,
    feed_type: object,
    evidence_package: object,
    dialect_verification_result: object,
    required_fields: object,
) -> OperationalEvidenceReadinessResult:
    venue, venue_reasons = _coerce_venue_id(venue_id)
    feed, feed_reasons = _coerce_feed_type(feed_type)
    dialect, dialect_reasons = _coerce_non_empty_string(dialect_id, "dialect_id")
    requirements = _normalize_requirements(required_fields)

    reasons: list[str] = [*venue_reasons, *feed_reasons, *dialect_reasons]
    package = evidence_package if isinstance(evidence_package, OfficialEvidencePackage) else None
    verification = (
        dialect_verification_result
        if isinstance(dialect_verification_result, PublicFeedDialectVerificationResult)
        else None
    )

    if package is None:
        reasons.append("operational_evidence:package_missing")
    else:
        reasons.extend(official_evidence_package_rejection_reasons(package))
        if venue is not None and package.venue_id is not venue:
            reasons.append("operational_evidence:comparison_only_not_evidence")
        if package.retrieved_at_ns <= 0:
            reasons.append("operational_evidence:retrieval_timestamp_missing")
        for item in package.evidence_items:
            if item.retrieved_at_ns <= 0:
                reasons.append("operational_evidence:retrieval_timestamp_missing")
            if _content_hash_unavailable(item.content_hash):
                reasons.append("operational_evidence:content_hash_missing")
            if _placeholder_doc_url(item.doc_url):
                reasons.append("operational_evidence:comparison_only_not_evidence")

    if verification is None:
        reasons.append("operational_evidence:verification_missing")
    else:
        if not verification.accepted:
            reasons.append("operational_evidence:verification_rejected")
        reasons.extend(verification.rejection_reasons)
        if venue is not None and verification.venue_id is not venue:
            reasons.append("operational_evidence:comparison_only_not_evidence")
        if feed is not None and verification.feed_type is not feed:
            reasons.append("operational_evidence:verification_rejected")
        if dialect is not None and verification.dialect_id != dialect:
            reasons.append("operational_evidence:verification_rejected")
        if not verification.official_doc_refs:
            reasons.append("operational_evidence:verification_rejected")
        if not verification.content_hashes:
            reasons.append("operational_evidence:content_hash_missing")
        for content_hash in verification.content_hashes:
            if _content_hash_unavailable(content_hash):
                reasons.append("operational_evidence:content_hash_missing")

    for requirement in requirements:
        if requirement.rejection_reasons:
            reasons.extend(requirement.rejection_reasons)
        if not requirement.satisfied or not requirement.evidence_refs:
            reasons.append(_REQUIREMENT_REJECTION_BY_FIELD[requirement.field_name])

    unique_reasons = tuple(dict.fromkeys(reasons))
    accepted = not unique_reasons and all(requirement.satisfied for requirement in requirements)
    return OperationalEvidenceReadinessResult(
        accepted=accepted,
        venue_id=venue,
        dialect_id=dialect,
        feed_type=feed,
        status=OperationalEvidenceReadinessStatus.READY if accepted else OperationalEvidenceReadinessStatus.BLOCKED,
        requirements=requirements,
        rejection_reasons=unique_reasons,
    )


def operational_evidence_ready(result: OperationalEvidenceReadinessResult | None) -> bool:
    return (
        isinstance(result, OperationalEvidenceReadinessResult)
        and result.accepted is True
        and result.status is OperationalEvidenceReadinessStatus.READY
        and result.rejection_reasons == ()
        and all(requirement.satisfied and not requirement.rejection_reasons for requirement in result.requirements)
    )


def evaluate_operational_evidence_acceptance(
    acceptance_input: object,
) -> OperationalEvidenceAcceptanceResult:
    if not isinstance(acceptance_input, OperationalEvidenceAcceptanceInput):
        return OperationalEvidenceAcceptanceResult(
            accepted=False,
            venue_id=None,
            rejection_reasons=("operational_evidence:malformed",),
        )

    reasons: list[str] = []
    venue = acceptance_input.venue_id if isinstance(acceptance_input.venue_id, VenueId) else None
    if venue is None:
        reasons.append("operational_evidence:malformed")
    if not isinstance(acceptance_input.static_registry_verified, bool):
        reasons.append("operational_evidence:malformed")
    if not isinstance(acceptance_input.connector_enablement_requested, bool):
        reasons.append("operational_evidence:malformed")
    elif acceptance_input.connector_enablement_requested:
        reasons.append("operational_policy:separate_connector_enablement_required")
    if not _strict_string_tuple_valid(acceptance_input.rejection_reasons) or acceptance_input.rejection_reasons:
        reasons.append("operational_evidence:preexisting_rejection")

    reasons.extend(_source_snapshot_acceptance_reasons(acceptance_input.source_snapshot_results, venue))
    reasons.extend(_claim_review_acceptance_reasons(acceptance_input.claim_review_results, venue))
    reasons.extend(_policy_acceptance_reasons(acceptance_input.policy_approvals, venue))

    unique_reasons = tuple(dict.fromkeys(reasons))
    return OperationalEvidenceAcceptanceResult(
        accepted=unique_reasons == (),
        venue_id=venue,
        rejection_reasons=unique_reasons,
    )


def operational_evidence_acceptance_ready(result: OperationalEvidenceAcceptanceResult | None) -> bool:
    return (
        isinstance(result, OperationalEvidenceAcceptanceResult)
        and result.accepted is True
        and result.venue_id is not None
        and result.rejection_reasons == ()
    )


def operational_evidence_readiness_result_to_dict(
    result: OperationalEvidenceReadinessResult,
) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "venue_id": result.venue_id.value if result.venue_id is not None else None,
        "dialect_id": result.dialect_id,
        "feed_type": result.feed_type.value if result.feed_type is not None else None,
        "status": result.status.value,
        "requirements": [_requirement_to_dict(requirement) for requirement in result.requirements],
        "rejection_reasons": list(result.rejection_reasons),
    }


def operational_policy_approval_to_dict(approval: OperationalPolicyApproval) -> dict[str, object]:
    return {
        "policy_id": approval.policy_id,
        "venue_id": approval.venue_id.value,
        "policy_status": approval.policy_status.value,
        "reviewer_id": approval.reviewer_id,
        "reviewed_at_iso": approval.reviewed_at_iso,
        "rejection_reasons": list(approval.rejection_reasons),
    }


def operational_policy_approval_from_dict(data: object) -> OperationalPolicyApproval:
    payload = _require_mapping(data, "policy_approval")
    return OperationalPolicyApproval(
        policy_id=_require_string(payload.get("policy_id"), "policy_id"),
        venue_id=_require_venue_id(payload.get("venue_id"), "venue_id"),
        policy_status=_require_policy_status(payload.get("policy_status"), "policy_status"),
        reviewer_id=_require_string(payload.get("reviewer_id"), "reviewer_id"),
        reviewed_at_iso=_require_string(payload.get("reviewed_at_iso"), "reviewed_at_iso"),
        rejection_reasons=_require_strict_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def operational_evidence_acceptance_input_to_dict(
    acceptance_input: OperationalEvidenceAcceptanceInput,
) -> dict[str, object]:
    return {
        "venue_id": acceptance_input.venue_id.value,
        "source_snapshot_results": [
            official_source_snapshot_result_to_dict(result) for result in acceptance_input.source_snapshot_results
        ],
        "claim_review_results": [
            official_claim_review_validation_result_to_dict(result) for result in acceptance_input.claim_review_results
        ],
        "policy_approvals": [
            operational_policy_approval_to_dict(approval) for approval in acceptance_input.policy_approvals
        ],
        "static_registry_verified": acceptance_input.static_registry_verified,
        "connector_enablement_requested": acceptance_input.connector_enablement_requested,
        "rejection_reasons": list(acceptance_input.rejection_reasons),
    }


def operational_evidence_acceptance_input_from_dict(data: object) -> OperationalEvidenceAcceptanceInput:
    payload = _require_mapping(data, "operational_evidence_acceptance_input")
    return OperationalEvidenceAcceptanceInput(
        venue_id=_require_venue_id(payload.get("venue_id"), "venue_id"),
        source_snapshot_results=tuple(
            _source_snapshot_result_from_dict(item)
            for item in _require_sequence(payload.get("source_snapshot_results"), "source_snapshot_results")
        ),
        claim_review_results=tuple(
            official_claim_review_validation_result_from_dict(item)
            for item in _require_sequence(payload.get("claim_review_results"), "claim_review_results")
        ),
        policy_approvals=tuple(
            operational_policy_approval_from_dict(item)
            for item in _require_sequence(payload.get("policy_approvals"), "policy_approvals")
        ),
        static_registry_verified=_require_bool(payload.get("static_registry_verified"), "static_registry_verified"),
        connector_enablement_requested=_require_bool(
            payload.get("connector_enablement_requested"),
            "connector_enablement_requested",
        ),
        rejection_reasons=_require_strict_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def operational_evidence_acceptance_result_to_dict(
    result: OperationalEvidenceAcceptanceResult,
) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "venue_id": None if result.venue_id is None else result.venue_id.value,
        "rejection_reasons": list(result.rejection_reasons),
    }


def operational_evidence_acceptance_result_from_dict(data: object) -> OperationalEvidenceAcceptanceResult:
    payload = _require_mapping(data, "operational_evidence_acceptance_result")
    venue_value = payload.get("venue_id")
    return OperationalEvidenceAcceptanceResult(
        accepted=_require_bool(payload.get("accepted"), "accepted"),
        venue_id=None if venue_value is None else _require_venue_id(venue_value, "venue_id"),
        rejection_reasons=_require_strict_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def operational_evidence_readiness_result_from_dict(data: object) -> OperationalEvidenceReadinessResult:
    payload = _require_mapping(data, "result")
    venue_value = payload.get("venue_id")
    feed_value = payload.get("feed_type")
    return OperationalEvidenceReadinessResult(
        accepted=_require_bool(payload.get("accepted"), "accepted"),
        venue_id=None if venue_value is None else _require_venue_id(venue_value, "venue_id"),
        dialect_id=None
        if payload.get("dialect_id") is None
        else _require_string(payload.get("dialect_id"), "dialect_id"),
        feed_type=None if feed_value is None else _require_feed_type(feed_value, "feed_type"),
        status=_require_status(payload.get("status"), "status"),
        requirements=tuple(
            _requirement_from_dict(item) for item in _require_sequence(payload.get("requirements"), "requirements")
        ),
        rejection_reasons=_require_string_tuple(payload.get("rejection_reasons"), "rejection_reasons"),
    )


def _source_snapshot_acceptance_reasons(
    results: object,
    venue: VenueId | None,
) -> tuple[str, ...]:
    if not isinstance(results, (tuple, list)):
        return ("operational_evidence:malformed",)
    if not results:
        return ("operational_evidence:missing_source_snapshot",)

    reasons: list[str] = []
    for result in results:
        if not isinstance(result, OfficialSourceSnapshotValidationResult):
            reasons.append("operational_evidence:malformed")
            continue
        if not result.accepted or result.rejection_reasons:
            reasons.append("operational_evidence:source_snapshot_rejected")
            reasons.extend(result.rejection_reasons)
        if venue is not None and result.venue_id is not None and result.venue_id is not venue:
            reasons.append("operational_evidence:source_snapshot_rejected")
    return tuple(dict.fromkeys(reasons))


def _claim_review_acceptance_reasons(
    results: object,
    venue: VenueId | None,
) -> tuple[str, ...]:
    if not isinstance(results, (tuple, list)):
        return ("operational_evidence:malformed",)
    if not results:
        return ("operational_evidence:missing_claim_review",)

    reasons: list[str] = []
    for result in results:
        if not isinstance(result, OfficialClaimReviewValidationResult):
            reasons.append("operational_evidence:malformed")
            continue
        if not result.accepted or result.rejection_reasons:
            reasons.append("operational_evidence:claim_review_rejected")
            reasons.extend(result.rejection_reasons)
        if venue is not None and result.venue_id is not None and result.venue_id is not venue:
            reasons.append("operational_evidence:claim_review_rejected")
    return tuple(dict.fromkeys(reasons))


def _policy_acceptance_reasons(
    approvals: object,
    venue: VenueId | None,
) -> tuple[str, ...]:
    if not isinstance(approvals, (tuple, list)):
        return ("operational_evidence:malformed",)

    reasons: list[str] = []
    policy_by_id: dict[str, OperationalPolicyApproval] = {}
    for approval in approvals:
        if not isinstance(approval, OperationalPolicyApproval):
            reasons.append("operational_evidence:malformed")
            continue
        if approval.policy_id not in _POLICY_REJECTION_BY_ID:
            reasons.append("operational_evidence:malformed")
            continue
        if approval.policy_id not in policy_by_id:
            policy_by_id[approval.policy_id] = approval
        if venue is not None and approval.venue_id is not venue:
            reasons.append("operational_evidence:malformed")
        if not isinstance(approval.policy_status, OperationalPolicyApprovalStatus):
            reasons.append("operational_evidence:malformed")
        elif approval.policy_status is not OperationalPolicyApprovalStatus.APPROVED:
            reasons.append(_POLICY_REJECTION_BY_ID[approval.policy_id])
        if not _provided_string(approval.reviewer_id):
            reasons.append("operational_policy:missing_reviewer")
        if not _provided_string(approval.reviewed_at_iso):
            reasons.append("operational_policy:missing_review_time")
        if not _strict_string_tuple_valid(approval.rejection_reasons) or approval.rejection_reasons:
            reasons.append("operational_evidence:preexisting_rejection")
            if _strict_string_tuple_valid(approval.rejection_reasons):
                reasons.extend(approval.rejection_reasons)

    for policy_id in OPERATIONAL_EVIDENCE_ACCEPTANCE_REQUIRED_POLICY_IDS:
        if policy_id not in policy_by_id:
            reasons.append(_POLICY_REJECTION_BY_ID[policy_id])
    return tuple(dict.fromkeys(reasons))


def _source_snapshot_result_from_dict(data: object) -> OfficialSourceSnapshotValidationResult:
    payload = _require_mapping(data, "source_snapshot_result")
    venue_value = payload.get("venue_id")
    return OfficialSourceSnapshotValidationResult(
        accepted=_require_bool(payload.get("accepted"), "accepted"),
        snapshot_id=_optional_string(payload.get("snapshot_id"), "snapshot_id"),
        source_id=_optional_string(payload.get("source_id"), "source_id"),
        venue_id=None if venue_value is None else _require_venue_id(venue_value, "venue_id"),
        content_sha256=_optional_string(payload.get("content_sha256"), "content_sha256"),
        rejection_reasons=_require_strict_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _normalize_requirements(required_fields: object) -> tuple[OperationalEvidenceReadinessRequirement, ...]:
    provided: dict[str, OperationalEvidenceReadinessRequirement] = {}
    if isinstance(required_fields, Mapping):
        for field_name, value in required_fields.items():
            if not isinstance(field_name, str) or field_name not in _REQUIREMENT_REJECTION_BY_FIELD:
                continue
            provided[field_name] = _requirement_from_mapping_value(field_name, value)
    elif isinstance(required_fields, (tuple, list)):
        for item in required_fields:
            if (
                isinstance(item, OperationalEvidenceReadinessRequirement)
                and item.field_name in _REQUIREMENT_REJECTION_BY_FIELD
            ):
                provided[item.field_name] = _normalize_requirement(item)

    requirements: list[OperationalEvidenceReadinessRequirement] = []
    for field_name in OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS:
        requirements.append(
            provided.get(
                field_name,
                OperationalEvidenceReadinessRequirement(
                    requirement_id=f"operational:{field_name}",
                    field_name=field_name,
                    satisfied=False,
                    evidence_refs=(),
                    rejection_reasons=(),
                ),
            )
        )
    return tuple(requirements)


def _requirement_from_mapping_value(field_name: str, value: object) -> OperationalEvidenceReadinessRequirement:
    if isinstance(value, Mapping):
        satisfied = _mapping_bool(value.get("satisfied"))
        evidence_refs = _tuple_of_strings(value.get("evidence_refs"))
        rejection_reasons = _tuple_of_strings(value.get("rejection_reasons"))
    elif isinstance(value, bool):
        satisfied = value
        evidence_refs = (f"required:{field_name}",) if value else ()
        rejection_reasons = ()
    elif isinstance(value, (tuple, list)):
        satisfied = True
        evidence_refs = _tuple_of_strings(value)
        rejection_reasons = ()
    else:
        satisfied = False
        evidence_refs = ()
        rejection_reasons = ()
    return OperationalEvidenceReadinessRequirement(
        requirement_id=f"operational:{field_name}",
        field_name=field_name,
        satisfied=satisfied,
        evidence_refs=evidence_refs,
        rejection_reasons=rejection_reasons,
    )


def _normalize_requirement(
    requirement: OperationalEvidenceReadinessRequirement,
) -> OperationalEvidenceReadinessRequirement:
    return OperationalEvidenceReadinessRequirement(
        requirement_id=requirement.requirement_id,
        field_name=requirement.field_name,
        satisfied=requirement.satisfied,
        evidence_refs=tuple(dict.fromkeys(requirement.evidence_refs)),
        rejection_reasons=tuple(dict.fromkeys(requirement.rejection_reasons)),
    )


def _requirement_to_dict(requirement: OperationalEvidenceReadinessRequirement) -> dict[str, object]:
    return {
        "requirement_id": requirement.requirement_id,
        "field_name": requirement.field_name,
        "satisfied": requirement.satisfied,
        "evidence_refs": list(requirement.evidence_refs),
        "rejection_reasons": list(requirement.rejection_reasons),
    }


def _requirement_from_dict(data: object) -> OperationalEvidenceReadinessRequirement:
    payload = _require_mapping(data, "requirement")
    field_name = _require_string(payload.get("field_name"), "field_name")
    if field_name not in _REQUIREMENT_REJECTION_BY_FIELD:
        raise OperationalEvidenceReadinessError("field_name is unsupported")
    return OperationalEvidenceReadinessRequirement(
        requirement_id=_require_string(payload.get("requirement_id"), "requirement_id"),
        field_name=field_name,
        satisfied=_require_bool(payload.get("satisfied"), "satisfied"),
        evidence_refs=_require_string_tuple(payload.get("evidence_refs"), "evidence_refs"),
        rejection_reasons=_require_string_tuple(payload.get("rejection_reasons"), "rejection_reasons"),
    )


def _coerce_venue_id(value: object) -> tuple[VenueId | None, tuple[str, ...]]:
    try:
        return _require_venue_id(value, "venue_id"), ()
    except OperationalEvidenceReadinessError:
        return None, ("operational_evidence:package_missing",)


def _coerce_feed_type(value: object) -> tuple[PublicFeedType | None, tuple[str, ...]]:
    try:
        return _require_feed_type(value, "feed_type"), ()
    except OperationalEvidenceReadinessError:
        return None, ("operational_evidence:verification_rejected",)


def _coerce_non_empty_string(value: object, field_name: str) -> tuple[str | None, tuple[str, ...]]:
    if isinstance(value, str) and value.strip():
        return value, ()
    return None, ("operational_evidence:verification_rejected",)


def _content_hash_unavailable(value: str) -> bool:
    return not value.strip() or value.startswith(_CONTENT_HASH_UNAVAILABLE_PREFIX)


def _placeholder_doc_url(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_URL_MARKERS)


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OperationalEvidenceReadinessError(f"{field_name} must be a mapping")
    return value


def _require_sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, (tuple, list)):
        raise OperationalEvidenceReadinessError(f"{field_name} must be a sequence")
    return tuple(value)


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperationalEvidenceReadinessError(f"{field_name} must be a non-empty string")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise OperationalEvidenceReadinessError(f"{field_name} must be a bool")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name)


def _mapping_bool(value: object) -> bool:
    return value is True


def _require_venue_id(value: object, field_name: str) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise OperationalEvidenceReadinessError(f"{field_name} is unsupported") from exc
    raise OperationalEvidenceReadinessError(f"{field_name} is malformed")


def _require_feed_type(value: object, field_name: str) -> PublicFeedType:
    if isinstance(value, PublicFeedType):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedType(value)
        except ValueError as exc:
            raise OperationalEvidenceReadinessError(f"{field_name} is unsupported") from exc
    raise OperationalEvidenceReadinessError(f"{field_name} is malformed")


def _require_status(value: object, field_name: str) -> OperationalEvidenceReadinessStatus:
    if isinstance(value, OperationalEvidenceReadinessStatus):
        return value
    if isinstance(value, str):
        try:
            return OperationalEvidenceReadinessStatus(value)
        except ValueError as exc:
            raise OperationalEvidenceReadinessError(f"{field_name} is unsupported") from exc
    raise OperationalEvidenceReadinessError(f"{field_name} is malformed")


def _require_policy_status(value: object, field_name: str) -> OperationalPolicyApprovalStatus:
    if isinstance(value, OperationalPolicyApprovalStatus):
        return value
    if isinstance(value, str):
        try:
            return OperationalPolicyApprovalStatus(value)
        except ValueError as exc:
            raise OperationalEvidenceReadinessError(f"{field_name} is unsupported") from exc
    raise OperationalEvidenceReadinessError(f"{field_name} is malformed")


def _require_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise OperationalEvidenceReadinessError(f"{field_name} must be a sequence")
    return _tuple_of_strings(value)


def _require_strict_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not _strict_string_tuple_valid(value):
        raise OperationalEvidenceReadinessError(f"{field_name} must contain non-empty strings")
    return tuple(value)


def _tuple_of_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item)
    return tuple(dict.fromkeys(result))


def _strict_string_tuple_valid(value: object) -> bool:
    if not isinstance(value, (tuple, list)):
        return False
    return all(isinstance(item, str) and bool(item) for item in value)


def _provided_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value != "PENDING"


__all__ = [
    "OPERATIONAL_EVIDENCE_ACCEPTANCE_REQUIRED_POLICY_IDS",
    "OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS",
    "OperationalEvidenceAcceptanceInput",
    "OperationalEvidenceAcceptanceResult",
    "OperationalEvidenceReadinessError",
    "OperationalEvidenceReadinessRequirement",
    "OperationalEvidenceReadinessResult",
    "OperationalEvidenceReadinessStatus",
    "OperationalPolicyApproval",
    "OperationalPolicyApprovalStatus",
    "evaluate_operational_evidence_acceptance",
    "evaluate_operational_public_connector_evidence",
    "operational_evidence_acceptance_input_from_dict",
    "operational_evidence_acceptance_input_to_dict",
    "operational_evidence_acceptance_ready",
    "operational_evidence_acceptance_result_from_dict",
    "operational_evidence_acceptance_result_to_dict",
    "operational_evidence_readiness_result_from_dict",
    "operational_evidence_readiness_result_to_dict",
    "operational_evidence_ready",
    "operational_policy_approval_from_dict",
    "operational_policy_approval_to_dict",
]
