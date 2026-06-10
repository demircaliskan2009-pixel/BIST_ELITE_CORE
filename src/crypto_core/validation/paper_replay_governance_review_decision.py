"""Paper replay governance review decision — deterministic paper-only record of a human review verdict.

A small, deterministic, fail-closed contract that records a *caller-supplied* governance review decision
over a READY ``PaperReplayPromotionReadiness``, re-proving the readiness digest at the boundary. READY
means only: "the READY promotion-readiness record has a deterministic paper-only governance decision of
APPROVED_FOR_PAPER_REVIEW, supported by caller-supplied evidence/rationale digests." READY never means
sleeve admitted, runtime enabled, shadow/live allowed, connector ready, scheduler enabled, orders allowed,
storage persisted, or EvidenceStore written — this gate executes, admits, promotes, stores, schedules,
routes, and mutates nothing.

Design rules:
  - Boundary digest re-proof: the readiness digest is recomputed via the public
    ``paper_replay_promotion_readiness_to_dict`` serializer (excluding ``readiness_digest``) and a
    mismatch is rejected before READY — a stale/forged/tampered readiness cannot be decided on.
  - Record, don't decide for the human: the decision and the evidence/rationale digests are supplied by
    the caller; the gate validates their shape, the readiness paper-safety flags, and the carried chain
    digests, then propagates terminal status. No upstream validation is redone.
  - Fail closed: a wrong-typed readiness, empty correlation id, or malformed metadata raises; an unknown
    or REJECTED decision, a readiness rejection, a digest mismatch, a malformed id/digest, an unsafe
    readiness flag, or a BIST/live/private/order/scheduler token in an identity/metadata value yields
    REJECTED; needs-research and insufficient-evidence propagate from both readiness and decision.
  - Deterministic: a canonical SHA-256 ``governance_decision_digest``; no wall-clock/random/IO. Frozen
    dataclass; ``paper_only=True`` and no order/route/venue/scheduler/runtime/persistence/store/engine field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_replay_promotion_readiness import (
    PaperReplayPromotionReadiness,
    PaperReplayPromotionReadinessStatus,
    paper_replay_promotion_readiness_to_dict,
)

_SCHEMA_VERSION = "paper-replay-governance-review-decision.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Safely-detectable BIST markers and forbidden live/order/scheduler/private config tokens (word-bounded).
# A bare ``order``/``orders`` token is rejected while ``border``/``orderly``/``preorder`` are spared.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|auto_loop|shadow_live_execution|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class PaperReplayGovernanceReviewDecisionError(RuntimeError):
    """Raised when decision inputs are malformed at the call level (wrong type / bad metadata)."""


class PaperReplayGovernanceReviewDecisionStatus(str, Enum):
    """Terminal readiness of a governance review decision record. Never an execution action."""

    READY = "READY"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PaperReplayGovernanceDecision(str, Enum):
    """Caller-supplied governance review verdict. A paper-only review label, never a runtime action."""

    APPROVED_FOR_PAPER_REVIEW = "APPROVED_FOR_PAPER_REVIEW"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperReplayGovernanceReviewDecision:
    """Deterministic, immutable governance review decision record over a readiness. PAPER ONLY."""

    schema_version: str
    status: PaperReplayGovernanceReviewDecisionStatus
    ready: bool
    governance_decision_id: str
    decision: str
    reviewer_id: str
    readiness_id: str
    promotion_target: str
    readiness_status: str
    result_report_id: str
    run_plan_id: str
    replay_mode: str
    requested_replay_id: str
    operator_id: str
    strategy_id: str | None
    strategy_digest: str | None
    bundle_digest: str
    admission_digest: str
    bridge_digest: str
    manifest_digest: str
    intake_digest: str
    run_plan_digest: str
    result_report_digest: str
    replay_trace_digest: str
    metrics_digest: str
    decision_trace_digest: str
    readiness_digest: str
    replay_source_id: str
    historical_data_source_id: str
    review_evidence_digest: str
    rationale_digest: str
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    governance_decision_digest: str
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


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _safe_digest_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _safe_optional_value(value: object) -> str | None:
    # Preserve a valid ``str | None`` field; coerce any other (non-serializable) value to "" so a forged
    # readiness cannot raise during canonical JSON hashing.
    return value if (value is None or isinstance(value, str)) else ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_replay_governance_review_decision:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("paper_replay_governance_review_decision:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperReplayGovernanceReviewDecisionError("paper_replay_governance_review_decision:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperReplayGovernanceReviewDecisionError("paper_replay_governance_review_decision:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _coerce_decision(value: object) -> PaperReplayGovernanceDecision | None:
    if isinstance(value, PaperReplayGovernanceDecision):
        return value
    if isinstance(value, str):
        try:
            return PaperReplayGovernanceDecision(value)
        except ValueError:
            return None
    return None


def _coerce_readiness_status(value: object) -> PaperReplayPromotionReadinessStatus | None:
    if isinstance(value, PaperReplayPromotionReadinessStatus):
        return value
    if isinstance(value, str):
        try:
            return PaperReplayPromotionReadinessStatus(value)
        except ValueError:
            return None
    return None


def _expected_readiness_digest(readiness: PaperReplayPromotionReadiness) -> str | None:
    try:
        payload = paper_replay_promotion_readiness_to_dict(readiness)
        payload.pop("readiness_digest", None)
        return _canonical_digest(payload)
    except (AttributeError, TypeError, ValueError):
        # A forged readiness carrying a non-string/non-serializable digest cannot re-prove: treat the
        # boundary digest as unresolvable (mismatch) rather than raising during canonical JSON hashing.
        return None


def build_paper_replay_governance_review_decision(
    readiness: PaperReplayPromotionReadiness,
    *,
    governance_decision_id: str,
    decision: PaperReplayGovernanceDecision | str,
    reviewer_id: str,
    review_evidence_digest: str,
    rationale_digest: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperReplayGovernanceReviewDecision:
    """Record a caller-supplied governance review decision over a READY ``PaperReplayPromotionReadiness``.

    ``readiness`` must be a ``PaperReplayPromotionReadiness``; a wrong-typed readiness or non
    ``Mapping[str, str]`` metadata raises ``PaperReplayGovernanceReviewDecisionError``. The record is
    READY only when the readiness is READY + ready and paper-safe, its ``readiness_digest`` re-proves via
    the public serializer, every carried chain digest and the caller-supplied evidence/rationale digests
    are canonical 64-hex, all ids are non-empty and token-clean, and the decision is
    APPROVED_FOR_PAPER_REVIEW; every other outcome maps fail-closed to REJECTED / INSUFFICIENT_EVIDENCE /
    NEEDS_RESEARCH. READY records a review label only — it never admits, promotes, persists, schedules,
    or enables any runtime/shadow/live/order behavior.
    """
    if not isinstance(readiness, PaperReplayPromotionReadiness):
        raise PaperReplayGovernanceReviewDecisionError("paper_replay_governance_review_decision:readiness_malformed")
    metadata_pairs = _normalize_metadata(metadata)

    resolved_decision = _coerce_decision(decision)
    decision_value = resolved_decision.value if resolved_decision is not None else _string_value(decision)
    readiness_status = _coerce_readiness_status(readiness.status)
    readiness_status_value = readiness_status.value if readiness_status is not None else _string_value(readiness.status)

    hard: list[str] = []
    needs: list[str] = []
    insufficient: list[str] = []

    if not _is_non_empty_string(governance_decision_id):
        hard.append("paper_replay_governance_review_decision:governance_decision_id_invalid")
    if not _is_non_empty_string(reviewer_id):
        hard.append("paper_replay_governance_review_decision:reviewer_id_invalid")
    if not _is_non_empty_string(correlation_id):
        hard.append("paper_replay_governance_review_decision:correlation_id_invalid")
    if resolved_decision is None:
        hard.append("paper_replay_governance_review_decision:decision_unknown")
    if readiness_status is None:
        hard.append("paper_replay_governance_review_decision:readiness_status_unknown")

    if not _is_non_empty_string(readiness.readiness_id):
        hard.append("paper_replay_governance_review_decision:readiness_id_invalid")
    if not _is_non_empty_string(readiness.promotion_target):
        hard.append("paper_replay_governance_review_decision:promotion_target_invalid")
    if not _is_non_empty_string(readiness.result_report_id):
        hard.append("paper_replay_governance_review_decision:result_report_id_invalid")
    if not _is_non_empty_string(readiness.run_plan_id):
        hard.append("paper_replay_governance_review_decision:run_plan_id_invalid")
    if not _is_non_empty_string(readiness.requested_replay_id):
        hard.append("paper_replay_governance_review_decision:requested_replay_id_invalid")
    if not _is_non_empty_string(readiness.operator_id):
        hard.append("paper_replay_governance_review_decision:operator_id_invalid")
    if not _is_non_empty_string(readiness.replay_source_id):
        hard.append("paper_replay_governance_review_decision:replay_source_id_invalid")
    if not _is_non_empty_string(readiness.historical_data_source_id):
        hard.append("paper_replay_governance_review_decision:historical_data_source_id_invalid")

    hard.extend(
        _scope_violations(
            governance_decision_id,
            reviewer_id,
            correlation_id,
            decision_value,
            readiness.readiness_id,
            readiness.promotion_target,
            readiness.reviewer_id,
            readiness.result_report_id,
            readiness.run_plan_id,
            readiness.replay_mode,
            readiness.requested_replay_id,
            readiness.operator_id,
            readiness.replay_source_id,
            readiness.historical_data_source_id,
            *(value for _, value in metadata_pairs),
        )
    )

    for name, digest in (
        ("bundle_digest", readiness.bundle_digest),
        ("admission_digest", readiness.admission_digest),
        ("bridge_digest", readiness.bridge_digest),
        ("manifest_digest", readiness.manifest_digest),
        ("intake_digest", readiness.intake_digest),
        ("run_plan_digest", readiness.run_plan_digest),
        ("result_report_digest", readiness.result_report_digest),
        ("readiness_digest", readiness.readiness_digest),
        ("replay_trace_digest", readiness.replay_trace_digest),
        ("metrics_digest", readiness.metrics_digest),
        ("decision_trace_digest", readiness.decision_trace_digest),
        ("review_evidence_digest", review_evidence_digest),
        ("rationale_digest", rationale_digest),
    ):
        if not _is_sha256_hex(digest):
            hard.append(f"paper_replay_governance_review_decision:{name}_invalid")

    if readiness.paper_only is not True:
        hard.append("paper_replay_governance_review_decision:readiness_non_paper")
    if readiness.real_orders_enabled is not False:
        hard.append("paper_replay_governance_review_decision:readiness_real_orders_enabled")
    if readiness.real_money_enabled is not False:
        hard.append("paper_replay_governance_review_decision:readiness_real_money_enabled")

    # Boundary digest re-proof: a stale/forged/tampered readiness must not be decided on.
    if _is_sha256_hex(readiness.readiness_digest):
        expected = _expected_readiness_digest(readiness)
        if readiness.readiness_digest != expected:
            hard.append("paper_replay_governance_review_decision:readiness_digest_mismatch")

    if readiness_status is PaperReplayPromotionReadinessStatus.REJECTED:
        hard.append("paper_replay_governance_review_decision:readiness_rejected")
        hard.extend(readiness.rejection_reasons)
    elif readiness_status is PaperReplayPromotionReadinessStatus.NEEDS_RESEARCH:
        needs.append("paper_replay_governance_review_decision:readiness_needs_research")
        needs.extend(readiness.needs_research_reasons)
    elif readiness_status is PaperReplayPromotionReadinessStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_governance_review_decision:readiness_insufficient_evidence")
    elif readiness_status is PaperReplayPromotionReadinessStatus.READY and readiness.ready is not True:
        hard.append("paper_replay_governance_review_decision:readiness_ready_mismatch")

    if resolved_decision is PaperReplayGovernanceDecision.REJECTED:
        hard.append("paper_replay_governance_review_decision:decision_rejected")
    elif resolved_decision is PaperReplayGovernanceDecision.NEEDS_RESEARCH:
        needs.append("paper_replay_governance_review_decision:decision_needs_research")
    elif resolved_decision is PaperReplayGovernanceDecision.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_governance_review_decision:decision_insufficient_evidence")

    rejection_reasons = _sorted_unique(tuple(hard))
    needs_research_reasons = _sorted_unique(tuple(needs))
    insufficient_reasons = _sorted_unique(tuple(insufficient))

    if rejection_reasons:
        status = PaperReplayGovernanceReviewDecisionStatus.REJECTED
    elif insufficient_reasons:
        status = PaperReplayGovernanceReviewDecisionStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = PaperReplayGovernanceReviewDecisionStatus.NEEDS_RESEARCH
    elif (
        readiness_status is PaperReplayPromotionReadinessStatus.READY
        and readiness.ready is True
        and resolved_decision is PaperReplayGovernanceDecision.APPROVED_FOR_PAPER_REVIEW
    ):
        status = PaperReplayGovernanceReviewDecisionStatus.READY
    else:
        status = PaperReplayGovernanceReviewDecisionStatus.INSUFFICIENT_EVIDENCE

    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons
    return _assemble(
        status=status,
        readiness=readiness,
        governance_decision_id=_string_value(governance_decision_id),
        decision_value=decision_value,
        reviewer_id=_string_value(reviewer_id),
        review_evidence_digest=_safe_digest_value(review_evidence_digest),
        rationale_digest=_safe_digest_value(rationale_digest),
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=_string_value(correlation_id),
        readiness_status_value=readiness_status_value,
    )


def _assemble(
    *,
    status: PaperReplayGovernanceReviewDecisionStatus,
    readiness: PaperReplayPromotionReadiness,
    governance_decision_id: str,
    decision_value: str,
    reviewer_id: str,
    review_evidence_digest: str,
    rationale_digest: str,
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
    readiness_status_value: str,
) -> PaperReplayGovernanceReviewDecision:
    ready = status is PaperReplayGovernanceReviewDecisionStatus.READY
    # Coerce carried digest fields so a forged readiness with a non-string/non-serializable digest cannot
    # raise during canonical JSON hashing; the corresponding ``*_invalid`` reason is already recorded.
    strategy_digest = _safe_optional_value(readiness.strategy_digest)
    bundle_digest = _safe_digest_value(readiness.bundle_digest)
    admission_digest = _safe_digest_value(readiness.admission_digest)
    bridge_digest = _safe_digest_value(readiness.bridge_digest)
    manifest_digest = _safe_digest_value(readiness.manifest_digest)
    intake_digest = _safe_digest_value(readiness.intake_digest)
    run_plan_digest = _safe_digest_value(readiness.run_plan_digest)
    result_report_digest = _safe_digest_value(readiness.result_report_digest)
    replay_trace_digest = _safe_digest_value(readiness.replay_trace_digest)
    metrics_digest = _safe_digest_value(readiness.metrics_digest)
    decision_trace_digest = _safe_digest_value(readiness.decision_trace_digest)
    readiness_digest = _safe_digest_value(readiness.readiness_digest)
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "ready": ready,
        "governance_decision_id": governance_decision_id,
        "decision": decision_value,
        "reviewer_id": reviewer_id,
        "readiness_id": readiness.readiness_id,
        "promotion_target": readiness.promotion_target,
        "readiness_status": readiness_status_value,
        "result_report_id": readiness.result_report_id,
        "run_plan_id": readiness.run_plan_id,
        "replay_mode": readiness.replay_mode,
        "requested_replay_id": readiness.requested_replay_id,
        "operator_id": readiness.operator_id,
        "strategy_id": readiness.strategy_id,
        "strategy_digest": strategy_digest,
        "bundle_digest": bundle_digest,
        "admission_digest": admission_digest,
        "bridge_digest": bridge_digest,
        "manifest_digest": manifest_digest,
        "intake_digest": intake_digest,
        "run_plan_digest": run_plan_digest,
        "result_report_digest": result_report_digest,
        "replay_trace_digest": replay_trace_digest,
        "metrics_digest": metrics_digest,
        "decision_trace_digest": decision_trace_digest,
        "readiness_digest": readiness_digest,
        "replay_source_id": readiness.replay_source_id,
        "historical_data_source_id": readiness.historical_data_source_id,
        "review_evidence_digest": review_evidence_digest,
        "rationale_digest": rationale_digest,
        "metadata": [list(pair) for pair in metadata],
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return PaperReplayGovernanceReviewDecision(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        governance_decision_id=governance_decision_id,
        decision=decision_value,
        reviewer_id=reviewer_id,
        readiness_id=readiness.readiness_id,
        promotion_target=readiness.promotion_target,
        readiness_status=readiness_status_value,
        result_report_id=readiness.result_report_id,
        run_plan_id=readiness.run_plan_id,
        replay_mode=readiness.replay_mode,
        requested_replay_id=readiness.requested_replay_id,
        operator_id=readiness.operator_id,
        strategy_id=readiness.strategy_id,
        strategy_digest=strategy_digest,
        bundle_digest=bundle_digest,
        admission_digest=admission_digest,
        bridge_digest=bridge_digest,
        manifest_digest=manifest_digest,
        intake_digest=intake_digest,
        run_plan_digest=run_plan_digest,
        result_report_digest=result_report_digest,
        replay_trace_digest=replay_trace_digest,
        metrics_digest=metrics_digest,
        decision_trace_digest=decision_trace_digest,
        readiness_digest=readiness_digest,
        replay_source_id=readiness.replay_source_id,
        historical_data_source_id=readiness.historical_data_source_id,
        review_evidence_digest=review_evidence_digest,
        rationale_digest=rationale_digest,
        metadata=metadata,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        governance_decision_digest=_canonical_digest(payload),
    )


def paper_replay_governance_review_decision_to_dict(
    record: PaperReplayGovernanceReviewDecision,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a governance review decision record (deterministic shape)."""
    return {
        "schema_version": record.schema_version,
        "status": record.status.value,
        "ready": record.ready,
        "governance_decision_id": record.governance_decision_id,
        "decision": record.decision,
        "reviewer_id": record.reviewer_id,
        "readiness_id": record.readiness_id,
        "promotion_target": record.promotion_target,
        "readiness_status": record.readiness_status,
        "result_report_id": record.result_report_id,
        "run_plan_id": record.run_plan_id,
        "replay_mode": record.replay_mode,
        "requested_replay_id": record.requested_replay_id,
        "operator_id": record.operator_id,
        "strategy_id": record.strategy_id,
        "strategy_digest": record.strategy_digest,
        "bundle_digest": record.bundle_digest,
        "admission_digest": record.admission_digest,
        "bridge_digest": record.bridge_digest,
        "manifest_digest": record.manifest_digest,
        "intake_digest": record.intake_digest,
        "run_plan_digest": record.run_plan_digest,
        "result_report_digest": record.result_report_digest,
        "replay_trace_digest": record.replay_trace_digest,
        "metrics_digest": record.metrics_digest,
        "decision_trace_digest": record.decision_trace_digest,
        "readiness_digest": record.readiness_digest,
        "replay_source_id": record.replay_source_id,
        "historical_data_source_id": record.historical_data_source_id,
        "review_evidence_digest": record.review_evidence_digest,
        "rationale_digest": record.rationale_digest,
        "metadata": [list(pair) for pair in record.metadata],
        "rejection_reasons": list(record.rejection_reasons),
        "needs_research_reasons": list(record.needs_research_reasons),
        "correlation_id": record.correlation_id,
        "governance_decision_digest": record.governance_decision_digest,
        "paper_only": record.paper_only,
        "real_orders_enabled": record.real_orders_enabled,
        "real_money_enabled": record.real_money_enabled,
    }


__all__ = [
    "PaperReplayGovernanceDecision",
    "PaperReplayGovernanceReviewDecision",
    "PaperReplayGovernanceReviewDecisionError",
    "PaperReplayGovernanceReviewDecisionStatus",
    "build_paper_replay_governance_review_decision",
    "paper_replay_governance_review_decision_to_dict",
]
