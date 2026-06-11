"""Paper sleeve admission review readiness — deterministic paper-only review-readiness record.

A small, deterministic, fail-closed contract that consumes a READY ``PaperReplayGovernanceReviewDecision``
carrying ``APPROVED_FOR_PAPER_REVIEW`` and records readiness for a *future human* paper-sleeve admission
review. READY means only: "an approved paper governance review decision is ready to be considered by a
future human paper-sleeve admission review process." READY never means sleeve admitted, sleeve active,
allocation allowed, budget assigned, order routing allowed, runtime enabled, scheduler enabled, connector
ready, shadow/live allowed, EvidenceStore written, or persistence performed — this gate admits, allocates,
persists, schedules, routes, and mutates nothing.

Design rules:
  - Boundary digest re-proof: the upstream digest is recomputed via the public
    ``paper_replay_governance_review_decision_to_dict`` serializer (excluding
    ``governance_decision_digest``) and a mismatch is rejected before READY. If a forged upstream record
    carries non-serializable fields, the re-proof resolves to mismatch — never a TypeError.
  - Record, don't admit: the action and the evidence/rationale digests are supplied by the caller; the
    gate validates their shape, the upstream paper-safety flags and approval, and the carried chain
    digests, then propagates terminal status. No upstream validation is redone.
  - Fail closed: a wrong-typed upstream record or malformed metadata raises; an unknown/REJECT action,
    an upstream rejection or missing approval, a digest mismatch, a malformed id/digest, an unsafe paper
    flag, or a BIST/live/shadow/private/order/scheduler token in an identity/metadata value yields
    REJECTED; needs-research and insufficient-evidence propagate from both upstream and action.
  - Deterministic: a canonical SHA-256 ``review_readiness_digest``; no wall-clock/random/IO. Frozen
    dataclass; ``paper_only=True`` and no order/route/venue/scheduler/runtime/persistence/store/engine/
    admitted/allocation field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_replay_governance_review_decision import (
    PaperReplayGovernanceDecision,
    PaperReplayGovernanceReviewDecision,
    PaperReplayGovernanceReviewDecisionStatus,
    paper_replay_governance_review_decision_to_dict,
)

_SCHEMA_VERSION = "paper-sleeve-admission-review-readiness.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Safely-detectable BIST markers and forbidden live/shadow/order/scheduler/private config tokens
# (word-bounded). A bare ``order``/``orders`` token is rejected while ``border``/``orderly``/``preorder``
# are spared.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|auto_loop|shadow|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class PaperSleeveAdmissionReviewReadinessError(RuntimeError):
    """Raised when readiness inputs are malformed at the call level (wrong type / bad metadata)."""


class PaperSleeveAdmissionReviewReadinessStatus(str, Enum):
    """Terminal readiness of a paper-sleeve admission review-readiness record. Never an execution action."""

    READY = "READY"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PaperSleeveAdmissionReviewAction(str, Enum):
    """Caller-supplied review-readiness action. A paper-only review label, never a runtime action."""

    REQUEST_PAPER_SLEEVE_ADMISSION_REVIEW = "REQUEST_PAPER_SLEEVE_ADMISSION_REVIEW"
    REJECT = "REJECT"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperSleeveAdmissionReviewReadiness:
    """Deterministic, immutable paper-sleeve admission review-readiness record. PAPER ONLY."""

    schema_version: str
    status: PaperSleeveAdmissionReviewReadinessStatus
    ready: bool
    review_readiness_id: str
    admission_case_id: str
    sleeve_candidate_id: str
    action: str
    reviewer_id: str
    governance_decision_id: str
    governance_decision: str
    governance_status: str
    governance_reviewer_id: str
    readiness_id: str
    promotion_target: str
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
    readiness_digest: str
    replay_trace_digest: str
    metrics_digest: str
    decision_trace_digest: str
    governance_review_evidence_digest: str
    governance_rationale_digest: str
    governance_decision_digest: str
    replay_source_id: str
    historical_data_source_id: str
    review_evidence_digest: str
    rationale_digest: str
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    review_readiness_digest: str
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
    # upstream record cannot raise during canonical JSON hashing.
    return value if (value is None or isinstance(value, str)) else ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_sleeve_admission_review_readiness:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("paper_sleeve_admission_review_readiness:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSleeveAdmissionReviewReadinessError("paper_sleeve_admission_review_readiness:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSleeveAdmissionReviewReadinessError("paper_sleeve_admission_review_readiness:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _coerce_action(value: object) -> PaperSleeveAdmissionReviewAction | None:
    if isinstance(value, PaperSleeveAdmissionReviewAction):
        return value
    if isinstance(value, str):
        try:
            return PaperSleeveAdmissionReviewAction(value)
        except ValueError:
            return None
    return None


def _coerce_governance_status(value: object) -> PaperReplayGovernanceReviewDecisionStatus | None:
    if isinstance(value, PaperReplayGovernanceReviewDecisionStatus):
        return value
    if isinstance(value, str):
        try:
            return PaperReplayGovernanceReviewDecisionStatus(value)
        except ValueError:
            return None
    return None


def _expected_governance_decision_digest(record: PaperReplayGovernanceReviewDecision) -> str | None:
    try:
        payload = paper_replay_governance_review_decision_to_dict(record)
        payload.pop("governance_decision_digest", None)
        return _canonical_digest(payload)
    except (AttributeError, TypeError, ValueError):
        # A forged upstream record carrying a non-serializable field cannot re-prove: treat the boundary
        # digest as unresolvable (mismatch) rather than raising during canonical JSON hashing.
        return None


def build_paper_sleeve_admission_review_readiness(
    governance_decision: PaperReplayGovernanceReviewDecision,
    *,
    review_readiness_id: str,
    admission_case_id: str,
    sleeve_candidate_id: str,
    reviewer_id: str,
    action: PaperSleeveAdmissionReviewAction | str,
    review_evidence_digest: str,
    rationale_digest: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSleeveAdmissionReviewReadiness:
    """Record paper-sleeve admission review readiness over an approved governance review decision.

    ``governance_decision`` must be a ``PaperReplayGovernanceReviewDecision``; a wrong-typed record or
    non ``Mapping[str, str]`` metadata raises ``PaperSleeveAdmissionReviewReadinessError``. The record is
    READY only when the upstream record is READY + ready + paper-safe with the decision
    APPROVED_FOR_PAPER_REVIEW, its ``governance_decision_digest`` re-proves via the public serializer,
    every carried chain digest and the caller-supplied evidence/rationale digests are canonical 64-hex,
    all ids are non-empty and token-clean, and the action is REQUEST_PAPER_SLEEVE_ADMISSION_REVIEW; every
    other outcome maps fail-closed to REJECTED / INSUFFICIENT_EVIDENCE / NEEDS_RESEARCH. READY records a
    review-readiness label only — it never admits a sleeve, allocates budget, persists evidence,
    schedules work, or enables any runtime/shadow/live/order behavior.
    """
    if not isinstance(governance_decision, PaperReplayGovernanceReviewDecision):
        raise PaperSleeveAdmissionReviewReadinessError(
            "paper_sleeve_admission_review_readiness:governance_decision_malformed"
        )
    metadata_pairs = _normalize_metadata(metadata)

    resolved_action = _coerce_action(action)
    action_value = resolved_action.value if resolved_action is not None else _string_value(action)
    governance_status = _coerce_governance_status(governance_decision.status)
    governance_status_value = (
        governance_status.value if governance_status is not None else _string_value(governance_decision.status)
    )
    decision_value = _string_value(governance_decision.decision)
    approved = decision_value == PaperReplayGovernanceDecision.APPROVED_FOR_PAPER_REVIEW.value

    hard: list[str] = []
    needs: list[str] = []
    insufficient: list[str] = []

    if not _is_non_empty_string(review_readiness_id):
        hard.append("paper_sleeve_admission_review_readiness:review_readiness_id_invalid")
    if not _is_non_empty_string(admission_case_id):
        hard.append("paper_sleeve_admission_review_readiness:admission_case_id_invalid")
    if not _is_non_empty_string(sleeve_candidate_id):
        hard.append("paper_sleeve_admission_review_readiness:sleeve_candidate_id_invalid")
    if not _is_non_empty_string(reviewer_id):
        hard.append("paper_sleeve_admission_review_readiness:reviewer_id_invalid")
    if not _is_non_empty_string(correlation_id):
        hard.append("paper_sleeve_admission_review_readiness:correlation_id_invalid")
    if resolved_action is None:
        hard.append("paper_sleeve_admission_review_readiness:action_unknown")
    if governance_status is None:
        hard.append("paper_sleeve_admission_review_readiness:governance_status_unknown")

    if not _is_non_empty_string(governance_decision.governance_decision_id):
        hard.append("paper_sleeve_admission_review_readiness:governance_decision_id_invalid")
    if not _is_non_empty_string(governance_decision.readiness_id):
        hard.append("paper_sleeve_admission_review_readiness:readiness_id_invalid")
    if not _is_non_empty_string(governance_decision.promotion_target):
        hard.append("paper_sleeve_admission_review_readiness:promotion_target_invalid")
    if not _is_non_empty_string(governance_decision.result_report_id):
        hard.append("paper_sleeve_admission_review_readiness:result_report_id_invalid")
    if not _is_non_empty_string(governance_decision.run_plan_id):
        hard.append("paper_sleeve_admission_review_readiness:run_plan_id_invalid")
    if not _is_non_empty_string(governance_decision.requested_replay_id):
        hard.append("paper_sleeve_admission_review_readiness:requested_replay_id_invalid")
    if not _is_non_empty_string(governance_decision.operator_id):
        hard.append("paper_sleeve_admission_review_readiness:operator_id_invalid")
    if not _is_non_empty_string(governance_decision.replay_source_id):
        hard.append("paper_sleeve_admission_review_readiness:replay_source_id_invalid")
    if not _is_non_empty_string(governance_decision.historical_data_source_id):
        hard.append("paper_sleeve_admission_review_readiness:historical_data_source_id_invalid")

    hard.extend(
        _scope_violations(
            review_readiness_id,
            admission_case_id,
            sleeve_candidate_id,
            reviewer_id,
            correlation_id,
            action_value,
            decision_value,
            governance_decision.governance_decision_id,
            governance_decision.reviewer_id,
            governance_decision.readiness_id,
            governance_decision.promotion_target,
            governance_decision.result_report_id,
            governance_decision.run_plan_id,
            governance_decision.replay_mode,
            governance_decision.requested_replay_id,
            governance_decision.operator_id,
            governance_decision.replay_source_id,
            governance_decision.historical_data_source_id,
            *(value for _, value in metadata_pairs),
        )
    )

    for name, digest in (
        ("bundle_digest", governance_decision.bundle_digest),
        ("admission_digest", governance_decision.admission_digest),
        ("bridge_digest", governance_decision.bridge_digest),
        ("manifest_digest", governance_decision.manifest_digest),
        ("intake_digest", governance_decision.intake_digest),
        ("run_plan_digest", governance_decision.run_plan_digest),
        ("result_report_digest", governance_decision.result_report_digest),
        ("readiness_digest", governance_decision.readiness_digest),
        ("replay_trace_digest", governance_decision.replay_trace_digest),
        ("metrics_digest", governance_decision.metrics_digest),
        ("decision_trace_digest", governance_decision.decision_trace_digest),
        ("governance_review_evidence_digest", governance_decision.review_evidence_digest),
        ("governance_rationale_digest", governance_decision.rationale_digest),
        ("governance_decision_digest", governance_decision.governance_decision_digest),
        ("review_evidence_digest", review_evidence_digest),
        ("rationale_digest", rationale_digest),
    ):
        if not _is_sha256_hex(digest):
            hard.append(f"paper_sleeve_admission_review_readiness:{name}_invalid")

    if governance_decision.paper_only is not True:
        hard.append("paper_sleeve_admission_review_readiness:governance_non_paper")
    if governance_decision.real_orders_enabled is not False:
        hard.append("paper_sleeve_admission_review_readiness:governance_real_orders_enabled")
    if governance_decision.real_money_enabled is not False:
        hard.append("paper_sleeve_admission_review_readiness:governance_real_money_enabled")

    # Boundary digest re-proof: a stale/forged/tampered governance decision must not reach review readiness.
    if _is_sha256_hex(governance_decision.governance_decision_digest):
        expected = _expected_governance_decision_digest(governance_decision)
        if governance_decision.governance_decision_digest != expected:
            hard.append("paper_sleeve_admission_review_readiness:governance_decision_digest_mismatch")

    if governance_status is PaperReplayGovernanceReviewDecisionStatus.REJECTED:
        hard.append("paper_sleeve_admission_review_readiness:governance_rejected")
        hard.extend(governance_decision.rejection_reasons)
    elif governance_status is PaperReplayGovernanceReviewDecisionStatus.NEEDS_RESEARCH:
        needs.append("paper_sleeve_admission_review_readiness:governance_needs_research")
        needs.extend(governance_decision.needs_research_reasons)
    elif governance_status is PaperReplayGovernanceReviewDecisionStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_sleeve_admission_review_readiness:governance_insufficient_evidence")
    elif governance_status is PaperReplayGovernanceReviewDecisionStatus.READY:
        if governance_decision.ready is not True:
            hard.append("paper_sleeve_admission_review_readiness:governance_ready_mismatch")
        if not approved:
            hard.append("paper_sleeve_admission_review_readiness:governance_decision_not_approved")

    if resolved_action is PaperSleeveAdmissionReviewAction.REJECT:
        hard.append("paper_sleeve_admission_review_readiness:action_rejected")
    elif resolved_action is PaperSleeveAdmissionReviewAction.NEEDS_RESEARCH:
        needs.append("paper_sleeve_admission_review_readiness:action_needs_research")
    elif resolved_action is PaperSleeveAdmissionReviewAction.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_sleeve_admission_review_readiness:action_insufficient_evidence")

    rejection_reasons = _sorted_unique(tuple(hard))
    needs_research_reasons = _sorted_unique(tuple(needs))
    insufficient_reasons = _sorted_unique(tuple(insufficient))

    if rejection_reasons:
        status = PaperSleeveAdmissionReviewReadinessStatus.REJECTED
    elif insufficient_reasons:
        status = PaperSleeveAdmissionReviewReadinessStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = PaperSleeveAdmissionReviewReadinessStatus.NEEDS_RESEARCH
    elif (
        governance_status is PaperReplayGovernanceReviewDecisionStatus.READY
        and governance_decision.ready is True
        and approved
        and resolved_action is PaperSleeveAdmissionReviewAction.REQUEST_PAPER_SLEEVE_ADMISSION_REVIEW
    ):
        status = PaperSleeveAdmissionReviewReadinessStatus.READY
    else:
        status = PaperSleeveAdmissionReviewReadinessStatus.INSUFFICIENT_EVIDENCE

    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons
    return _assemble(
        status=status,
        governance_decision=governance_decision,
        review_readiness_id=_string_value(review_readiness_id),
        admission_case_id=_string_value(admission_case_id),
        sleeve_candidate_id=_string_value(sleeve_candidate_id),
        action_value=action_value,
        reviewer_id=_string_value(reviewer_id),
        review_evidence_digest=_safe_digest_value(review_evidence_digest),
        rationale_digest=_safe_digest_value(rationale_digest),
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=_string_value(correlation_id),
        governance_status_value=governance_status_value,
        decision_value=decision_value,
    )


def _assemble(
    *,
    status: PaperSleeveAdmissionReviewReadinessStatus,
    governance_decision: PaperReplayGovernanceReviewDecision,
    review_readiness_id: str,
    admission_case_id: str,
    sleeve_candidate_id: str,
    action_value: str,
    reviewer_id: str,
    review_evidence_digest: str,
    rationale_digest: str,
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
    governance_status_value: str,
    decision_value: str,
) -> PaperSleeveAdmissionReviewReadiness:
    ready = status is PaperSleeveAdmissionReviewReadinessStatus.READY
    # Coerce carried digest fields so a forged upstream record with a non-string/non-serializable digest
    # cannot raise during canonical JSON hashing; the corresponding ``*_invalid`` reason is already recorded.
    strategy_digest = _safe_optional_value(governance_decision.strategy_digest)
    bundle_digest = _safe_digest_value(governance_decision.bundle_digest)
    admission_digest = _safe_digest_value(governance_decision.admission_digest)
    bridge_digest = _safe_digest_value(governance_decision.bridge_digest)
    manifest_digest = _safe_digest_value(governance_decision.manifest_digest)
    intake_digest = _safe_digest_value(governance_decision.intake_digest)
    run_plan_digest = _safe_digest_value(governance_decision.run_plan_digest)
    result_report_digest = _safe_digest_value(governance_decision.result_report_digest)
    readiness_digest = _safe_digest_value(governance_decision.readiness_digest)
    replay_trace_digest = _safe_digest_value(governance_decision.replay_trace_digest)
    metrics_digest = _safe_digest_value(governance_decision.metrics_digest)
    decision_trace_digest = _safe_digest_value(governance_decision.decision_trace_digest)
    governance_review_evidence_digest = _safe_digest_value(governance_decision.review_evidence_digest)
    governance_rationale_digest = _safe_digest_value(governance_decision.rationale_digest)
    governance_decision_digest = _safe_digest_value(governance_decision.governance_decision_digest)
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "ready": ready,
        "review_readiness_id": review_readiness_id,
        "admission_case_id": admission_case_id,
        "sleeve_candidate_id": sleeve_candidate_id,
        "action": action_value,
        "reviewer_id": reviewer_id,
        "governance_decision_id": governance_decision.governance_decision_id,
        "governance_decision": decision_value,
        "governance_status": governance_status_value,
        "governance_reviewer_id": governance_decision.reviewer_id,
        "readiness_id": governance_decision.readiness_id,
        "promotion_target": governance_decision.promotion_target,
        "result_report_id": governance_decision.result_report_id,
        "run_plan_id": governance_decision.run_plan_id,
        "replay_mode": governance_decision.replay_mode,
        "requested_replay_id": governance_decision.requested_replay_id,
        "operator_id": governance_decision.operator_id,
        "strategy_id": governance_decision.strategy_id,
        "strategy_digest": strategy_digest,
        "bundle_digest": bundle_digest,
        "admission_digest": admission_digest,
        "bridge_digest": bridge_digest,
        "manifest_digest": manifest_digest,
        "intake_digest": intake_digest,
        "run_plan_digest": run_plan_digest,
        "result_report_digest": result_report_digest,
        "readiness_digest": readiness_digest,
        "replay_trace_digest": replay_trace_digest,
        "metrics_digest": metrics_digest,
        "decision_trace_digest": decision_trace_digest,
        "governance_review_evidence_digest": governance_review_evidence_digest,
        "governance_rationale_digest": governance_rationale_digest,
        "governance_decision_digest": governance_decision_digest,
        "replay_source_id": governance_decision.replay_source_id,
        "historical_data_source_id": governance_decision.historical_data_source_id,
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
    return PaperSleeveAdmissionReviewReadiness(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        review_readiness_id=review_readiness_id,
        admission_case_id=admission_case_id,
        sleeve_candidate_id=sleeve_candidate_id,
        action=action_value,
        reviewer_id=reviewer_id,
        governance_decision_id=governance_decision.governance_decision_id,
        governance_decision=decision_value,
        governance_status=governance_status_value,
        governance_reviewer_id=governance_decision.reviewer_id,
        readiness_id=governance_decision.readiness_id,
        promotion_target=governance_decision.promotion_target,
        result_report_id=governance_decision.result_report_id,
        run_plan_id=governance_decision.run_plan_id,
        replay_mode=governance_decision.replay_mode,
        requested_replay_id=governance_decision.requested_replay_id,
        operator_id=governance_decision.operator_id,
        strategy_id=governance_decision.strategy_id,
        strategy_digest=strategy_digest,
        bundle_digest=bundle_digest,
        admission_digest=admission_digest,
        bridge_digest=bridge_digest,
        manifest_digest=manifest_digest,
        intake_digest=intake_digest,
        run_plan_digest=run_plan_digest,
        result_report_digest=result_report_digest,
        readiness_digest=readiness_digest,
        replay_trace_digest=replay_trace_digest,
        metrics_digest=metrics_digest,
        decision_trace_digest=decision_trace_digest,
        governance_review_evidence_digest=governance_review_evidence_digest,
        governance_rationale_digest=governance_rationale_digest,
        governance_decision_digest=governance_decision_digest,
        replay_source_id=governance_decision.replay_source_id,
        historical_data_source_id=governance_decision.historical_data_source_id,
        review_evidence_digest=review_evidence_digest,
        rationale_digest=rationale_digest,
        metadata=metadata,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        review_readiness_digest=_canonical_digest(payload),
    )


def paper_sleeve_admission_review_readiness_to_dict(
    record: PaperSleeveAdmissionReviewReadiness,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper-sleeve admission review-readiness record."""
    return {
        "schema_version": record.schema_version,
        "status": record.status.value,
        "ready": record.ready,
        "review_readiness_id": record.review_readiness_id,
        "admission_case_id": record.admission_case_id,
        "sleeve_candidate_id": record.sleeve_candidate_id,
        "action": record.action,
        "reviewer_id": record.reviewer_id,
        "governance_decision_id": record.governance_decision_id,
        "governance_decision": record.governance_decision,
        "governance_status": record.governance_status,
        "governance_reviewer_id": record.governance_reviewer_id,
        "readiness_id": record.readiness_id,
        "promotion_target": record.promotion_target,
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
        "readiness_digest": record.readiness_digest,
        "replay_trace_digest": record.replay_trace_digest,
        "metrics_digest": record.metrics_digest,
        "decision_trace_digest": record.decision_trace_digest,
        "governance_review_evidence_digest": record.governance_review_evidence_digest,
        "governance_rationale_digest": record.governance_rationale_digest,
        "governance_decision_digest": record.governance_decision_digest,
        "replay_source_id": record.replay_source_id,
        "historical_data_source_id": record.historical_data_source_id,
        "review_evidence_digest": record.review_evidence_digest,
        "rationale_digest": record.rationale_digest,
        "metadata": [list(pair) for pair in record.metadata],
        "rejection_reasons": list(record.rejection_reasons),
        "needs_research_reasons": list(record.needs_research_reasons),
        "correlation_id": record.correlation_id,
        "review_readiness_digest": record.review_readiness_digest,
        "paper_only": record.paper_only,
        "real_orders_enabled": record.real_orders_enabled,
        "real_money_enabled": record.real_money_enabled,
    }


__all__ = [
    "PaperSleeveAdmissionReviewAction",
    "PaperSleeveAdmissionReviewReadiness",
    "PaperSleeveAdmissionReviewReadinessError",
    "PaperSleeveAdmissionReviewReadinessStatus",
    "build_paper_sleeve_admission_review_readiness",
    "paper_sleeve_admission_review_readiness_to_dict",
]
