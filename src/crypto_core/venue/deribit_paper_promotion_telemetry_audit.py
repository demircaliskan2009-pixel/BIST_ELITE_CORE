from __future__ import annotations

from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import (
    DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_ID,
    DERIBIT_PHASE55_PROMOTION_READINESS,
    DERIBIT_PHASE58_APPROVED_ACTION,
    DERIBIT_PHASE58_NEXT_BLOCKER,
    DERIBIT_PHASE58_PROMOTION_SCOPE,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_PROMOTION_TELEMETRY_AUDIT_ID = "deterministic_phase59_paper_promotion_execution_telemetry_audit"
DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION = "docs/crypto_core/DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_58B.json"
DERIBIT_PHASE59_NEXT_BLOCKER = "PAPER_PROMOTION_EXECUTION_POST_AUDIT_NOT_READY"
DERIBIT_PHASE59_FALLBACK_BLOCKER = DERIBIT_PHASE58_NEXT_BLOCKER
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE55_FALSE_FIELDS = tuple(
    "promotion_granted live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled".split()
)
_PHASE58_FALSE_FIELDS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_AUDIT_CHECKS = tuple(
    "source_phase58_execution_exists phase58_execution_status_executed phase58_approved_action_valid phase58_paper_scope_preserved phase58_no_live_scope_preserved phase58_no_new_execution_preserved source_phase55_promotion_readiness_exists phase55_ready_for_operator_promotion_review connector_ready_dialects_count_preserved telemetry_audit_report_only".split()
)


class DeribitPaperPromotionTelemetryAuditResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_promotion_execution_telemetry(
    phase58_approved_paper_promotion_execution_artifact: object,
    phase55_promotion_readiness_artifact: object,
) -> DeribitPaperPromotionTelemetryAuditResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase58_rejection_reasons(phase58_approved_paper_promotion_execution_artifact),
                *_phase55_rejection_reasons(phase55_promotion_readiness_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_paper_promotion_telemetry_audit:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_promotion_telemetry_audit:accepted" if accepted else reasons[0]
    return DeribitPaperPromotionTelemetryAuditResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase58_approved_paper_promotion_execution_artifact,
            phase55_promotion_readiness_artifact,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase58_rejection_reasons(phase58_approved_paper_promotion_execution_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase58_approved_paper_promotion_execution_artifact, dict):
        return ("deribit_paper_promotion_telemetry_audit:phase58_artifact_missing",)
    reasons: list[str] = []
    if (
        phase58_approved_paper_promotion_execution_artifact.get("schema_version")
        != "deribit_approved_paper_promotion_execution.v1"
        or phase58_approved_paper_promotion_execution_artifact.get("phase") != "58"
        or phase58_approved_paper_promotion_execution_artifact.get("source")
        != DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_ID
        or phase58_approved_paper_promotion_execution_artifact.get("source_phase55_promotion_readiness")
        != DERIBIT_PHASE55_PROMOTION_READINESS
        or phase58_approved_paper_promotion_execution_artifact.get("promotion_execution_status") != "EXECUTED"
        or phase58_approved_paper_promotion_execution_artifact.get("approved_action") != DERIBIT_PHASE58_APPROVED_ACTION
        or phase58_approved_paper_promotion_execution_artifact.get("promotion_granted") is not True
        or phase58_approved_paper_promotion_execution_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase58_approved_paper_promotion_execution_artifact.get("paper_promoted") is not True
        or phase58_approved_paper_promotion_execution_artifact.get("approval_status") != "APPROVED"
        or phase58_approved_paper_promotion_execution_artifact.get("approval_decision")
        != "APPROVE_PAPER_PROMOTION_REVIEW"
        or phase58_approved_paper_promotion_execution_artifact.get("operator_id") != "demir_operator"
        or phase58_approved_paper_promotion_execution_artifact.get("next_blocker") != DERIBIT_PHASE58_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase58_metadata_invalid")
    if not _bool_fields_match(phase58_approved_paper_promotion_execution_artifact, _PHASE58_FALSE_FIELDS, False):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase58_scope_flags_invalid")
    if not _bool_fields_match(phase58_approved_paper_promotion_execution_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase58_safety_flags_invalid")
    if not _strict_int_is_one(
        phase58_approved_paper_promotion_execution_artifact.get("connector_ready_dialects_count")
    ):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase58_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase55_rejection_reasons(phase55_promotion_readiness_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase55_promotion_readiness_artifact, dict):
        return ("deribit_paper_promotion_telemetry_audit:phase55_artifact_missing",)
    reasons: list[str] = []
    if (
        phase55_promotion_readiness_artifact.get("schema_version")
        != "deribit_paper_performance_promotion_readiness_evaluation.v1"
        or phase55_promotion_readiness_artifact.get("phase") != "55"
        or phase55_promotion_readiness_artifact.get("promotion_readiness_verdict") != "READY_FOR_OPERATOR_REVIEW"
        or phase55_promotion_readiness_artifact.get("ready_for_operator_promotion_review") is not True
    ):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase55_metadata_invalid")
    if not _bool_fields_match(phase55_promotion_readiness_artifact, _PHASE55_FALSE_FIELDS, False):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase55_scope_flags_invalid")
    if not _bool_fields_match(phase55_promotion_readiness_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase55_safety_flags_invalid")
    if not _strict_int_is_one(phase55_promotion_readiness_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_promotion_telemetry_audit:phase55_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase58_approved_paper_promotion_execution_artifact: object,
    phase55_promotion_readiness_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase58 = (
        phase58_approved_paper_promotion_execution_artifact
        if isinstance(phase58_approved_paper_promotion_execution_artifact, dict)
        else {}
    )
    phase55 = phase55_promotion_readiness_artifact if isinstance(phase55_promotion_readiness_artifact, dict) else {}
    phase58_false_flags = {field: (phase58.get(field) if accepted else False) for field in _PHASE58_FALSE_FIELDS}
    phase58_safety_flags = {field: (phase58.get(field) if accepted else True) for field in _TRUE_SAFETY_FIELDS}
    return {
        "schema_version": "deribit_paper_promotion_execution_telemetry_audit.v1",
        "phase": "59",
        "source": DERIBIT_PAPER_PROMOTION_TELEMETRY_AUDIT_ID,
        "source_phase58_execution": DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION,
        "source_phase55_promotion_readiness": DERIBIT_PHASE55_PROMOTION_READINESS,
        "source_phase58_promotion_execution_status": phase58.get("promotion_execution_status"),
        "source_phase58_approval_status": phase58.get("approval_status"),
        "source_phase58_approval_decision": phase58.get("approval_decision"),
        "source_phase55_ready_for_operator_promotion_review": phase55.get("ready_for_operator_promotion_review"),
        "telemetry_audit_status": "AUDITED" if accepted else "FAIL_CLOSED",
        "telemetry_audit_verdict": "PASS" if accepted else "FAIL_CLOSED",
        "execution_verdict": "PASS" if accepted else "FAIL_CLOSED",
        "promotion_execution_status": phase58.get("promotion_execution_status"),
        "approved_action": phase58.get("approved_action"),
        "promotion_scope": phase58.get("promotion_scope"),
        "promotion_granted": phase58.get("promotion_granted") if accepted else False,
        "paper_promoted": phase58.get("paper_promoted") if accepted else False,
        "approval_status": phase58.get("approval_status"),
        "approval_decision": phase58.get("approval_decision"),
        "operator_id": phase58.get("operator_id"),
        **phase58_false_flags,
        **phase58_safety_flags,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "telemetry_checks": list(_AUDIT_CHECKS),
        "report_only": True,
        "no_new_execution": True,
        "campaign_execution_replayed": False,
        "session_execution_replayed": False,
        "run_execution_replayed": False,
        "ledger_mutation_replayed": False,
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE59_NEXT_BLOCKER if accepted else DERIBIT_PHASE59_FALLBACK_BLOCKER,
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_PAPER_PROMOTION_TELEMETRY_AUDIT_ID",
    "DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION",
    "DERIBIT_PHASE59_NEXT_BLOCKER",
    "DERIBIT_PHASE59_FALLBACK_BLOCKER",
    "DeribitPaperPromotionTelemetryAuditResult",
    "audit_deribit_paper_promotion_execution_telemetry",
]
