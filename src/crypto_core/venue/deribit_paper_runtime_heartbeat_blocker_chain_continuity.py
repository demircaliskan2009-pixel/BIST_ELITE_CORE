from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_ID = (
    "deterministic_phase80_paper_runtime_heartbeat_blocker_chain_continuity"
)
DERIBIT_PHASE80_BLOCKER_CHAIN_CONTINUITY_ARTIFACT = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_80B.json"
)
DERIBIT_PHASE80_NEXT_BLOCKER = "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING"
DERIBIT_PHASE80_FALLBACK_BLOCKER = "BLOCKER_CHAIN_CONTINUITY_REPORT_NOT_READY"

DERIBIT_PHASE79_BLOCKER_PERSISTENCE = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_79B.json"
)
DERIBIT_PHASE79_BLOCKER_PERSISTENCE_SHA256 = "60aa85c41971d4d8d6b21562701d75b2538cf3ccf66ceb020b51de9d3ae57a41"

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


class DeribitPaperRuntimeHeartbeatBlockerChainContinuityResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity(
    phase79_blocker_persistence_artifact: object,
) -> DeribitPaperRuntimeHeartbeatBlockerChainContinuityResult:
    reasons: list[str] = []
    phase79 = phase79_blocker_persistence_artifact if isinstance(phase79_blocker_persistence_artifact, dict) else {}

    if not phase79:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity:phase79_artifact_missing")

    if phase79:
        if (
            phase79.get("schema_version") != "deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence.v1"
            or phase79.get("phase") != "79"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity:phase79_artifact_malformed")
        if _canonical_sha256(phase79) != DERIBIT_PHASE79_BLOCKER_PERSISTENCE_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity:phase79_blocker_persistence_drift")

    if phase79 and phase79.get("provenance_gate_blocker_persistence") != "PASS":
        reasons.append(
            "deribit_paper_runtime_heartbeat_blocker_chain_continuity:provenance_gate_blocker_persistence_invalid"
        )

    for field in _FALSE_SCOPE:
        if phase79 and phase79.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_blocker_chain_continuity:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase79 and phase79.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_blocker_chain_continuity:{field}_invalid")

    if phase79 and phase79.get("connector_ready_dialects_count") != 1:
        reasons.append(
            "deribit_paper_runtime_heartbeat_blocker_chain_continuity:connector_ready_dialects_count_invalid"
        )

    if phase79 and phase79.get("provenance_reason") != DERIBIT_PHASE80_NEXT_BLOCKER:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity:provenance_reason_invalid")

    if len(connector_ready_dialects()) != 1:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_blocker_chain_continuity:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatBlockerChainContinuityResult(
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
        "schema_version": "deribit_paper_runtime_heartbeat_blocker_chain_continuity.v1",
        "phase": "80",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_ID,
        "source_phase79_blocker_persistence": DERIBIT_PHASE79_BLOCKER_PERSISTENCE,
        "source_phase79_blocker_persistence_sha256": DERIBIT_PHASE79_BLOCKER_PERSISTENCE_SHA256,
        "blocker_chain_continuity": "PASS" if accepted else "FAIL_CLOSED",
        "b5_status": "BLOCKED",
        "connector_enablement_ready": False,
        "provenance_reason": DERIBIT_PHASE80_NEXT_BLOCKER,
        **dict.fromkeys(_FALSE_SCOPE, False),
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE80_NEXT_BLOCKER if accepted else DERIBIT_PHASE80_FALLBACK_BLOCKER,
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
