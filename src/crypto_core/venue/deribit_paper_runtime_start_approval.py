from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import NamedTuple

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
from crypto_core.venue.deribit_paper_runtime_start_proposal import (
    DERIBIT_PAPER_RUNTIME_START_PROPOSAL_ID,
    DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION,
    DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256,
    DERIBIT_PHASE66_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_START_APPROVAL_ID = "deterministic_phase67_paper_runtime_start_approval"
DERIBIT_PHASE66_RUNTIME_START_PROPOSAL = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_REVIEW_PROPOSAL_66B.json"
)
DERIBIT_PHASE66_RUNTIME_START_PROPOSAL_SHA256 = "a1d2f675177819fe1a9427785d42d735979a37b7212a430669e156552f18a53b"
DERIBIT_PHASE67_NEXT_BLOCKER = "APPROVED_PAPER_RUNTIME_START_EXECUTION_NOT_READY"
DERIBIT_PHASE67_FALLBACK_BLOCKER = DERIBIT_PHASE66_NEXT_BLOCKER
DERIBIT_PHASE67_OPERATOR_ID = "demir_operator"
DERIBIT_PHASE67_APPROVAL_DECISION = "APPROVE_PAPER_RUNTIME_START_REVIEW"
DERIBIT_PHASE67_REVIEWED_AT_ISO = "2026-05-28T09:36:15Z"
_PLACEHOLDER = "<OPERATOR_REQUIRED>"
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE65_FALSE_SCOPE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE66_FALSE_SCOPE_FIELDS = tuple(
    "runtime_start_approved runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE66_PROPOSAL_CHECKS = tuple(
    "source_runtime_enablement_executed runtime_enabled_but_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_APPROVAL_CHECKS = tuple(
    "source_phase66_runtime_start_proposal_exists phase66_ready_for_operator_review phase66_pre_approval_status_not_approved source_phase65_runtime_enablement_exists phase65_runtime_enablement_executed exact_operator_metadata_supplied reviewed_at_iso_utc_z approval_scope_paper_only runtime_enabled_preserved runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_APPROVAL_SCOPE = dict.fromkeys(
    (
        "paper_only",
        "simulation_only",
        "deribit_public_market_data_only",
        *_TRUE_SAFETY_FIELDS,
    ),
    True,
)


class DeribitPaperRuntimeStartApprovalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_paper_runtime_start_approval(
    phase66_runtime_start_proposal_artifact: object,
    phase65_runtime_enablement_artifact: object,
    *,
    reviewed_at_iso: str,
) -> DeribitPaperRuntimeStartApprovalResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase66_rejection_reasons(
                    phase66_runtime_start_proposal_artifact,
                    phase65_runtime_enablement_artifact,
                ),
                *_phase65_rejection_reasons(phase65_runtime_enablement_artifact),
                *(
                    ()
                    if reviewed_at_iso == DERIBIT_PHASE67_REVIEWED_AT_ISO
                    else ("deribit_paper_runtime_start_approval:reviewed_at_iso_mismatch",)
                ),
                *(
                    ()
                    if _is_utc_z(reviewed_at_iso)
                    else ("deribit_paper_runtime_start_approval:reviewed_at_iso_invalid",)
                ),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_paper_runtime_start_approval:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_runtime_start_approval:accepted" if accepted else reasons[0]
    return DeribitPaperRuntimeStartApprovalResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase66_runtime_start_proposal_artifact,
            phase65_runtime_enablement_artifact,
            reviewed_at_iso,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase66_rejection_reasons(
    phase66_runtime_start_proposal_artifact: object,
    phase65_runtime_enablement_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase66_runtime_start_proposal_artifact, dict):
        return ("deribit_paper_runtime_start_approval:phase66_artifact_missing",)
    phase65 = phase65_runtime_enablement_artifact if isinstance(phase65_runtime_enablement_artifact, dict) else {}
    reasons: list[str] = []
    if (
        phase66_runtime_start_proposal_artifact.get("schema_version")
        != "deribit_paper_runtime_start_operator_review_proposal.v1"
        or phase66_runtime_start_proposal_artifact.get("phase") != "66"
        or phase66_runtime_start_proposal_artifact.get("source") != DERIBIT_PAPER_RUNTIME_START_PROPOSAL_ID
        or phase66_runtime_start_proposal_artifact.get("source_phase65_runtime_enablement")
        != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION
        or phase66_runtime_start_proposal_artifact.get("source_phase65_runtime_enablement_sha256")
        != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256
        or (
            phase65
            and phase66_runtime_start_proposal_artifact.get("source_phase65_runtime_enablement_sha256")
            != _canonical_sha256(phase65)
        )
        or phase66_runtime_start_proposal_artifact.get("source_phase64_runtime_enablement_approval")
        != DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL
        or phase66_runtime_start_proposal_artifact.get("source_phase64_runtime_enablement_approval_sha256")
        != DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL_SHA256
        or _canonical_sha256(phase66_runtime_start_proposal_artifact) != DERIBIT_PHASE66_RUNTIME_START_PROPOSAL_SHA256
        or phase66_runtime_start_proposal_artifact.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW"
        or phase66_runtime_start_proposal_artifact.get("proposal_type") != "OPERATOR_PAPER_RUNTIME_START_REVIEW"
        or phase66_runtime_start_proposal_artifact.get("approval_status") != "NOT_APPROVED"
        or phase66_runtime_start_proposal_artifact.get("operator_metadata_required") is not True
        or phase66_runtime_start_proposal_artifact.get("approval_decision") != "PLACEHOLDER_ONLY"
        or phase66_runtime_start_proposal_artifact.get("runtime_start_approved") is not False
        or phase66_runtime_start_proposal_artifact.get("runtime_enabled") is not True
        or phase66_runtime_start_proposal_artifact.get("runtime_started") is not False
        or phase66_runtime_start_proposal_artifact.get("paper_promoted") is not True
        or phase66_runtime_start_proposal_artifact.get("promotion_granted") is not True
        or phase66_runtime_start_proposal_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase66_runtime_start_proposal_artifact.get("proposal_checks") != list(_PHASE66_PROPOSAL_CHECKS)
        or phase66_runtime_start_proposal_artifact.get("reason_code") != "deribit_paper_runtime_start_proposal:accepted"
        or phase66_runtime_start_proposal_artifact.get("rejection_reasons") != []
        or phase66_runtime_start_proposal_artifact.get("next_blocker") != DERIBIT_PHASE66_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_runtime_start_approval:phase66_metadata_invalid")
    if any(
        phase66_runtime_start_proposal_artifact.get(field) != _PLACEHOLDER
        for field in ("reviewer_id", "reviewed_at_iso", "approval_scope", "approval_notes")
    ):
        reasons.append("deribit_paper_runtime_start_approval:phase66_placeholder_metadata_invalid")
    if not _bool_fields_match(phase66_runtime_start_proposal_artifact, _PHASE66_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_paper_runtime_start_approval:phase66_scope_flags_invalid")
    if not _bool_fields_match(phase66_runtime_start_proposal_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_runtime_start_approval:phase66_safety_flags_invalid")
    if not _strict_int_is_one(phase66_runtime_start_proposal_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_runtime_start_approval:phase66_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase65_rejection_reasons(
    phase65_runtime_enablement_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase65_runtime_enablement_artifact, dict):
        return ("deribit_paper_runtime_start_approval:phase65_artifact_missing",)
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
        reasons.append("deribit_paper_runtime_start_approval:phase65_metadata_invalid")
    if not _bool_fields_match(phase65_runtime_enablement_artifact, _PHASE65_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_paper_runtime_start_approval:phase65_scope_flags_invalid")
    if not _bool_fields_match(phase65_runtime_enablement_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_runtime_start_approval:phase65_safety_flags_invalid")
    if not _strict_int_is_one(phase65_runtime_enablement_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_runtime_start_approval:phase65_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase66_runtime_start_proposal_artifact: object,
    phase65_runtime_enablement_artifact: object,
    reviewed_at_iso: str,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase66 = (
        phase66_runtime_start_proposal_artifact if isinstance(phase66_runtime_start_proposal_artifact, dict) else {}
    )
    phase65 = phase65_runtime_enablement_artifact if isinstance(phase65_runtime_enablement_artifact, dict) else {}
    return {
        "schema_version": "deribit_paper_runtime_start_operator_approval.v1",
        "phase": "67",
        "generated_at": reviewed_at_iso,
        "source": DERIBIT_PAPER_RUNTIME_START_APPROVAL_ID,
        "source_phase66_runtime_start_proposal": DERIBIT_PHASE66_RUNTIME_START_PROPOSAL,
        "source_phase66_runtime_start_proposal_sha256": _canonical_sha256(phase66) if phase66 else None,
        "source_phase65_runtime_enablement": DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION,
        "source_phase65_runtime_enablement_sha256": _canonical_sha256(phase65) if phase65 else None,
        "source_phase66_proposal_status": phase66.get("proposal_status"),
        "source_phase66_approval_status": phase66.get("approval_status"),
        "source_phase65_runtime_enablement_status": phase65.get("runtime_enablement_execution_status"),
        "approval_status": "APPROVED" if accepted else "FAIL_CLOSED",
        "operator_id": DERIBIT_PHASE67_OPERATOR_ID,
        "reviewed_at_iso": reviewed_at_iso,
        "approval_decision": DERIBIT_PHASE67_APPROVAL_DECISION,
        "runtime_start_approved": accepted,
        "runtime_enabled": phase66.get("runtime_enabled") if accepted else False,
        "runtime_started": False,
        "paper_promoted": phase66.get("paper_promoted") if accepted else False,
        "promotion_granted": phase66.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
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
        "ledger_mutated": False,
        "approval_scope": dict(_APPROVAL_SCOPE),
        "operator_metadata_source": "explicit_user_approval_in_chat",
        **dict.fromkeys(_TRUE_SAFETY_FIELDS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "approval_checks": list(_APPROVAL_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE67_NEXT_BLOCKER if accepted else DERIBIT_PHASE67_FALLBACK_BLOCKER,
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_utc_z(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo == timezone.utc
    except ValueError:
        return False


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_PAPER_RUNTIME_START_APPROVAL_ID",
    "DERIBIT_PHASE66_RUNTIME_START_PROPOSAL",
    "DERIBIT_PHASE66_RUNTIME_START_PROPOSAL_SHA256",
    "DERIBIT_PHASE67_APPROVAL_DECISION",
    "DERIBIT_PHASE67_FALLBACK_BLOCKER",
    "DERIBIT_PHASE67_NEXT_BLOCKER",
    "DERIBIT_PHASE67_OPERATOR_ID",
    "DERIBIT_PHASE67_REVIEWED_AT_ISO",
    "DeribitPaperRuntimeStartApprovalResult",
    "execute_deribit_paper_runtime_start_approval",
]
