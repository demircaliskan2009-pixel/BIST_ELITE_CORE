from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crypto_core.venue.contracts import PublicFeedType, VenueId


class DialectEvidenceError(ValueError):
    """Raised when inert public-feed dialect evidence payloads are malformed."""


class OfficialDocEvidenceStatus(str, Enum):
    UNKNOWN = "unknown"
    SUPPLIED = "supplied"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass(frozen=True)
class OfficialDocEvidence:
    evidence_id: str
    venue_id: VenueId
    doc_type: str
    doc_url: str
    retrieved_at_ns: int
    content_hash: str
    source_name: str
    status: OfficialDocEvidenceStatus
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedDialectEvidenceBundle:
    bundle_id: str
    dialect_id: str
    venue_id: VenueId
    feed_type: PublicFeedType
    evidence_items: tuple[OfficialDocEvidence, ...]
    verified_at_ns: int
    verifier_id: str
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicFeedDialectVerificationResult:
    accepted: bool
    dialect_id: str | None
    venue_id: VenueId | None
    feed_type: PublicFeedType | None
    official_doc_refs: tuple[str, ...]
    content_hashes: tuple[str, ...]
    rejection_reasons: tuple[str, ...]


def official_doc_evidence_rejection_reasons(evidence: object) -> tuple[str, ...]:
    if evidence is None:
        return ("official_doc:evidence_missing",)
    if not isinstance(evidence, OfficialDocEvidence):
        return ("official_doc:evidence_malformed",)

    reasons: list[str] = []
    if not _non_empty(evidence.evidence_id):
        reasons.append("official_doc:evidence_id_missing")
    if not isinstance(evidence.venue_id, VenueId):
        reasons.append("official_doc:venue_missing")
    if not _non_empty(evidence.doc_type):
        reasons.append("official_doc:doc_type_missing")
    if not _non_empty(evidence.doc_url):
        reasons.append("official_doc:doc_url_missing")
    elif not evidence.doc_url.startswith(("https://", "http://")):
        reasons.append("official_doc:doc_url_scheme_invalid")
    if not _positive_int(evidence.retrieved_at_ns):
        reasons.append("official_doc:retrieved_at_invalid")
    if not _non_empty(evidence.content_hash):
        reasons.append("official_doc:content_hash_missing")
    if not _non_empty(evidence.source_name):
        reasons.append("official_doc:source_name_missing")
    if not isinstance(evidence.status, OfficialDocEvidenceStatus):
        reasons.append("official_doc:status_malformed")
    elif evidence.status is not OfficialDocEvidenceStatus.VERIFIED:
        reasons.append("official_doc:status_not_verified")
    reasons.extend(_string_reasons(evidence.rejection_reasons, "official_doc:evidence_rejected"))
    return tuple(dict.fromkeys(reasons))


def public_feed_dialect_evidence_bundle_rejection_reasons(bundle: object) -> tuple[str, ...]:
    if bundle is None:
        return ("official_doc:bundle_missing",)
    if not isinstance(bundle, PublicFeedDialectEvidenceBundle):
        return ("official_doc:bundle_malformed",)

    reasons: list[str] = []
    if not _non_empty(bundle.bundle_id):
        reasons.append("official_doc:bundle_id_missing")
    if not _non_empty(bundle.dialect_id):
        reasons.append("official_doc:dialect_id_missing")
    if not isinstance(bundle.venue_id, VenueId):
        reasons.append("official_doc:venue_missing")
    if not isinstance(bundle.feed_type, PublicFeedType):
        reasons.append("official_doc:feed_type_missing")
    if not _positive_int(bundle.verified_at_ns):
        reasons.append("official_doc:verified_at_invalid")
    if not _non_empty(bundle.verifier_id):
        reasons.append("official_doc:verifier_id_missing")
    reasons.extend(_string_reasons(bundle.rejection_reasons, "official_doc:bundle_rejected"))
    if not isinstance(bundle.evidence_items, tuple) or not bundle.evidence_items:
        reasons.append("official_doc:evidence_missing")
        return tuple(dict.fromkeys(reasons))

    evidence_ids: set[str] = set()
    doc_hashes_by_type: set[tuple[str, str]] = set()
    for item in bundle.evidence_items:
        reasons.extend(official_doc_evidence_rejection_reasons(item))
        if not isinstance(item, OfficialDocEvidence):
            continue
        if item.evidence_id in evidence_ids:
            reasons.append("official_doc:duplicate_evidence_id")
        evidence_ids.add(item.evidence_id)
        doc_hash_key = (item.doc_type, item.content_hash)
        if doc_hash_key in doc_hashes_by_type:
            reasons.append("official_doc:duplicate_content_hash")
        doc_hashes_by_type.add(doc_hash_key)
        if item.venue_id != bundle.venue_id:
            reasons.append("official_doc:venue_mismatch")
        if item.doc_type != bundle.feed_type.value:
            reasons.append("official_doc:feed_type_mismatch")
        if not item.evidence_id.startswith(f"{bundle.dialect_id}::"):
            reasons.append("official_doc:dialect_mismatch")
    return tuple(dict.fromkeys(reasons))


def verify_public_feed_dialect_evidence_bundle(
    bundle: object,
) -> PublicFeedDialectVerificationResult:
    reasons = public_feed_dialect_evidence_bundle_rejection_reasons(bundle)
    if not isinstance(bundle, PublicFeedDialectEvidenceBundle):
        return PublicFeedDialectVerificationResult(
            accepted=False,
            dialect_id=None,
            venue_id=None,
            feed_type=None,
            official_doc_refs=(),
            content_hashes=(),
            rejection_reasons=reasons,
        )

    doc_refs = tuple(
        dict.fromkeys(item.doc_url for item in bundle.evidence_items if isinstance(item, OfficialDocEvidence))
    )
    content_hashes = tuple(
        dict.fromkeys(item.content_hash for item in bundle.evidence_items if isinstance(item, OfficialDocEvidence))
    )
    return PublicFeedDialectVerificationResult(
        accepted=reasons == (),
        dialect_id=bundle.dialect_id,
        venue_id=bundle.venue_id if isinstance(bundle.venue_id, VenueId) else None,
        feed_type=bundle.feed_type if isinstance(bundle.feed_type, PublicFeedType) else None,
        official_doc_refs=doc_refs if reasons == () else (),
        content_hashes=content_hashes if reasons == () else (),
        rejection_reasons=reasons,
    )


def official_doc_evidence_to_dict(evidence: OfficialDocEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "venue_id": evidence.venue_id.value,
        "doc_type": evidence.doc_type,
        "doc_url": evidence.doc_url,
        "retrieved_at_ns": evidence.retrieved_at_ns,
        "content_hash": evidence.content_hash,
        "source_name": evidence.source_name,
        "status": evidence.status.value,
        "rejection_reasons": list(evidence.rejection_reasons),
    }


def official_doc_evidence_from_dict(data: object) -> OfficialDocEvidence:
    payload = _mapping(data, "official doc evidence payload")
    return OfficialDocEvidence(
        evidence_id=_non_empty_string(payload.get("evidence_id"), "evidence_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        doc_type=_non_empty_string(payload.get("doc_type"), "doc_type"),
        doc_url=_non_empty_string(payload.get("doc_url"), "doc_url"),
        retrieved_at_ns=_positive_int_field(payload.get("retrieved_at_ns"), "retrieved_at_ns"),
        content_hash=_non_empty_string(payload.get("content_hash"), "content_hash"),
        source_name=_non_empty_string(payload.get("source_name"), "source_name"),
        status=_status(payload.get("status")),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_dialect_evidence_bundle_to_dict(
    bundle: PublicFeedDialectEvidenceBundle,
) -> dict[str, object]:
    return {
        "bundle_id": bundle.bundle_id,
        "dialect_id": bundle.dialect_id,
        "venue_id": bundle.venue_id.value,
        "feed_type": bundle.feed_type.value,
        "evidence_items": [official_doc_evidence_to_dict(item) for item in bundle.evidence_items],
        "verified_at_ns": bundle.verified_at_ns,
        "verifier_id": bundle.verifier_id,
        "rejection_reasons": list(bundle.rejection_reasons),
    }


def public_feed_dialect_evidence_bundle_from_dict(data: object) -> PublicFeedDialectEvidenceBundle:
    payload = _mapping(data, "public feed dialect evidence bundle payload")
    evidence_items = payload.get("evidence_items")
    if not isinstance(evidence_items, tuple | list):
        raise DialectEvidenceError("evidence_items must be a sequence")
    return PublicFeedDialectEvidenceBundle(
        bundle_id=_non_empty_string(payload.get("bundle_id"), "bundle_id"),
        dialect_id=_non_empty_string(payload.get("dialect_id"), "dialect_id"),
        venue_id=_venue_id(payload.get("venue_id")),
        feed_type=_feed_type(payload.get("feed_type")),
        evidence_items=tuple(official_doc_evidence_from_dict(item) for item in evidence_items),
        verified_at_ns=_positive_int_field(payload.get("verified_at_ns"), "verified_at_ns"),
        verifier_id=_non_empty_string(payload.get("verifier_id"), "verifier_id"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_feed_dialect_verification_result_to_dict(
    result: PublicFeedDialectVerificationResult,
) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "dialect_id": result.dialect_id,
        "venue_id": None if result.venue_id is None else result.venue_id.value,
        "feed_type": None if result.feed_type is None else result.feed_type.value,
        "official_doc_refs": list(result.official_doc_refs),
        "content_hashes": list(result.content_hashes),
        "rejection_reasons": list(result.rejection_reasons),
    }


def public_feed_dialect_verification_result_from_dict(data: object) -> PublicFeedDialectVerificationResult:
    payload = _mapping(data, "public feed dialect verification result payload")
    return PublicFeedDialectVerificationResult(
        accepted=_bool(payload.get("accepted"), "accepted"),
        dialect_id=_optional_non_empty_string(payload.get("dialect_id"), "dialect_id"),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        feed_type=_optional_feed_type(payload.get("feed_type")),
        official_doc_refs=_string_tuple(payload.get("official_doc_refs", ()), "official_doc_refs"),
        content_hashes=_string_tuple(payload.get("content_hashes", ()), "content_hashes"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def _string_reasons(value: object, fallback: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return (fallback,)
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        return (fallback,)
    return result


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise DialectEvidenceError(f"{name} must be a mapping")
    return data


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise DialectEvidenceError("venue_id is unsupported") from exc
    raise DialectEvidenceError("venue_id is malformed")


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
            raise DialectEvidenceError("feed_type is unsupported") from exc
    raise DialectEvidenceError("feed_type is malformed")


def _optional_feed_type(value: object) -> PublicFeedType | None:
    if value is None:
        return None
    return _feed_type(value)


def _status(value: object) -> OfficialDocEvidenceStatus:
    if isinstance(value, OfficialDocEvidenceStatus):
        return value
    if isinstance(value, str):
        try:
            return OfficialDocEvidenceStatus(value)
        except ValueError as exc:
            raise DialectEvidenceError("status is unsupported") from exc
    raise DialectEvidenceError("status is malformed")


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise DialectEvidenceError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise DialectEvidenceError(f"{field_name} must be a positive integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise DialectEvidenceError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise DialectEvidenceError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise DialectEvidenceError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "DialectEvidenceError",
    "OfficialDocEvidence",
    "OfficialDocEvidenceStatus",
    "PublicFeedDialectEvidenceBundle",
    "PublicFeedDialectVerificationResult",
    "official_doc_evidence_from_dict",
    "official_doc_evidence_rejection_reasons",
    "official_doc_evidence_to_dict",
    "public_feed_dialect_evidence_bundle_from_dict",
    "public_feed_dialect_evidence_bundle_rejection_reasons",
    "public_feed_dialect_evidence_bundle_to_dict",
    "public_feed_dialect_verification_result_from_dict",
    "public_feed_dialect_verification_result_to_dict",
    "verify_public_feed_dialect_evidence_bundle",
]
