from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_91_ID = (
    "deterministic_phase91_paper_runtime_heartbeat_blocker_chain_continuity"
)
DERIBIT_PHASE91_BLOCKER_CHAIN_CONTINUITY_ARTIFACT = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_91B.json"
)
DERIBIT_PHASE91_NEXT_BLOCKER = "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING"
DERIBIT_PHASE91_FALLBACK_BLOCKER = "BLOCKER_CHAIN_CONTINUITY_REPORT_NOT_READY"

DERIBIT_PHASE90_BLOCKER_CHAIN_CONTINUITY = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_90B.json"
)
DERIBIT_PHASE90_BLOCKER_CHAIN_CONTINUITY_SHA256 = "b36a045e82497c1b8c3e1dd4cec41f04b0b2fa814f453738a59600d35576b200"

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


class DeribitPaperRuntimeHeartbeatBlockerChainContinuity91Result(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_91(
    phase90_blocker_chain_continuity_artifact: object,
) -> DeribitPaperRuntimeHeartbeatBlockerChainContinuity91Result:
    reasons: list[str] = []
    phase90 = (
        phase90_blocker_chain_continuity_artifact if isinstance(phase90_blocker_chain_continuity_artifact, dict) else {}
    )

    if not phase90:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:phase90_artifact_missing")

    if phase90:
        if (
            phase90.get("schema_version") != "deribit_paper_runtime_heartbeat_blocker_chain_continuity.v1"
            or phase90.get("phase") != "90"
        ):
            reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:phase90_artifact_malformed")
        if _canonical_sha256(phase90) != DERIBIT_PHASE90_BLOCKER_CHAIN_CONTINUITY_SHA256:
            reasons.append(
                "deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:phase90_blocker_chain_continuity_drift"
            )

    if phase90 and phase90.get("blocker_chain_continuity") != "PASS":
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:blocker_chain_continuity_invalid")

    for field in _FALSE_SCOPE:
        if phase90 and phase90.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase90 and phase90.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:{field}_invalid")

    if phase90 and phase90.get("connector_ready_dialects_count") != 1:
        reasons.append(
            "deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:connector_ready_dialects_count_invalid"
        )

    if phase90 and phase90.get("provenance_reason") != DERIBIT_PHASE91_NEXT_BLOCKER:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:provenance_reason_invalid")

    if len(connector_ready_dialects()) != 1:
        reasons.append("deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat_blocker_chain_continuity_91:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatBlockerChainContinuity91Result(
        accepted,
        reason_code,
        reasons_t,
        _artifact_payload(accepted, reason_code, reasons_t),
    )


def _artifact_payload(accepted: bool, reason_code: str, rejection_reasons: tuple[str, ...]) -> dict[str, object]:
    return {
        "schema_version": "deribit_paper_runtime_heartbeat_blocker_chain_continuity.v1",
        "phase": "91",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_91_ID,
        "source_phase90_blocker_chain_continuity": DERIBIT_PHASE90_BLOCKER_CHAIN_CONTINUITY,
        "source_phase90_blocker_chain_continuity_sha256": DERIBIT_PHASE90_BLOCKER_CHAIN_CONTINUITY_SHA256,
        "blocker_chain_continuity": "PASS" if accepted else "FAIL_CLOSED",
        "b5_status": "BLOCKED",
        "connector_enablement_ready": False,
        "provenance_reason": DERIBIT_PHASE91_NEXT_BLOCKER,
        **dict.fromkeys(_FALSE_SCOPE, False),
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE91_NEXT_BLOCKER if accepted else DERIBIT_PHASE91_FALLBACK_BLOCKER,
    }


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
