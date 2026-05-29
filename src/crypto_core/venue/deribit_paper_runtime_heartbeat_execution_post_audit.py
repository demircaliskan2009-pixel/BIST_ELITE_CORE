from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_approved_paper_runtime_start import DERIBIT_PHASE68_REQUIRED_DIALECT_ID
from crypto_core.venue.deribit_paper_runtime_heartbeat_approval import (
    DERIBIT_PHASE73_APPROVAL_SCOPE,
    DERIBIT_PHASE73_OPERATOR_ID,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_ID = (
    "deterministic_phase76_paper_runtime_heartbeat_execution_post_audit"
)
DERIBIT_PHASE76_POST_AUDIT_ARTIFACT = "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json"
DERIBIT_PHASE76_POST_AUDIT_NEXT_BLOCKER = "PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_REPORT_NOT_READY"
DERIBIT_PHASE76_POST_AUDIT_FALLBACK_BLOCKER = "PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_NOT_READY"

DERIBIT_PHASE75_HEARTBEAT_EXECUTION_TELEMETRY = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json"
)
DERIBIT_PHASE75_HEARTBEAT_EXECUTION_TELEMETRY_SHA256 = (
    "9135d10a57a169886fc35db9542c000579bcab42b60740be26eb6681a389c327"
)

_FALSE_SCOPE = tuple(
    "runtime_loop_started runtime_order_routing_enabled live_ready shadow_ready "
    "scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution "
    "session_execution run_execution ledger_mutation strategy_signal_generated order_intent_generated".split()
)
_TRUE_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter "
    "no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


class DeribitPaperRuntimeHeartbeatExecutionPostAuditResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_runtime_heartbeat_execution_post_audit(
    phase75_heartbeat_execution_telemetry_artifact: object,
) -> DeribitPaperRuntimeHeartbeatExecutionPostAuditResult:
    reasons: list[str] = []
    phase75 = (
        phase75_heartbeat_execution_telemetry_artifact
        if isinstance(phase75_heartbeat_execution_telemetry_artifact, dict)
        else {}
    )

    if not phase75:
        reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:phase75_artifact_missing")

    if phase75:
        if (
            phase75.get("schema_version") != "deribit_paper_runtime_heartbeat_execution_telemetry_audit.v1"
            or phase75.get("phase") != "75"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:phase75_artifact_malformed")
        if _canonical_sha256(phase75) != DERIBIT_PHASE75_HEARTBEAT_EXECUTION_TELEMETRY_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:phase75_provenance_drift")

    if phase75:
        if (
            phase75.get("source_phase74_approved_heartbeat_execution")
            != "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:phase74_provenance_drift")
        if (
            phase75.get("source_phase73_heartbeat_operator_approval")
            != "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:phase73_provenance_drift")

    if phase75 and phase75.get("heartbeat_execution_telemetry_status") != "PASS":
        reasons.append(
            "deribit_paper_runtime_heartbeat_execution_post_audit:heartbeat_execution_telemetry_status_invalid"
        )
    if phase75 and phase75.get("heartbeat_execution_status") != "EXECUTED":
        reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:heartbeat_execution_status_invalid")
    if phase75 and phase75.get("runtime_enabled") is not True:
        reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:runtime_enabled_invalid")
    if phase75 and phase75.get("runtime_started") is not True:
        reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:runtime_started_invalid")

    for field in _FALSE_SCOPE:
        if phase75 and phase75.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_execution_post_audit:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase75 and phase75.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_execution_post_audit:{field}_invalid")

    if phase75 and phase75.get("connector_ready_dialects_count") != 1:
        reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:connector_ready_dialects_count_invalid")
    if not _deribit_connector_ready():
        reasons.append("deribit_paper_runtime_heartbeat_execution_post_audit:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_execution_post_audit:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatExecutionPostAuditResult(
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
        "schema_version": "deribit_paper_runtime_heartbeat_execution_post_audit.v1",
        "phase": "76",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_ID,
        "source_phase75_heartbeat_execution_telemetry_audit": DERIBIT_PHASE75_HEARTBEAT_EXECUTION_TELEMETRY,
        "source_phase75_heartbeat_execution_telemetry_audit_sha256": DERIBIT_PHASE75_HEARTBEAT_EXECUTION_TELEMETRY_SHA256,
        "source_phase74_approved_heartbeat_execution": "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json",
        "source_phase74_approved_heartbeat_execution_sha256": "233a5e2ebba8c17d3341e1a38ccb0a6af28359a9339f648cdc4ea205bc75e05a",
        "source_phase73_heartbeat_operator_approval": "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json",
        "source_phase73_heartbeat_operator_approval_sha256": "482be64bad44824f970672f12bcd8418ccafb51df76945c3df4af58a057abfcb",
        "heartbeat_execution_post_audit_status": "PASS" if accepted else "FAIL_CLOSED",
        "heartbeat_execution_telemetry_status": "PASS" if accepted else "FAIL_CLOSED",
        "heartbeat_execution_status": "EXECUTED" if accepted else "FAIL_CLOSED",
        "execution_mode": "APPROVED_PAPER_RUNTIME_HEARTBEAT_ONLY" if accepted else "FAIL_CLOSED",
        "approval_status": "APPROVED" if accepted else "FAIL_CLOSED",
        "operator_id": DERIBIT_PHASE73_OPERATOR_ID,
        "approval_scope": DERIBIT_PHASE73_APPROVAL_SCOPE,
        "runtime_enabled": accepted,
        "runtime_started": accepted,
        "heartbeat_status": "RECORDED" if accepted else "FAIL_CLOSED",
        "heartbeat_mode": "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY" if accepted else "FAIL_CLOSED",
        "heartbeat_trigger": "OPERATOR_MANUAL",
        "heartbeat_sequence": 1,
        "heartbeat_count": 1,
        "paper_promoted": accepted,
        "promotion_granted": accepted,
        "promotion_scope": "PAPER_ONLY_SIMULATION_ONLY",
        **dict.fromkeys(_FALSE_SCOPE, False),
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE76_POST_AUDIT_NEXT_BLOCKER
        if accepted
        else DERIBIT_PHASE76_POST_AUDIT_FALLBACK_BLOCKER,
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
    "DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_ID",
    "DERIBIT_PHASE76_POST_AUDIT_ARTIFACT",
    "DERIBIT_PHASE76_POST_AUDIT_NEXT_BLOCKER",
    "DERIBIT_PHASE76_POST_AUDIT_FALLBACK_BLOCKER",
    "DeribitPaperRuntimeHeartbeatExecutionPostAuditResult",
    "audit_deribit_paper_runtime_heartbeat_execution_post_audit",
]
