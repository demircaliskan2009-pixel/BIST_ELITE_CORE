from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import DERIBIT_PHASE58_PROMOTION_SCOPE
from crypto_core.venue.deribit_approved_paper_runtime_enablement import (
    DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_ID,
    DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL,
    DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL_SHA256,
    DERIBIT_PHASE65_NEXT_BLOCKER,
)
from crypto_core.venue.deribit_operator_runtime_enablement_approval import (
    DERIBIT_OPERATOR_RUNTIME_ENABLEMENT_APPROVAL_ID,
    DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL,
    DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL_SHA256,
    DERIBIT_PHASE64_APPROVAL_DECISION,
    DERIBIT_PHASE64_NEXT_BLOCKER,
    DERIBIT_PHASE64_OPERATOR_ID,
    DERIBIT_PHASE64_REVIEWED_AT_ISO,
)
from crypto_core.venue.deribit_paper_runtime_enablement_proposal import (
    DERIBIT_PHASE62_RUNTIME_WIRING,
    DERIBIT_PHASE62_RUNTIME_WIRING_SHA256,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_START_PROPOSAL_ID = "deterministic_phase66_paper_runtime_start_proposal"
DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION = (
    "docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json"
)
DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256 = "d60bfd007a2c2733a95c09d538abdeb9d253b4bb977e995e36fc7c729ee9c54d"
DERIBIT_PHASE66_NEXT_BLOCKER = "OPERATOR_PAPER_RUNTIME_START_APPROVAL_NOT_READY"
DERIBIT_PHASE66_FALLBACK_BLOCKER = DERIBIT_PHASE65_NEXT_BLOCKER
_PLACEHOLDER = "<OPERATOR_REQUIRED>"
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE64_FALSE_SCOPE_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE65_FALSE_SCOPE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE64_APPROVAL_CHECKS = tuple(
    "source_phase63_runtime_enablement_proposal_exists phase63_ready_for_operator_review phase63_pre_approval_status_not_approved source_phase62_runtime_wiring_exists phase62_runtime_wiring_wired exact_operator_metadata_supplied reviewed_at_iso_utc_z approval_scope_paper_only runtime_not_enabled runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_PHASE65_EXECUTION_CHECKS = tuple(
    "source_phase64_runtime_enablement_approval_exists phase64_runtime_enablement_approved phase64_runtime_not_started source_phase62_runtime_wiring_exists phase62_runtime_wiring_wired source_chain_stable runtime_enabled_without_runtime_start no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_PHASE66_PROPOSAL_CHECKS = tuple(
    "source_runtime_enablement_executed runtime_enabled_but_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_APPROVAL_SCOPE_TRUE_FIELDS = tuple(
    "paper_only simulation_only deribit_public_market_data_only no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


class DeribitPaperRuntimeStartProposalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def propose_deribit_paper_runtime_start(
    phase65_runtime_enablement_artifact: object,
    phase64_runtime_enablement_approval_artifact: object,
) -> DeribitPaperRuntimeStartProposalResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase65_rejection_reasons(
                    phase65_runtime_enablement_artifact,
                    phase64_runtime_enablement_approval_artifact,
                ),
                *_phase64_rejection_reasons(phase64_runtime_enablement_approval_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_paper_runtime_start_proposal:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_runtime_start_proposal:accepted" if accepted else reasons[0]
    return DeribitPaperRuntimeStartProposalResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase65_runtime_enablement_artifact,
            phase64_runtime_enablement_approval_artifact,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase65_rejection_reasons(
    phase65_runtime_enablement_artifact: object,
    phase64_runtime_enablement_approval_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase65_runtime_enablement_artifact, dict):
        return ("deribit_paper_runtime_start_proposal:phase65_artifact_missing",)
    phase64 = (
        phase64_runtime_enablement_approval_artifact
        if isinstance(phase64_runtime_enablement_approval_artifact, dict)
        else None
    )
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
        or (
            phase64 is not None
            and phase65_runtime_enablement_artifact.get("source_phase64_runtime_enablement_approval_sha256")
            != _canonical_sha256(phase64)
        )
        or phase65_runtime_enablement_artifact.get("source_phase63_runtime_enablement_proposal")
        != DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL
        or phase65_runtime_enablement_artifact.get("source_phase63_runtime_enablement_proposal_sha256")
        != DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL_SHA256
        or phase65_runtime_enablement_artifact.get("source_phase62_runtime_wiring") != DERIBIT_PHASE62_RUNTIME_WIRING
        or phase65_runtime_enablement_artifact.get("source_phase62_runtime_wiring_sha256")
        != DERIBIT_PHASE62_RUNTIME_WIRING_SHA256
        or _canonical_sha256(phase65_runtime_enablement_artifact) != DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256
        or phase65_runtime_enablement_artifact.get("runtime_wiring_status") != "WIRED"
        or phase65_runtime_enablement_artifact.get("approval_status") != "APPROVED"
        or phase65_runtime_enablement_artifact.get("approval_decision") != DERIBIT_PHASE64_APPROVAL_DECISION
        or phase65_runtime_enablement_artifact.get("operator_id") != DERIBIT_PHASE64_OPERATOR_ID
        or phase65_runtime_enablement_artifact.get("reviewed_at_iso") != DERIBIT_PHASE64_REVIEWED_AT_ISO
        or phase65_runtime_enablement_artifact.get("runtime_enablement_approved") is not True
        or phase65_runtime_enablement_artifact.get("runtime_enablement_execution_status") != "EXECUTED"
        or phase65_runtime_enablement_artifact.get("runtime_enabled") is not True
        or phase65_runtime_enablement_artifact.get("paper_promoted") is not True
        or phase65_runtime_enablement_artifact.get("promotion_granted") is not True
        or phase65_runtime_enablement_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase65_runtime_enablement_artifact.get("execution_checks") != list(_PHASE65_EXECUTION_CHECKS)
        or phase65_runtime_enablement_artifact.get("reason_code")
        != "deribit_approved_paper_runtime_enablement:accepted"
        or phase65_runtime_enablement_artifact.get("rejection_reasons") != []
        or phase65_runtime_enablement_artifact.get("next_blocker") != DERIBIT_PHASE65_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_runtime_start_proposal:phase65_metadata_invalid")
    if not _bool_fields_match(phase65_runtime_enablement_artifact, _PHASE65_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_paper_runtime_start_proposal:phase65_scope_flags_invalid")
    if not _bool_fields_match(phase65_runtime_enablement_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_runtime_start_proposal:phase65_safety_flags_invalid")
    if not _strict_int_is_one(phase65_runtime_enablement_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_runtime_start_proposal:phase65_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase64_rejection_reasons(
    phase64_runtime_enablement_approval_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase64_runtime_enablement_approval_artifact, dict):
        return ("deribit_paper_runtime_start_proposal:phase64_artifact_missing",)
    reasons: list[str] = []
    if (
        phase64_runtime_enablement_approval_artifact.get("schema_version")
        != "deribit_paper_runtime_enablement_operator_approval.v1"
        or phase64_runtime_enablement_approval_artifact.get("phase") != "64"
        or phase64_runtime_enablement_approval_artifact.get("source") != DERIBIT_OPERATOR_RUNTIME_ENABLEMENT_APPROVAL_ID
        or phase64_runtime_enablement_approval_artifact.get("source_phase63_runtime_enablement_proposal")
        != DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL
        or phase64_runtime_enablement_approval_artifact.get("source_phase63_runtime_enablement_proposal_sha256")
        != DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL_SHA256
        or phase64_runtime_enablement_approval_artifact.get("source_phase62_runtime_wiring")
        != DERIBIT_PHASE62_RUNTIME_WIRING
        or phase64_runtime_enablement_approval_artifact.get("source_phase62_runtime_wiring_sha256")
        != DERIBIT_PHASE62_RUNTIME_WIRING_SHA256
        or _canonical_sha256(phase64_runtime_enablement_approval_artifact)
        != DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL_SHA256
        or phase64_runtime_enablement_approval_artifact.get("source_phase63_proposal_status")
        != "READY_FOR_OPERATOR_REVIEW"
        or phase64_runtime_enablement_approval_artifact.get("source_phase63_approval_status") != "NOT_APPROVED"
        or phase64_runtime_enablement_approval_artifact.get("source_phase62_runtime_wiring_status") != "WIRED"
        or phase64_runtime_enablement_approval_artifact.get("approval_status") != "APPROVED"
        or phase64_runtime_enablement_approval_artifact.get("operator_id") != DERIBIT_PHASE64_OPERATOR_ID
        or phase64_runtime_enablement_approval_artifact.get("reviewed_at_iso") != DERIBIT_PHASE64_REVIEWED_AT_ISO
        or phase64_runtime_enablement_approval_artifact.get("approval_decision") != DERIBIT_PHASE64_APPROVAL_DECISION
        or phase64_runtime_enablement_approval_artifact.get("runtime_enablement_approved") is not True
        or phase64_runtime_enablement_approval_artifact.get("paper_promoted") is not True
        or phase64_runtime_enablement_approval_artifact.get("promotion_granted") is not True
        or phase64_runtime_enablement_approval_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase64_runtime_enablement_approval_artifact.get("operator_metadata_source")
        != "explicit_user_approval_in_chat"
        or phase64_runtime_enablement_approval_artifact.get("approval_checks") != list(_PHASE64_APPROVAL_CHECKS)
        or phase64_runtime_enablement_approval_artifact.get("next_blocker") != DERIBIT_PHASE64_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_runtime_start_proposal:phase64_metadata_invalid")
    if not _bool_fields_match(phase64_runtime_enablement_approval_artifact, _PHASE64_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_paper_runtime_start_proposal:phase64_scope_flags_invalid")
    if not _bool_fields_match(phase64_runtime_enablement_approval_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_runtime_start_proposal:phase64_safety_flags_invalid")
    if not _approval_scope_valid(phase64_runtime_enablement_approval_artifact.get("approval_scope")):
        reasons.append("deribit_paper_runtime_start_proposal:phase64_approval_scope_invalid")
    if not _strict_int_is_one(phase64_runtime_enablement_approval_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_runtime_start_proposal:phase64_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase65_runtime_enablement_artifact: object,
    phase64_runtime_enablement_approval_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase65 = phase65_runtime_enablement_artifact if isinstance(phase65_runtime_enablement_artifact, dict) else {}
    phase64 = (
        phase64_runtime_enablement_approval_artifact
        if isinstance(phase64_runtime_enablement_approval_artifact, dict)
        else {}
    )
    false_scope = {field: (phase65.get(field) if accepted else False) for field in _PHASE65_FALSE_SCOPE_FIELDS}
    safety_flags = {field: (phase65.get(field) if accepted else True) for field in _TRUE_SAFETY_FIELDS}
    return {
        "schema_version": "deribit_paper_runtime_start_operator_review_proposal.v1",
        "phase": "66",
        "source": DERIBIT_PAPER_RUNTIME_START_PROPOSAL_ID,
        "source_phase65_runtime_enablement": DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION,
        "source_phase65_runtime_enablement_sha256": _canonical_sha256(phase65) if phase65 else None,
        "source_phase64_runtime_enablement_approval": DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL,
        "source_phase64_runtime_enablement_approval_sha256": _canonical_sha256(phase64) if phase64 else None,
        "proposal_status": "READY_FOR_OPERATOR_REVIEW" if accepted else "FAIL_CLOSED",
        "proposal_type": "OPERATOR_PAPER_RUNTIME_START_REVIEW",
        "approval_status": "NOT_APPROVED",
        "operator_metadata_required": True,
        "reviewer_id": _PLACEHOLDER,
        "reviewed_at_iso": _PLACEHOLDER,
        "approval_scope": _PLACEHOLDER,
        "approval_decision": "PLACEHOLDER_ONLY",
        "approval_notes": _PLACEHOLDER,
        "runtime_start_approved": False,
        "runtime_enabled": phase65.get("runtime_enabled") if accepted else False,
        "runtime_started": False,
        "paper_promoted": phase65.get("paper_promoted") if accepted else False,
        "promotion_granted": phase65.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
        **false_scope,
        **safety_flags,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "proposal_checks": list(_PHASE66_PROPOSAL_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE66_NEXT_BLOCKER if accepted else DERIBIT_PHASE66_FALLBACK_BLOCKER,
    }


def _approval_scope_valid(value: object) -> bool:
    return isinstance(value, dict) and all(value.get(field) is True for field in _APPROVAL_SCOPE_TRUE_FIELDS)


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_PAPER_RUNTIME_START_PROPOSAL_ID",
    "DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION",
    "DERIBIT_PHASE65_RUNTIME_ENABLEMENT_EXECUTION_SHA256",
    "DERIBIT_PHASE66_FALLBACK_BLOCKER",
    "DERIBIT_PHASE66_NEXT_BLOCKER",
    "DeribitPaperRuntimeStartProposalResult",
    "propose_deribit_paper_runtime_start",
]
