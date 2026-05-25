from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from crypto_core.venue.deribit_bounded_paper_campaign import (
    DERIBIT_APPROVAL_DECISION,
    DERIBIT_APPROVAL_SCOPE,
    DERIBIT_APPROVAL_STATUS,
    DERIBIT_APPROVED_REVIEWED_AT_ISO,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION,
    DERIBIT_PHASE44_REPORT_PACK,
    DERIBIT_PHASE46_PROPOSAL,
    DeribitBoundedPaperCampaignRequest,
    DeribitBoundedPaperCampaignSessionFixture,
    run_deribit_bounded_paper_campaign,
)
from crypto_core.venue.deribit_campaign_performance_evaluation import (
    DERIBIT_CAMPAIGN_PERFORMANCE_EVALUATION_ID,
    DERIBIT_PHASE49_AUDIT,
)
from crypto_core.venue.deribit_hard_capped_paper_session import (
    DERIBIT_PAPER_SESSION_HARD_CAP,
    DeribitHardCappedPaperSessionResult,
)
from crypto_core.venue.deribit_paper_ledger import DeribitPaperLedgerState
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_APPROVED_PAPER_PERFORMANCE_CAMPAIGN_ID = "deribit_approved_paper_performance_campaign_v1"
DERIBIT_PHASE48_CAMPAIGN_EXECUTION = "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json"
DERIBIT_PHASE50_PERFORMANCE_EVALUATION = (
    "docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json"
)
DERIBIT_PHASE52_APPROVAL = "docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_52B.json"
DERIBIT_PHASE53_NEXT_BLOCKER = "APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_NOT_READY"
DERIBIT_PHASE53_FALLBACK_BLOCKER = "APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_NOT_READY"
DERIBIT_PHASE52_APPROVAL_STATUS = "APPROVED"
DERIBIT_PHASE52_APPROVAL_DECISION = "APPROVE_PAPER_CAMPAIGN_PERFORMANCE"
DERIBIT_PHASE52_OPERATOR_ID = "demir_operator"
_POLICY_REFS = (
    "PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_EXECUTION_52A.md",
    "APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53A.md",
)
_TRUE_SAFETY_FIELDS = (
    "no_private_api",
    "no_credentials",
    "no_exchange_orders",
    "no_execution_adapter",
    "no_strategy_signal",
    "no_order_routing",
    "no_scheduler",
    "no_automatic_paper_loop",
    "no_shadow",
    "no_live",
)
_APPROVAL_SCOPE_TRUE_FIELDS = (
    "paper_only",
    "simulation_only",
    "deribit_public_market_data_only",
    "hard_cap_unchanged",
    "per_session_max_trades_unchanged",
)
_APPROVAL_FALSE_FIELDS = (
    "promotion_granted",
    "campaign_execution",
    "session_execution",
    "run_execution",
    "ledger_mutated",
    "live_ready",
    "shadow_ready",
    "scheduler_enabled",
    "auto_loop_enabled",
    "live_enabled",
    "shadow_enabled",
)
_SOURCE_FALSE_FIELDS = (
    "ready_for_live",
    "ready_for_shadow",
    "scheduler_enabled",
    "auto_loop_enabled",
    "live_enabled",
    "shadow_enabled",
)
_PHASE48_FALSE_FIELDS = (
    "live_ready",
    "live_enabled",
    "shadow_enabled",
    "auto_loop_enabled",
    "scheduler_enabled",
)


@dataclass(frozen=True)
class DeribitApprovedPaperPerformanceCampaignRequest:
    operator_id: str
    campaign_request_id: str
    idempotency_key: str
    simulation_only: bool
    hard_cap: int = DERIBIT_PAPER_SESSION_HARD_CAP
    per_session_max_trades: int = DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
    max_campaign_sessions: int = DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS
    live_enabled: bool = False
    shadow_enabled: bool = False
    auto_loop_enabled: bool = False
    scheduler_enabled: bool = False


DeribitApprovedPaperPerformanceCampaignSessionFixture = DeribitBoundedPaperCampaignSessionFixture


class DeribitApprovedPaperPerformanceCampaignResult(NamedTuple):
    accepted: bool
    campaign_request_id: str | None
    sessions_requested: int
    sessions_attempted: int
    sessions_accepted: int
    sessions_rejected: int
    aggregate_trades_requested: int
    aggregate_trades_filled: int
    aggregate_ledger_mutations: int
    ledger_mutated: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    session_results: tuple[DeribitHardCappedPaperSessionResult, ...]
    final_ledger_state: DeribitPaperLedgerState | None
    before_ledger_summary: dict[str, object] | None
    after_ledger_summary: dict[str, object] | None
    artifact_payload: dict[str, object]


def run_deribit_approved_paper_performance_campaign(
    request: object,
    approval_artifact: object,
    performance_evaluation_artifact: object,
    phase48_campaign_execution_artifact: object,
    session_fixtures: object,
    ledger_state: object,
    *,
    kill_switch_active: bool = False,
    now_ns: int | None = None,
) -> DeribitApprovedPaperPerformanceCampaignResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_request_rejection_reasons(request),
                *_approval_rejection_reasons(approval_artifact),
                *_performance_evaluation_rejection_reasons(performance_evaluation_artifact),
                *_phase48_rejection_reasons(phase48_campaign_execution_artifact),
                *_source_chain_rejection_reasons(
                    request,
                    approval_artifact,
                    performance_evaluation_artifact,
                    phase48_campaign_execution_artifact,
                ),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_approved_paper_performance_campaign:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    if reasons:
        return _result(
            request=request,
            approval_artifact=approval_artifact,
            campaign_result=None,
            reason_code=reasons[0],
            rejection_reasons=reasons,
        )

    assert isinstance(request, DeribitApprovedPaperPerformanceCampaignRequest)
    bounded_request = DeribitBoundedPaperCampaignRequest(
        operator_id=request.operator_id,
        campaign_id=request.campaign_request_id,
        idempotency_key=request.idempotency_key,
        simulation_only=True,
        approved_campaign=True,
        hard_cap=request.hard_cap,
        per_session_max_trades=request.per_session_max_trades,
        max_campaign_sessions=request.max_campaign_sessions,
        live_enabled=False,
        shadow_enabled=False,
        auto_loop_enabled=False,
        scheduler_enabled=False,
    )
    campaign_result = run_deribit_bounded_paper_campaign(
        bounded_request,
        _phase48_compatible_approval_artifact(request),
        session_fixtures,
        ledger_state,
        kill_switch_active=kill_switch_active,
        now_ns=now_ns,
    )
    reason_code = (
        "deribit_approved_paper_performance_campaign:accepted"
        if campaign_result.accepted
        else campaign_result.reason_code
    )
    rejection_reasons = () if campaign_result.accepted else tuple(dict.fromkeys(campaign_result.rejection_reasons))
    return _result(
        request=request,
        approval_artifact=approval_artifact,
        campaign_result=campaign_result,
        reason_code=reason_code,
        rejection_reasons=rejection_reasons,
    )


def _request_rejection_reasons(request: object) -> tuple[str, ...]:
    if not isinstance(request, DeribitApprovedPaperPerformanceCampaignRequest):
        return ("deribit_approved_paper_performance_campaign:request_malformed",)
    reasons: list[str] = []
    if not _non_empty(request.operator_id):
        reasons.append("deribit_approved_paper_performance_campaign:operator_id_missing")
    elif request.operator_id != DERIBIT_PHASE52_OPERATOR_ID:
        reasons.append("deribit_approved_paper_performance_campaign:operator_id_mismatch")
    if not _non_empty(request.campaign_request_id):
        reasons.append("deribit_approved_paper_performance_campaign:campaign_request_id_missing")
    if not _non_empty(request.idempotency_key):
        reasons.append("deribit_approved_paper_performance_campaign:idempotency_key_missing")
    if request.simulation_only is not True:
        reasons.append("deribit_approved_paper_performance_campaign:not_simulation_only")
    if request.live_enabled is not False:
        reasons.append("deribit_approved_paper_performance_campaign:live_enabled")
    if request.shadow_enabled is not False:
        reasons.append("deribit_approved_paper_performance_campaign:shadow_enabled")
    if request.auto_loop_enabled is not False:
        reasons.append("deribit_approved_paper_performance_campaign:auto_loop_enabled")
    if request.scheduler_enabled is not False:
        reasons.append("deribit_approved_paper_performance_campaign:scheduler_enabled")
    if request.hard_cap != DERIBIT_PAPER_SESSION_HARD_CAP:
        reasons.append("deribit_approved_paper_performance_campaign:hard_cap_mismatch")
    if request.per_session_max_trades != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION:
        reasons.append("deribit_approved_paper_performance_campaign:per_session_max_trades_mismatch")
    if request.max_campaign_sessions != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS:
        reasons.append("deribit_approved_paper_performance_campaign:max_campaign_sessions_mismatch")
    return tuple(dict.fromkeys(reasons))


def _approval_rejection_reasons(approval_artifact: object) -> tuple[str, ...]:
    if not isinstance(approval_artifact, dict):
        return ("deribit_approved_paper_performance_campaign:phase52_approval_missing",)
    reasons: list[str] = []
    if (
        approval_artifact.get("schema_version") != "deribit_paper_campaign_performance_operator_approval.v1"
        or approval_artifact.get("phase") != "52"
        or approval_artifact.get("source_phase50_performance_evaluation") != DERIBIT_PHASE50_PERFORMANCE_EVALUATION
        or approval_artifact.get("source_phase49_telemetry_audit") != DERIBIT_PHASE49_AUDIT
        or approval_artifact.get("source_phase50_performance_evaluation_verdict") != "PASS"
        or approval_artifact.get("source_phase50_ready_for_operator_review") is not True
        or approval_artifact.get("source_phase49_audit_verdict") != "PASS"
        or approval_artifact.get("source_phase49_campaign_execution_verdict") != "PASS"
        or approval_artifact.get("approval_status") != DERIBIT_PHASE52_APPROVAL_STATUS
        or approval_artifact.get("approval_decision") != DERIBIT_PHASE52_APPROVAL_DECISION
        or approval_artifact.get("operator_id") != DERIBIT_PHASE52_OPERATOR_ID
    ):
        reasons.append("deribit_approved_paper_performance_campaign:phase52_approval_metadata_invalid")
    scope = approval_artifact.get("approval_scope")
    if not isinstance(scope, dict) or not _bool_fields_match(scope, _APPROVAL_SCOPE_TRUE_FIELDS, True):
        reasons.append("deribit_approved_paper_performance_campaign:phase52_approval_scope_invalid")
    if not _bool_fields_match(approval_artifact, _APPROVAL_FALSE_FIELDS, False):
        reasons.append("deribit_approved_paper_performance_campaign:phase52_approval_execution_flags_invalid")
    if not _bool_fields_match(approval_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_performance_campaign:phase52_approval_safety_flags_invalid")
    if _strict_int(approval_artifact.get("connector_ready_dialects_count")) != 1:
        reasons.append("deribit_approved_paper_performance_campaign:phase52_connector_ready_dialects_invalid")
    return tuple(dict.fromkeys(reasons))


def _performance_evaluation_rejection_reasons(performance_evaluation_artifact: object) -> tuple[str, ...]:
    if not isinstance(performance_evaluation_artifact, dict):
        return ("deribit_approved_paper_performance_campaign:phase50_artifact_missing",)
    reasons: list[str] = []
    if (
        performance_evaluation_artifact.get("schema_version")
        != "deribit_bounded_paper_campaign_performance_evaluation.v1"
        or performance_evaluation_artifact.get("phase") != "50"
        or performance_evaluation_artifact.get("source") != DERIBIT_CAMPAIGN_PERFORMANCE_EVALUATION_ID
        or performance_evaluation_artifact.get("source_phase49_audit") != DERIBIT_PHASE49_AUDIT
        or performance_evaluation_artifact.get("source_phase48_campaign_execution")
        != DERIBIT_PHASE48_CAMPAIGN_EXECUTION
        or performance_evaluation_artifact.get("performance_evaluation_verdict") != "PASS"
        or performance_evaluation_artifact.get("audit_verdict") != "PASS"
        or performance_evaluation_artifact.get("campaign_execution_verdict") != "PASS"
        or performance_evaluation_artifact.get("ready_for_operator_review") is not True
    ):
        reasons.append("deribit_approved_paper_performance_campaign:phase50_metadata_invalid")
    if not _bool_fields_match(performance_evaluation_artifact, _SOURCE_FALSE_FIELDS, False):
        reasons.append("deribit_approved_paper_performance_campaign:phase50_scope_flags_invalid")
    if not _bool_fields_match(performance_evaluation_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_performance_campaign:phase50_safety_flags_invalid")
    if (
        _strict_int(performance_evaluation_artifact.get("hard_cap")) != DERIBIT_PAPER_SESSION_HARD_CAP
        or _strict_int(performance_evaluation_artifact.get("per_session_max_trades"))
        != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        or _strict_int(performance_evaluation_artifact.get("connector_ready_dialects_count")) != 1
    ):
        reasons.append("deribit_approved_paper_performance_campaign:phase50_bounds_invalid")
    return tuple(dict.fromkeys(reasons))


def _phase48_rejection_reasons(phase48_campaign_execution_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase48_campaign_execution_artifact, dict):
        return ("deribit_approved_paper_performance_campaign:phase48_artifact_missing",)
    reasons: list[str] = []
    if (
        phase48_campaign_execution_artifact.get("schema_version")
        != "deribit_bounded_repeated_paper_campaign_execution.v1"
        or phase48_campaign_execution_artifact.get("phase") != "48"
        or phase48_campaign_execution_artifact.get("source") != DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID
        or phase48_campaign_execution_artifact.get("approval_status") != DERIBIT_APPROVAL_STATUS
        or phase48_campaign_execution_artifact.get("approval_decision") != DERIBIT_APPROVAL_DECISION
        or phase48_campaign_execution_artifact.get("campaign_execution_verdict") != "PASS"
        or _strict_bool(phase48_campaign_execution_artifact.get("simulation_only")) is not True
    ):
        reasons.append("deribit_approved_paper_performance_campaign:phase48_metadata_invalid")
    if not _bool_fields_match(phase48_campaign_execution_artifact, _PHASE48_FALSE_FIELDS, False):
        reasons.append("deribit_approved_paper_performance_campaign:phase48_scope_flags_invalid")
    if not _bool_fields_match(phase48_campaign_execution_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_paper_performance_campaign:phase48_safety_flags_invalid")
    if (
        _strict_int(phase48_campaign_execution_artifact.get("hard_cap")) != DERIBIT_PAPER_SESSION_HARD_CAP
        or _strict_int(phase48_campaign_execution_artifact.get("per_session_max_trades"))
        != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        or _strict_int(phase48_campaign_execution_artifact.get("max_campaign_sessions"))
        != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS
        or _strict_int(phase48_campaign_execution_artifact.get("connector_ready_dialects_count")) != 1
    ):
        reasons.append("deribit_approved_paper_performance_campaign:phase48_bounds_invalid")
    return tuple(dict.fromkeys(reasons))


def _source_chain_rejection_reasons(
    request: object,
    approval_artifact: object,
    performance_evaluation_artifact: object,
    phase48_campaign_execution_artifact: object,
) -> tuple[str, ...]:
    if not isinstance(request, DeribitApprovedPaperPerformanceCampaignRequest):
        return ()
    if not isinstance(approval_artifact, dict):
        return ()
    if not isinstance(performance_evaluation_artifact, dict):
        return ()
    if not isinstance(phase48_campaign_execution_artifact, dict):
        return ()
    reasons: list[str] = []
    if request.hard_cap != performance_evaluation_artifact.get("hard_cap"):
        reasons.append("deribit_approved_paper_performance_campaign:request_hard_cap_source_mismatch")
    if request.hard_cap != phase48_campaign_execution_artifact.get("hard_cap"):
        reasons.append("deribit_approved_paper_performance_campaign:request_hard_cap_phase48_mismatch")
    if request.per_session_max_trades != performance_evaluation_artifact.get("per_session_max_trades"):
        reasons.append("deribit_approved_paper_performance_campaign:request_per_session_max_trades_source_mismatch")
    if request.per_session_max_trades != phase48_campaign_execution_artifact.get("per_session_max_trades"):
        reasons.append("deribit_approved_paper_performance_campaign:request_per_session_max_trades_phase48_mismatch")
    if request.max_campaign_sessions != phase48_campaign_execution_artifact.get("max_campaign_sessions"):
        reasons.append("deribit_approved_paper_performance_campaign:max_campaign_sessions_source_mismatch")
    if approval_artifact.get("promotion_granted") is not False:
        reasons.append("deribit_approved_paper_performance_campaign:promotion_granted")
    return tuple(dict.fromkeys(reasons))


def _phase48_compatible_approval_artifact(
    request: DeribitApprovedPaperPerformanceCampaignRequest,
) -> dict[str, object]:
    return {
        "source_phase46_operator_proposal": DERIBIT_PHASE46_PROPOSAL,
        "source_phase44_report_pack": DERIBIT_PHASE44_REPORT_PACK,
        "approval_status": DERIBIT_APPROVAL_STATUS,
        "approval_decision": DERIBIT_APPROVAL_DECISION,
        "reviewer_id": request.operator_id,
        "reviewed_at_iso": DERIBIT_APPROVED_REVIEWED_AT_ISO,
        "approval_scope": DERIBIT_APPROVAL_SCOPE,
        "bounded_repeated_paper_campaign_approved": True,
        "operator_approval_executed": True,
        "promotion_granted": False,
        "campaign_execution_status": "NOT_EXECUTED",
        "session_execution_status": "NOT_EXECUTED",
        "run_execution_status": "NOT_EXECUTED",
        "campaign_scope": {
            "venue": "deribit",
            "public_market_data_only": True,
            "paper_only": True,
            "simulation_only": True,
            "explicit_operator_triggered": True,
            "live_enabled": False,
            "shadow_enabled": False,
            "auto_loop_enabled": False,
            "scheduler_enabled": False,
        },
        "campaign_bounds": {
            "hard_cap": request.hard_cap,
            "per_session_max_trades": request.per_session_max_trades,
            "max_sessions_approved": request.max_campaign_sessions,
            "max_total_paper_trades_approved": request.max_campaign_sessions * request.per_session_max_trades,
        },
        "safety_flags": dict.fromkeys(_TRUE_SAFETY_FIELDS, True),
        "connector_ready_dialects_count": 1,
    }


def _result(
    *,
    request: object,
    approval_artifact: object,
    campaign_result: object,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> DeribitApprovedPaperPerformanceCampaignResult:
    request_is_valid = isinstance(request, DeribitApprovedPaperPerformanceCampaignRequest)
    campaign_is_valid = hasattr(campaign_result, "accepted")
    session_results = campaign_result.session_results if campaign_is_valid else ()
    return DeribitApprovedPaperPerformanceCampaignResult(
        accepted=bool(campaign_is_valid and campaign_result.accepted),
        campaign_request_id=request.campaign_request_id if request_is_valid else None,
        sessions_requested=campaign_result.sessions_requested if campaign_is_valid else 0,
        sessions_attempted=campaign_result.sessions_attempted if campaign_is_valid else 0,
        sessions_accepted=campaign_result.sessions_accepted if campaign_is_valid else 0,
        sessions_rejected=campaign_result.sessions_rejected if campaign_is_valid else 0,
        aggregate_trades_requested=campaign_result.aggregate_trades_requested if campaign_is_valid else 0,
        aggregate_trades_filled=campaign_result.aggregate_trades_filled if campaign_is_valid else 0,
        aggregate_ledger_mutations=campaign_result.aggregate_ledger_mutations if campaign_is_valid else 0,
        ledger_mutated=bool(campaign_is_valid and campaign_result.ledger_mutated),
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        session_results=session_results,
        final_ledger_state=campaign_result.final_ledger_state if campaign_is_valid else None,
        before_ledger_summary=campaign_result.before_ledger_summary if campaign_is_valid else None,
        after_ledger_summary=campaign_result.after_ledger_summary if campaign_is_valid else None,
        artifact_payload=_artifact_payload(
            request=request,
            approval_artifact=approval_artifact,
            campaign_result=campaign_result if campaign_is_valid else None,
            reason_code=reason_code,
            rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        ),
    )


def _artifact_payload(
    *,
    request: object,
    approval_artifact: object,
    campaign_result: object,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    request_is_valid = isinstance(request, DeribitApprovedPaperPerformanceCampaignRequest)
    approval_is_valid = isinstance(approval_artifact, dict)
    campaign_is_valid = hasattr(campaign_result, "accepted")
    return {
        "schema_version": "deribit_approved_paper_performance_campaign_execution.v1",
        "phase": "53",
        "source": DERIBIT_APPROVED_PAPER_PERFORMANCE_CAMPAIGN_ID,
        "source_phase52_approval": DERIBIT_PHASE52_APPROVAL,
        "source_phase50_performance_evaluation": DERIBIT_PHASE50_PERFORMANCE_EVALUATION,
        "source_phase48_campaign_execution": DERIBIT_PHASE48_CAMPAIGN_EXECUTION,
        "campaign_execution_status": "EXECUTED" if campaign_is_valid and campaign_result.accepted else "FAIL_CLOSED",
        "execution_mode": "OFFLINE_DETERMINISTIC_PAPER_ONLY",
        "campaign_request_id": request.campaign_request_id if request_is_valid else None,
        "idempotency_key_sha256": _sha256(request.idempotency_key)
        if request_is_valid and _non_empty(request.idempotency_key)
        else None,
        "operator_id": request.operator_id
        if request_is_valid
        else approval_artifact.get("operator_id")
        if approval_is_valid
        else None,
        "approval_status": approval_artifact.get("approval_status") if approval_is_valid else None,
        "approval_decision": approval_artifact.get("approval_decision") if approval_is_valid else None,
        "simulation_only": request.simulation_only if request_is_valid else None,
        "live_enabled": request.live_enabled if request_is_valid else None,
        "shadow_enabled": request.shadow_enabled if request_is_valid else None,
        "scheduler_enabled": request.scheduler_enabled if request_is_valid else None,
        "auto_loop_enabled": request.auto_loop_enabled if request_is_valid else None,
        "hard_cap": request.hard_cap if request_is_valid else None,
        "per_session_max_trades": request.per_session_max_trades if request_is_valid else None,
        "sessions_requested": campaign_result.sessions_requested if campaign_is_valid else 0,
        "sessions_attempted": campaign_result.sessions_attempted if campaign_is_valid else 0,
        "sessions_accepted": campaign_result.sessions_accepted if campaign_is_valid else 0,
        "sessions_rejected": campaign_result.sessions_rejected if campaign_is_valid else 0,
        "aggregate_trades_requested": campaign_result.aggregate_trades_requested if campaign_is_valid else 0,
        "aggregate_trades_filled": campaign_result.aggregate_trades_filled if campaign_is_valid else 0,
        "aggregate_ledger_mutations": campaign_result.aggregate_ledger_mutations if campaign_is_valid else 0,
        "duplicate_mutation_blocked": True,
        "promotion_granted": False,
        "live_ready": False,
        "shadow_ready": False,
        **{field: approval_artifact.get(field) if approval_is_valid else None for field in _TRUE_SAFETY_FIELDS},
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "execution_verdict": "PASS" if campaign_is_valid and campaign_result.accepted else "FAIL_CLOSED",
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "session_results": [_session_result_summary(item) for item in campaign_result.session_results]
        if campaign_is_valid
        else [],
        "before_ledger_summary": campaign_result.before_ledger_summary if campaign_is_valid else None,
        "after_ledger_summary": campaign_result.after_ledger_summary if campaign_is_valid else None,
        "policy_refs": list(_POLICY_REFS),
        "next_blocker": DERIBIT_PHASE53_NEXT_BLOCKER
        if campaign_is_valid and campaign_result.accepted
        else DERIBIT_PHASE53_FALLBACK_BLOCKER,
    }


def _session_result_summary(result: DeribitHardCappedPaperSessionResult) -> dict[str, object]:
    return {
        "session_id": result.session_id,
        "accepted": result.accepted,
        "trades_requested": result.trades_requested,
        "trades_attempted": result.trades_attempted,
        "trades_filled": result.trades_filled,
        "trades_rejected": result.trades_rejected,
        "ledger_mutated": result.ledger_mutated,
        "reason_code": result.reason_code,
        "rejection_reasons": list(result.rejection_reasons),
    }


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(_strict_bool(payload.get(field)) is expected for field in fields)


def _strict_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _strict_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "DERIBIT_APPROVED_PAPER_PERFORMANCE_CAMPAIGN_ID",
    "DERIBIT_PHASE48_CAMPAIGN_EXECUTION",
    "DERIBIT_PHASE50_PERFORMANCE_EVALUATION",
    "DERIBIT_PHASE52_APPROVAL",
    "DERIBIT_PHASE53_NEXT_BLOCKER",
    "DeribitApprovedPaperPerformanceCampaignRequest",
    "DeribitApprovedPaperPerformanceCampaignResult",
    "DeribitApprovedPaperPerformanceCampaignSessionFixture",
    "run_deribit_approved_paper_performance_campaign",
]
