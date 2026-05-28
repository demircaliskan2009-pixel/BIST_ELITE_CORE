from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_approved_paper_runtime_start import DERIBIT_PHASE68_REQUIRED_DIALECT_ID
from crypto_core.venue.deribit_paper_runtime_start_telemetry import (
    DERIBIT_PHASE68_RUNTIME_START_EXECUTION,
    DERIBIT_PHASE68_RUNTIME_START_EXECUTION_SHA256,
    DERIBIT_PHASE69_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_HEARTBEAT_ID = "deterministic_phase70_paper_runtime_operator_triggered_heartbeat"
DERIBIT_PHASE69_RUNTIME_START_TELEMETRY = "docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json"
DERIBIT_PHASE69_RUNTIME_START_TELEMETRY_SHA256 = "5d5b6c681eb93efd38b028b4e074ccd624827a44a5d37d83dd8613c79e12e8a2"
DERIBIT_PHASE70_NEXT_BLOCKER = "PAPER_RUNTIME_HEARTBEAT_TELEMETRY_NOT_READY"
DERIBIT_PHASE70_FALLBACK_BLOCKER = DERIBIT_PHASE69_NEXT_BLOCKER

_TRUE_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_FALSE_SCOPE = tuple(
    "runtime_loop_started runtime_order_routing_enabled live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation strategy_signal_generated order_intent_generated".split()
)


class DeribitPaperRuntimeHeartbeatResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def record_deribit_paper_runtime_heartbeat(
    phase69_runtime_start_telemetry_artifact: object,
    phase68_runtime_start_execution_artifact: object,
) -> DeribitPaperRuntimeHeartbeatResult:
    reasons: list[str] = []
    phase69 = (
        phase69_runtime_start_telemetry_artifact if isinstance(phase69_runtime_start_telemetry_artifact, dict) else {}
    )
    phase68 = (
        phase68_runtime_start_execution_artifact if isinstance(phase68_runtime_start_execution_artifact, dict) else {}
    )

    if not phase69:
        reasons.append("deribit_paper_runtime_heartbeat:phase69_artifact_missing")
    if not phase68:
        reasons.append("deribit_paper_runtime_heartbeat:phase68_artifact_missing")
    if phase69:
        if (
            phase69.get("schema_version") != "deribit_paper_runtime_start_telemetry_audit.v1"
            or phase69.get("phase") != "69"
        ):
            reasons.append("deribit_paper_runtime_heartbeat:phase69_artifact_malformed")
        if _canonical_sha256(phase69) != DERIBIT_PHASE69_RUNTIME_START_TELEMETRY_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat:phase69_provenance_drift")
        if (
            phase69.get("source_phase68_runtime_start_execution") != DERIBIT_PHASE68_RUNTIME_START_EXECUTION
            or phase69.get("source_phase68_runtime_start_execution_sha256")
            != DERIBIT_PHASE68_RUNTIME_START_EXECUTION_SHA256
        ):
            reasons.append("deribit_paper_runtime_heartbeat:phase69_source_chain_drift")
        if (
            phase69.get("runtime_start_telemetry_status") != "PASS"
            or phase69.get("runtime_enabled") is not True
            or phase69.get("runtime_started") is not True
        ):
            reasons.append("deribit_paper_runtime_heartbeat:phase69_runtime_state_invalid")
    if phase68:
        if (
            phase68.get("schema_version") != "deribit_approved_paper_runtime_start_execution.v1"
            or phase68.get("phase") != "68"
        ):
            reasons.append("deribit_paper_runtime_heartbeat:phase68_artifact_malformed")
        if _canonical_sha256(phase68) != DERIBIT_PHASE68_RUNTIME_START_EXECUTION_SHA256:
            reasons.append("deribit_paper_runtime_heartbeat:phase68_provenance_drift")
        if (
            phase68.get("runtime_start_execution_status") != "EXECUTED"
            or phase68.get("runtime_enabled") is not True
            or phase68.get("runtime_started") is not True
        ):
            reasons.append("deribit_paper_runtime_heartbeat:phase68_runtime_state_invalid")
    for field in (
        "runtime_loop_started",
        "runtime_order_routing_enabled",
        "live_ready",
        "shadow_ready",
        "scheduler_enabled",
        "auto_loop_enabled",
        "live_enabled",
        "shadow_enabled",
        "campaign_execution",
        "session_execution",
        "run_execution",
        "ledger_mutation",
    ):
        if phase69 and phase69.get(field) is not False:
            reasons.append(f"deribit_paper_runtime_heartbeat:{field}_invalid")
    for field in _TRUE_FLAGS:
        if phase69 and phase69.get(field) is not True:
            reasons.append(f"deribit_paper_runtime_heartbeat:{field}_invalid")
    if phase69 and phase69.get("connector_ready_dialects_count") != 1:
        reasons.append("deribit_paper_runtime_heartbeat:connector_ready_dialects_count_invalid")
    if not _deribit_connector_ready():
        reasons.append("deribit_paper_runtime_heartbeat:connector_ready_dialects_mismatch")

    reasons_t = tuple(dict.fromkeys(reasons))
    accepted = not reasons_t
    reason_code = "deribit_paper_runtime_heartbeat:accepted" if accepted else reasons_t[0]
    return DeribitPaperRuntimeHeartbeatResult(
        accepted, reason_code, reasons_t, _artifact_payload(accepted, reason_code, reasons_t)
    )


def _artifact_payload(accepted: bool, reason_code: str, rejection_reasons: tuple[str, ...]) -> dict[str, object]:
    return {
        "schema_version": "deribit_paper_runtime_operator_triggered_heartbeat.v1",
        "phase": "70",
        "source": DERIBIT_PAPER_RUNTIME_HEARTBEAT_ID,
        "source_phase69_runtime_start_telemetry": DERIBIT_PHASE69_RUNTIME_START_TELEMETRY,
        "source_phase69_runtime_start_telemetry_sha256": DERIBIT_PHASE69_RUNTIME_START_TELEMETRY_SHA256,
        "source_phase68_runtime_start_execution": DERIBIT_PHASE68_RUNTIME_START_EXECUTION,
        "source_phase68_runtime_start_execution_sha256": DERIBIT_PHASE68_RUNTIME_START_EXECUTION_SHA256,
        "heartbeat_status": "RECORDED" if accepted else "FAIL_CLOSED",
        "heartbeat_mode": "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY" if accepted else "FAIL_CLOSED",
        "runtime_enabled": accepted,
        "runtime_started": accepted,
        **dict.fromkeys(_FALSE_SCOPE, False),
        "heartbeat_trigger": "OPERATOR_MANUAL",
        "heartbeat_sequence": 1,
        "paper_promoted": accepted,
        "promotion_granted": accepted,
        "promotion_scope": "PAPER_ONLY_SIMULATION_ONLY",
        **dict.fromkeys(_TRUE_FLAGS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE70_NEXT_BLOCKER if accepted else DERIBIT_PHASE70_FALLBACK_BLOCKER,
    }


def _deribit_connector_ready() -> bool:
    ready = connector_ready_dialects()
    return len(ready) == 1 and all(
        d.venue_id == VenueId.DERIBIT and d.dialect_id == DERIBIT_PHASE68_REQUIRED_DIALECT_ID for d in ready
    )


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "DERIBIT_PAPER_RUNTIME_HEARTBEAT_ID",
    "DERIBIT_PHASE69_RUNTIME_START_TELEMETRY",
    "DERIBIT_PHASE69_RUNTIME_START_TELEMETRY_SHA256",
    "DERIBIT_PHASE70_NEXT_BLOCKER",
    "DERIBIT_PHASE70_FALLBACK_BLOCKER",
    "DeribitPaperRuntimeHeartbeatResult",
    "record_deribit_paper_runtime_heartbeat",
]
