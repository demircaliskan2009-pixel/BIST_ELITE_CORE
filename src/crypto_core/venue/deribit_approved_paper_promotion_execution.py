from __future__ import annotations

from typing import NamedTuple

from crypto_core.venue.deribit_operator_promotion_approval import (
    DERIBIT_OPERATOR_PROMOTION_APPROVAL_ID,
    DERIBIT_PHASE55_PROMOTION_READINESS,
    DERIBIT_PHASE57_APPROVAL_DECISION,
    DERIBIT_PHASE57_NEXT_BLOCKER,
    DERIBIT_PHASE57_OPERATOR_ID,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_ID = "deterministic_phase58_approved_paper_promotion_execution"
DERIBIT_PHASE57_OPERATOR_PROMOTION_APPROVAL = (
    "docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_APPROVAL_57B.json"
)
DERIBIT_PHASE58_APPROVED_ACTION = "APPROVED_PAPER_PROMOTION_EXECUTION"
DERIBIT_PHASE58_PROMOTION_SCOPE = "PAPER_ONLY_SIMULATION_ONLY"
DERIBIT_PHASE58_NEXT_BLOCKER = "PAPER_PROMOTION_EXECUTION_TELEMETRY_NOT_READY"
DERIBIT_PHASE58_FALLBACK_BLOCKER = "APPROVED_PROMOTION_EXECUTION_NOT_READY"
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE55_FALSE_FIELDS = tuple(
    "promotion_granted live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled".split()
)
_PHASE57_FALSE_FIELDS = tuple(
    "promotion_granted campaign_execution session_execution run_execution ledger_mutated live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled".split()
)
_PHASE57_APPROVAL_SCOPE_TRUE_FIELDS = (
    "paper_only",
    "simulation_only",
    "deribit_public_market_data_only",
    *_TRUE_SAFETY_FIELDS,
)
_PHASE58_FALSE_FIELDS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_EXECUTION_CHECKS = tuple(
    "source_phase57_operator_promotion_approval_exists phase57_approval_status_approved phase57_approval_decision_valid phase57_operator_valid source_phase55_promotion_readiness_exists phase55_ready_for_operator_promotion_review paper_only_scope_approved promotion_granted_only_for_paper no_campaign_execution no_ledger_mutation no_live_scope_preserved connector_ready_dialects_count_preserved".split()
)


class DeribitApprovedPaperPromotionExecutionResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_approved_paper_promotion(
    phase57_operator_promotion_approval_artifact: object,
    phase55_promotion_readiness_artifact: object,
) -> DeribitApprovedPaperPromotionExecutionResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase57_rejection_reasons(phase57_operator_promotion_approval_artifact),
                *_phase55_rejection_reasons(phase55_promotion_readiness_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_approved_paper_promotion_execution:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_approved_paper_promotion_execution:accepted" if accepted else reasons[0]
    return DeribitApprovedPaperPromotionExecutionResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase57_operator_promotion_approval_artifact,
            phase55_promotion_readiness_artifact,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase57_rejection_reasons(phase57_operator_promotion_approval_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase57_operator_promotion_approval_artifact, dict):
        return ("deribit_approved_paper_promotion_execution:phase57_artifact_missing",)
    reasons: list[str] = []
    if (
        phase57_operator_promotion_approval_artifact.get("schema_version")
        != "deribit_paper_performance_operator_promotion_approval.v1"
        or phase57_operator_promotion_approval_artifact.get("phase") != "57"
        or phase57_operator_promotion_approval_artifact.get("source") != DERIBIT_OPERATOR_PROMOTION_APPROVAL_ID
        or phase57_operator_promotion_approval_artifact.get("source_phase55_promotion_readiness")
        != DERIBIT_PHASE55_PROMOTION_READINESS
        or phase57_operator_promotion_approval_artifact.get("approval_status") != "APPROVED"
        or phase57_operator_promotion_approval_artifact.get("approval_decision") != DERIBIT_PHASE57_APPROVAL_DECISION
        or phase57_operator_promotion_approval_artifact.get("operator_id") != DERIBIT_PHASE57_OPERATOR_ID
        or phase57_operator_promotion_approval_artifact.get("next_blocker") != DERIBIT_PHASE57_NEXT_BLOCKER
    ):
        reasons.append("deribit_approved_paper_promotion_execution:phase57_metadata_invalid")
    if not _bool_fields_match(phase57_operator_promotion_approval_artifact, _PHASE57_FALSE_FIELDS, False):
        reasons.append("deribit_approved_paper_promotion_execution:phase57_scope_flags_invalid")
    if not _bool_fields_match(phase57_operator_promotion_approval_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_promotion_execution:phase57_safety_flags_invalid")
    approval_scope = phase57_operator_promotion_approval_artifact.get("approval_scope")
    if not isinstance(approval_scope, dict) or not _bool_fields_match(
        approval_scope, _PHASE57_APPROVAL_SCOPE_TRUE_FIELDS, True
    ):
        reasons.append("deribit_approved_paper_promotion_execution:phase57_approval_scope_invalid")
    if not _strict_int_is_one(phase57_operator_promotion_approval_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_approved_paper_promotion_execution:phase57_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase55_rejection_reasons(phase55_promotion_readiness_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase55_promotion_readiness_artifact, dict):
        return ("deribit_approved_paper_promotion_execution:phase55_artifact_missing",)
    reasons: list[str] = []
    if (
        phase55_promotion_readiness_artifact.get("schema_version")
        != "deribit_paper_performance_promotion_readiness_evaluation.v1"
        or phase55_promotion_readiness_artifact.get("phase") != "55"
        or phase55_promotion_readiness_artifact.get("promotion_readiness_verdict") != "READY_FOR_OPERATOR_REVIEW"
        or phase55_promotion_readiness_artifact.get("ready_for_operator_promotion_review") is not True
    ):
        reasons.append("deribit_approved_paper_promotion_execution:phase55_metadata_invalid")
    if not _bool_fields_match(phase55_promotion_readiness_artifact, _PHASE55_FALSE_FIELDS, False):
        reasons.append("deribit_approved_paper_promotion_execution:phase55_scope_flags_invalid")
    if not _bool_fields_match(phase55_promotion_readiness_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_promotion_execution:phase55_safety_flags_invalid")
    if not _strict_int_is_one(phase55_promotion_readiness_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_approved_paper_promotion_execution:phase55_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase57_operator_promotion_approval_artifact: object,
    phase55_promotion_readiness_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase57 = (
        phase57_operator_promotion_approval_artifact
        if isinstance(phase57_operator_promotion_approval_artifact, dict)
        else {}
    )
    phase55 = phase55_promotion_readiness_artifact if isinstance(phase55_promotion_readiness_artifact, dict) else {}
    return {
        "schema_version": "deribit_approved_paper_promotion_execution.v1",
        "phase": "58",
        "source": DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_ID,
        "source_phase57_operator_promotion_approval": DERIBIT_PHASE57_OPERATOR_PROMOTION_APPROVAL,
        "source_phase55_promotion_readiness": DERIBIT_PHASE55_PROMOTION_READINESS,
        "source_phase57_approval_status": phase57.get("approval_status"),
        "source_phase57_approval_decision": phase57.get("approval_decision"),
        "source_phase55_ready_for_operator_promotion_review": phase55.get("ready_for_operator_promotion_review"),
        "promotion_execution_status": "EXECUTED" if accepted else "FAIL_CLOSED",
        "approved_action": DERIBIT_PHASE58_APPROVED_ACTION,
        "promotion_granted": accepted,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE if accepted else "FAIL_CLOSED",
        "operator_id": phase57.get("operator_id"),
        "approval_status": phase57.get("approval_status"),
        "approval_decision": phase57.get("approval_decision"),
        "paper_promoted": accepted,
        **dict.fromkeys(_PHASE58_FALSE_FIELDS, False),
        **{field: phase57.get(field) for field in _TRUE_SAFETY_FIELDS},
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "execution_checks": list(_EXECUTION_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE58_NEXT_BLOCKER if accepted else DERIBIT_PHASE58_FALLBACK_BLOCKER,
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_ID",
    "DERIBIT_PHASE57_OPERATOR_PROMOTION_APPROVAL",
    "DERIBIT_PHASE58_APPROVED_ACTION",
    "DERIBIT_PHASE58_FALLBACK_BLOCKER",
    "DERIBIT_PHASE58_NEXT_BLOCKER",
    "DERIBIT_PHASE58_PROMOTION_SCOPE",
    "DeribitApprovedPaperPromotionExecutionResult",
    "execute_deribit_approved_paper_promotion",
]
