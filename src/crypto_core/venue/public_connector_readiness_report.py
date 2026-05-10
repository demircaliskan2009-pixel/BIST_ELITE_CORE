from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.official_claim_reviews import OfficialClaimReviewValidationResult
from crypto_core.venue.official_source_snapshots import OfficialSourceSnapshotValidationResult
from crypto_core.venue.operational_evidence_readiness import OperationalEvidenceAcceptanceResult
from crypto_core.venue.public_connector_enablement import PublicConnectorEnablementDecision


class PublicConnectorReadinessReportError(ValueError):
    """Raised when inert public connector readiness report payloads are malformed."""


class PublicConnectorReadinessStageStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PublicConnectorReadinessReport:
    venue_id: VenueId | None
    dialect_id: str | None
    source_snapshots_ready: PublicConnectorReadinessStageStatus
    claim_reviews_ready: PublicConnectorReadinessStageStatus
    operational_evidence_ready: PublicConnectorReadinessStageStatus
    connector_enablement_ready: PublicConnectorReadinessStageStatus
    static_registry_verified: bool
    connector_ready: bool
    blocker_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def build_public_connector_readiness_report(
    *,
    venue_id: object,
    dialect_id: object,
    source_snapshot_results: object,
    claim_review_results: object,
    operational_evidence_result: object,
    connector_enablement_decision: object,
    static_registry_verified: object,
    evidence_refs: object,
    extra_rejection_reasons: object = (),
) -> PublicConnectorReadinessReport:
    venue, venue_reasons = _coerce_venue_id(venue_id)
    dialect, dialect_reasons = _coerce_non_empty_string(dialect_id)
    source_ready, source_reasons = _source_snapshot_stage(source_snapshot_results, venue)
    claim_ready, claim_reasons = _claim_review_stage(claim_review_results, venue)
    operational_ready, operational_reasons = _operational_evidence_stage(operational_evidence_result, venue)
    enablement_ready, enablement_reasons = _connector_enablement_stage(connector_enablement_decision, venue, dialect)
    refs, ref_reasons = _evidence_refs(evidence_refs)
    extra_reasons = _extra_rejection_reasons(extra_rejection_reasons)

    reasons = [
        *venue_reasons,
        *dialect_reasons,
        *source_reasons,
        *claim_reasons,
        *operational_reasons,
        *enablement_reasons,
        *ref_reasons,
        *extra_reasons,
    ]
    if static_registry_verified is not True:
        reasons.append("public_connector_readiness:static_registry_unverified")
        if not isinstance(static_registry_verified, bool):
            reasons.append("public_connector_readiness:malformed")

    blocker_reasons = tuple(dict.fromkeys(reasons))
    connector_ready = (
        not blocker_reasons
        and source_ready
        and claim_ready
        and operational_ready
        and enablement_ready
        and static_registry_verified is True
        and bool(refs)
    )
    return PublicConnectorReadinessReport(
        venue_id=venue,
        dialect_id=dialect,
        source_snapshots_ready=_stage_status(source_ready),
        claim_reviews_ready=_stage_status(claim_ready),
        operational_evidence_ready=_stage_status(operational_ready),
        connector_enablement_ready=_stage_status(enablement_ready),
        static_registry_verified=static_registry_verified is True,
        connector_ready=connector_ready,
        blocker_reasons=blocker_reasons,
        evidence_refs=refs,
    )


def public_connector_readiness_ready(report: PublicConnectorReadinessReport | None) -> bool:
    return (
        isinstance(report, PublicConnectorReadinessReport)
        and report.connector_ready is True
        and report.source_snapshots_ready is PublicConnectorReadinessStageStatus.READY
        and report.claim_reviews_ready is PublicConnectorReadinessStageStatus.READY
        and report.operational_evidence_ready is PublicConnectorReadinessStageStatus.READY
        and report.connector_enablement_ready is PublicConnectorReadinessStageStatus.READY
        and report.static_registry_verified is True
        and report.blocker_reasons == ()
        and bool(report.evidence_refs)
    )


def public_connector_readiness_report_to_dict(report: PublicConnectorReadinessReport) -> dict[str, object]:
    return {
        "venue_id": None if report.venue_id is None else report.venue_id.value,
        "dialect_id": report.dialect_id,
        "source_snapshots_ready": report.source_snapshots_ready.value,
        "claim_reviews_ready": report.claim_reviews_ready.value,
        "operational_evidence_ready": report.operational_evidence_ready.value,
        "connector_enablement_ready": report.connector_enablement_ready.value,
        "static_registry_verified": report.static_registry_verified,
        "connector_ready": report.connector_ready,
        "blocker_reasons": list(report.blocker_reasons),
        "evidence_refs": list(report.evidence_refs),
    }


def public_connector_readiness_report_from_dict(payload: object) -> PublicConnectorReadinessReport:
    data = _mapping(payload, "public connector readiness report payload")
    venue_value = data.get("venue_id")
    return PublicConnectorReadinessReport(
        venue_id=None if venue_value is None else _venue_id(venue_value),
        dialect_id=_optional_string(data.get("dialect_id"), "dialect_id"),
        source_snapshots_ready=_stage(data.get("source_snapshots_ready"), "source_snapshots_ready"),
        claim_reviews_ready=_stage(data.get("claim_reviews_ready"), "claim_reviews_ready"),
        operational_evidence_ready=_stage(data.get("operational_evidence_ready"), "operational_evidence_ready"),
        connector_enablement_ready=_stage(data.get("connector_enablement_ready"), "connector_enablement_ready"),
        static_registry_verified=_bool(data.get("static_registry_verified"), "static_registry_verified"),
        connector_ready=_bool(data.get("connector_ready"), "connector_ready"),
        blocker_reasons=_string_tuple(data.get("blocker_reasons", ()), "blocker_reasons"),
        evidence_refs=_string_tuple(data.get("evidence_refs", ()), "evidence_refs"),
    )


def _source_snapshot_stage(
    results: object,
    venue: VenueId | None,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(results, (tuple, list)) or not results:
        return False, ("public_connector_readiness:source_snapshots_not_ready",)

    reasons: list[str] = []
    for result in results:
        if not isinstance(result, OfficialSourceSnapshotValidationResult):
            reasons.append("public_connector_readiness:malformed")
            reasons.append("public_connector_readiness:source_snapshots_not_ready")
            continue
        if not result.accepted or result.rejection_reasons:
            reasons.append("public_connector_readiness:source_snapshots_not_ready")
            reasons.extend(result.rejection_reasons)
        if venue is not None and result.venue_id is not None and result.venue_id is not venue:
            reasons.append("public_connector_readiness:source_snapshots_not_ready")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return unique_reasons == (), unique_reasons


def _claim_review_stage(
    results: object,
    venue: VenueId | None,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(results, (tuple, list)) or not results:
        return False, ("public_connector_readiness:claim_reviews_not_ready",)

    reasons: list[str] = []
    for result in results:
        if not isinstance(result, OfficialClaimReviewValidationResult):
            reasons.append("public_connector_readiness:malformed")
            reasons.append("public_connector_readiness:claim_reviews_not_ready")
            continue
        if not result.accepted or result.rejection_reasons:
            reasons.append("public_connector_readiness:claim_reviews_not_ready")
            reasons.extend(result.rejection_reasons)
        if venue is not None and result.venue_id is not None and result.venue_id is not venue:
            reasons.append("public_connector_readiness:claim_reviews_not_ready")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return unique_reasons == (), unique_reasons


def _operational_evidence_stage(
    result: object,
    venue: VenueId | None,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(result, OperationalEvidenceAcceptanceResult):
        return False, (
            "public_connector_readiness:operational_evidence_not_ready",
            "public_connector_readiness:malformed",
        )

    reasons: list[str] = []
    if not result.accepted or result.rejection_reasons:
        reasons.append("public_connector_readiness:operational_evidence_not_ready")
        reasons.extend(result.rejection_reasons)
    if venue is not None and result.venue_id is not None and result.venue_id is not venue:
        reasons.append("public_connector_readiness:operational_evidence_not_ready")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return unique_reasons == (), unique_reasons


def _connector_enablement_stage(
    decision: object,
    venue: VenueId | None,
    dialect_id: str | None,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(decision, PublicConnectorEnablementDecision):
        return False, (
            "public_connector_readiness:connector_enablement_not_ready",
            "public_connector_readiness:malformed",
        )

    reasons: list[str] = []
    if not decision.accepted or decision.rejection_reasons:
        reasons.append("public_connector_readiness:connector_enablement_not_ready")
        reasons.extend(decision.rejection_reasons)
    if venue is not None and decision.venue_id is not None and decision.venue_id is not venue:
        reasons.append("public_connector_readiness:connector_enablement_not_ready")
    if dialect_id is not None and decision.dialect_id is not None and decision.dialect_id != dialect_id:
        reasons.append("public_connector_readiness:connector_enablement_not_ready")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return unique_reasons == (), unique_reasons


def _evidence_refs(value: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not _strict_string_tuple_valid(value):
        return (), ("public_connector_readiness:missing_evidence_ref",)
    refs = tuple(dict.fromkeys(item for item in value if item != "PENDING"))
    if not refs:
        return (), ("public_connector_readiness:missing_evidence_ref",)
    return refs, ()


def _extra_rejection_reasons(value: object) -> tuple[str, ...]:
    if not _strict_string_tuple_valid(value):
        return (
            "public_connector_readiness:preexisting_rejection",
            "public_connector_readiness:malformed",
        )
    if not value:
        return ()
    return tuple(dict.fromkeys(("public_connector_readiness:preexisting_rejection", *value)))


def _coerce_venue_id(value: object) -> tuple[VenueId | None, tuple[str, ...]]:
    try:
        return _venue_id(value), ()
    except PublicConnectorReadinessReportError:
        return None, ("public_connector_readiness:malformed",)


def _coerce_non_empty_string(value: object) -> tuple[str | None, tuple[str, ...]]:
    if isinstance(value, str) and value.strip() and value != "PENDING":
        return value, ()
    return None, ("public_connector_readiness:malformed",)


def _stage_status(ready: bool) -> PublicConnectorReadinessStageStatus:
    return PublicConnectorReadinessStageStatus.READY if ready else PublicConnectorReadinessStageStatus.BLOCKED


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicConnectorReadinessReportError(f"{field_name} must be a mapping")
    return value


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicConnectorReadinessReportError("venue_id is unsupported") from exc
    raise PublicConnectorReadinessReportError("venue_id is malformed")


def _stage(value: object, field_name: str) -> PublicConnectorReadinessStageStatus:
    if isinstance(value, PublicConnectorReadinessStageStatus):
        return value
    if isinstance(value, str):
        try:
            return PublicConnectorReadinessStageStatus(value)
        except ValueError as exc:
            raise PublicConnectorReadinessReportError(f"{field_name} is unsupported") from exc
    raise PublicConnectorReadinessReportError(f"{field_name} is malformed")


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise PublicConnectorReadinessReportError(f"{field_name} must be a string")


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicConnectorReadinessReportError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise PublicConnectorReadinessReportError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise PublicConnectorReadinessReportError(f"{field_name} must contain non-empty strings")
    return result


def _strict_string_tuple_valid(value: object) -> bool:
    if not isinstance(value, (tuple, list)):
        return False
    return all(isinstance(item, str) and bool(item) for item in value)


__all__ = [
    "PublicConnectorReadinessReport",
    "PublicConnectorReadinessReportError",
    "PublicConnectorReadinessStageStatus",
    "build_public_connector_readiness_report",
    "public_connector_readiness_ready",
    "public_connector_readiness_report_from_dict",
    "public_connector_readiness_report_to_dict",
]
