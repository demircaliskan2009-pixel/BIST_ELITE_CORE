from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from crypto_core.venue.deribit_approved_paper_promotion_execution import DERIBIT_PHASE58_PROMOTION_SCOPE
from crypto_core.venue.deribit_paper_promoted_runtime_readiness import (
    DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_ID,
    DERIBIT_PHASE60_POST_AUDIT,
    DERIBIT_PHASE61_NEXT_BLOCKER,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID = "deterministic_phase62_paper_promoted_runtime_wiring"
DERIBIT_PHASE61_RUNTIME_READINESS = "docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_61B.json"
DERIBIT_PHASE62_NEXT_BLOCKER = "PAPER_PROMOTED_RUNTIME_ENABLEMENT_APPROVAL_NOT_READY"
DERIBIT_PHASE62_FALLBACK_BLOCKER = DERIBIT_PHASE61_NEXT_BLOCKER
_TRUE_SAFETY_FIELDS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
_FALSE_SCOPE_FIELDS = tuple(
    "runtime_enabled live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
_WIRING_CHECKS = tuple(
    "source_readiness_passed promotion_scope_preserved runtime_not_started no_live_scope_preserved no_private_execution_scope_preserved no_scheduler_loop_scope_preserved connector_ready_dialects_preserved".split()
)


class DeribitPaperPromotedRuntimeWiringResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def wire_deribit_paper_promoted_runtime(
    phase61_runtime_readiness_artifact: object,
) -> DeribitPaperPromotedRuntimeWiringResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase61_rejection_reasons(phase61_runtime_readiness_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_paper_promoted_runtime_wiring:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_promoted_runtime_wiring:accepted" if accepted else reasons[0]
    return DeribitPaperPromotedRuntimeWiringResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(phase61_runtime_readiness_artifact, accepted, reason_code, reasons),
    )


def _phase61_rejection_reasons(phase61_runtime_readiness_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase61_runtime_readiness_artifact, dict):
        return ("deribit_paper_promoted_runtime_wiring:phase61_artifact_missing",)
    reasons: list[str] = []
    if (
        phase61_runtime_readiness_artifact.get("schema_version") != "deribit_paper_promoted_runtime_readiness.v1"
        or phase61_runtime_readiness_artifact.get("phase") != "61"
        or phase61_runtime_readiness_artifact.get("source") != DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_ID
        or phase61_runtime_readiness_artifact.get("source_phase60_post_audit") != DERIBIT_PHASE60_POST_AUDIT
        or phase61_runtime_readiness_artifact.get("runtime_readiness_verdict") != "PASS"
        or phase61_runtime_readiness_artifact.get("ready_for_paper_runtime") is not True
        or phase61_runtime_readiness_artifact.get("paper_promoted") is not True
        or phase61_runtime_readiness_artifact.get("promotion_granted") is not True
        or phase61_runtime_readiness_artifact.get("promotion_scope") != DERIBIT_PHASE58_PROMOTION_SCOPE
        or phase61_runtime_readiness_artifact.get("next_blocker") != DERIBIT_PHASE61_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_promoted_runtime_wiring:phase61_metadata_invalid")
    if not _bool_fields_match(phase61_runtime_readiness_artifact, _FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_paper_promoted_runtime_wiring:phase61_scope_flags_invalid")
    if _runtime_started_field_invalid(phase61_runtime_readiness_artifact):
        reasons.append("deribit_paper_promoted_runtime_wiring:phase61_runtime_started_invalid")
    if not _bool_fields_match(phase61_runtime_readiness_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_promoted_runtime_wiring:phase61_safety_flags_invalid")
    if not _strict_int_is_one(phase61_runtime_readiness_artifact.get("connector_ready_dialects_count")):
        reasons.append("deribit_paper_promoted_runtime_wiring:phase61_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _artifact_payload(
    phase61_runtime_readiness_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    phase61 = phase61_runtime_readiness_artifact if isinstance(phase61_runtime_readiness_artifact, dict) else {}
    false_scope = {field: (phase61.get(field) if accepted else False) for field in _FALSE_SCOPE_FIELDS}
    safety_flags = {field: (phase61.get(field) if accepted else True) for field in _TRUE_SAFETY_FIELDS}
    return {
        "schema_version": "deribit_paper_promoted_runtime_wiring.v1",
        "phase": "62",
        "source": DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID,
        "source_phase61_runtime_readiness": DERIBIT_PHASE61_RUNTIME_READINESS,
        "source_phase61_runtime_readiness_sha256": _canonical_sha256(phase61) if phase61 else None,
        "source_phase60_post_audit": DERIBIT_PHASE60_POST_AUDIT,
        "runtime_wiring_status": "WIRED" if accepted else "FAIL_CLOSED",
        "ready_for_paper_runtime": phase61.get("ready_for_paper_runtime") if accepted else False,
        "paper_promoted": phase61.get("paper_promoted") if accepted else False,
        "promotion_granted": phase61.get("promotion_granted") if accepted else False,
        "promotion_scope": DERIBIT_PHASE58_PROMOTION_SCOPE,
        "runtime_started": False,
        **false_scope,
        **safety_flags,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "wiring_checks": list(_WIRING_CHECKS),
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE62_NEXT_BLOCKER if accepted else DERIBIT_PHASE62_FALLBACK_BLOCKER,
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(payload.get(field) is expected for field in fields)


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _runtime_started_field_invalid(payload: dict[str, object]) -> bool:
    return "runtime_started" in payload and payload.get("runtime_started") is not False


def _strict_int_is_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1


__all__ = [
    "DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_ID",
    "DERIBIT_PHASE61_RUNTIME_READINESS",
    "DERIBIT_PHASE62_FALLBACK_BLOCKER",
    "DERIBIT_PHASE62_NEXT_BLOCKER",
    "DeribitPaperPromotedRuntimeWiringResult",
    "wire_deribit_paper_promoted_runtime",
]
