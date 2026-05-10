from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from crypto_core.venue.contracts import VenueId


class OfficialSourceSnapshotError(ValueError):
    """Raised when inert official source snapshot payloads are malformed."""


class OfficialSourceSnapshotStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class OfficialSourceSnapshot:
    snapshot_id: str
    source_id: str
    venue_id: VenueId
    official_url: str
    retrieved_at_iso: str
    content_sha256: str
    content_size_bytes: int
    reviewer_id: str
    reviewed_at_iso: str
    manual_review_status: str
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OfficialSourceSnapshotValidationResult:
    accepted: bool
    snapshot_id: str | None
    source_id: str | None
    venue_id: VenueId | None
    content_sha256: str | None
    rejection_reasons: tuple[str, ...]


def validate_official_source_snapshot(snapshot: object) -> OfficialSourceSnapshotValidationResult:
    if not isinstance(snapshot, OfficialSourceSnapshot):
        return OfficialSourceSnapshotValidationResult(
            accepted=False,
            snapshot_id=None,
            source_id=None,
            venue_id=None,
            content_sha256=None,
            rejection_reasons=(
                "official_snapshot:missing_source_id",
                "official_snapshot:missing_venue_id",
                "official_snapshot:missing_url",
                "official_snapshot:missing_retrieved_at",
                "official_snapshot:missing_hash",
                "official_snapshot:invalid_size",
                "official_snapshot:missing_reviewer",
                "official_snapshot:missing_review_time",
                "official_snapshot:manual_review_not_approved",
            ),
        )

    reasons: list[str] = []
    if not _non_empty(snapshot.source_id):
        reasons.append("official_snapshot:missing_source_id")
    if not isinstance(snapshot.venue_id, VenueId):
        reasons.append("official_snapshot:missing_venue_id")
    if not _non_empty(snapshot.official_url):
        reasons.append("official_snapshot:missing_url")
    if not _non_empty(snapshot.retrieved_at_iso):
        reasons.append("official_snapshot:missing_retrieved_at")
    if not _non_empty(snapshot.content_sha256):
        reasons.append("official_snapshot:missing_hash")
    elif not _valid_sha256_hex(snapshot.content_sha256):
        reasons.append("official_snapshot:invalid_hash")
    if not _positive_int(snapshot.content_size_bytes):
        reasons.append("official_snapshot:invalid_size")
    if not _non_empty(snapshot.reviewer_id):
        reasons.append("official_snapshot:missing_reviewer")
    if not _non_empty(snapshot.reviewed_at_iso):
        reasons.append("official_snapshot:missing_review_time")
    if snapshot.manual_review_status != "APPROVED":
        reasons.append("official_snapshot:manual_review_not_approved")
    if not _string_tuple_valid(snapshot.rejection_reasons, allow_empty=True) or snapshot.rejection_reasons:
        reasons.append("official_snapshot:preexisting_rejection")

    rejection_reasons = tuple(dict.fromkeys(reasons))
    return OfficialSourceSnapshotValidationResult(
        accepted=rejection_reasons == (),
        snapshot_id=snapshot.snapshot_id if _non_empty(snapshot.snapshot_id) else None,
        source_id=snapshot.source_id if _non_empty(snapshot.source_id) else None,
        venue_id=snapshot.venue_id if isinstance(snapshot.venue_id, VenueId) else None,
        content_sha256=snapshot.content_sha256 if _non_empty(snapshot.content_sha256) else None,
        rejection_reasons=rejection_reasons,
    )


def official_source_snapshot_to_dict(snapshot: OfficialSourceSnapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "source_id": snapshot.source_id,
        "venue_id": snapshot.venue_id.value,
        "official_url": snapshot.official_url,
        "retrieved_at_iso": snapshot.retrieved_at_iso,
        "content_sha256": snapshot.content_sha256,
        "content_size_bytes": snapshot.content_size_bytes,
        "reviewer_id": snapshot.reviewer_id,
        "reviewed_at_iso": snapshot.reviewed_at_iso,
        "manual_review_status": snapshot.manual_review_status,
        "rejection_reasons": list(snapshot.rejection_reasons),
    }


def official_source_snapshot_from_dict(payload: object) -> OfficialSourceSnapshot:
    data = _mapping(payload)
    return OfficialSourceSnapshot(
        snapshot_id=_string_field(data.get("snapshot_id"), "snapshot_id"),
        source_id=_string_field(data.get("source_id"), "source_id"),
        venue_id=_venue_id(data.get("venue_id")),
        official_url=_string_field(data.get("official_url"), "official_url"),
        retrieved_at_iso=_string_field(data.get("retrieved_at_iso"), "retrieved_at_iso"),
        content_sha256=_string_field(data.get("content_sha256"), "content_sha256"),
        content_size_bytes=_int_field(data.get("content_size_bytes"), "content_size_bytes"),
        reviewer_id=_string_field(data.get("reviewer_id"), "reviewer_id"),
        reviewed_at_iso=_string_field(data.get("reviewed_at_iso"), "reviewed_at_iso"),
        manual_review_status=_string_field(data.get("manual_review_status"), "manual_review_status"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


def official_source_snapshot_result_to_dict(
    result: OfficialSourceSnapshotValidationResult,
) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "snapshot_id": result.snapshot_id,
        "source_id": result.source_id,
        "venue_id": None if result.venue_id is None else result.venue_id.value,
        "content_sha256": result.content_sha256,
        "rejection_reasons": list(result.rejection_reasons),
    }


def sha256_hex_from_text(text: str) -> str:
    if not isinstance(text, str):
        raise OfficialSourceSnapshotError("text must be a string")
    return sha256_hex_from_bytes(text.encode("utf-8"))


def sha256_hex_from_bytes(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise OfficialSourceSnapshotError("data must be bytes")
    return hashlib.sha256(data).hexdigest()


def _mapping(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise OfficialSourceSnapshotError("official source snapshot payload must be a mapping")
    return payload


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise OfficialSourceSnapshotError("venue_id is unsupported") from exc
    raise OfficialSourceSnapshotError("venue_id is malformed")


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _string_field(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise OfficialSourceSnapshotError(f"{field_name} must be a string")
    return value


def _int_field(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise OfficialSourceSnapshotError(f"{field_name} must be an integer")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise OfficialSourceSnapshotError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise OfficialSourceSnapshotError(f"{field_name} must contain non-empty strings")
    return result


def _string_tuple_valid(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, tuple | list):
        return False
    result = tuple(value)
    if not allow_empty and not result:
        return False
    return all(_non_empty(reason) for reason in result)


def _valid_sha256_hex(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value)


__all__ = [
    "OfficialSourceSnapshot",
    "OfficialSourceSnapshotError",
    "OfficialSourceSnapshotStatus",
    "OfficialSourceSnapshotValidationResult",
    "official_source_snapshot_from_dict",
    "official_source_snapshot_result_to_dict",
    "official_source_snapshot_to_dict",
    "sha256_hex_from_bytes",
    "sha256_hex_from_text",
    "validate_official_source_snapshot",
]
