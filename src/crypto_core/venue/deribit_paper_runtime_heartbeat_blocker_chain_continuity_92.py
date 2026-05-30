from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_92_ID = (
    "deterministic_phase92_paper_runtime_heartbeat_blocker_chain_continuity"
)
DERIBIT_PHASE92_BLOCKER_CHAIN_CONTINUITY_ARTIFACT = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_92B.json"
)
DERIBIT_PHASE92_NEXT_BLOCKER = "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING"
DERIBIT_PHASE92_FALLBACK_BLOCKER = "BLOCKER_CHAIN_CONTINUITY_REPORT_NOT_READY"

DERIBIT_PHASE91_BLOCKER_CHAIN_CONTINUITY = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_91B.json"
)
DERIBIT_PHASE91_BLOCKER_CHAIN_CONTINUITY_SHA256 = "3cbb01e7ffa5fa45f8f7db27566c7dfd05d1fd6459d71694963a40325d31831b"

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


class DeribitPaperRuntimeHeartbeatBlockerChainContinuity92Result(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_92(
    phase91_blocker_chain_continuity_artifact: object,
) -> DeribitPaperRuntimeHeartbeatBlockerChainContinuity92Result:
    reasons: list[str] = []
    phase91 = (
        phase91_blocker_chain_continuity_artifact if isinstance(phase91_blocker_chain_continuity_artifact, dict) else {}
    )

    if not phase91:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:phase91_artifact_missing")

    if phase91:
        if (
            phase91.get("schema_version") != "deribit_paper_runtime_heartbeat_blocker_chain_continuity.v1"
            or phase91.get("phase") != "91"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:phase91_artifact_malformed")
        if _canonical_sha256(phase91) != DERIBIT_PHASE91_BLOCKER_CHAIN_CONTINUITY_SHA256:
            reasons.append(
                "deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:phase91_blocker_chain_continuity_drift"
            )

    if phase91 and phase91.get("blocker_chain_continuity") != "PASS":
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:blocker_chain_continuity_invalid")

    for field in _FALSE_SCOPE:
        if phase91 and phase91.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase91 and phase91.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:{field}_invalid")

    if phase91 and phase91.get("connector_ready_dialects_count") != 1:
        reasons.append(
            "deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:connector_ready_dialects_count_invalid"
        )

    if phase91 and phase91.get("provenance_reason") != DERIBIT_PHASE92_NEXT_BLOCKER:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:provenance_reason_invalid")

    if len(connector_ready_dialects()) != 1:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_blocker_chain_continuity_92:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatBlockerChainContinuity92Result(
        accepted,
        reason_code,
        reasons_t,
        _artifact_payload(accepted, reason_code, reasons_t),
    )


def _artifact_payload(accepted: bool, reason_code: str, rejection_reasons: tuple[str, ...]) -> dict[str, object]:
    return {
        "schema_version": "deribit_paper_runtime_heartbeat_blocker_chain_continuity.v1",
        "phase": "92",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_92_ID,
        "source_phase91_blocker_chain_continuity": DERIBIT_PHASE91_BLOCKER_CHAIN_CONTINUITY,
        "source_phase91_blocker_chain_continuity_sha256": DERIBIT_PHASE91_BLOCKER_CHAIN_CONTINUITY_SHA256,
        "blocker_chain_continuity": "PASS" if accepted else "FAIL_CLOSED",
        "b5_status": "BLOCKED",
        "connector_enablement_ready": False,
        "provenance_reason": DERIBIT_PHASE92_NEXT_BLOCKER,
        **dict.fromkeys(_FALSE_SCOPE, False),
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE92_NEXT_BLOCKER if accepted else DERIBIT_PHASE92_FALLBACK_BLOCKER,
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
