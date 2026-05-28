from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_approved_paper_promotion_execution import DERIBIT_PHASE58_PROMOTION_SCOPE
from crypto_core.venue.deribit_approved_paper_runtime_enablement import (
    DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_ID,
    DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL,
    DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL_SHA256,
    DERIBIT_PHASE65_NEXT_BLOCKER,
)
from crypto_core.venue.deribit_operator_runtime_enablement_approval import (
    DERIBIT_PHASE64_APPROVAL_DECISION,
    DERIBIT_PHASE64_OPERATOR_ID,
    DERIBIT_PHASE64_REVIEWED_AT_ISO,
)
from crypto_core.venue.deribit_paper_runtime_start_approval import (
    DERIBIT_PAPER_RUNTIME_START_APPROVAL_ID,
    DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION,
    DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256,
    DERIBIT_PHASE66_RUNTIME_START_PROPOSAL,
    DERIBIT_PHASE66_RUNTIME_START_PROPOSAL_SHA256,
    DERIBIT_PHASE67_APPROVAL_DECISION,
    DERIBIT_PHASE67_NEXT_BLOCKER,
    DERIBIT_PHASE67_OPERATOR_ID,
    DERIBIT_PHASE67_REVIEWED_AT_ISO,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_APPROVED_PAPER_RUNTIME_START_ID = "deterministic_phase68_approved_paper_runtime_start_execution"
DERIBIT_PHASE67_RUNTIME_START_APPROVAL = "docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_APPROVAL_67B.json"
DERIBIT_PHASE67_RUNTIME_START_APPROVAL_SHA256 = "04d4603923a12d518bc49c95800f439558bfb35460f91ff2d6f28b45fd49e5ef"
DERIBIT_PHASE68_REQUIRED_DIALECT_ID = "deribit:l2_orderbook:book_instrument_interval"
DERIBIT_PHASE68_NEXT_BLOCKER = "PAPER_RUNTIME_START_TELEMETRY_NOT_READY"
DERIBIT_PHASE68_FALLBACK_BLOCKER = DERIBIT_PHASE67_NEXT_BLOCKER
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE65_FALSE_SCOPE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE67_FALSE_SCOPE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE68_FALSE_SCOPE_FIELDS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_APPROVAL_SCOPE_TRUE_FIELDS = tuple(
    "paper_only simulation_only deribit_public_market_data_only no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE68_EXECUTION_CHECKS = tuple(
    "source_phase67_runtime_start_approval_exists phase67_runtime_start_approved phase67_runtime_enabled phase67_runtime_not_started source_phase65_runtime_enablement_exists phase65_runtime_enablement_executed source_chain_stable runtime_started_without_scope_widening no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_PHASE67_APPROVAL_CHECKS = tuple(
    "source_phase66_runtime_start_proposal_exists phase66_ready_for_operator_review phase66_pre_approval_status_not_approved source_phase65_runtime_enablement_exists phase65_runtime_enablement_executed exact_operator_metadata_supplied reviewed_at_iso_utc_z approval_scope_paper_only runtime_enabled_preserved runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)


class DeribitApprovedPaperRuntimeStartResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_approved_paper_runtime_start(
    phase67_runtime_start_approval_artifact: object,
    phase65_runtime_enablement_artifact: object,
) -> DeribitApprovedPaperRuntimeStartResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase67_rejection_reasons(
                    phase67_runtime_start_approval_artifact,
                    phase65_runtime_enablement_artifact,
                ),
                *_phase65_rejection_reasons(phase65_runtime_enablement_artifact),
                *(
                    ()
                    if _deribit_connector_ready()
                    else ("deribit_approved_paper_runtime_start:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_approved_paper_runtime_start:accepted" if accepted else reasons[0]
    return DeribitApprovedPaperRuntimeStartResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase67_runtime_start_approval_artifact,
            phase65_runtime_enablement_artifact,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase67_rejection_reasons(
    phase67_runtime_start_approval_artifact: object,
    phase65_runtime_enablement_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase67_runtime_start_approval_artifact, dict):
        return ("deribit_approved_paper_runtime_start:phase67_artifact_missing",)
    phase65 = phase65_runtime_enablement_artifact if isinstance(phase65_runtime_enablement_artifact, dict) else {}
    reasons: list[str] = []
    if (
        phase67_runtime_start_approval_artifact.get("schema_version")
        != "deribit_paper_runtime_start_operator_approval.v1"
        or phase67_runtime_start_approval_artifact.get("phase") != "67"
        or phase67_runtime_start_approval_artifact.get("source") != DERIBIT_PAPER_RUNTIME_START_APPROVAL_ID
        or phase67_runtime_start_approval_artifact.get("source_phase66_runtime_start_proposal")
        != DERIBIT_PHASE66_RUNTIME_START_PROPOSAL
        or phase67_runtime_start_approval_artifact.get("source_phase66_runtime_start_proposal_sha256")
        != DERIBIT_PHASE66_RUNTIME_START_PROPOSAL_SHA256
        or phase67_runtime_start_approval_artifact.get("source_phase65_runtime_enablement")
        != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION
        or phase67_runtime_start_approval_artifact.get("source_phase65_runtime_enablement_sha256")
        != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256
        or (
            phase65
            and phase67_runtime_start_approval_artifact.get("source_phase65_runtime_enablement_sha256")
            != _canonical_sha256(phase65)
        )
        or phase67_runtime_start_approval_artifact.get("approval_checks") != list(_PHASE67_APPROVAL_CHECKS)
        or phase67_runtime_start_approval_artifact.get("source_phase65_runtime_enablement_sha256")
        != _canonical_sha256(phase65)
        or _canonical_sha256(phase67_runtime_start_approval_artifact) != DERIBIT_PHASE67_RUNTIME_START_APPROVAL_SHA256
        or phase67_runtime_start_approval_artifact.get("source_phase66_proposal_status") != "READY_FOR_OPERATOR_REVIEW"
        or phase67_runtime_start_approval_artifact.get("source_phase66_approval_status") != "NOT_APPROVED"
        or phase67_runtime_start_approval_artifact.get("source_phase65_runtime_enablement_status") != "EXECUTED"
        or phase67_runtime_start_approval_artifact.get("approval_status") != "APPROVED"
        or phase67_runtime_start_approval_artifact.get("operator_id") != DERIBIT_PHASE67_OPERATOR_ID
        or phase67_runtime_start_approval_artifact.get("reviewed_at_iso") != DERIBIT_PHASE67_REVIEWED_AT_ISO
        or phase67_runtime_start_approval_artifact.get("approval_decision") != DERIBIT_PHASE67_APPROVAL_DECISION
        or phase67_runtime_start_approval_artifact.get("runtime_start_approved") is not True
        or phase67_runtime_start_approval_artifact.get("runtime_enabled") is not True
        or phase67_runtime_start_approval_artifact.get("runtime_started") is not False
        or phase67_runtime_start_approval_artifact.get("paper_promoted") is not True
        or phase67_runtime_start_approval_artifact.get("promotion_granted") is not True
        or phase67_runtime_start_approval_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase67_runtime_start_approval_artifact.get("operator_metadata_source") != "explicit_user_approval_in_chat"
        or phase67_runtime_start_approval_artifact.get("reason_code") != "deribit_paper_runtime_start_approval:accepted"
        or phase67_runtime_start_approval_artifact.get("rejection_reasons") != []
        or phase67_runtime_start_approval_artifact.get("next_blocker") != DERIBIT_PHASE67_NEXT_BLOCKER
    ):
        reasons.append("deribit_approved_paper_runtime_start:phase67_metadata_invalid")
    if not _approval_scope_valid(phase67_runtime_start_approval_artifact.get("approval_scope")):
        reasons.append("deribit_approved_paper_runtime_start:phase67_approval_scope_invalid")
    if not _bool_fields_match(phase67_runtime_start_approval_artifact, _PHASE67_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_approved_paper_runtime_start:phase67_scope_flags_invalid")
    if not _bool_fields_match(phase67_runtime_start_approval_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_runtime_start:phase67_safety_flags_invalid")
    if not _strict_int_is_one(phase67_runtime_start_approval_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_approved_paper_runtime_start:phase67_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase65_rejection_reasons(phase65_runtime_enablement_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase65_runtime_enablement_artifact, dict):
        return ("deribit_approved_paper_runtime_start:phase65_artifact_missing",)
    reasons: list[str] = []
    if (
        phase65_runtime_enablement_artifact.get("schema_version")
        != "deribit_approved_paper_runtime_enablement_execution.v1"
        or phase65_runtime_enablement_artifact.get("phase") != "65"
        or phase65_runtime_enablement_artifact.get("source") != DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_ID
        or phase65_runtime_enablement_artifact.get("source_phase64_runtime_enablement_approval")
        != DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL
        or phase65_runtime_enablement_artifact.get("source_phase64_runtime_enablement_approval_sha256")
        != DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL_SHA256
        or _canonical_sha256(phase65_runtime_enablement_artifact) != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256
        or phase65_runtime_enablement_artifact.get("approval_status") != "APPROVED"
        or phase65_runtime_enablement_artifact.get("approval_decision") != DERIBIT_PHASE64_APPROVAL_DECISION
        or phase65_runtime_enablement_artifact.get("operator_id") != DERIBIT_PHASE64_OPERATOR_ID
        or phase65_runtime_enablement_artifact.get("reviewed_at_iso") != DERIBIT_PHASE64_REVIEWED_AT_ISO
        or phase65_runtime_enablement_artifact.get("runtime_enablement_approved") is not True
        or phase65_runtime_enablement_artifact.get("runtime_enablement_execution_status") != "EXECUTED"
        or phase65_runtime_enablement_artifact.get("runtime_enabled") is not True
        or phase65_runtime_enablement_artifact.get("runtime_started") is not False
        or phase65_runtime_enablement_artifact.get("paper_promoted") is not True
        or phase65_runtime_enablement_artifact.get("promotion_granted") is not True
        or phase65_runtime_enablement_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase65_runtime_enablement_artifact.get("next_blocker") != DERIBIT_PHASE65_NEXT_BLOCKER
    ):
        reasons.append("deribit_approved_paper_runtime_start:phase65_metadata_invalid")
    if not _bool_fields_match(phase65_runtime_enablement_artifact, _PHASE65_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_approved_paper_runtime_start:phase65_scope_flags_invalid")
    if not _bool_fields_match(phase65_runtime_enablement_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_runtime_start:phase65_safety_flags_invalid")
    if not _strict_int_is_one(phase65_runtime_enablement_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_approved_paper_runtime_start:phase65_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase67_runtime_start_approval_artifact: object,
    phase65_runtime_enablement_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase67 = (
        phase67_runtime_start_approval_artifact if isinstance(phase67_runtime_start_approval_artifact, dict) else {}
    )
    phase65 = phase65_runtime_enablement_artifact if isinstance(phase65_runtime_enablement_artifact, dict) else {}
    return {
        "schema_version": "deribit_approved_paper_runtime_start_execution.v1",
        "phase": "68",
        "source": DERIBIT_APPROVED_PAPER_RUNTIME_START_ID,
        "source_phase67_runtime_start_approval": DERIBIT_PHASE67_RUNTIME_START_APPROVAL,
        "source_phase67_runtime_start_approval_sha256": _canonical_sha256(phase67) if phase67 else None,
        "source_phase65_runtime_enablement_execution": DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION,
        "source_phase65_runtime_enablement_execution_sha256": _canonical_sha256(phase65) if phase65 else None,
        "source_phase66_runtime_start_proposal": phase67.get("source_phase66_runtime_start_proposal")
        if accepted
        else None,
        "source_phase66_runtime_start_proposal_sha256": phase67.get("source_phase66_runtime_start_proposal_sha256")
        if accepted
        else None,
        "approval_status": phase67.get("approval_status") if accepted else "FAIL_CLOSED",
        "approval_decision": phase67.get("approval_decision") if accepted else "FAIL_CLOSED",
        "operator_id": phase67.get("operator_id") if accepted else None,
        "reviewed_at_iso": phase67.get("reviewed_at_iso") if accepted else None,
        "runtime_start_approved": phase67.get("runtime_start_approved") if accepted else False,
        "runtime_start_execution_status": "EXECUTED" if accepted else "FAIL_CLOSED",
        "runtime_enabled": phase67.get("runtime_enabled") if accepted else False,
        "runtime_started": accepted,
        "paper_promoted": phase67.get("paper_promoted") if accepted else False,
        "promotion_granted": phase67.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
        **dict.fromkeys(_PHASE68_FALSE_SCOPE_FIELDS, False),
        **dict.fromkeys(_TRUE_SAFETY_FIELDS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "execution_checks": list(_PHASE68_EXECUTION_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE68_NEXT_BLOCKER if accepted else DERIBIT_PHASE68_FALLBACK_BLOCKER,
    }


def _approval_scope_valid(value: object) -> bool:
    return isinstance(value, dict) and all(value.get(field) is True for field in _APPROVAL_SCOPE_TRUE_FIELDS)


def _deribit_connector_ready() -> bool:
    ready_dialects = connector_ready_dialects()
    return len(ready_dialects) == 1 and all(
        dialect.venue_id == VenueId.DERIBIT and dialect.dialect_id == DERIBIT_PHASE68_REQUIRED_DIALECT_ID
        for dialect in ready_dialects
    )


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_APPROVED_PAPER_RUNTIME_START_ID",
    "DERIBIT_PHASE67_RUNTIME_START_APPROVAL",
    "DERIBIT_PHASE67_RUNTIME_START_APPROVAL_SHA256",
    "DERIBIT_PHASE68_FALLBACK_BLOCKER",
    "DERIBIT_PHASE68_NEXT_BLOCKER",
    "DeribitApprovedPaperRuntimeStartResult",
    "execute_deribit_approved_paper_runtime_start",
]
