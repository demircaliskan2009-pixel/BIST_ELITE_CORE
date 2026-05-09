from __future__ import annotations

from dataclasses import dataclass

from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.dialect_evidence import (
    OfficialDocEvidence,
    PublicFeedDialectEvidenceBundle,
    official_doc_evidence_from_dict,
    official_doc_evidence_rejection_reasons,
    official_doc_evidence_to_dict,
)


class OfficialEvidencePackageError(ValueError):
    """Raised when inert official venue evidence package payloads are malformed."""


@dataclass(frozen=True)
class OfficialEvidencePackage:
    package_id: str
    venue_id: VenueId
    retrieved_at_ns: int
    source_count: int
    evidence_items: tuple[OfficialDocEvidence, ...]
    rejection_reasons: tuple[str, ...] = ()


def official_evidence_package_rejection_reasons(package: object) -> tuple[str, ...]:
    if package is None:
        return ("official_evidence_package:package_missing",)
    if not isinstance(package, OfficialEvidencePackage):
        return ("official_evidence_package:package_malformed",)

    reasons: list[str] = []
    if not _non_empty(package.package_id):
        reasons.append("official_evidence_package:package_id_missing")
    if not isinstance(package.venue_id, VenueId):
        reasons.append("official_evidence_package:venue_missing")
    if not _positive_int(package.retrieved_at_ns):
        reasons.append("official_evidence_package:retrieved_at_invalid")
    if not _positive_int(package.source_count):
        reasons.append("official_evidence_package:source_count_invalid")
    reasons.extend(_string_reasons(package.rejection_reasons, "official_evidence_package:package_rejected"))

    if not isinstance(package.evidence_items, tuple) or not package.evidence_items:
        reasons.append("official_evidence_package:evidence_missing")
        return tuple(dict.fromkeys(reasons))
    if package.source_count != len(package.evidence_items):
        reasons.append("official_evidence_package:source_count_mismatch")

    evidence_ids: set[str] = set()
    doc_urls: set[str] = set()
    for item in package.evidence_items:
        item_reasons = official_doc_evidence_rejection_reasons(item)
        reasons.extend(item_reasons)
        if item_reasons:
            reasons.append("official_evidence_package:evidence_rejected")
        if not isinstance(item, OfficialDocEvidence):
            continue
        if item.venue_id != package.venue_id:
            reasons.append("official_evidence_package:venue_mismatch")
        if item.evidence_id in evidence_ids:
            reasons.append("official_evidence_package:duplicate_evidence_id")
        evidence_ids.add(item.evidence_id)
        if item.doc_url in doc_urls:
            reasons.append("official_evidence_package:duplicate_doc_url")
        doc_urls.add(item.doc_url)
    return tuple(dict.fromkeys(reasons))


def build_public_feed_dialect_evidence_bundle_from_package(
    package: OfficialEvidencePackage,
    *,
    dialect_id: str,
    feed_type: PublicFeedType,
) -> PublicFeedDialectEvidenceBundle:
    if not isinstance(package, OfficialEvidencePackage):
        raise OfficialEvidencePackageError("package must be an OfficialEvidencePackage")
    if not _non_empty(dialect_id):
        raise OfficialEvidencePackageError("dialect_id must be a non-empty string")
    if not isinstance(feed_type, PublicFeedType):
        raise OfficialEvidencePackageError("feed_type must be a PublicFeedType")

    evidence_items = tuple(sorted(package.evidence_items, key=lambda item: (item.evidence_id, item.doc_url)))
    package_reasons = official_evidence_package_rejection_reasons(package)
    return PublicFeedDialectEvidenceBundle(
        bundle_id=f"{package.package_id}::{dialect_id}::{feed_type.value}",
        dialect_id=dialect_id,
        venue_id=package.venue_id,
        feed_type=feed_type,
        evidence_items=evidence_items,
        verified_at_ns=package.retrieved_at_ns,
        verifier_id=package.package_id,
        rejection_reasons=package_reasons,
    )


def official_evidence_package_to_dict(package: OfficialEvidencePackage) -> dict[str, object]:
    return {
        "package_id": package.package_id,
        "venue_id": package.venue_id.value,
        "retrieved_at_ns": package.retrieved_at_ns,
        "source_count": package.source_count,
        "evidence_items": [official_doc_evidence_to_dict(item) for item in package.evidence_items],
        "rejection_reasons": list(package.rejection_reasons),
    }


def official_evidence_package_from_dict(data: object) -> OfficialEvidencePackage:
    payload = _mapping(data)
    evidence_items = payload.get("evidence_items")
    if not isinstance(evidence_items, tuple | list):
        raise OfficialEvidencePackageError("evidence_items must be a sequence")
    return OfficialEvidencePackage(
        package_id=_non_empty_string(payload.get("package_id"), "package_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        retrieved_at_ns=_positive_int_field(payload.get("retrieved_at_ns"), "retrieved_at_ns"),
        source_count=_positive_int_field(payload.get("source_count"), "source_count"),
        evidence_items=tuple(official_doc_evidence_from_dict(item) for item in evidence_items),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _mapping(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise OfficialEvidencePackageError("official evidence package payload must be a mapping")
    return data


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise OfficialEvidencePackageError("venue_id is unsupported") from exc
    raise OfficialEvidencePackageError("venue_id is malformed")


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise OfficialEvidencePackageError(f"{field_name} must be a non-empty string")
    return value


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise OfficialEvidencePackageError(f"{field_name} must be a positive integer")
    return value


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        return (fallback,)
    return result


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise OfficialEvidencePackageError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise OfficialEvidencePackageError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "OfficialEvidencePackage",
    "OfficialEvidencePackageError",
    "build_public_feed_dialect_evidence_bundle_from_package",
    "official_evidence_package_from_dict",
    "official_evidence_package_rejection_reasons",
    "official_evidence_package_to_dict",
]
