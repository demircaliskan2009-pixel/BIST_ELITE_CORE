from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import (
    DERIBIT_PHASE58_APPROVED_ACTION,
    DERIBIT_PHASE58_PROMOTION_SCOPE,
)
from crypto_core.venue.deribit_paper_promotion_post_audit import (
    DERIBIT_PAPER_PROMOTION_POST_AUDIT_ID,
    DERIBIT_PHASE59_TELEMETRY_AUDIT,
    DERIBIT_PHASE60_NEXT_BLOCKER,
)
from crypto_core.venue.deribit_paper_promotion_telemetry_audit import (
    DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_ID = "deterministic_phase61_paper_promoted_runtime_readiness"
DERIBIT_PHASE60_POST_AUDIT = "docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_POST_AUDIT_60B.json"
DERIBIT_PHASE61_NEXT_BLOCKER = "PAPER_PROMOTED_RUNTIME_WIRING_NOT_READY"
DERIBIT_PHASE61_FALLBACK_BLOCKER = DERIBIT_PHASE60_NEXT_BLOCKER
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE_FALSE_FIELDS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_READINESS_CHECKS = tuple(
    "source_post_audit_passed promotion_scope_preserved no_live_scope_preserved no_private_execution_scope_preserved connector_ready_dialects_preserved deterministic_artifact_chain_preserved".split()
)


class DeribitPaperPromotedRuntimeReadinessResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def evaluate_deribit_paper_promoted_runtime_readiness(
    phase60_paper_promotion_post_audit_artifact: object,
) -> DeribitPaperPromotedRuntimeReadinessResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase60_rejection_reasons(phase60_paper_promotion_post_audit_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_paper_promoted_runtime_readiness:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_promoted_runtime_readiness:accepted" if accepted else reasons[0]
    return DeribitPaperPromotedRuntimeReadinessResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(phase60_paper_promotion_post_audit_artifact, accepted, reason_code, reasons),
    )


def _phase60_rejection_reasons(phase60_paper_promotion_post_audit_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase60_paper_promotion_post_audit_artifact, dict):
        return ("deribit_paper_promoted_runtime_readiness:phase60_artifact_missing",)
    reasons: list[str] = []
    if (
        phase60_paper_promotion_post_audit_artifact.get("schema_version")
        != "deribit_paper_promotion_execution_post_audit.v1"
        or phase60_paper_promotion_post_audit_artifact.get("phase") != "60"
        or phase60_paper_promotion_post_audit_artifact.get("source") != DERIBIT_PAPER_PROMOTION_POST_AUDIT_ID
        or phase60_paper_promotion_post_audit_artifact.get("source_phase59_telemetry_audit")
        != DERIBIT_PHASE59_TELEMETRY_AUDIT
        or phase60_paper_promotion_post_audit_artifact.get("source_phase58_promotion_execution")
        != DERIBIT_PHASE58_APPROVED_PROMOTION_EXECUTION
        or phase60_paper_promotion_post_audit_artifact.get("post_audit_status") != "POST_AUDITED"
        or phase60_paper_promotion_post_audit_artifact.get("post_audit_verdict") != "PASS"
        or phase60_paper_promotion_post_audit_artifact.get("promotion_telemetry_audit_verdict") != "PASS"
        or phase60_paper_promotion_post_audit_artifact.get("promotion_execution_status") != "EXECUTED"
        or phase60_paper_promotion_post_audit_artifact.get("approved_action") != DERIBIT_PHASE58_APPROVED_ACTION
        or phase60_paper_promotion_post_audit_artifact.get("promotion_granted") is not True
        or phase60_paper_promotion_post_audit_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase60_paper_promotion_post_audit_artifact.get("paper_promoted") is not True
        or phase60_paper_promotion_post_audit_artifact.get("approval_status") != "APPROVED"
        or phase60_paper_promotion_post_audit_artifact.get("approval_decision") != "APPROVE_PAPER_PROMOTION_REVIEW"
        or phase60_paper_promotion_post_audit_artifact.get("operator_id") != "demir_operator"
        or phase60_paper_promotion_post_audit_artifact.get("next_blocker") != DERIBIT_PHASE60_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_promoted_runtime_readiness:phase60_metadata_invalid")
    if not _bool_fields_match(phase60_paper_promotion_post_audit_artifact, _PHASE_FALSE_FIELDS, False):
        reasons.append("deribit_paper_promoted_runtime_readiness:phase60_scope_flags_invalid")
    if phase60_paper_promotion_post_audit_artifact.get("runtime_enabled") is True:
        reasons.append("deribit_paper_promoted_runtime_readiness:phase60_runtime_flag_invalid")
    if not _bool_fields_match(phase60_paper_promotion_post_audit_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_promoted_runtime_readiness:phase60_safety_flags_invalid")
    if not _strict_int_is_one(phase60_paper_promotion_post_audit_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_promoted_runtime_readiness:phase60_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase60_paper_promotion_post_audit_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase60 = (
        phase60_paper_promotion_post_audit_artifact
        if isinstance(phase60_paper_promotion_post_audit_artifact, dict)
        else {}
    )
    phase_false_flags = {field: (phase60.get(field) if accepted else False) for field in _PHASE_FALSE_FIELDS}
    phase_safety_flags = {field: (phase60.get(field) if accepted else True) for field in _TRUE_SAFETY_FIELDS}
    return {
        "schema_version": "deribit_paper_promoted_runtime_readiness.v1",
        "phase": "61",
        "source": DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_ID,
        "source_phase60_post_audit": DERIBIT_PHASE60_POST_AUDIT,
        "source_phase60_post_audit_sha256": _canonical_sha256(phase60) if phase60 else None,
        "runtime_readiness_verdict": "PASS" if accepted else "FAIL_CLOSED",
        "paper_promoted": phase60.get("paper_promoted") if accepted else False,
        "promotion_granted": phase60.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
        "ready_for_paper_runtime": accepted,
        "runtime_enabled": False,
        **phase_false_flags,
        **phase_safety_flags,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "readiness_checks": list(_READINESS_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE61_NEXT_BLOCKER if accepted else DERIBIT_PHASE61_FALLBACK_BLOCKER,
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_ID",
    "DERIBIT_PHASE60_POST_AUDIT",
    "DERIBIT_PHASE61_NEXT_BLOCKER",
    "DERIBIT_PHASE61_FALLBACK_BLOCKER",
    "DeribitPaperPromotedRuntimeReadinessResult",
    "evaluate_deribit_paper_promoted_runtime_readiness",
]
