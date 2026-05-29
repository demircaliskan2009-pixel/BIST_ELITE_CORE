from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_ID = (
    "deterministic_phase78_paper_runtime_heartbeat_provenance_gate_continuity"
)
DERIBIT_PHASE78_PROVENANCE_GATE_CONTINUITY_ARTIFACT = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_78B.json"
)
DERIBIT_PHASE78_NEXT_BLOCKER = "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING"
DERIBIT_PHASE78_FALLBACK_BLOCKER = "PROVENANCE_GATE_CONTINUITY_REPORT_NOT_READY"

DERIBIT_PHASE77_PROVENANCE_GATE_STATUS = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json"
)
DERIBIT_PHASE77_PROVENANCE_GATE_STATUS_SHA256 = "e1747b03ce6e966de84e8d165aac4be1f37c4cf06369688c8cf5a2aad09f62ed"

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


class DeribitPaperRuntimeHeartbeatProvenanceGateContinuityResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(
    phase77_provenance_gate_status_artifact: object,
) -> DeribitPaperRuntimeHeartbeatProvenanceGateContinuityResult:
    reasons: list[str] = []
    phase77 = (
        phase77_provenance_gate_status_artifact if isinstance(phase77_provenance_gate_status_artifact, dict) else {}
    )

    if not phase77:
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_continuity:phase77_artifact_missing")

    if phase77:
        if (
            phase77.get("schema_version") != "deribit_paper_runtime_heartbeat_provenance_gate_status.v1"
            or phase77.get("phase") != "77"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_continuity:phase77_artifact_malformed")
        if _canonical_sha256(phase77) != DERIBIT_PHASE77_PROVENANCE_GATE_STATUS_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_continuity:phase77_provenance_drift")

    if phase77 and phase77.get("heartbeat_execution_post_audit_status") != "PASS":
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_continuity:provenance_gate_status_invalid")

    for field in _FALSE_SCOPE:
        if phase77 and phase77.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_provenance_gate_continuity:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase77 and phase77.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_provenance_gate_continuity:{field}_invalid")

    if phase77 and phase77.get("connector_ready_dialects_count") != 1:
        reasons.append(
            "deribit_paper_runtime_heartbeat_provenance_gate_continuity:connector_ready_dialects_count_invalid"
        )

    if phase77 and phase77.get("provenance_reason") != DERIBIT_PHASE78_NEXT_BLOCKER:
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_continuity:provenance_reason_invalid")

    if len(connector_ready_dialects()) != 1:
        reasons.append("deribit_paper_runtime_heartbeat_provenance_gate_continuity:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_provenance_gate_continuity:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatProvenanceGateContinuityResult(
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
        "schema_version": "deribit_paper_runtime_heartbeat_provenance_gate_continuity.v1",
        "phase": "78",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_ID,
        "source_phase77_provenance_gate_status": DERIBIT_PHASE77_PROVENANCE_GATE_STATUS,
        "source_phase77_provenance_gate_status_sha256": DERIBIT_PHASE77_PROVENANCE_GATE_STATUS_SHA256,
        "provenance_gate_status_continuity": "PASS" if accepted else "FAIL_CLOSED",
        "b5_status": "BLOCKED",
        "connector_enablement_ready": False,
        "provenance_reason": DERIBIT_PHASE78_NEXT_BLOCKER,
        **dict.fromkeys(_FALSE_SCOPE, False),
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE78_NEXT_BLOCKER if accepted else DERIBIT_PHASE78_FALLBACK_BLOCKER,
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
