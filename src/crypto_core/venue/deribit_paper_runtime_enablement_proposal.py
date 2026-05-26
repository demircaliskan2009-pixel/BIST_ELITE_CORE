from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import DERIBIT_PHASE58_PROMOTION_SCOPE
from crypto_core.venue.deribit_paper_promoted_runtime_wiring import (
    DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID,
    DERIBIT_PHASE61_RUNTIME_READINESS,
    DERIBIT_PHASE62_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUNTIME_ENABLEMENT_PROPOSAL_ID = "deterministic_phase63_paper_runtime_enablement_proposal"
DERIBIT_PHASE62_RUNTIME_WIRING = "docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_62B.json"
DERIBIT_PHASE62_RUNTIME_WIRING_SHA256 = "23f20a820aed0c2d947de8a50ea278e975536ea8057db8990e5231d2fc9ad436"
DERIBIT_PHASE63_NEXT_BLOCKER = "OPERATOR_PAPER_RUNTIME_ENABLEMENT_APPROVAL_NOT_READY"
DERIBIT_PHASE63_FALLBACK_BLOCKER = DERIBIT_PHASE62_NEXT_BLOCKER
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_FALSE_SCOPE_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_WIRING_CHECKS = tuple(
    "source_readiness_passed promotion_scope_preserved runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_PROPOSAL_CHECKS = tuple(
    "source_runtime_wiring_passed runtime_not_enabled runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)
_PLACEHOLDER = "<OPERATOR_REQUIRED>"


class DeribitPaperRuntimeEnablementProposalResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def propose_deribit_paper_runtime_enablement(
    phase62_runtime_wiring_artifact: object,
) -> DeribitPaperRuntimeEnablementProposalResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase62_rejection_reasons(phase62_runtime_wiring_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_paper_runtime_enablement_proposal:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_runtime_enablement_proposal:accepted" if accepted else reasons[0]
    return DeribitPaperRuntimeEnablementProposalResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(phase62_runtime_wiring_artifact, accepted, reason_code, reasons),
    )


def _phase62_rejection_reasons(phase62_runtime_wiring_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase62_runtime_wiring_artifact, dict):
        return ("deribit_paper_runtime_enablement_proposal:phase62_artifact_missing",)
    reasons: list[str] = []
    if (
        phase62_runtime_wiring_artifact.get("schema_version") != "deribit_paper_promoted_runtime_wiring.v1"
        or phase62_runtime_wiring_artifact.get("phase") != "62"
        or phase62_runtime_wiring_artifact.get("source") != DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID
        or phase62_runtime_wiring_artifact.get("source_phase61_runtime_readiness") != DERIBIT_PHASE61_RUNTIME_READINESS
        or phase62_runtime_wiring_artifact.get("source_phase61_runtime_readiness_sha256")
        != "c99038090b76261f7dc64a568995f87ddf4a0764f25704d9f60c99dff747dffb"
        or phase62_runtime_wiring_artifact.get("runtime_wiring_status") != "WIRED"
        or phase62_runtime_wiring_artifact.get("ready_for_paper_runtime") is not True
        or phase62_runtime_wiring_artifact.get("paper_promoted") is not True
        or phase62_runtime_wiring_artifact.get("promotion_granted") is not True
        or phase62_runtime_wiring_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase62_runtime_wiring_artifact.get("wiring_checks") != list(_WIRING_CHECKS)
        or phase62_runtime_wiring_artifact.get("next_blocker") != DERIBIT_PHASE62_NEXT_BLOCKER
        or _canonical_sha256(phase62_runtime_wiring_artifact) != DERIBIT_PHASE62_RUNTIME_WIRING_SHA256
    ):
        reasons.append("deribit_paper_runtime_enablement_proposal:phase62_metadata_invalid")
    if not _bool_fields_match(phase62_runtime_wiring_artifact, _FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_paper_runtime_enablement_proposal:phase62_scope_flags_invalid")
    if not _bool_fields_match(phase62_runtime_wiring_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_runtime_enablement_proposal:phase62_safety_flags_invalid")
    if not _strict_int_is_one(phase62_runtime_wiring_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_runtime_enablement_proposal:phase62_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase62_runtime_wiring_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase62 = phase62_runtime_wiring_artifact if isinstance(phase62_runtime_wiring_artifact, dict) else {}
    false_scope = {field: (phase62.get(field) if accepted else False) for field in _FALSE_SCOPE_FIELDS}
    safety_flags = {field: (phase62.get(field) if accepted else True) for field in _TRUE_SAFETY_FIELDS}
    return {
        "schema_version": "deribit_paper_runtime_enablement_operator_review_proposal.v1",
        "phase": "63",
        "source": DERIBIT_PAPER_RUNTIME_ENABLEMENT_PROPOSAL_ID,
        "source_phase62_runtime_wiring": DERIBIT_PHASE62_RUNTIME_WIRING,
        "source_phase62_runtime_wiring_sha256": _canonical_sha256(phase62) if phase62 else None,
        "proposal_status": "READY_FOR_OPERATOR_REVIEW" if accepted else "FAIL_CLOSED",
        "proposal_type": "OPERATOR_PAPER_RUNTIME_ENABLEMENT_REVIEW",
        "approval_status": "NOT_APPROVED",
        "operator_metadata_required": True,
        "reviewer_id": _PLACEHOLDER,
        "reviewed_at_iso": _PLACEHOLDER,
        "approval_scope": _PLACEHOLDER,
        "approval_decision": "PLACEHOLDER_ONLY",
        "approval_notes": _PLACEHOLDER,
        "runtime_enablement_approved": False,
        **false_scope,
        "paper_promoted": phase62.get("paper_promoted") if accepted else False,
        "promotion_granted": phase62.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
        **safety_flags,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "proposal_checks": list(_PROPOSAL_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE63_NEXT_BLOCKER if accepted else DERIBIT_PHASE63_FALLBACK_BLOCKER,
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_PAPER_RUNTIME_ENABLEMENT_PROPOSAL_ID",
    "DERIBIT_PHASE62_RUNTIME_WIRING",
    "DERIBIT_PHASE62_RUNTIME_WIRING_SHA256",
    "DERIBIT_PHASE63_FALLBACK_BLOCKER",
    "DERIBIT_PHASE63_NEXT_BLOCKER",
    "DeribitPaperRuntimeEnablementProposalResult",
    "propose_deribit_paper_runtime_enablement",
]
