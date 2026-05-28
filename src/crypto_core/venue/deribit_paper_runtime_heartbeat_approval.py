from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import NamedTuple

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_approved_paper_runtime_start import DERIBIT_PHASE68_REQUIRED_DIALECT_ID
from crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
    DERIBIT_PHASE72_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_APPROVAL_ID = "deterministic_phase73_paper_runtime_heartbeat_operator_approval"
DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json"
)
DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256 = "24a20d61a317cc4c1685ee1bfcca1f6682912c79f482cddbfc9062c7e4506a25"
DERIBIT_PHASE73_NEXT_BLOCKER = "APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_NOT_READY"
DERIBIT_PHASE73_FALLBACK_BLOCKER = DERIBIT_PHASE72_NEXT_BLOCKER
DERIBIT_PHASE73_OPERATOR_ID = "demir_operator"
DERIBIT_PHASE73_APPROVAL_DECISION = "APPROVE_PAPER_RUNTIME_HEARTBEAT_REVIEW"
DERIBIT_PHASE73_REVIEWED_AT_ISO = "2026-05-28T20:04:43Z"
DERIBIT_PHASE73_APPROVAL_SCOPE = "PAPER_ONLY_SIMULATION_ONLY"

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


class DeribitPaperRuntimeHeartbeatApprovalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_paper_runtime_heartbeat_approval(
    phase72_heartbeat_review_proposal_artifact: object,
    phase71_heartbeat_telemetry_artifact: object,
    *,
    operator_id: str,
    approval_decision: str,
    reviewed_at_iso: str,
    approval_scope: str,
) -> DeribitPaperRuntimeHeartbeatApprovalResult:
    reasons: list[str] = []
    phase72 = (
        phase72_heartbeat_review_proposal_artifact
        if isinstance(phase72_heartbeat_review_proposal_artifact, dict)
        else {}
    )
    phase71 = phase71_heartbeat_telemetry_artifact if isinstance(phase71_heartbeat_telemetry_artifact, dict) else {}

    if not phase72:
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase72_artifact_missing")
    if not phase71:
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase71_artifact_missing")

    if phase72:
        if (
            phase72.get("schema_version") != "deribit_paper_runtime_heartbeat_review_proposal.v1"
            or phase72.get("phase") != "72"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_approval:phase72_artifact_malformed")
        if _canonical_sha256(phase72) != DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat_approval:phase72_provenance_drift")

    if phase71:
        if (
            phase71.get("schema_version") != "deribit_paper_runtime_heartbeat_telemetry_audit.v1"
            or phase71.get("phase") != "71"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_approval:phase71_artifact_malformed")
        if _canonical_sha256(phase71) != DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat_approval:phase71_provenance_drift")

    if phase72 and phase72.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("deribit_paper_runtime_heartbeat_approval:proposal_status_invalid")
    if phase72 and phase72.get("approval_status") != "NOT_APPROVED":
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase72_approval_status_invalid")
    if phase72 and phase72.get("operator_id") is not None:
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase72_operator_id_not_null")
    if phase72 and phase72.get("reviewed_at_iso") is not None:
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase72_reviewed_at_iso_not_null")
    if phase72 and phase72.get("approval_decision") is not None:
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase72_approval_decision_not_null")

    if phase72 and phase72.get("runtime_enabled") is not True:
        reasons.append("deribit_paper_runtime_heartbeat_approval:runtime_enabled_invalid")
    if phase72 and phase72.get("runtime_started") is not True:
        reasons.append("deribit_paper_runtime_heartbeat_approval:runtime_started_invalid")

    if phase72 and phase72.get("heartbeat_telemetry_status") != "PASS":
        reasons.append("deribit_paper_runtime_heartbeat_approval:heartbeat_telemetry_status_invalid")
    if phase72 and phase72.get("heartbeat_status") != "RECORDED":
        reasons.append("deribit_paper_runtime_heartbeat_approval:heartbeat_status_invalid")
    if phase72 and phase72.get("heartbeat_mode") != "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY":
        reasons.append("deribit_paper_runtime_heartbeat_approval:heartbeat_mode_invalid")
    if phase72 and phase72.get("heartbeat_trigger") != "OPERATOR_MANUAL":
        reasons.append("deribit_paper_runtime_heartbeat_approval:heartbeat_trigger_invalid")
    if phase72 and phase72.get("heartbeat_sequence") != 1:
        reasons.append("deribit_paper_runtime_heartbeat_approval:heartbeat_sequence_invalid")
    if phase72 and phase72.get("heartbeat_count") != 1:
        reasons.append("deribit_paper_runtime_heartbeat_approval:heartbeat_count_invalid")

    if phase72 and phase72.get("connector_ready_dialects_count") != 1:
        reasons.append("deribit_paper_runtime_heartbeat_approval:connector_ready_dialects_count_invalid")
    if not _deribit_connector_ready():
        reasons.append("deribit_paper_runtime_heartbeat_approval:connector_ready_dialects_mismatch")

    for field in _FALSE_SCOPE:
        if phase72 and phase72.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_approval:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase72 and phase72.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_approval:{field}_invalid")

    if phase72 and phase72.get("source_phase71_heartbeat_telemetry_audit") != DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT:
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase71_source_chain_drift")
    if (
        phase72
        and phase72.get("source_phase71_heartbeat_telemetry_audit_sha256")
        != DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256
    ):
        reasons.append("deribit_paper_runtime_heartbeat_approval:phase71_source_chain_sha_drift")

    if operator_id != DERIBIT_PHASE73_OPERATOR_ID:
        reasons.append("deribit_paper_runtime_heartbeat_approval:operator_id_mismatch")
    if approval_decision != DERIBIT_PHASE73_APPROVAL_DECISION:
        reasons.append("deribit_paper_runtime_heartbeat_approval:approval_decision_mismatch")
    if approval_scope != DERIBIT_PHASE73_APPROVAL_SCOPE:
        reasons.append("deribit_paper_runtime_heartbeat_approval:approval_scope_mismatch")
    if reviewed_at_iso != DERIBIT_PHASE73_REVIEWED_AT_ISO:
        reasons.append("deribit_paper_runtime_heartbeat_approval:reviewed_at_iso_mismatch")
    if not _is_iso_utc_z(reviewed_at_iso):
        reasons.append("deribit_paper_runtime_heartbeat_approval:reviewed_at_iso_invalid")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_approval:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatApprovalResult(
        accepted,
        reason_code,
        reasons_t,
        _artifact_payload(accepted, reason_code, reasons_t, reviewed_at_iso),
    )


def _artifact_payload(
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    reviewed_at_iso: str,
) -> dict[str, object]:
    return {
        "schema_version": "deribit_paper_runtime_heartbeat_operator_approval.v1",
        "phase": "73",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_APPROVAL_ID,
        "source_phase72_heartbeat_review_proposal": DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL,
        "source_phase72_heartbeat_review_proposal_sha256": DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256,
        "source_phase71_heartbeat_telemetry": DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
        "source_phase71_heartbeat_telemetry_sha256": DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
        "proposal_status": "READY_FOR_OPERATOR_REVIEW",
        "approval_status": "APPROVED" if accepted else "FAIL_CLOSED",
        "operator_metadata_required": False,
        "operator_id": DERIBIT_PHASE73_OPERATOR_ID,
        "reviewed_at_iso": reviewed_at_iso,
        "approval_decision": DERIBIT_PHASE73_APPROVAL_DECISION,
        "approval_scope": DERIBIT_PHASE73_APPROVAL_SCOPE,
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
        "next_blocker": DERIBIT_PHASE73_NEXT_BLOCKER if accepted else DERIBIT_PHASE73_FALLBACK_BLOCKER,
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_iso_utc_z(ts: str) -> bool:
    if not isinstance(ts, str) or not ts.endswith("Z"):
        return False
    try:
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _deribit_connector_ready() -> bool:
    ready = connector_ready_dialects()
    return len(ready) == 1 and all(
        dialect.venue_id == VenueId.DERIBIT and dialect.dialect_id == DERIBIT_PHASE68_REQUIRED_DIALECT_ID
        for dialect in ready
    )


__all__ = [
    "DERIBIT_PAPER_RUNTIME_HEARTBEAT_APPROVAL_ID",
    "DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL",
    "DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256",
    "DERIBIT_PHASE73_NEXT_BLOCKER",
    "DERIBIT_PHASE73_FALLBACK_BLOCKER",
    "DERIBIT_PHASE73_OPERATOR_ID",
    "DERIBIT_PHASE73_APPROVAL_DECISION",
    "DERIBIT_PHASE73_REVIEWED_AT_ISO",
    "DERIBIT_PHASE73_APPROVAL_SCOPE",
    "DeribitPaperRuntimeHeartbeatApprovalResult",
    "execute_deribit_paper_runtime_heartbeat_approval",
]
