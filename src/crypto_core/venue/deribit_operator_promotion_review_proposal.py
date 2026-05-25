from __future__ import annotations

from typing import NamedTuple

from crypto_core.venue.deribit_paper_promotion_readiness import (
    DERIBIT_PHASE54_TELEMETRY_AUDIT,
    evaluate_deribit_paper_promotion_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_OPERATOR_PROMOTION_REVIEW_PROPOSAL_ID = "deterministic_phase56_operator_promotion_review_proposal"
DERIBIT_PHASE55_PROMOTION_READINESS = (
    "docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json"
)
DERIBIT_PHASE56_NEXT_BLOCKER = "OPERATOR_PROMOTION_APPROVAL_NOT_READY"
DERIBIT_PHASE56_FALLBACK_BLOCKER = "OPERATOR_PROMOTION_REVIEW_PROPOSAL_NOT_READY"
_PLACEHOLDER = "<OPERATOR_REQUIRED>"
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter "
    "no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop "
    "no_shadow no_live".split()
)
_PROPOSAL_CHECKS = [
    "source_phase55_promotion_readiness_exists",
    "phase55_ready_for_operator_promotion_review",
    "phase55_promotion_not_granted",
    "phase55_no_live_scope_preserved",
    "source_phase54_execution_telemetry_exists",
    "phase54_telemetry_audit_pass",
    "phase54_execution_verdict_pass",
    "operator_metadata_placeholders_only",
    "approval_status_not_approved",
    "connector_ready_dialects_count_preserved",
]


class DeribitOperatorPromotionReviewProposalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def propose_deribit_operator_promotion_review(
    phase55_promotion_readiness_artifact: object,
    phase54_execution_telemetry_artifact: object,
) -> DeribitOperatorPromotionReviewProposalResult:
    phase55_validation = evaluate_deribit_paper_promotion_readiness(phase54_execution_telemetry_artifact)
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase55_rejection_reasons(phase55_promotion_readiness_artifact, phase55_validation),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_operator_promotion_review_proposal:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_operator_promotion_review_proposal:accepted" if accepted else reasons[0]
    return DeribitOperatorPromotionReviewProposalResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase55_promotion_readiness_artifact, phase54_execution_telemetry_artifact, accepted, reason_code, reasons
        ),
    )


def _phase55_rejection_reasons(
    phase55_promotion_readiness_artifact: object,
    phase55_validation,
) -> tuple[str, ...]:
    if not isinstance(phase55_promotion_readiness_artifact, dict):
        return ("deribit_operator_promotion_review_proposal:phase55_artifact_missing",)
    reasons: list[str] = []
    if phase55_validation.accepted is not True:
        reasons.append("deribit_operator_promotion_review_proposal:phase54_readiness_chain_invalid")
    if phase55_promotion_readiness_artifact != phase55_validation.artifact_payload:
        reasons.append("deribit_operator_promotion_review_proposal:phase55_artifact_drift")
    if (
        phase55_promotion_readiness_artifact.get("promotion_readiness_verdict") != "READY_FOR_OPERATOR_REVIEW"
        or phase55_promotion_readiness_artifact.get("ready_for_operator_promotion_review") is not True
    ):
        reasons.append("deribit_operator_promotion_review_proposal:phase55_not_ready_for_operator_promotion_review")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase55_promotion_readiness_artifact: object,
    phase54_execution_telemetry_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase55 = phase55_promotion_readiness_artifact if isinstance(phase55_promotion_readiness_artifact, dict) else {}
    phase54 = phase54_execution_telemetry_artifact if isinstance(phase54_execution_telemetry_artifact, dict) else {}
    payload = {
        "schema_version": "deribit_paper_performance_operator_promotion_review_proposal.v1",
        "phase": "56",
        "source": DERIBIT_OPERATOR_PROMOTION_REVIEW_PROPOSAL_ID,
        "source_phase55_promotion_readiness": DERIBIT_PHASE55_PROMOTION_READINESS,
        "source_phase54_execution_telemetry": DERIBIT_PHASE54_TELEMETRY_AUDIT,
        "source_phase55_promotion_readiness_verdict": phase55.get("promotion_readiness_verdict"),
        "source_phase55_ready_for_operator_promotion_review": phase55.get("ready_for_operator_promotion_review"),
        "source_phase54_telemetry_audit_verdict": phase54.get("telemetry_audit_verdict"),
        "source_phase54_execution_verdict": phase54.get("execution_verdict"),
        "proposal_status": "READY_FOR_OPERATOR_REVIEW" if accepted else "FAIL_CLOSED",
        "proposal_type": "OPERATOR_PROMOTION_REVIEW",
        "approval_status": "NOT_APPROVED",
        "operator_metadata_required": True,
        "reviewer_id": _PLACEHOLDER,
        "reviewed_at_iso": _PLACEHOLDER,
        "approval_scope": _PLACEHOLDER,
        "approval_decision": "PLACEHOLDER_ONLY",
        "approval_notes": _PLACEHOLDER,
        "promotion_granted": False,
        "ready_for_live": False,
        "ready_for_shadow": False,
        "scheduler_enabled": False,
        "auto_loop_enabled": False,
        "live_enabled": False,
        "shadow_enabled": False,
        "ready_for_operator_promotion_review": accepted,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "proposal_checks": list(_PROPOSAL_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE56_NEXT_BLOCKER if accepted else DERIBIT_PHASE56_FALLBACK_BLOCKER,
    }
    payload.update({field: phase55.get(field) for field in _TRUE_SAFETY_FIELDS})
    return payload


__all__ = [
    "DERIBIT_OPERATOR_PROMOTION_REVIEW_PROPOSAL_ID",
    "DERIBIT_PHASE55_PROMOTION_READINESS",
    "DERIBIT_PHASE56_NEXT_BLOCKER",
    "DeribitOperatorPromotionReviewProposalResult",
    "propose_deribit_operator_promotion_review",
]
