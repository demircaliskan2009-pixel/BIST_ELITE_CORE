from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_approved_paper_runtime_start import (
    DERIBIT_APPROVED_PAPER_RUNTIME_START_ID,
    DERIBIT_PHASE67_RUNTIME_START_APPROVAL,
    DERIBIT_PHASE67_RUNTIME_START_APPROVAL_SHA256,
    DERIBIT_PHASE68_NEXT_BLOCKER,
    DERIBIT_PHASE68_REQUIRED_DIALECT_ID,
)
from crypto_core.venue.deribit_paper_runtime_start_approval import (
    DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION,
    DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_START_TELEMETRY_ID = "deterministic_phase69_paper_runtime_start_telemetry"
DERIBIT_PHASE68_RUNTIME_START_EXECUTION = "docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_START_EXECUTION_68B.json"
DERIBIT_PHASE68_RUNTIME_START_EXECUTION_SHA256 = "bc402eea5067accf3d57219fec979bc857386ef43bfad4eee60a9e92d9c9f550"
DERIBIT_PHASE69_NEXT_BLOCKER = "PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_NOT_READY"
DERIBIT_PHASE69_FALLBACK_BLOCKER = DERIBIT_PHASE68_NEXT_BLOCKER

_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE68_FALSE_SCOPE_FIELDS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE69_TELEMETRY_CHECKS = tuple(
    "source_phase68_runtime_start_execution_exists phase68_runtime_start_executed runtime_enabled_true runtime_started_true no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved no_campaign_session_run_scope_preserved source_phase67_65_provenance_stable connector_ready_dialects_preserved".split()
)


class DeribitPaperRuntimeStartTelemetryResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_paper_runtime_start_telemetry(
    phase68_runtime_start_execution_artifact: object,
    phase67_runtime_start_approval_artifact: object,
    phase65_runtime_enablement_execution_artifact: object,
) -> DeribitPaperRuntimeStartTelemetryResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase68_rejection_reasons(
                    phase68_runtime_start_execution_artifact,
                    phase67_runtime_start_approval_artifact,
                    phase65_runtime_enablement_execution_artifact,
                ),
                *_phase67_rejection_reasons(phase67_runtime_start_approval_artifact),
                *_phase65_rejection_reasons(phase65_runtime_enablement_execution_artifact),
                *(
                    ()
                    if _deribit_connector_ready()
                    else ("deribit_paper_runtime_start_telemetry:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_runtime_start_telemetry:accepted" if accepted else reasons[0]
    return DeribitPaperRuntimeStartTelemetryResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase68_runtime_start_execution_artifact,
            phase67_runtime_start_approval_artifact,
            phase65_runtime_enablement_execution_artifact,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase68_rejection_reasons(
    phase68_runtime_start_execution_artifact: object,
    phase67_runtime_start_approval_artifact: object,
    phase65_runtime_enablement_execution_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase68_runtime_start_execution_artifact, dict):
        return ("deribit_paper_runtime_start_telemetry:phase68_artifact_missing",)

    phase68 = phase68_runtime_start_execution_artifact
    phase67 = (
        phase67_runtime_start_approval_artifact if isinstance(phase67_runtime_start_approval_artifact, dict) else {}
    )
    phase65 = (
        phase65_runtime_enablement_execution_artifact
        if isinstance(phase65_runtime_enablement_execution_artifact, dict)
        else {}
    )

    reasons: list[str] = []
    if (
        phase68.get("schema_version") != "deribit_approved_paper_runtime_start_execution.v1"
        or phase68.get("phase") != "68"
        or phase68.get("source") != DERIBIT_APPROVED_PAPER_RUNTIME_START_ID
        or phase68.get("source_phase67_runtime_start_approval") != DERIBIT_PHASE67_RUNTIME_START_APPROVAL
        or phase68.get("source_phase67_runtime_start_approval_sha256") != DERIBIT_PHASE67_RUNTIME_START_APPROVAL_SHA256
        or phase68.get("source_phase65_runtime_enablement_execution") != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION
        or phase68.get("source_phase65_runtime_enablement_execution_sha256")
        != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256
        or phase68.get("runtime_start_execution_status") != "EXECUTED"
        or phase68.get("runtime_enabled") is not True
        or phase68.get("runtime_started") is not True
        or phase68.get("paper_promoted") is not True
        or phase68.get("promotion_granted") is not True
        or phase68.get("promotion_scope") != "PAPER_ONLY_SIMULATION_ONLY"
        or phase68.get("reason_code") != "deribit_approved_paper_runtime_start:accepted"
        or phase68.get("rejection_reasons") != []
        or phase68.get("next_blocker") != DERIBIT_PHASE68_NEXT_BLOCKER
        or _canonical_sha256(phase68) != DERIBIT_PHASE68_RUNTIME_START_EXECUTION_SHA256
    ):
        reasons.append("deribit_paper_runtime_start_telemetry:phase68_metadata_invalid")

    if not _bool_fields_match(phase68, _PHASE68_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_paper_runtime_start_telemetry:phase68_scope_flags_invalid")
    if not _bool_fields_match(phase68, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_runtime_start_telemetry:phase68_safety_flags_invalid")
    if not _strict_int_is_one(phase68.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_runtime_start_telemetry:phase68_connector_ready_dialects_invalid")
    if phase68.get("runtime_loop_started") is True:
        reasons.append("deribit_paper_runtime_start_telemetry:runtime_loop_started_true")
    if phase68.get("runtime_order_routing_enabled") is True:
        reasons.append("deribit_paper_runtime_start_telemetry:runtime_order_routing_enabled_true")

    if phase67 and _canonical_sha256(phase67) != DERIBIT_PHASE67_RUNTIME_START_APPROVAL_SHA256:
        reasons.append("deribit_paper_runtime_start_telemetry:phase67_provenance_drift")
    if phase65 and _canonical_sha256(phase65) != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256:
        reasons.append("deribit_paper_runtime_start_telemetry:phase65_provenance_drift")

    if phase67 and phase68.get("source_phase67_runtime_start_approval_sha256") != _canonical_sha256(phase67):
        reasons.append("deribit_paper_runtime_start_telemetry:phase67_source_chain_drift")
    if phase65 and phase68.get("source_phase65_runtime_enablement_execution_sha256") != _canonical_sha256(phase65):
        reasons.append("deribit_paper_runtime_start_telemetry:phase65_source_chain_drift")

    return tuple(dict.fromkeys(reasons))


def _phase67_rejection_reasons(phase67_runtime_start_approval_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase67_runtime_start_approval_artifact, dict):
        return ("deribit_paper_runtime_start_telemetry:phase67_artifact_missing",)
    phase67 = phase67_runtime_start_approval_artifact
    reasons: list[str] = []
    if (
        phase67.get("schema_version") != "deribit_paper_runtime_start_operator_approval.v1"
        or phase67.get("phase") != "67"
        or phase67.get("approval_status") != "APPROVED"
        or phase67.get("runtime_start_approved") is not True
        or phase67.get("runtime_enabled") is not True
        or phase67.get("runtime_started") is not False
    ):
        reasons.append("deribit_paper_runtime_start_telemetry:phase67_metadata_invalid")
    return tuple(reasons)


def _phase65_rejection_reasons(phase65_runtime_enablement_execution_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase65_runtime_enablement_execution_artifact, dict):
        return ("deribit_paper_runtime_start_telemetry:phase65_artifact_missing",)
    phase65 = phase65_runtime_enablement_execution_artifact
    reasons: list[str] = []
    if (
        phase65.get("schema_version") != "deribit_approved_paper_runtime_enablement_execution.v1"
        or phase65.get("phase") != "65"
        or phase65.get("runtime_enablement_execution_status") != "EXECUTED"
        or phase65.get("runtime_enabled") is not True
        or phase65.get("runtime_started") is not False
    ):
        reasons.append("deribit_paper_runtime_start_telemetry:phase65_metadata_invalid")
    return tuple(reasons)


def _artifact_payload(
    phase68_runtime_start_execution_artifact: object,
    phase67_runtime_start_approval_artifact: object,
    phase65_runtime_enablement_execution_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase68 = (
        phase68_runtime_start_execution_artifact if isinstance(phase68_runtime_start_execution_artifact, dict) else {}
    )
    phase67 = (
        phase67_runtime_start_approval_artifact if isinstance(phase67_runtime_start_approval_artifact, dict) else {}
    )
    phase65 = (
        phase65_runtime_enablement_execution_artifact
        if isinstance(phase65_runtime_enablement_execution_artifact, dict)
        else {}
    )

    return {
        "schema_version": "deribit_paper_runtime_start_telemetry_audit.v1",
        "phase": "69",
        "source": DERIBIT_PAPER_RUNTIME_START_TELEMETRY_ID,
        "source_phase68_runtime_start_execution": DERIBIT_PHASE68_RUNTIME_START_EXECUTION,
        "source_phase68_runtime_start_execution_sha256": _canonical_sha256(phase68) if phase68 else None,
        "source_phase67_runtime_start_approval": DERIBIT_PHASE67_RUNTIME_START_APPROVAL,
        "source_phase67_runtime_start_approval_sha256": _canonical_sha256(phase67) if phase67 else None,
        "source_phase65_runtime_enablement_execution": DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION,
        "source_phase65_runtime_enablement_execution_sha256": _canonical_sha256(phase65) if phase65 else None,
        "source_phase68_runtime_start_execution_status": phase68.get("runtime_start_execution_status")
        if accepted
        else "FAIL_CLOSED",
        "runtime_start_telemetry_status": "PASS" if accepted else "FAIL_CLOSED",
        "runtime_enabled": phase68.get("runtime_enabled") if accepted else False,
        "runtime_started": phase68.get("runtime_started") if accepted else False,
        "runtime_mode": "PAPER_ONLY_PASSIVE_STARTED" if accepted else "FAIL_CLOSED",
        "runtime_loop_started": False,
        "runtime_order_routing_enabled": False,
        "paper_promoted": phase68.get("paper_promoted") if accepted else False,
        "promotion_granted": phase68.get("promotion_granted") if accepted else False,
        "promotion_scope": "PAPER_ONLY_SIMULATION_ONLY",
        "live_ready": False,
        "shadow_ready": False,
        "scheduler_enabled": False,
        "auto_loop_enabled": False,
        "live_enabled": False,
        "shadow_enabled": False,
        "campaign_execution": False,
        "session_execution": False,
        "run_execution": False,
        "ledger_mutation": False,
        **dict.fromkeys(_TRUE_SAFETY_FIELDS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "execution_checks": list(_PHASE69_TELEMETRY_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE69_NEXT_BLOCKER if accepted else DERIBIT_PHASE69_FALLBACK_BLOCKER,
    }


def _deribit_connector_ready() -> bool:
    ready = connector_ready_dialects()
    return len(ready) == 1 and all(
        dialect.venue_id == VenueId.DERIBIT and dialect.dialect_id == DERIBIT_PHASE68_REQUIRED_DIALECT_ID
        for dialect in ready
    )


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "DERIBIT_PAPER_RUNTIME_START_TELEMETRY_ID",
    "DERIBIT_PHASE68_RUNTIME_START_EXECUTION",
    "DERIBIT_PHASE68_RUNTIME_START_EXECUTION_SHA256",
    "DERIBIT_PHASE69_NEXT_BLOCKER",
    "DERIBIT_PHASE69_FALLBACK_BLOCKER",
    "DeribitPaperRuntimeStartTelemetryResult",
    "audit_deribit_paper_runtime_start_telemetry",
]
