"""Replay evidence manifest — deterministic paper-only record of the admitted replay evidence chain.

A pure, deterministic, fail-closed manifest/packet that records the bundle → admission → bridge → replay
evidence chain (by digest) for a later paper replay. It is a *contract*, not storage: it performs no DB/
file/network IO, holds no persistence/repository adapter, runs no backtest engine, and wires no runtime/
scheduler/live path. It derives its readiness solely from an already-computed ``BacktestReplayBridgeResult``
plus the caller-supplied chain digests/source ids, cross-checking them for consistency.

Design rules:
  - Consume + cross-check, never fabricate: the manifest is READY only when the bridge/replay verdict is
    ACCEPTED, the supplied bundle/admission/bridge digests are canonical 64-hex, the admission digest
    matches the bridge result, the replay source ids match the delegated replay result, and the ledger
    evidence digests are present and well-formed.
  - Fail closed: a wrong-typed bridge result, empty correlation id, or malformed metadata raises; a hard
    bridge/replay rejection, a digest/source mismatch, malformed evidence digests, or a BIST/live/order/
    scheduler/private token in a source id/metadata value yields REJECTED; missing replay result or ledger
    evidence yields INSUFFICIENT_EVIDENCE; needs-research propagates.
  - Deterministic: a canonical SHA-256 ``manifest_digest`` over the material fields; no wall-clock/random/
    IO. Frozen dataclass; ``paper_only=True`` and no order/route/venue/scheduler/store/engine field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.backtest_replay_admission import BacktestReplayAdmissionStatus
from crypto_core.validation.backtest_replay_bridge import BacktestReplayBridgeResult

_SCHEMA_VERSION = "replay-evidence-manifest.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Safely-detectable BIST markers and forbidden live/order/scheduler/private config tokens (word-bounded).
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"\b(?:private|order_router|auto_loop|shadow_live_execution|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class ReplayEvidenceManifestError(RuntimeError):
    """Raised when manifest inputs are malformed at the call level (wrong type / bad id / bad metadata)."""


class ReplayEvidenceManifestStatus(str, Enum):
    """Terminal readiness of the replay evidence manifest. Never an order/live action."""

    READY = "READY"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ReplayEvidenceManifest:
    """Deterministic, immutable record of the admitted replay evidence chain. PAPER ONLY."""

    schema_version: str
    status: ReplayEvidenceManifestStatus
    ready: bool
    strategy_id: str | None
    strategy_digest: str | None
    bundle_digest: str
    admission_digest: str
    bridge_digest: str
    replay_source_id: str
    historical_data_source_id: str
    replay_admission_status: str | None
    decision_ledger_digests: tuple[tuple[str, str], ...]
    evidence_digest_by_stage: tuple[tuple[str, str], ...]
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    manifest_digest: str
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


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("replay_evidence_manifest:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("replay_evidence_manifest:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise ReplayEvidenceManifestError("replay_evidence_manifest:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ReplayEvidenceManifestError("replay_evidence_manifest:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _digest_pairs(mapping: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(stage), str(digest)) for stage, digest in mapping.items()))


def build_replay_evidence_manifest(
    bridge_result: BacktestReplayBridgeResult,
    *,
    bundle_digest: str,
    admission_digest: str,
    replay_source_id: str,
    historical_data_source_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> ReplayEvidenceManifest:
    """Record the admitted bundle → admission → bridge → replay evidence chain as a deterministic manifest.

    ``bridge_result`` must be a ``BacktestReplayBridgeResult``. A wrong-typed result, an empty
    ``correlation_id``, or non ``Mapping[str, str]`` metadata raises ``ReplayEvidenceManifestError``. The
    manifest is READY only when the bridge/replay verdict is ACCEPTED, the supplied digests are canonical
    64-hex, the admission digest matches the bridge result, the replay source ids match the delegated
    replay result, and the ledger evidence digests are present and well-formed; every other outcome maps
    fail-closed to REJECTED / INSUFFICIENT_EVIDENCE / NEEDS_RESEARCH. Deterministic and immutable.
    """
    if not isinstance(bridge_result, BacktestReplayBridgeResult):
        raise ReplayEvidenceManifestError("replay_evidence_manifest:bridge_result_malformed")
    if not _is_non_empty_string(correlation_id):
        raise ReplayEvidenceManifestError("replay_evidence_manifest:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)

    replay = bridge_result.replay_admission_result

    hard: list[str] = []
    needs: list[str] = []
    insufficient: list[str] = []

    if not _is_sha256_hex(bundle_digest):
        hard.append("replay_evidence_manifest:bundle_digest_invalid")
    if not _is_sha256_hex(admission_digest):
        hard.append("replay_evidence_manifest:admission_digest_invalid")
    elif admission_digest != bridge_result.admission_digest:
        hard.append("replay_evidence_manifest:admission_digest_mismatch")
    if not _is_sha256_hex(bridge_result.bridge_digest):
        hard.append("replay_evidence_manifest:bridge_digest_invalid")

    if not _is_non_empty_string(replay_source_id):
        hard.append("replay_evidence_manifest:replay_source_id_invalid")
    if not _is_non_empty_string(historical_data_source_id):
        hard.append("replay_evidence_manifest:historical_data_source_id_invalid")
    hard.extend(_scope_violations(replay_source_id, historical_data_source_id, *(value for _, value in metadata_pairs)))

    if bridge_result.status is BacktestReplayAdmissionStatus.REJECTED:
        hard.append("replay_evidence_manifest:bridge_rejected")
        hard.extend(bridge_result.rejection_reasons)
    elif bridge_result.status is BacktestReplayAdmissionStatus.NEEDS_RESEARCH:
        needs.append("replay_evidence_manifest:bridge_needs_research")
        needs.extend(bridge_result.needs_research_reasons)
    elif bridge_result.status is BacktestReplayAdmissionStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("replay_evidence_manifest:bridge_insufficient_evidence")

    ledger_pairs: tuple[tuple[str, str], ...] = ()
    evidence_pairs: tuple[tuple[str, str], ...] = ()
    if replay is None:
        insufficient.append("replay_evidence_manifest:replay_admission_result_missing")
    else:
        if not replay.accepted and bridge_result.status is BacktestReplayAdmissionStatus.ACCEPTED:
            hard.append("replay_evidence_manifest:replay_result_not_accepted")
        if _is_non_empty_string(replay_source_id) and replay.replay_source_id != replay_source_id:
            hard.append("replay_evidence_manifest:replay_source_id_mismatch")
        if (
            _is_non_empty_string(historical_data_source_id)
            and replay.historical_data_source_id != historical_data_source_id
        ):
            hard.append("replay_evidence_manifest:historical_data_source_id_mismatch")

        ledger_pairs = _digest_pairs(replay.decision_ledger_digests)
        if not ledger_pairs:
            insufficient.append("replay_evidence_manifest:decision_ledger_digests_missing")
        elif any(not _is_sha256_hex(digest) for _, digest in ledger_pairs):
            hard.append("replay_evidence_manifest:decision_ledger_digest_malformed")

        evidence_pairs = _digest_pairs(replay.evidence_digest_by_stage)
        if evidence_pairs and any(not _is_sha256_hex(digest) for _, digest in evidence_pairs):
            hard.append("replay_evidence_manifest:evidence_digest_malformed")

    rejection_reasons = _sorted_unique(tuple(hard))
    needs_research_reasons = _sorted_unique(tuple(needs))
    insufficient_reasons = _sorted_unique(tuple(insufficient))

    if rejection_reasons:
        status = ReplayEvidenceManifestStatus.REJECTED
    elif insufficient_reasons:
        status = ReplayEvidenceManifestStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = ReplayEvidenceManifestStatus.NEEDS_RESEARCH
    elif (
        bridge_result.status is BacktestReplayAdmissionStatus.ACCEPTED
        and bridge_result.accepted
        and replay is not None
        and replay.accepted
        and ledger_pairs
    ):
        status = ReplayEvidenceManifestStatus.READY
    else:
        status = ReplayEvidenceManifestStatus.INSUFFICIENT_EVIDENCE

    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons
    return _assemble(
        status=status,
        bridge_result=bridge_result,
        bundle_digest=bundle_digest,
        admission_digest=admission_digest,
        replay_source_id=replay_source_id,
        historical_data_source_id=historical_data_source_id,
        decision_ledger_digests=ledger_pairs,
        evidence_digest_by_stage=evidence_pairs,
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
    )


def _assemble(
    *,
    status: ReplayEvidenceManifestStatus,
    bridge_result: BacktestReplayBridgeResult,
    bundle_digest: str,
    admission_digest: str,
    replay_source_id: str,
    historical_data_source_id: str,
    decision_ledger_digests: tuple[tuple[str, str], ...],
    evidence_digest_by_stage: tuple[tuple[str, str], ...],
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
) -> ReplayEvidenceManifest:
    ready = status is ReplayEvidenceManifestStatus.READY
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "ready": ready,
        "strategy_id": bridge_result.strategy_id,
        "strategy_digest": bridge_result.strategy_digest,
        "bundle_digest": bundle_digest,
        "admission_digest": admission_digest,
        "bridge_digest": bridge_result.bridge_digest,
        "replay_source_id": replay_source_id,
        "historical_data_source_id": historical_data_source_id,
        "replay_admission_status": bridge_result.replay_admission_status,
        "decision_ledger_digests": [list(pair) for pair in decision_ledger_digests],
        "evidence_digest_by_stage": [list(pair) for pair in evidence_digest_by_stage],
        "metadata": [list(pair) for pair in metadata],
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return ReplayEvidenceManifest(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        strategy_id=bridge_result.strategy_id,
        strategy_digest=bridge_result.strategy_digest,
        bundle_digest=bundle_digest,
        admission_digest=admission_digest,
        bridge_digest=bridge_result.bridge_digest,
        replay_source_id=replay_source_id,
        historical_data_source_id=historical_data_source_id,
        replay_admission_status=bridge_result.replay_admission_status,
        decision_ledger_digests=decision_ledger_digests,
        evidence_digest_by_stage=evidence_digest_by_stage,
        metadata=metadata,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        manifest_digest=_canonical_digest(payload),
    )


def replay_evidence_manifest_to_dict(manifest: ReplayEvidenceManifest) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a replay evidence manifest (deterministic shape)."""
    return {
        "schema_version": manifest.schema_version,
        "status": manifest.status.value,
        "ready": manifest.ready,
        "strategy_id": manifest.strategy_id,
        "strategy_digest": manifest.strategy_digest,
        "bundle_digest": manifest.bundle_digest,
        "admission_digest": manifest.admission_digest,
        "bridge_digest": manifest.bridge_digest,
        "replay_source_id": manifest.replay_source_id,
        "historical_data_source_id": manifest.historical_data_source_id,
        "replay_admission_status": manifest.replay_admission_status,
        "decision_ledger_digests": [list(pair) for pair in manifest.decision_ledger_digests],
        "evidence_digest_by_stage": [list(pair) for pair in manifest.evidence_digest_by_stage],
        "metadata": [list(pair) for pair in manifest.metadata],
        "rejection_reasons": list(manifest.rejection_reasons),
        "needs_research_reasons": list(manifest.needs_research_reasons),
        "correlation_id": manifest.correlation_id,
        "manifest_digest": manifest.manifest_digest,
        "paper_only": manifest.paper_only,
        "real_orders_enabled": manifest.real_orders_enabled,
        "real_money_enabled": manifest.real_money_enabled,
    }


__all__ = [
    "ReplayEvidenceManifest",
    "ReplayEvidenceManifestError",
    "ReplayEvidenceManifestStatus",
    "build_replay_evidence_manifest",
    "replay_evidence_manifest_to_dict",
]
