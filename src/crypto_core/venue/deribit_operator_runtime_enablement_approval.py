from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import DERIBIT_PHASE58_PROMOTION_SCOPE
from crypto_core.venue.deribit_paper_promoted_runtime_wiring import (
    DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID,
    DERIBIT_PHASE61_RUNTIME_READINESS,
)
from crypto_core.venue.deribit_paper_runtime_enablement_proposal import (
    DERIBIT_PAPER_RUNTIME_ENABLEMENT_PROPOSAL_ID,
    DERIBIT_PHASE62_RUNTIME_WIRING,
    DERIBIT_PHASE62_RUNTIME_WIRING_SHA256,
    DERIBIT_PHASE63_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_OPERATOR_RUNTIME_ENABLEMENT_APPROVAL_ID = "deterministic_phase64_operator_runtime_enablement_approval"
DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_ENABLEMENT_OPERATOR_REVIEW_PROPOSAL_63B.json"
)
DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL_SHA256 = "c6625e76c6bff42900e5fe5323edfef8565835450110f62cf87b27f3260001a8"
DERIBIT_PHASE64_NEXT_BLOCKER = "APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_NOT_READY"
DERIBIT_PHASE64_FALLBACK_BLOCKER = DERIBIT_PHASE63_NEXT_BLOCKER
DERIBIT_PHASE64_OPERATOR_ID = "demir_operator"
DERIBIT_PHASE64_APPROVAL_DECISION = "APPROVE_PAPER_RUNTIME_ENABLEMENT_REVIEW"
_PLACEHOLDER = "<OPERATOR_REQUIRED>"
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_FALSE_SCOPE_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PROPOSAL_CHECKS = tuple(
    "source_runtime_wiring_passed runtime_not_enabled runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_WIRING_CHECKS = tuple(
    "source_readiness_passed promotion_scope_preserved runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_APPROVAL_CHECKS = tuple(
    "source_phase63_runtime_enablement_proposal_exists phase63_ready_for_operator_review phase63_pre_approval_status_not_approved source_phase62_runtime_wiring_exists phase62_runtime_wiring_wired exact_operator_metadata_supplied reviewed_at_iso_utc_z approval_scope_paper_only runtime_not_enabled runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
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


class DeribitOperatorRuntimeEnablementApprovalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_operator_runtime_enablement_approval(
    phase63_runtime_enablement_proposal_artifact: object,
    phase62_runtime_wiring_artifact: object,
    *,
    reviewed_at_iso: str,
) -> DeribitOperatorRuntimeEnablementApprovalResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase62_rejection_reasons(phase62_runtime_wiring_artifact),
                *_phase63_rejection_reasons(
                    phase63_runtime_enablement_proposal_artifact,
                    phase62_runtime_wiring_artifact,
                ),
                *(
                    ()
                    if _is_utc_z(reviewed_at_iso)
                    else ("deribit_operator_runtime_enablement_approval:reviewed_at_iso_invalid",)
                ),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_operator_runtime_enablement_approval:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_operator_runtime_enablement_approval:accepted" if accepted else reasons[0]
    return DeribitOperatorRuntimeEnablementApprovalResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase63_runtime_enablement_proposal_artifact,
            phase62_runtime_wiring_artifact,
            reviewed_at_iso,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase62_rejection_reasons(phase62_runtime_wiring_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase62_runtime_wiring_artifact, dict):
        return ("deribit_operator_runtime_enablement_approval:phase62_artifact_missing",)
    reasons: list[str] = []
    if (
        phase62_runtime_wiring_artifact.get("schema_version") != "deribit_paper_promoted_runtime_wiring.v1"
        or phase62_runtime_wiring_artifact.get("phase") != "62"
        or phase62_runtime_wiring_artifact.get("source") != DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID
        or phase62_runtime_wiring_artifact.get("source_phase61_runtime_readiness") != DERIBIT_PHASE61_RUNTIME_READINESS
        or phase62_runtime_wiring_artifact.get("runtime_wiring_status") != "WIRED"
        or phase62_runtime_wiring_artifact.get("ready_for_paper_runtime") is not True
        or phase62_runtime_wiring_artifact.get("paper_promoted") is not True
        or phase62_runtime_wiring_artifact.get("promotion_granted") is not True
        or phase62_runtime_wiring_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase62_runtime_wiring_artifact.get("wiring_checks") != list(_WIRING_CHECKS)
        or _canonical_sha256(phase62_runtime_wiring_artifact) != DERIBIT_PHASE62_RUNTIME_WIRING_SHA256
    ):
        reasons.append("deribit_operator_runtime_enablement_approval:phase62_metadata_invalid")
    if not _bool_fields_match(phase62_runtime_wiring_artifact, _FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_operator_runtime_enablement_approval:phase62_scope_flags_invalid")
    if not _bool_fields_match(phase62_runtime_wiring_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_operator_runtime_enablement_approval:phase62_safety_flags_invalid")
    if not _strict_int_is_one(phase62_runtime_wiring_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_operator_runtime_enablement_approval:phase62_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase63_rejection_reasons(
    phase63_runtime_enablement_proposal_artifact: object,
    phase62_runtime_wiring_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase63_runtime_enablement_proposal_artifact, dict):
        return ("deribit_operator_runtime_enablement_approval:phase63_artifact_missing",)
    phase62 = phase62_runtime_wiring_artifact if isinstance(phase62_runtime_wiring_artifact, dict) else {}
    reasons: list[str] = []
    if (
        phase63_runtime_enablement_proposal_artifact.get("schema_version")
        != "deribit_paper_runtime_enablement_operator_review_proposal.v1"
        or phase63_runtime_enablement_proposal_artifact.get("phase") != "63"
        or phase63_runtime_enablement_proposal_artifact.get("source") != DERIBIT_PAPER_RUNTIME_ENABLEMENT_PROPOSAL_ID
        or phase63_runtime_enablement_proposal_artifact.get("source_phase62_runtime_wiring")
        != DERIBIT_PHASE62_RUNTIME_WIRING
        or phase63_runtime_enablement_proposal_artifact.get("source_phase62_runtime_wiring_sha256")
        != DERIBIT_PHASE62_RUNTIME_WIRING_SHA256
        or _canonical_sha256(phase63_runtime_enablement_proposal_artifact)
        != DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL_SHA256
        or phase63_runtime_enablement_proposal_artifact.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW"
        or phase63_runtime_enablement_proposal_artifact.get("proposal_type")
        != "OPERATOR_PAPER_RUNTIME_ENABLEMENT_REVIEW"
        or phase63_runtime_enablement_proposal_artifact.get("approval_status") != "NOT_APPROVED"
        or phase63_runtime_enablement_proposal_artifact.get("operator_metadata_required") is not True
        or phase63_runtime_enablement_proposal_artifact.get("approval_decision") != "PLACEHOLDER_ONLY"
        or phase63_runtime_enablement_proposal_artifact.get("runtime_enablement_approved") is not False
        or phase63_runtime_enablement_proposal_artifact.get("paper_promoted") is not True
        or phase63_runtime_enablement_proposal_artifact.get("promotion_granted") is not True
        or phase63_runtime_enablement_proposal_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase63_runtime_enablement_proposal_artifact.get("proposal_checks") != list(_PROPOSAL_CHECKS)
        or phase63_runtime_enablement_proposal_artifact.get("next_blocker") != DERIBIT_PHASE63_NEXT_BLOCKER
        or phase63_runtime_enablement_proposal_artifact.get("source_phase62_runtime_wiring_sha256")
        != _canonical_sha256(phase62)
    ):
        reasons.append("deribit_operator_runtime_enablement_approval:phase63_metadata_invalid")
    if any(
        phase63_runtime_enablement_proposal_artifact.get(field) != _PLACEHOLDER
        for field in ("reviewer_id", "reviewed_at_iso", "approval_scope", "approval_notes")
    ):
        reasons.append("deribit_operator_runtime_enablement_approval:phase63_placeholder_metadata_invalid")
    if not _bool_fields_match(phase63_runtime_enablement_proposal_artifact, _FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_operator_runtime_enablement_approval:phase63_scope_flags_invalid")
    if not _bool_fields_match(phase63_runtime_enablement_proposal_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_operator_runtime_enablement_approval:phase63_safety_flags_invalid")
    if not _strict_int_is_one(phase63_runtime_enablement_proposal_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_operator_runtime_enablement_approval:phase63_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase63_runtime_enablement_proposal_artifact: object,
    phase62_runtime_wiring_artifact: object,
    reviewed_at_iso: str,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase63 = (
        phase63_runtime_enablement_proposal_artifact
        if isinstance(phase63_runtime_enablement_proposal_artifact, dict)
        else {}
    )
    phase62 = phase62_runtime_wiring_artifact if isinstance(phase62_runtime_wiring_artifact, dict) else {}
    return {
        "schema_version": "deribit_paper_runtime_enablement_operator_approval.v1",
        "phase": "64",
        "generated_at": reviewed_at_iso,
        "source": DERIBIT_OPERATOR_RUNTIME_ENABLEMENT_APPROVAL_ID,
        "source_phase63_runtime_enablement_proposal": DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL,
        "source_phase63_runtime_enablement_proposal_sha256": _canonical_sha256(phase63) if phase63 else None,
        "source_phase62_runtime_wiring": DERIBIT_PHASE62_RUNTIME_WIRING,
        "source_phase62_runtime_wiring_sha256": _canonical_sha256(phase62) if phase62 else None,
        "source_phase63_proposal_status": phase63.get("proposal_status"),
        "source_phase63_approval_status": phase63.get("approval_status"),
        "source_phase62_runtime_wiring_status": phase62.get("runtime_wiring_status"),
        "approval_status": "APPROVED" if accepted else "FAIL_CLOSED",
        "operator_id": DERIBIT_PHASE64_OPERATOR_ID,
        "reviewed_at_iso": reviewed_at_iso,
        "approval_decision": DERIBIT_PHASE64_APPROVAL_DECISION,
        "runtime_enablement_approved": accepted,
        "runtime_enabled": False,
        "runtime_started": False,
        "paper_promoted": phase63.get("paper_promoted") if accepted else False,
        "promotion_granted": phase63.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
        **dict.fromkeys(_FALSE_SCOPE_FIELDS[2:], False),
        "approval_scope": dict(_APPROVAL_SCOPE),
        "operator_metadata_source": "explicit_user_approval_in_chat",
        **dict.fromkeys(_TRUE_SAFETY_FIELDS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "approval_checks": list(_APPROVAL_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE64_NEXT_BLOCKER if accepted else DERIBIT_PHASE64_FALLBACK_BLOCKER,
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
    "DERIBIT_OPERATOR_RUNTIME_ENABLEMENT_APPROVAL_ID",
    "DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL",
    "DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL_SHA256",
    "DERIBIT_PHASE64_APPROVAL_DECISION",
    "DERIBIT_PHASE64_FALLBACK_BLOCKER",
    "DERIBIT_PHASE64_NEXT_BLOCKER",
    "DERIBIT_PHASE64_OPERATOR_ID",
    "DeribitOperatorRuntimeEnablementApprovalResult",
    "execute_deribit_operator_runtime_enablement_approval",
]
