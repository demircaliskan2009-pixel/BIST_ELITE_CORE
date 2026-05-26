from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import (
    DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_ID,
    DERIBIT_PHASE55_PROMOTION_READINESS,
    DERIBIT_PHASE57_OPERATOR_PROMOTION_APPROVAL,
    DERIBIT_PHASE58_APPROVED_ACTION,
    DERIBIT_PHASE58_NEXT_BLOCKER,
    DERIBIT_PHASE58_PROMOTION_SCOPE,
)
from crypto_core.venue.deribit_paper_promotion_telemetry_audit import (
    DERIBIT_PAPER_PROMOTION_TELEMETRY_AUDIT_ID,
    DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION,
    DERIBIT_PHASE59_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_PROMOTION_POST_AUDIT_ID = "deterministic_phase60_paper_promotion_execution_post_audit"
DERIBIT_PHASE59_TELEMETRY_AUDIT = "docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_TELEMETRY_AUDIT_59B.json"
DERIBIT_PHASE60_NEXT_BLOCKER = "PAPER_PROMOTED_RUNTIME_READINESS_NOT_READY"
DERIBIT_PHASE60_FALLBACK_BLOCKER = DERIBIT_PHASE59_NEXT_BLOCKER
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE_FALSE_FIELDS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_POST_AUDIT_CHECKS = tuple(
    "source_hashes_stable no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)


class DeribitPaperPromotionPostAuditResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_promotion_execution_post_audit(
    phase59_promotion_telemetry_audit_artifact: object,
    phase58_approved_paper_promotion_execution_artifact: object,
) -> DeribitPaperPromotionPostAuditResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase59_rejection_reasons(phase59_promotion_telemetry_audit_artifact),
                *_phase58_rejection_reasons(phase58_approved_paper_promotion_execution_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    or phase58_approved_paper_promotion_execution_artifact.get(
                        "source_phase57_operator_promotion_approval"
                    )
                    != DERIBIT_PHASE57_OPERATOR_PROMOTION_APPROVAL
                    or phase58_approved_paper_promotion_execution_artifact.get("source_phase55_promotion_readiness")
                    != DERIBIT_PHASE55_PROMOTION_READINESS
                    else ("deribit_paper_promotion_post_audit:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_promotion_post_audit:accepted" if accepted else reasons[0]
    return DeribitPaperPromotionPostAuditResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase59_promotion_telemetry_audit_artifact,
            phase58_approved_paper_promotion_execution_artifact,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase59_rejection_reasons(phase59_promotion_telemetry_audit_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase59_promotion_telemetry_audit_artifact, dict):
        return ("deribit_paper_promotion_post_audit:phase59_artifact_missing",)
    reasons: list[str] = []
    if (
        phase59_promotion_telemetry_audit_artifact.get("schema_version")
        != "deribit_paper_promotion_execution_telemetry_audit.v1"
        or phase59_promotion_telemetry_audit_artifact.get("phase") != "59"
        or phase59_promotion_telemetry_audit_artifact.get("source") != DERIBIT_PAPER_PROMOTION_TELEMETRY_AUDIT_ID
        or phase59_promotion_telemetry_audit_artifact.get("source_phase58_execution")
        != DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION
        or phase59_promotion_telemetry_audit_artifact.get("telemetry_audit_status") != "AUDITED"
        or phase59_promotion_telemetry_audit_artifact.get("telemetry_audit_verdict") != "PASS"
        or phase59_promotion_telemetry_audit_artifact.get("execution_verdict") != "PASS"
        or phase59_promotion_telemetry_audit_artifact.get("promotion_execution_status") != "EXECUTED"
        or phase59_promotion_telemetry_audit_artifact.get("promotion_granted") is not True
        or phase59_promotion_telemetry_audit_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase59_promotion_telemetry_audit_artifact.get("paper_promoted") is not True
        or phase59_promotion_telemetry_audit_artifact.get("report_only") is not True
        or phase59_promotion_telemetry_audit_artifact.get("no_new_execution") is not True
        or phase59_promotion_telemetry_audit_artifact.get("next_blocker") != DERIBIT_PHASE59_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_promotion_post_audit:phase59_metadata_invalid")
    if not _bool_fields_match(phase59_promotion_telemetry_audit_artifact, _PHASE_FALSE_FIELDS, False):
        reasons.append("deribit_paper_promotion_post_audit:phase59_scope_flags_invalid")
    if not _bool_fields_match(phase59_promotion_telemetry_audit_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_promotion_post_audit:phase59_safety_flags_invalid")
    if not _strict_int_is_one(phase59_promotion_telemetry_audit_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_promotion_post_audit:phase59_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase58_rejection_reasons(phase58_approved_paper_promotion_execution_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase58_approved_paper_promotion_execution_artifact, dict):
        return ("deribit_paper_promotion_post_audit:phase58_artifact_missing",)
    reasons: list[str] = []
    if (
        phase58_approved_paper_promotion_execution_artifact.get("schema_version")
        != "deribit_approved_paper_promotion_execution.v1"
        or phase58_approved_paper_promotion_execution_artifact.get("phase") != "58"
        or phase58_approved_paper_promotion_execution_artifact.get("source")
        != DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_ID
        or phase58_approved_paper_promotion_execution_artifact.get("source_phase57_operator_promotion_approval")
        != DERIBIT_PHASE57_OPERATOR_PROMOTION_APPROVAL
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
        reasons.append("deribit_paper_promotion_post_audit:phase58_metadata_invalid")
    if not _bool_fields_match(phase58_approved_paper_promotion_execution_artifact, _PHASE_FALSE_FIELDS, False):
        reasons.append("deribit_paper_promotion_post_audit:phase58_scope_flags_invalid")
    if not _bool_fields_match(phase58_approved_paper_promotion_execution_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_promotion_post_audit:phase58_safety_flags_invalid")
    if not _strict_int_is_one(
        phase58_approved_paper_promotion_execution_artifact.get("connector_ready_dialects_count")
    ):
        reasons.append("deribit_paper_promotion_post_audit:phase58_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase59_promotion_telemetry_audit_artifact: object,
    phase58_approved_paper_promotion_execution_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase59 = (
        phase59_promotion_telemetry_audit_artifact
        if isinstance(phase59_promotion_telemetry_audit_artifact, dict)
        else {}
    )
    phase58 = (
        phase58_approved_paper_promotion_execution_artifact
        if isinstance(phase58_approved_paper_promotion_execution_artifact, dict)
        else {}
    )
    phase_false_flags = {field: (phase59.get(field) if accepted else False) for field in _PHASE_FALSE_FIELDS}
    phase_safety_flags = {field: (phase59.get(field) if accepted else True) for field in _TRUE_SAFETY_FIELDS}
    return {
        "schema_version": "deribit_paper_promotion_execution_post_audit.v1",
        "phase": "60",
        "source": DERIBIT_PAPER_PROMOTION_POST_AUDIT_ID,
        "source_phase59_telemetry_audit": DERIBIT_PHASE59_TELEMETRY_AUDIT,
        "source_phase58_promotion_execution": DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION,
        "source_phase59_telemetry_audit_sha256": _canonical_sha256(phase59) if phase59 else None,
        "source_phase58_promotion_execution_sha256": _canonical_sha256(phase58) if phase58 else None,
        "promotion_telemetry_audit_status": phase59.get("telemetry_audit_status"),
        "promotion_telemetry_audit_verdict": phase59.get("telemetry_audit_verdict"),
        "promotion_execution_status": phase58.get("promotion_execution_status"),
        "approved_action": phase58.get("approved_action"),
        "promotion_scope": phase58.get("promotion_scope"),
        "promotion_granted": phase58.get("promotion_granted") if accepted else False,
        "paper_promoted": phase58.get("paper_promoted") if accepted else False,
        "approval_status": phase58.get("approval_status"),
        "approval_decision": phase58.get("approval_decision"),
        "operator_id": phase58.get("operator_id"),
        "post_audit_status": "POST_AUDITED" if accepted else "FAIL_CLOSED",
        "post_audit_verdict": "PASS" if accepted else "FAIL_CLOSED",
        **phase_false_flags,
        **phase_safety_flags,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "post_audit_checks": list(_POST_AUDIT_CHECKS),
        "report_only": True,
        "no_new_execution": True,
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE60_NEXT_BLOCKER if accepted else DERIBIT_PHASE60_FALLBACK_BLOCKER,
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_PAPER_PROMOTION_POST_AUDIT_ID",
    "DERIBIT_PHASE59_TELEMETRY_AUDIT",
    "DERIBIT_PHASE60_NEXT_BLOCKER",
    "DERIBIT_PHASE60_FALLBACK_BLOCKER",
    "DeribitPaperPromotionPostAuditResult",
    "audit_deribit_paper_promotion_execution_post_audit",
]
