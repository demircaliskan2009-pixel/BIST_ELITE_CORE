from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import DERIBIT_PHASE58_PROMOTION_SCOPE
from crypto_core.venue.deribit_operator_runtime_enablement_approval import (
    DERIBIT_OPERATOR_RUNTIME_ENABLEMENT_APPROVAL_ID,
    DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL,
    DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL_SHA256,
    DERIBIT_PHASE64_APPROVAL_DECISION,
    DERIBIT_PHASE64_NEXT_BLOCKER,
    DERIBIT_PHASE64_OPERATOR_ID,
    DERIBIT_PHASE64_REVIEWED_AT_ISO,
)
from crypto_core.venue.deribit_paper_promoted_runtime_wiring import (
    DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID,
    DERIBIT_PHASE61_RUNTIME_READINESS,
    DERIBIT_PHASE62_NEXT_BLOCKER,
)
from crypto_core.venue.deribit_paper_runtime_enablement_proposal import (
    DERIBIT_PHASE62_RUNTIME_WIRING,
    DERIBIT_PHASE62_RUNTIME_WIRING_SHA256,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_ID = "deterministic_phase65_approved_paper_runtime_enablement_execution"
DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL = (
    "docs/crypto_core/DERIBIT_PAPER_RUNTIME_ENABLEMENT_OPERATOR_APPROVAL_64B.json"
)
DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL_SHA256 = "b5eeb636b0f83ec43b9a17106d2f14055fd40513fc89e8d613cbf8ef64f4d9eb"
DERIBIT_PHASE65_NEXT_BLOCKER = "PAPER_RUNTIME_START_PROPOSAL_NOT_READY"
DERIBIT_PHASE65_FALLBACK_BLOCKER = DERIBIT_PHASE64_NEXT_BLOCKER
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_PHASE64_FALSE_SCOPE_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE62_FALSE_SCOPE_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE65_FALSE_SCOPE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_PHASE64_APPROVAL_CHECKS = tuple(
    "source_phase63_runtime_enablement_proposal_exists phase63_ready_for_operator_review phase63_pre_approval_status_not_approved source_phase62_runtime_wiring_exists phase62_runtime_wiring_wired exact_operator_metadata_supplied reviewed_at_iso_utc_z approval_scope_paper_only runtime_not_enabled runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_PHASE62_WIRING_CHECKS = tuple(
    "source_readiness_passed promotion_scope_preserved runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_PHASE65_EXECUTION_CHECKS = tuple(
    "source_phase64_runtime_enablement_approval_exists phase64_runtime_enablement_approved phase64_runtime_not_started source_phase62_runtime_wiring_exists phase62_runtime_wiring_wired source_chain_stable runtime_enabled_without_runtime_start no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_APPROVAL_SCOPE_TRUE_FIELDS = tuple(
    "paper_only simulation_only deribit_public_market_data_only no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


class DeribitApprovedPaperRuntimeEnablementResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def execute_deribit_approved_paper_runtime_enablement(
    phase64_runtime_enablement_approval_artifact: object,
    phase62_runtime_wiring_artifact: object,
) -> DeribitApprovedPaperRuntimeEnablementResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase64_rejection_reasons(
                    phase64_runtime_enablement_approval_artifact,
                    phase62_runtime_wiring_artifact,
                ),
                *_phase62_rejection_reasons(phase62_runtime_wiring_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_approved_paper_runtime_enablement:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_approved_paper_runtime_enablement:accepted" if accepted else reasons[0]
    return DeribitApprovedPaperRuntimeEnablementResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(
            phase64_runtime_enablement_approval_artifact,
            phase62_runtime_wiring_artifact,
            accepted,
            reason_code,
            reasons,
        ),
    )


def _phase64_rejection_reasons(
    phase64_runtime_enablement_approval_artifact: object,
    phase62_runtime_wiring_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(phase64_runtime_enablement_approval_artifact, dict):
        return ("deribit_approved_paper_runtime_enablement:phase64_artifact_missing",)
    phase62 = phase62_runtime_wiring_artifact if isinstance(phase62_runtime_wiring_artifact, dict) else None
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
        or (
            phase62 is not None
            and phase64_runtime_enablement_approval_artifact.get("source_phase62_runtime_wiring_sha256")
            != _canonical_sha256(phase62)
        )
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
        reasons.append("deribit_approved_paper_runtime_enablement:phase64_metadata_invalid")
    if not _bool_fields_match(phase64_runtime_enablement_approval_artifact, _PHASE64_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_approved_paper_runtime_enablement:phase64_scope_flags_invalid")
    if not _bool_fields_match(phase64_runtime_enablement_approval_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_runtime_enablement:phase64_safety_flags_invalid")
    if not _approval_scope_valid(phase64_runtime_enablement_approval_artifact.get("approval_scope")):
        reasons.append("deribit_approved_paper_runtime_enablement:phase64_approval_scope_invalid")
    if not _strict_int_is_one(phase64_runtime_enablement_approval_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_approved_paper_runtime_enablement:phase64_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase62_rejection_reasons(phase62_runtime_wiring_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase62_runtime_wiring_artifact, dict):
        return ("deribit_approved_paper_runtime_enablement:phase62_artifact_missing",)
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
        or phase62_runtime_wiring_artifact.get("wiring_checks") != list(_PHASE62_WIRING_CHECKS)
        or phase62_runtime_wiring_artifact.get("next_blocker") != DERIBIT_PHASE62_NEXT_BLOCKER
        or _canonical_sha256(phase62_runtime_wiring_artifact) != DERIBIT_PHASE62_RUNTIME_WIRING_SHA256
    ):
        reasons.append("deribit_approved_paper_runtime_enablement:phase62_metadata_invalid")
    if not _bool_fields_match(phase62_runtime_wiring_artifact, _PHASE62_FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_approved_paper_runtime_enablement:phase62_scope_flags_invalid")
    if not _bool_fields_match(phase62_runtime_wiring_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_runtime_enablement:phase62_safety_flags_invalid")
    if not _strict_int_is_one(phase62_runtime_wiring_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_approved_paper_runtime_enablement:phase62_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase64_runtime_enablement_approval_artifact: object,
    phase62_runtime_wiring_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase64 = (
        phase64_runtime_enablement_approval_artifact
        if isinstance(phase64_runtime_enablement_approval_artifact, dict)
        else {}
    )
    phase62 = phase62_runtime_wiring_artifact if isinstance(phase62_runtime_wiring_artifact, dict) else {}
    return {
        "schema_version": "deribit_approved_paper_runtime_enablement_execution.v1",
        "phase": "65",
        "source": DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_ID,
        "source_phase64_runtime_enablement_approval": DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL,
        "source_phase64_runtime_enablement_approval_sha256": _canonical_sha256(phase64) if phase64 else None,
        "source_phase63_runtime_enablement_proposal": DERIBIT_PHASE63_RUNTIME_ENABLEMENT_PROPOSAL,
        "source_phase63_runtime_enablement_proposal_sha256": phase64.get(
            "source_phase63_runtime_enablement_proposal_sha256"
        ),
        "source_phase62_runtime_wiring": DERIBIT_PHASE62_RUNTIME_WIRING,
        "source_phase62_runtime_wiring_sha256": _canonical_sha256(phase62) if phase62 else None,
        "runtime_wiring_status": phase62.get("runtime_wiring_status") if accepted else "FAIL_CLOSED",
        "approval_status": phase64.get("approval_status") if accepted else "FAIL_CLOSED",
        "approval_decision": phase64.get("approval_decision") if accepted else "FAIL_CLOSED",
        "operator_id": phase64.get("operator_id") if accepted else None,
        "reviewed_at_iso": phase64.get("reviewed_at_iso") if accepted else None,
        "runtime_enablement_approved": phase64.get("runtime_enablement_approved") if accepted else False,
        "runtime_enablement_execution_status": "EXECUTED" if accepted else "FAIL_CLOSED",
        "runtime_enabled": accepted,
        "runtime_started": False,
        "paper_promoted": phase64.get("paper_promoted") if accepted else False,
        "promotion_granted": phase64.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
        **dict.fromkeys(_PHASE65_FALSE_SCOPE_FIELDS, False),
        **dict.fromkeys(_TRUE_SAFETY_FIELDS, True),
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "execution_checks": list(_PHASE65_EXECUTION_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE65_NEXT_BLOCKER if accepted else DERIBIT_PHASE65_FALLBACK_BLOCKER,
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
    "DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_ID",
    "DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL",
    "DERIBIT_PHASE64_RUNTIME_ENABLEMENT_APPROVAL_SHA256",
    "DERIBIT_PHASE65_FALLBACK_BLOCKER",
    "DERIBIT_PHASE65_NEXT_BLOCKER",
    "DeribitApprovedPaperRuntimeEnablementResult",
    "execute_deribit_approved_paper_runtime_enablement",
]
