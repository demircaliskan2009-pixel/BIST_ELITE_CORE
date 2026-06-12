"""Paper replay intake — first deterministic paper-only consumer of a READY replay evidence manifest.

A small, deterministic, fail-closed intake gate/candidate that an operator uses to request a later paper
replay of an already-evidenced strategy. It consumes a ``ReplayEvidenceManifest`` (the bundle → admission
→ bridge → replay chain record), re-proves the manifest digest at the boundary, attaches the requesting
operator/replay identity, and emits a deterministic ``PaperReplayIntake`` candidate. It is *not* storage,
*not* runtime, and *not* a backtest engine: no DB/file/network IO, no persistence/repository adapter, no
scheduler/connector/live path, and no replay execution.

Design rules:
  - Boundary digest re-proof: the manifest digest is recomputed via the public
    ``replay_evidence_manifest_to_dict`` serializer (excluding ``manifest_digest``) and a mismatch is
    rejected before READY — a stale/forged manifest cannot intake.
  - Consume, don't re-validate: terminal status (READY/REJECTED/NEEDS_RESEARCH/INSUFFICIENT_EVIDENCE)
    propagates from the manifest; the intake adds only the boundary digest re-proof, operator/replay
    identity, and chain-digest shape checks. No upstream validation is reimplemented.
  - Fail closed: a wrong-typed manifest, empty correlation id, or malformed metadata raises; a hard
    manifest rejection, a manifest-digest mismatch, a malformed chain digest / source id, or a BIST/live/
    private/order/scheduler token in an identity/metadata value yields REJECTED; needs-research and
    insufficient-evidence propagate.
  - Deterministic: a canonical SHA-256 ``intake_digest``; no wall-clock/random/IO. Frozen dataclass;
    ``paper_only=True`` and no order/route/venue/scheduler/runtime/persistence/store/engine field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.replay_evidence_manifest import (
    ReplayEvidenceManifest,
    ReplayEvidenceManifestStatus,
    replay_evidence_manifest_to_dict,
)

_SCHEMA_VERSION = "paper-replay-intake.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Safely-detectable BIST markers and forbidden live/order/scheduler/private config tokens (word-bounded).
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|auto_loop|shadow_live_execution|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class PaperReplayIntakeError(RuntimeError):
    """Raised when intake inputs are malformed at the call level (wrong type / bad id / bad metadata)."""


class PaperReplayIntakeStatus(str, Enum):
    """Terminal readiness of a paper replay intake candidate. Never an order/live action."""

    READY = "READY"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperReplayIntake:
    """Deterministic, immutable paper replay intake candidate over a manifest. PAPER ONLY."""

    schema_version: str
    status: PaperReplayIntakeStatus
    ready: bool
    requested_replay_id: str
    operator_id: str
    strategy_id: str | None
    strategy_digest: str | None
    bundle_digest: str
    admission_digest: str
    bridge_digest: str
    manifest_digest: str
    manifest_status: str
    replay_source_id: str
    historical_data_source_id: str
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    intake_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _safe_digest_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _safe_optional_digest_value(value: object) -> str | None:
    return value if isinstance(value, str) or value is None else None


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_replay_intake:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("paper_replay_intake:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperReplayIntakeError("paper_replay_intake:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperReplayIntakeError("paper_replay_intake:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _expected_manifest_digest(manifest: ReplayEvidenceManifest) -> str | None:
    try:
        payload = replay_evidence_manifest_to_dict(manifest)
        payload.pop("manifest_digest", None)
        return _canonical_digest(payload)
    except Exception:
        return None


def build_paper_replay_intake(
    manifest: ReplayEvidenceManifest,
    *,
    requested_replay_id: str,
    operator_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperReplayIntake:
    """Build a deterministic paper replay intake candidate from a ``ReplayEvidenceManifest``.

    ``manifest`` must be a ``ReplayEvidenceManifest``; a wrong-typed manifest, an empty ``correlation_id``,
    or non ``Mapping[str, str]`` metadata raises ``PaperReplayIntakeError``. The intake is READY only when
    the manifest is READY + ready, its ``manifest_digest`` re-proves via the public serializer, the chain
    digests are canonical 64-hex, the source ids are non-empty, and no forbidden/BIST token appears in the
    identity/metadata values; every other outcome maps fail-closed to REJECTED / INSUFFICIENT_EVIDENCE /
    NEEDS_RESEARCH. Deterministic and immutable; no persistence/runtime/execution path.
    """
    if not isinstance(manifest, ReplayEvidenceManifest):
        raise PaperReplayIntakeError("paper_replay_intake:manifest_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperReplayIntakeError("paper_replay_intake:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)

    hard: list[str] = []
    needs: list[str] = []
    insufficient: list[str] = []

    if not _is_non_empty_string(requested_replay_id):
        hard.append("paper_replay_intake:requested_replay_id_invalid")
    if not _is_non_empty_string(operator_id):
        hard.append("paper_replay_intake:operator_id_invalid")
    hard.extend(
        _scope_violations(
            requested_replay_id,
            operator_id,
            correlation_id,
            manifest.replay_source_id,
            manifest.historical_data_source_id,
            *(value for _, value in metadata_pairs),
        )
    )

    for name, digest in (
        ("bundle_digest", manifest.bundle_digest),
        ("admission_digest", manifest.admission_digest),
        ("bridge_digest", manifest.bridge_digest),
        ("manifest_digest", manifest.manifest_digest),
    ):
        if not _is_sha256_hex(digest):
            hard.append(f"paper_replay_intake:{name}_invalid")

    if not _is_non_empty_string(manifest.replay_source_id):
        hard.append("paper_replay_intake:replay_source_id_invalid")
    if not _is_non_empty_string(manifest.historical_data_source_id):
        hard.append("paper_replay_intake:historical_data_source_id_invalid")

    # Boundary digest re-proof: a stale/forged manifest must not intake.
    if _is_sha256_hex(manifest.manifest_digest) and manifest.manifest_digest != _expected_manifest_digest(manifest):
        hard.append("paper_replay_intake:manifest_digest_mismatch")

    if manifest.status is ReplayEvidenceManifestStatus.REJECTED:
        hard.append("paper_replay_intake:manifest_rejected")
        hard.extend(manifest.rejection_reasons)
    elif manifest.status is ReplayEvidenceManifestStatus.NEEDS_RESEARCH:
        needs.append("paper_replay_intake:manifest_needs_research")
        needs.extend(manifest.needs_research_reasons)
    elif manifest.status is ReplayEvidenceManifestStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_intake:manifest_insufficient_evidence")
    elif manifest.status is ReplayEvidenceManifestStatus.READY and not manifest.ready:
        hard.append("paper_replay_intake:manifest_ready_mismatch")

    rejection_reasons = _sorted_unique(tuple(hard))
    needs_research_reasons = _sorted_unique(tuple(needs))
    insufficient_reasons = _sorted_unique(tuple(insufficient))

    if rejection_reasons:
        status = PaperReplayIntakeStatus.REJECTED
    elif insufficient_reasons:
        status = PaperReplayIntakeStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = PaperReplayIntakeStatus.NEEDS_RESEARCH
    elif manifest.status is ReplayEvidenceManifestStatus.READY and manifest.ready:
        status = PaperReplayIntakeStatus.READY
    else:
        status = PaperReplayIntakeStatus.INSUFFICIENT_EVIDENCE

    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons
    return _assemble(
        status=status,
        manifest=manifest,
        requested_replay_id=requested_replay_id,
        operator_id=operator_id,
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
    )


def _assemble(
    *,
    status: PaperReplayIntakeStatus,
    manifest: ReplayEvidenceManifest,
    requested_replay_id: str,
    operator_id: str,
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
) -> PaperReplayIntake:
    ready = status is PaperReplayIntakeStatus.READY
    strategy_digest = _safe_optional_digest_value(manifest.strategy_digest)
    bundle_digest = _safe_digest_value(manifest.bundle_digest)
    admission_digest = _safe_digest_value(manifest.admission_digest)
    bridge_digest = _safe_digest_value(manifest.bridge_digest)
    manifest_digest = _safe_digest_value(manifest.manifest_digest)
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "ready": ready,
        "requested_replay_id": requested_replay_id,
        "operator_id": operator_id,
        "strategy_id": manifest.strategy_id,
        "strategy_digest": strategy_digest,
        "bundle_digest": bundle_digest,
        "admission_digest": admission_digest,
        "bridge_digest": bridge_digest,
        "manifest_digest": manifest_digest,
        "manifest_status": manifest.status.value,
        "replay_source_id": manifest.replay_source_id,
        "historical_data_source_id": manifest.historical_data_source_id,
        "metadata": [list(pair) for pair in metadata],
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return PaperReplayIntake(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        requested_replay_id=requested_replay_id,
        operator_id=operator_id,
        strategy_id=manifest.strategy_id,
        strategy_digest=strategy_digest,
        bundle_digest=bundle_digest,
        admission_digest=admission_digest,
        bridge_digest=bridge_digest,
        manifest_digest=manifest_digest,
        manifest_status=manifest.status.value,
        replay_source_id=manifest.replay_source_id,
        historical_data_source_id=manifest.historical_data_source_id,
        metadata=metadata,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        intake_digest=_canonical_digest(payload),
    )


def paper_replay_intake_to_dict(intake: PaperReplayIntake) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper replay intake candidate (deterministic shape)."""
    return {
        "schema_version": intake.schema_version,
        "status": intake.status.value,
        "ready": intake.ready,
        "requested_replay_id": intake.requested_replay_id,
        "operator_id": intake.operator_id,
        "strategy_id": intake.strategy_id,
        "strategy_digest": intake.strategy_digest,
        "bundle_digest": intake.bundle_digest,
        "admission_digest": intake.admission_digest,
        "bridge_digest": intake.bridge_digest,
        "manifest_digest": intake.manifest_digest,
        "manifest_status": intake.manifest_status,
        "replay_source_id": intake.replay_source_id,
        "historical_data_source_id": intake.historical_data_source_id,
        "metadata": [list(pair) for pair in intake.metadata],
        "rejection_reasons": list(intake.rejection_reasons),
        "needs_research_reasons": list(intake.needs_research_reasons),
        "correlation_id": intake.correlation_id,
        "intake_digest": intake.intake_digest,
        "paper_only": intake.paper_only,
        "real_orders_enabled": intake.real_orders_enabled,
        "real_money_enabled": intake.real_money_enabled,
    }


__all__ = [
    "PaperReplayIntake",
    "PaperReplayIntakeError",
    "PaperReplayIntakeStatus",
    "build_paper_replay_intake",
    "paper_replay_intake_to_dict",
]
