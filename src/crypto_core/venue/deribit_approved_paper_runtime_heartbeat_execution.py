from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_approved_paper_runtime_start import DERIBIT_PHASE68_REQUIRED_DIALECT_ID
from crypto_core.venue.deribit_paper_runtime_heartbeat_approval import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
    DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL,
    DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256,
    DERIBIT_PHASE73_APPROVAL_DECISION,
    DERIBIT_PHASE73_APPROVAL_SCOPE,
    DERIBIT_PHASE73_FALLBACK_BLOCKER,
    DERIBIT_PHASE73_NEXT_BLOCKER,
    DERIBIT_PHASE73_OPERATOR_ID,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_ID = (
    "deterministic_phase74_approved_paper_runtime_heartbeat_execution"
)
DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json"
)
DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256 = "482be64bad44824f970672f12bcd8418ccafb51df76945c3df4af58a057abfcb"
DERIBIT_PHASE74_NEXT_BLOCKER = "PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_NOT_READY"
DERIBIT_PHASE74_FALLBACK_BLOCKER = DERIBIT_PHASE73_FALLBACK_BLOCKER

_FALSE_SCOPE = tuple(
    "runtime_loop_started runtime_order_routing_enabled live_ready shadow_ready "
    "scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution "
    "session_execution run_execution ledger_mutation strategy_signal_generated "
    "order_intent_generated".split()
)
_TRUE_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter "
    "no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop "
    "no_shadow no_live".split()
)


class DeribitApprovedPaperRuntimeHeartbeatExecutionResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_approved_paper_runtime_heartbeat_execution(
    phase73_heartbeat_operator_approval_artifact: object,
    phase72_heartbeat_review_proposal_artifact: object,
    phase71_heartbeat_telemetry_artifact: object,
) -> DeribitApprovedPaperRuntimeHeartbeatExecutionResult:
    reasons: list[str] = []
    phase73 = (
        phase73_heartbeat_operator_approval_artifact
        if isinstance(phase73_heartbeat_operator_approval_artifact, dict)
        else {}
    )
    phase72 = (
        phase72_heartbeat_review_proposal_artifact
        if isinstance(phase72_heartbeat_review_proposal_artifact, dict)
        else {}
    )
    phase71 = phase71_heartbeat_telemetry_artifact if isinstance(phase71_heartbeat_telemetry_artifact, dict) else {}

    if not phase73:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase73_artifact_missing")
    if not phase72:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase72_artifact_missing")
    if not phase71:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase71_artifact_missing")

    if phase73:
        if (
            phase73.get("schema_version") != "deribit_paper_runtime_heartbeat_operator_approval.v1"
            or phase73.get("phase") != "73"
        ):
            reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase73_artifact_malformed")
        if _canonical_sha256(phase73) != DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256:
            reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase73_provenance_drift")

    if phase72:
        if (
            phase72.get("schema_version") != "deribit_paper_runtime_heartbeat_review_proposal.v1"
            or phase72.get("phase") != "72"
        ):
            reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase72_artifact_malformed")
        if _canonical_sha256(phase72) != DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256:
            reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase72_provenance_drift")

    if phase71:
        if (
            phase71.get("schema_version") != "deribit_paper_runtime_heartbeat_telemetry_audit.v1"
            or phase71.get("phase") != "71"
        ):
            reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase71_artifact_malformed")
        if _canonical_sha256(phase71) != DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256:
            reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase71_provenance_drift")

    if phase73 and phase73.get("next_blocker") != DERIBIT_PHASE73_NEXT_BLOCKER:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase73_next_blocker_drift")

    if phase73 and phase73.get("approval_status") != "APPROVED":
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:approval_status_invalid")
    if phase73 and phase73.get("operator_id") != DERIBIT_PHASE73_OPERATOR_ID:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:operator_id_mismatch")
    if phase73 and phase73.get("approval_decision") != DERIBIT_PHASE73_APPROVAL_DECISION:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:approval_decision_mismatch")
    if phase73 and phase73.get("approval_scope") != DERIBIT_PHASE73_APPROVAL_SCOPE:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:approval_scope_mismatch")

    if phase73 and phase73.get("source_phase72_heartbeat_review_proposal") != DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase72_source_chain_drift")
    if (
        phase73
        and phase73.get("source_phase72_heartbeat_review_proposal_sha256")
        != DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256
    ):
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase72_source_chain_sha_drift")
    if phase73 and phase73.get("source_phase71_heartbeat_telemetry") != DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase71_source_chain_drift")
    if (
        phase73
        and phase73.get("source_phase71_heartbeat_telemetry_sha256") != DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256
    ):
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:phase71_source_chain_sha_drift")

    if phase73 and phase73.get("heartbeat_status") != "RECORDED":
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:heartbeat_status_invalid")
    if phase73 and phase73.get("heartbeat_mode") != "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY":
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:heartbeat_mode_invalid")
    if phase73 and phase73.get("heartbeat_trigger") != "OPERATOR_MANUAL":
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:heartbeat_trigger_invalid")
    if phase73 and phase73.get("heartbeat_sequence") != 1:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:heartbeat_sequence_invalid")
    if phase73 and phase73.get("heartbeat_count") != 1:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:heartbeat_count_invalid")

    if phase73 and phase73.get("runtime_enabled") is not True:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:runtime_enabled_invalid")
    if phase73 and phase73.get("runtime_started") is not True:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:runtime_started_invalid")

    for field in _FALSE_SCOPE:
        if phase73 and phase73.get(field) is not False:
            reasons.append(f"deribit_approved_paper_runtime_heartbeat_execution:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase73 and phase73.get(field) is not True:
            reasons.append(f"deribit_approved_paper_runtime_heartbeat_execution:{field}_invalid")

    if phase73 and phase73.get("connector_ready_dialects_count") != 1:
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:connector_ready_dialects_count_invalid")
    if not _deribit_connector_ready():
        reasons.append("deribit_approved_paper_runtime_heartbeat_execution:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_approved_paper_runtime_heartbeat_execution:accepted" if accepted else reasons_t[0]
    return DeribitApprovedPaperRuntimeHeartbeatExecutionResult(
        accepted,
        reason_code,
        reasons_t,
        _artifact_payload(accepted, reason_code, reasons_t),
    )


def _artifact_payload(
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": "deribit_approved_paper_runtime_heartbeat_execution.v1",
        "phase": "74",
        "source": DERIBIT_APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_ID,
        "source_phase73_heartbeat_operator_approval": DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL,
        "source_phase73_heartbeat_operator_approval_sha256": DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256,
        "source_phase72_heartbeat_review_proposal": DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL,
        "source_phase72_heartbeat_review_proposal_sha256": DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256,
        "source_phase71_heartbeat_telemetry": DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
        "source_phase71_heartbeat_telemetry_sha256": DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
        "heartbeat_execution_status": "EXECUTED" if accepted else "FAIL_CLOSED",
        "execution_mode": "APPROVED_PAPER_RUNTIME_HEARTBEAT_ONLY" if accepted else "FAIL_CLOSED",
        "approval_status": "APPROVED" if accepted else "FAIL_CLOSED",
        "operator_id": DERIBIT_PHASE73_OPERATOR_ID,
        "approval_decision": DERIBIT_PHASE73_APPROVAL_DECISION,
        "approval_scope": DERIBIT_PHASE73_APPROVAL_SCOPE,
        "runtime_enabled": accepted,
        "runtime_started": accepted,
        **dict.fromkeys(_FALSE_SCOPE, False),
        "heartbeat_status": "RECORDED" if accepted else "FAIL_CLOSED",
        "heartbeat_mode": "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY" if accepted else "FAIL_CLOSED",
        "heartbeat_trigger": "OPERATOR_MANUAL",
        "heartbeat_sequence": 1,
        "heartbeat_count": 1,
        "paper_promoted": accepted,
        "promotion_granted": accepted,
        "promotion_scope": "PAPER_ONLY_SIMULATION_ONLY",
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE74_NEXT_BLOCKER if accepted else DERIBIT_PHASE74_FALLBACK_BLOCKER,
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _deribit_connector_ready() -> bool:
    ready = connector_ready_dialects()
    return len(ready) == 1 and all(
        dialect.venue_id == VenueId.DERIBIT and dialect.dialect_id == DERIBIT_PHASE68_REQUIRED_DIALECT_ID
        for dialect in ready
    )


__all__ = [
    "DERIBIT_APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_ID",
    "DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL",
    "DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256",
    "DERIBIT_PHASE74_NEXT_BLOCKER",
    "DERIBIT_PHASE74_FALLBACK_BLOCKER",
    "DeribitApprovedPaperRuntimeHeartbeatExecutionResult",
    "execute_deribit_approved_paper_runtime_heartbeat_execution",
]
