from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_approved_paper_runtime_start import DERIBIT_PHASE68_REQUIRED_DIALECT_ID
from crypto_core.venue.deribit_paper_runtime_heartbeat import (
    DERIBIT_PHASE69_RUNTIME_START_TELEMETRY,
    DERIBIT_PHASE69_RUNTIME_START_TELEMETRY_SHA256,
)
from crypto_core.venue.deribit_paper_runtime_heartbeat_telemetry import (
    DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT,
    DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT_SHA256,
    DERIBIT_PHASE71_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_REVIEW_PROPOSAL_ID = "deterministic_phase72_paper_runtime_heartbeat_review_proposal"
DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT = "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json"
DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256 = "079ef1023465a05eb905d87d469e24b04e47148f0e5920b197c58ebe3e5d499e"
DERIBIT_PHASE72_NEXT_BLOCKER = "PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_NOT_READY"
DERIBIT_PHASE72_FALLBACK_BLOCKER = "PAPER_RUNTIME_HEARTBEAT_REVIEW_PROPOSAL_NOT_READY"

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


class DeribitPaperRuntimeHeartbeatReviewProposalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def evaluate_deribit_paper_runtime_heartbeat_review_proposal(
    phase71_heartbeat_telemetry_artifact: object,
) -> DeribitPaperRuntimeHeartbeatReviewProposalResult:
    reasons: list[str] = []
    phase71 = phase71_heartbeat_telemetry_artifact if isinstance(phase71_heartbeat_telemetry_artifact, dict) else {}

    if not phase71:
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:phase71_artifact_missing")
    if phase71:
        if (
            phase71.get("schema_version") != "deribit_paper_runtime_heartbeat_telemetry_audit.v1"
            or phase71.get("phase") != "71"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_review_proposal:phase71_artifact_malformed")
        if _canonical_sha256(phase71) != DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat_review_proposal:phase71_provenance_drift")
    if phase71 and phase71.get("heartbeat_telemetry_status") != "PASS":
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:heartbeat_telemetry_not_pass")
    if phase71 and phase71.get("next_blocker") != DERIBIT_PHASE71_NEXT_BLOCKER:
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:phase71_next_blocker_drift")
    if phase71 and phase71.get("heartbeat_status") != "RECORDED":
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:heartbeat_status_invalid")
    if phase71 and phase71.get("heartbeat_mode") != "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY":
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:heartbeat_mode_invalid")
    if phase71 and (phase71.get("runtime_enabled") is not True or phase71.get("runtime_started") is not True):
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:runtime_state_invalid")
    for field in _FALSE_SCOPE:
        if phase71 and phase71.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_review_proposal:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase71 and phase71.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_review_proposal:{field}_invalid")
    if phase71 and phase71.get("connector_ready_dialects_count") != 1:
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:connector_ready_dialects_count_invalid")
    if not _deribit_connector_ready():
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:connector_ready_dialects_mismatch")
    if phase71 and (
        phase71.get("source_phase70_operator_triggered_heartbeat") != DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT
        or phase71.get("source_phase70_operator_triggered_heartbeat_sha256")
        != DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT_SHA256
    ):
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:phase70_source_chain_drift")
    if phase71 and (
        phase71.get("source_phase69_runtime_start_telemetry") != DERIBIT_PHASE69_RUNTIME_START_TELEMETRY
        or phase71.get("source_phase69_runtime_start_telemetry_sha256")
        != DERIBIT_PHASE69_RUNTIME_START_TELEMETRY_SHA256
    ):
        reasons.append("deribit_paper_runtime_heartbeat_review_proposal:phase69_source_chain_drift")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_review_proposal:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatReviewProposalResult(
        accepted, reason_code, reasons_t, _artifact_payload(accepted, reason_code, reasons_t)
    )


def _artifact_payload(accepted: bool, reason_code: str, rejection_reasons: tuple[str, ...]) -> dict[str, object]:
    return {
        "schema_version": "deribit_paper_runtime_heartbeat_review_proposal.v1",
        "phase": "72",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_REVIEW_PROPOSAL_ID,
        "source_phase71_heartbeat_telemetry_audit": DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
        "source_phase71_heartbeat_telemetry_audit_sha256": DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
        "source_phase70_operator_triggered_heartbeat": DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT,
        "source_phase70_operator_triggered_heartbeat_sha256": DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT_SHA256,
        "source_phase69_runtime_start_telemetry": DERIBIT_PHASE69_RUNTIME_START_TELEMETRY,
        "source_phase69_runtime_start_telemetry_sha256": DERIBIT_PHASE69_RUNTIME_START_TELEMETRY_SHA256,
        "proposal_status": "READY_FOR_OPERATOR_REVIEW" if accepted else "FAIL_CLOSED",
        "approval_status": "NOT_APPROVED",
        "operator_id": None,
        "reviewed_at_iso": None,
        "approval_decision": None,
        "heartbeat_telemetry_status": "PASS" if accepted else "FAIL_CLOSED",
        "heartbeat_status": "RECORDED" if accepted else "FAIL_CLOSED",
        "heartbeat_mode": "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY" if accepted else "FAIL_CLOSED",
        "heartbeat_trigger": "OPERATOR_MANUAL",
        "heartbeat_sequence": 1,
        "heartbeat_count": 1,
        "runtime_enabled": accepted,
        "runtime_started": accepted,
        **dict.fromkeys(_FALSE_SCOPE, False),
        "paper_promoted": accepted,
        "promotion_granted": accepted,
        "promotion_scope": "PAPER_ONLY_SIMULATION_ONLY",
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE72_NEXT_BLOCKER if accepted else DERIBIT_PHASE72_FALLBACK_BLOCKER,
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
    "DERIBIT_PAPER_RUNTIME_HEARTBEAT_REVIEW_PROPOSAL_ID",
    "DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT",
    "DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256",
    "DERIBIT_PHASE72_NEXT_BLOCKER",
    "DERIBIT_PHASE72_FALLBACK_BLOCKER",
    "DeribitPaperRuntimeHeartbeatReviewProposalResult",
    "evaluate_deribit_paper_runtime_heartbeat_review_proposal",
]
