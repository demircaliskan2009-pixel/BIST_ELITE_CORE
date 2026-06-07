"""Strategy source packet — typed edge-idea provenance intake.

Captures the provenance of an edge idea — where it came from, its rights posture, a content digest,
and its claimed hypothesis — as a deterministic, immutable, fail-closed, paper-only record. This is
the upstream intake seam *before* an idea is compiled into a ``StrategySpec`` (no blind import: rights
+ crypto scope + content digest are required up front). No runtime/orchestrator/data-registry/PIT/
leakage/backtest wiring, no persistence, no venue facts, no live/order path.

Design rules:
  - Immutable + deterministic: a frozen dataclass with a canonical SHA-256 ``packet_digest`` over its
    material fields; identical input yields an identical packet/digest. No wall-clock/random/IO/network.
  - Fail closed: empty/whitespace/malformed identifiers, unknown source-type/rights-status, a malformed
    ``content_digest`` (must be 64-hex), or an empty crypto scope are rejected with ``SourcePacketError``.
  - Crypto-only: any safely-detectable BIST marker (bist/borsa/kap/matriks) in any text field is rejected.
  - No live/order leakage: any forbidden live/private/order/scheduler config token in any text field is
    rejected; the record carries ``paper_only=True`` and no order/route/venue/scheduler field.
  - Rights discipline: ``RESTRICTED`` rights are recorded but mark ``usable_for_compilation=False`` and
    add a stable risk flag, so a restricted source cannot silently flow into a StrategySpec.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum

_SOURCE_PACKET_SCHEMA_VERSION = "source-packet.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

_RESTRICTED_RIGHTS_FLAG = "source_packet:restricted_rights"

# Safely-detectable BIST markers only (word-bounded; "ideal" is intentionally excluded because it
# collides with the ordinary English word and is not safely detectable).
_BIST_PATTERN = re.compile(r"\b(bist|bist30|bist100|borsa|kap|matriks)\b", re.IGNORECASE)
# Forbidden live/private/order/scheduler config tokens (word-bounded so "live" matches "live trading"
# but not "delivery").
_FORBIDDEN_PATTERN = re.compile(
    r"\b(live|private_api|credentials|order_router|scheduler|auto_loop|shadow_live_execution)\b",
    re.IGNORECASE,
)


class SourcePacketError(RuntimeError):
    """Raised when a source-packet input is malformed, non-crypto, or carries a forbidden token."""


class SourcePacketSourceType(str, Enum):
    """Where the edge idea originated. Research-neutral; no venue facts."""

    ACADEMIC_PAPER = "academic_paper"
    PREPRINT = "preprint"
    CODE_REPOSITORY = "code_repository"
    BLOG_POST = "blog_post"
    FORUM_THREAD = "forum_thread"
    DOCUMENTATION = "documentation"
    MANUAL_NOTE = "manual_note"


class SourcePacketRightsStatus(str, Enum):
    """Rights posture of the source material (no-blind-import discipline)."""

    OWN_RESEARCH = "own_research"
    PUBLIC_DOMAIN = "public_domain"
    PERMISSIVE_LICENSE = "permissive_license"
    CITED_FAIR_USE = "cited_fair_use"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class SourcePacket:
    """Deterministic, immutable typed provenance record for an edge idea. PAPER ONLY."""

    schema_version: str
    packet_id: str
    source_type: SourcePacketSourceType
    source_reference: str
    source_title: str
    rights_status: SourcePacketRightsStatus
    usable_for_compilation: bool
    edge_hypothesis: str
    market_scope_tags: tuple[str, ...]
    data_requirement_hints: tuple[str, ...]
    risk_flags: tuple[str, ...]
    content_digest: str
    packet_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _scan_text(value: str, field_name: str) -> None:
    if _BIST_PATTERN.search(value):
        raise SourcePacketError(f"source_packet:bist_scope_leakage:{field_name}")
    if _FORBIDDEN_PATTERN.search(value):
        raise SourcePacketError(f"source_packet:forbidden_token:{field_name}")


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise SourcePacketError(f"source_packet:{field_name}_invalid")
    trimmed = value.strip()
    _scan_text(trimmed, field_name)
    return trimmed


def _coerce_source_type(value: object) -> SourcePacketSourceType:
    if isinstance(value, SourcePacketSourceType):
        return value
    if isinstance(value, str):
        try:
            return SourcePacketSourceType(value.strip().lower())
        except ValueError as exc:
            raise SourcePacketError("source_packet:source_type_unknown") from exc
    raise SourcePacketError("source_packet:source_type_malformed")


def _coerce_rights_status(value: object) -> SourcePacketRightsStatus:
    if isinstance(value, SourcePacketRightsStatus):
        return value
    if isinstance(value, str):
        try:
            return SourcePacketRightsStatus(value.strip().lower())
        except ValueError as exc:
            raise SourcePacketError("source_packet:rights_status_unknown") from exc
    raise SourcePacketError("source_packet:rights_status_malformed")


def _canonical_tags(values: object, field_name: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise SourcePacketError(f"source_packet:{field_name}_malformed")
    cleaned: list[str] = []
    for item in values:
        if not isinstance(item, str) or item.strip() == "":
            raise SourcePacketError(f"source_packet:{field_name}_malformed")
        trimmed = item.strip()
        _scan_text(trimmed, field_name)
        cleaned.append(trimmed)
    if required and not cleaned:
        raise SourcePacketError(f"source_packet:{field_name}_empty")
    return tuple(sorted(set(cleaned)))


def build_source_packet(
    *,
    packet_id: str,
    source_type: object,
    source_reference: str,
    source_title: str,
    rights_status: object,
    edge_hypothesis: str,
    content_digest: str,
    market_scope_tags: tuple[str, ...] | list[str] = (),
    data_requirement_hints: tuple[str, ...] | list[str] = (),
    risk_flags: tuple[str, ...] | list[str] = (),
) -> SourcePacket:
    """Build a deterministic, fail-closed source packet from edge-idea provenance fields.

    Identifiers must be non-empty strings; ``source_type``/``rights_status`` must be known enums (or
    their string values); ``content_digest`` must be canonical 64-hex; ``market_scope_tags`` must be a
    non-empty crypto scope. Any BIST marker or forbidden live/private/order/scheduler token in any text
    field is rejected. ``RESTRICTED`` rights are recorded but mark ``usable_for_compilation=False`` and
    add a stable risk flag. The packet is immutable and carries its own canonical digest; no order
    intent or live wiring is produced.
    """
    resolved_packet_id = _required_text(packet_id, "packet_id")
    resolved_source_reference = _required_text(source_reference, "source_reference")
    resolved_source_title = _required_text(source_title, "source_title")
    resolved_edge_hypothesis = _required_text(edge_hypothesis, "edge_hypothesis")
    resolved_source_type = _coerce_source_type(source_type)
    resolved_rights_status = _coerce_rights_status(rights_status)
    if not _is_sha256_hex(content_digest):
        raise SourcePacketError("source_packet:content_digest_invalid")

    resolved_scope = _canonical_tags(market_scope_tags, "market_scope_tags", required=True)
    resolved_hints = _canonical_tags(data_requirement_hints, "data_requirement_hints", required=False)
    provided_flags = _canonical_tags(risk_flags, "risk_flags", required=False)

    usable_for_compilation = resolved_rights_status is not SourcePacketRightsStatus.RESTRICTED
    flag_values = set(provided_flags)
    if not usable_for_compilation:
        flag_values.add(_RESTRICTED_RIGHTS_FLAG)
    resolved_flags = tuple(sorted(flag_values))

    digest_payload: dict[str, object] = {
        "schema_version": _SOURCE_PACKET_SCHEMA_VERSION,
        "packet_id": resolved_packet_id,
        "source_type": resolved_source_type.value,
        "source_reference": resolved_source_reference,
        "source_title": resolved_source_title,
        "rights_status": resolved_rights_status.value,
        "usable_for_compilation": usable_for_compilation,
        "edge_hypothesis": resolved_edge_hypothesis,
        "market_scope_tags": list(resolved_scope),
        "data_requirement_hints": list(resolved_hints),
        "risk_flags": list(resolved_flags),
        "content_digest": content_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return SourcePacket(
        schema_version=_SOURCE_PACKET_SCHEMA_VERSION,
        packet_id=resolved_packet_id,
        source_type=resolved_source_type,
        source_reference=resolved_source_reference,
        source_title=resolved_source_title,
        rights_status=resolved_rights_status,
        usable_for_compilation=usable_for_compilation,
        edge_hypothesis=resolved_edge_hypothesis,
        market_scope_tags=resolved_scope,
        data_requirement_hints=resolved_hints,
        risk_flags=resolved_flags,
        content_digest=content_digest,
        packet_digest=_canonical_digest(digest_payload),
    )


def source_packet_to_dict(packet: SourcePacket) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a source packet (deterministic key/value shape)."""
    return {
        "schema_version": packet.schema_version,
        "packet_id": packet.packet_id,
        "source_type": packet.source_type.value,
        "source_reference": packet.source_reference,
        "source_title": packet.source_title,
        "rights_status": packet.rights_status.value,
        "usable_for_compilation": packet.usable_for_compilation,
        "edge_hypothesis": packet.edge_hypothesis,
        "market_scope_tags": list(packet.market_scope_tags),
        "data_requirement_hints": list(packet.data_requirement_hints),
        "risk_flags": list(packet.risk_flags),
        "content_digest": packet.content_digest,
        "packet_digest": packet.packet_digest,
        "paper_only": packet.paper_only,
        "real_orders_enabled": packet.real_orders_enabled,
        "real_money_enabled": packet.real_money_enabled,
    }


__all__ = [
    "SourcePacket",
    "SourcePacketError",
    "SourcePacketRightsStatus",
    "SourcePacketSourceType",
    "build_source_packet",
    "source_packet_to_dict",
]
