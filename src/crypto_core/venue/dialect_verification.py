from __future__ import annotations

from dataclasses import dataclass, replace

from crypto_core.data.public_feed_dialect import (
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    PublicFeedDialectSpec,
    public_feed_dialect_connector_ready,
    public_feed_dialect_rejection_reasons,
    public_feed_dialect_spec_from_dict,
    public_feed_dialect_spec_to_dict,
)
from crypto_core.venue.dialect_evidence import PublicFeedDialectVerificationResult


class DialectVerificationOverlayError(ValueError):
    """Raised when inert public-feed dialect verification overlay payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedDialectVerificationOverlayResult:
    accepted: bool
    original_spec: PublicFeedDialectSpec | None
    verified_spec: PublicFeedDialectSpec | None
    rejection_reasons: tuple[str, ...]


def apply_public_feed_dialect_verification(
    spec: object,
    verification_result: object,
) -> PublicFeedDialectVerificationOverlayResult:
    reasons: list[str] = []
    if not isinstance(spec, PublicFeedDialectSpec):
        reasons.append("public_feed_dialect_overlay:spec_missing")
    if not isinstance(verification_result, PublicFeedDialectVerificationResult):
        reasons.append("public_feed_dialect_overlay:verification_missing")
    if reasons:
        return _overlay_result(spec=None, verified_spec=None, reasons=reasons)

    assert isinstance(spec, PublicFeedDialectSpec)
    assert isinstance(verification_result, PublicFeedDialectVerificationResult)

    if verification_result.accepted is not True or verification_result.rejection_reasons:
        reasons.append("public_feed_dialect_overlay:verification_rejected")
        reasons.extend(verification_result.rejection_reasons)
    if verification_result.dialect_id != spec.dialect_id:
        reasons.append("public_feed_dialect_overlay:dialect_mismatch")
    if verification_result.venue_id != spec.venue_id:
        reasons.append("public_feed_dialect_overlay:venue_mismatch")
    if verification_result.feed_type != spec.feed_type:
        reasons.append("public_feed_dialect_overlay:feed_type_mismatch")
    if not verification_result.official_doc_refs:
        reasons.append("public_feed_dialect_overlay:official_docs_missing")
    if not verification_result.content_hashes:
        reasons.append("public_feed_dialect_overlay:content_hashes_missing")

    base_reasons = public_feed_dialect_rejection_reasons(spec)
    unexpected_base_reasons = tuple(reason for reason in base_reasons if reason not in _ALLOWED_BASE_REASONS)
    reasons.extend(unexpected_base_reasons)
    if spec.sequence_model is FeedSequenceModel.UNKNOWN:
        reasons.append("public_feed_dialect_overlay:sequence_model_unknown")
    if not spec.supports_delta_stream:
        reasons.append("public_feed_dialect_overlay:delta_stream_unsupported")

    candidate = replace(
        spec,
        verification_status=FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS,
        official_doc_refs=verification_result.official_doc_refs,
        enabled_for_connector=True,
        rejection_reasons=(),
    )
    candidate_reasons = public_feed_dialect_rejection_reasons(candidate)
    if candidate_reasons:
        reasons.extend(candidate_reasons)
    if not public_feed_dialect_connector_ready(candidate):
        reasons.append("public_feed_dialect_overlay:not_connector_ready")

    normalized_reasons = tuple(dict.fromkeys(reasons))
    return _overlay_result(
        spec=spec,
        verified_spec=candidate if normalized_reasons == () else None,
        reasons=normalized_reasons,
    )


def public_feed_dialect_verification_overlay_result_to_dict(
    result: PublicFeedDialectVerificationOverlayResult,
) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "original_spec": None
        if result.original_spec is None
        else public_feed_dialect_spec_to_dict(result.original_spec),
        "verified_spec": None
        if result.verified_spec is None
        else public_feed_dialect_spec_to_dict(result.verified_spec),
        "rejection_reasons": list(result.rejection_reasons),
    }


def public_feed_dialect_verification_overlay_result_from_dict(
    data: object,
) -> PublicFeedDialectVerificationOverlayResult:
    payload = _mapping(data)
    original_payload = payload.get("original_spec")
    verified_payload = payload.get("verified_spec")
    return PublicFeedDialectVerificationOverlayResult(
        accepted=_bool(payload.get("accepted"), "accepted"),
        original_spec=None if original_payload is None else public_feed_dialect_spec_from_dict(original_payload),
        verified_spec=None if verified_payload is None else public_feed_dialect_spec_from_dict(verified_payload),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


_ALLOWED_BASE_REASONS = frozenset(
    {
        "public_feed_dialect:unverified",
        "public_feed_dialect:connector_disabled",
        "public_feed_dialect:connector_unverified",
    }
)


def _overlay_result(
    *,
    spec: PublicFeedDialectSpec | None,
    verified_spec: PublicFeedDialectSpec | None,
    reasons: tuple[str, ...] | list[str],
) -> PublicFeedDialectVerificationOverlayResult:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return PublicFeedDialectVerificationOverlayResult(
        accepted=normalized_reasons == () and verified_spec is not None,
        original_spec=spec,
        verified_spec=verified_spec if normalized_reasons == () else None,
        rejection_reasons=normalized_reasons,
    )


def _mapping(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise DialectVerificationOverlayError("dialect verification overlay payload must be a mapping")
    return data


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise DialectVerificationOverlayError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise DialectVerificationOverlayError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise DialectVerificationOverlayError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "DialectVerificationOverlayError",
    "PublicFeedDialectVerificationOverlayResult",
    "apply_public_feed_dialect_verification",
    "public_feed_dialect_verification_overlay_result_from_dict",
    "public_feed_dialect_verification_overlay_result_to_dict",
]
