from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_OPERATOR_PROMOTION_APPROVAL_ID = "deterministic_phase57_operator_promotion_approval"
DERIBIT_PHASE56_PROMOTION_REVIEW_PROPOSAL = (
    "docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_REVIEW_PROPOSAL_56B.json"
)
DERIBIT_PHASE55_PROMOTION_READINESS = (
    "docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json"
)
DERIBIT_PHASE57_NEXT_BLOCKER = "APPROVED_PROMOTION_EXECUTION_NOT_READY"
DERIBIT_PHASE57_FALLBACK_BLOCKER = "OPERATOR_PROMOTION_APPROVAL_NOT_READY"
DERIBIT_PHASE57_OPERATOR_ID = "demir_operator"
DERIBIT_PHASE57_APPROVAL_DECISION = "APPROVE_PAPER_PROMOTION_REVIEW"
DERIBIT_PHASE57_MERGE_POLICY_NOTE = "MERGE_POLICY_VIOLATION_RECORDED"
_PLACEHOLDER = "<OPERATOR_REQUIRED>"
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE56_FALSE_SCOPE_FIELDS = tuple(
    "promotion_granted ready_for_live ready_for_shadow scheduler_enabled auto_loop_enabled live_enabled shadow_enabled".split()
)
_PHASE57_FALSE_SCOPE_FIELDS = tuple(
    "promotion_granted campaign_execution session_execution run_execution ledger_mutated live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled".split()
)
_APPROVAL_SCOPE = dict.fromkeys(
    ("paper_only", "simulation_only", "deribit_public_market_data_only", *_TRUE_SAFETY_FIELDS), True
)
_APPROVAL_CHECKS = tuple(
    "source_phase56_operator_promotion_review_proposal_exists phase56_ready_for_operator_promotion_review phase56_pre_approval_status_not_approved source_phase55_promotion_readiness_exists phase55_ready_for_operator_promotion_review exact_operator_metadata_supplied reviewed_at_iso_utc_z approval_scope_paper_only promotion_not_granted campaign_not_executed ledger_not_mutated no_live_scope_preserved merge_policy_violation_recorded connector_ready_dialects_count_preserved".split()
)


class DeribitOperatorPromotionApprovalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_operator_promotion_approval(
    phase56_operator_promotion_review_proposal_artifact: object,
    phase55_promotion_readiness_artifact: object,
    *,
    reviewed_at_iso: str,
    merge_policy_note: str = DERIBIT_PHASE57_MERGE_POLICY_NOTE,
):
    reasons = [
        *_phase55_rejection_reasons(phase55_promotion_readiness_artifact),
        *_phase56_rejection_reasons(
            phase56_operator_promotion_review_proposal_artifact, phase55_promotion_readiness_artifact
        ),
    ]
    if not _is_utc_z(reviewed_at_iso):
        reasons.append("deribit_operator_promotion_approval:reviewed_at_iso_invalid")
    if merge_policy_note != DERIBIT_PHASE57_MERGE_POLICY_NOTE:
        reasons.append("deribit_operator_promotion_approval:merge_policy_note_invalid")
    if len(connector_ready_dialects()) != 1:
        reasons.append("deribit_operator_promotion_approval:connector_ready_dialects_mismatch")
    rejection_reasons = tuple(dict.fromkeys(reasons))
    accepted = not rejection_reasons
    reason_code = "deribit_operator_promotion_approval:accepted" if accepted else rejection_reasons[0]
    return DeribitOperatorPromotionApprovalResult(
        accepted,
        reason_code,
        rejection_reasons,
        _artifact_payload(
            phase56_operator_promotion_review_proposal_artifact,
            phase55_promotion_readiness_artifact,
            reviewed_at_iso,
            merge_policy_note,
            accepted,
            reason_code,
            rejection_reasons,
        ),
    )


def _phase55_rejection_reasons(phase55_promotion_readiness_artifact: object):
    if not isinstance(phase55_promotion_readiness_artifact, dict):
        return ("deribit_operator_promotion_approval:phase55_artifact_missing",)
    reasons: list[str] = []
    if (
        any(
            phase55_promotion_readiness_artifact.get(field) != expected
            for field, expected in {
                "schema_version": "deribit_paper_performance_promotion_readiness_evaluation.v1",
                "phase": "55",
                "promotion_readiness_verdict": "READY_FOR_OPERATOR_REVIEW",
            }.items()
        )
        or phase55_promotion_readiness_artifact.get("ready_for_operator_promotion_review") is not True
    ):
        reasons.append("deribit_operator_promotion_approval:phase55_metadata_invalid")
    if not _bool_fields_match(phase55_promotion_readiness_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_operator_promotion_approval:phase55_safety_flags_invalid")
    criteria = phase55_promotion_readiness_artifact.get("criteria_results")
    if not isinstance(criteria, dict) or not criteria or not all(criteria.values()):
        reasons.append("deribit_operator_promotion_approval:phase55_criteria_invalid")
    if not _strict_int_is_one(phase55_promotion_readiness_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_operator_promotion_approval:phase55_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase56_rejection_reasons(
    phase56_operator_promotion_review_proposal_artifact: object, phase55_promotion_readiness_artifact: object
):
    if not isinstance(phase56_operator_promotion_review_proposal_artifact, dict):
        return ("deribit_operator_promotion_approval:phase56_artifact_missing",)
    phase55 = phase55_promotion_readiness_artifact if isinstance(phase55_promotion_readiness_artifact, dict) else {}
    reasons: list[str] = []
    if any(
        phase56_operator_promotion_review_proposal_artifact.get(field) != expected
        for field, expected in {
            "schema_version": "deribit_paper_performance_operator_promotion_review_proposal.v1",
            "phase": "56",
            "source": "deterministic_phase56_operator_promotion_review_proposal",
            "source_phase55_promotion_readiness": DERIBIT_PHASE55_PROMOTION_READINESS,
            "proposal_status": "READY_FOR_OPERATOR_REVIEW",
            "proposal_type": "OPERATOR_PROMOTION_REVIEW",
            "approval_status": "NOT_APPROVED",
            "approval_decision": "PLACEHOLDER_ONLY",
            "next_blocker": DERIBIT_PHASE57_FALLBACK_BLOCKER,
        }.items()
    ) or any(
        phase56_operator_promotion_review_proposal_artifact.get(field) != expected
        for field, expected in {
            "source_phase55_promotion_readiness_verdict": phase55.get("promotion_readiness_verdict"),
            "source_phase55_ready_for_operator_promotion_review": phase55.get("ready_for_operator_promotion_review"),
            "operator_metadata_required": True,
            "ready_for_operator_promotion_review": True,
        }.items()
    ):
        reasons.append("deribit_operator_promotion_approval:phase56_metadata_invalid")
    if any(
        phase56_operator_promotion_review_proposal_artifact.get(field) != _PLACEHOLDER
        for field in ("reviewer_id", "reviewed_at_iso", "approval_scope", "approval_notes")
    ):
        reasons.append("deribit_operator_promotion_approval:phase56_placeholder_metadata_invalid")
    if not _bool_fields_match(phase56_operator_promotion_review_proposal_artifact, _PHASE56_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_operator_promotion_approval:phase56_scope_flags_invalid")
    if not _bool_fields_match(phase56_operator_promotion_review_proposal_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_operator_promotion_approval:phase56_safety_flags_invalid")
    if not _strict_int_is_one(
        phase56_operator_promotion_review_proposal_artifact.get("connector_ready_dialects_count")
    ):
        reasons.append("deribit_operator_promotion_approval:phase56_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase56_operator_promotion_review_proposal_artifact: object,
    phase55_promotion_readiness_artifact: object,
    reviewed_at_iso: str,
    merge_policy_note: str,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
):
    phase56 = (
        phase56_operator_promotion_review_proposal_artifact
        if isinstance(phase56_operator_promotion_review_proposal_artifact, dict)
        else {}
    )
    phase55 = phase55_promotion_readiness_artifact if isinstance(phase55_promotion_readiness_artifact, dict) else {}
    return {
        "schema_version": "deribit_paper_performance_operator_promotion_approval.v1",
        "phase": "57",
        "generated_at": reviewed_at_iso,
        "source": DERIBIT_OPERATOR_PROMOTION_APPROVAL_ID,
        "source_phase56_operator_promotion_review_proposal": DERIBIT_PHASE56_PROMOTION_REVIEW_PROPOSAL,
        "source_phase55_promotion_readiness": DERIBIT_PHASE55_PROMOTION_READINESS,
        "source_phase56_proposal_status": phase56.get("proposal_status"),
        "source_phase56_approval_status": phase56.get("approval_status"),
        "source_phase55_promotion_readiness_verdict": phase55.get("promotion_readiness_verdict"),
        "approval_status": "APPROVED" if accepted else "FAIL_CLOSED",
        "operator_id": DERIBIT_PHASE57_OPERATOR_ID,
        "reviewed_at_iso": reviewed_at_iso,
        "approval_decision": DERIBIT_PHASE57_APPROVAL_DECISION,
        "approval_scope": dict(_APPROVAL_SCOPE),
        "operator_metadata_source": "explicit_user_approval_in_chat",
        **dict.fromkeys(_PHASE57_FALSE_SCOPE_FIELDS, False),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "merge_policy_note": merge_policy_note,
        "approval_checks": list(_APPROVAL_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE57_NEXT_BLOCKER if accepted else DERIBIT_PHASE57_FALLBACK_BLOCKER,
        **{field: phase56.get(field) for field in _TRUE_SAFETY_FIELDS},
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool):
    return all(payload.get(field) is expected for field in fields)


def _is_utc_z(value: object):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo == timezone.utc
    except ValueError:
        return False


def _strict_int_is_one(value: object):
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_OPERATOR_PROMOTION_APPROVAL_ID",
    "DERIBIT_PHASE56_PROMOTION_REVIEW_PROPOSAL",
    "DERIBIT_PHASE55_PROMOTION_READINESS",
    "DERIBIT_PHASE57_NEXT_BLOCKER",
    "DERIBIT_PHASE57_OPERATOR_ID",
    "DERIBIT_PHASE57_APPROVAL_DECISION",
    "DERIBIT_PHASE57_MERGE_POLICY_NOTE",
    "DeribitOperatorPromotionApprovalResult",
    "execute_deribit_operator_promotion_approval",
]
