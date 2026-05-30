from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_ID = (
    "deterministic_phase77_paper_runtime_heartbeat_provenance_gate_status"
)
DERIBIT_PHASE77_PROVENANCE_GATE_STATUS_ARTIFACT = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json"
)
DERIBIT_PHASE77_NEXT_BLOCKER = "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING"
DERIBIT_PHASE77_FALLBACK_BLOCKER = "PROVENANCE_GATE_STATUS_REPORT_NOT_READY"

DERIBIT_PHASE76_POST_AUDIT = "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json"
DERIBIT_PHASE76_POST_AUDIT_SHA256 = "3a227d33d72fbdda557ef6c7bc2f2e83f0550e19853acb07ebf439024d07d043"

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


class DeribitPaperRuntimeHeartbeatProvenanceGateStatusResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_runtime_heartbeat_provenance_gate_status(
    phase76_post_audit_artifact: object,
) -> DeribitPaperRuntimeHeartbeatProvenanceGateStatusResult:
    reasons: list[str] = []
    phase76 = phase76_post_audit_artifact if isinstance(phase76_post_audit_artifact, dict) else {}

    if not phase76:
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_status:phase76_artifact_missing")

    if phase76:
        if (
            phase76.get("schema_version") != "deribit_paper_runtime_heartbeat_execution_post_audit.v1"
            or phase76.get("phase") != "76"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_status:phase76_artifact_malformed")
        if _canonical_sha256(phase76) != DERIBIT_PHASE76_POST_AUDIT_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_status:phase76_provenance_drift")

    if phase76 and phase76.get("heartbeat_execution_post_audit_status") != "PASS":
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_status:post_audit_status_invalid")

    for field in _FALSE_SCOPE:
        if phase76 and phase76.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_provenance_gate_status:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase76 and phase76.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_provenance_gate_status:{field}_invalid")

    if phase76 and phase76.get("connector_ready_dialects_count") != 1:
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_status:connector_ready_dialects_count_invalid")

    if len(connector_ready_dialects()) != 1:
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_status:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_provenance_gate_status:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatProvenanceGateStatusResult(
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
        "schema_version": "deribit_paper_runtime_heartbeat_provenance_gate_status.v1",
        "phase": "77",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_ID,
        "source_phase76_post_audit": DERIBIT_PHASE76_POST_AUDIT,
        "source_phase76_post_audit_sha256": DERIBIT_PHASE76_POST_AUDIT_SHA256,
        "heartbeat_execution_post_audit_status": "PASS" if accepted else "FAIL_CLOSED",
        "b5_status": "BLOCKED",
        "connector_enablement_ready": False,
        "provenance_reason": DERIBIT_PHASE77_NEXT_BLOCKER,
        **dict.fromkeys(_FALSE_SCOPE, False),
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE77_NEXT_BLOCKER if accepted else DERIBIT_PHASE77_FALLBACK_BLOCKER,
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
