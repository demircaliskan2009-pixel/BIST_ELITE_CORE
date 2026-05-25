from __future__ import annotations

from typing import NamedTuple

from crypto_core.venue.deribit_bounded_paper_campaign import (
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION,
)
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_APPROVED_EXECUTION_TELEMETRY_AUDIT_ID = "deribit_approved_paper_performance_execution_telemetry_audit_v1"
DERIBIT_PHASE53_EXECUTION = "docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53B.json"
DERIBIT_PHASE52_APPROVAL = "docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_52B.json"
DERIBIT_PHASE54_NEXT_BLOCKER = "PAPER_PERFORMANCE_PROMOTION_READINESS_NOT_READY"
DERIBIT_PHASE54_FALLBACK_BLOCKER = "APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_NOT_READY"
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
_FALSE_SCOPE_FIELDS = (
    "promotion_granted",
    "live_ready",
    "shadow_ready",
    "live_enabled",
    "shadow_enabled",
    "scheduler_enabled",
    "auto_loop_enabled",
)
_PAYLOAD_FIELDS = (
    "execution_verdict",
    "campaign_execution_status",
    "execution_mode",
    "sessions_requested",
    "sessions_attempted",
    "sessions_accepted",
    "sessions_rejected",
    "aggregate_trades_requested",
    "aggregate_trades_filled",
    "aggregate_ledger_mutations",
    "duplicate_mutation_blocked",
    "hard_cap",
    "per_session_max_trades",
)


class DeribitApprovedExecutionTelemetryAuditResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def audit_deribit_approved_execution_telemetry(
    phase53_execution_artifact: object,
    phase52_approval_artifact: object,
) -> DeribitApprovedExecutionTelemetryAuditResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase53_rejection_reasons(phase53_execution_artifact),
                *_phase52_rejection_reasons(phase52_approval_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_approved_execution_telemetry_audit:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_approved_execution_telemetry_audit:accepted" if accepted else reasons[0]
    return DeribitApprovedExecutionTelemetryAuditResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(phase53_execution_artifact, accepted, reason_code, reasons),
    )


def _phase53_rejection_reasons(phase53_execution_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase53_execution_artifact, dict):
        return ("deribit_approved_execution_telemetry_audit:phase53_artifact_missing",)
    reasons: list[str] = []
    if (
        phase53_execution_artifact.get("schema_version") != "deribit_approved_paper_performance_campaign_execution.v1"
        or phase53_execution_artifact.get("phase") != "53"
        or phase53_execution_artifact.get("source") != "deribit_approved_paper_performance_campaign_v1"
        or phase53_execution_artifact.get("source_phase52_approval") != DERIBIT_PHASE52_APPROVAL
        or phase53_execution_artifact.get("campaign_execution_status") != "EXECUTED"
        or phase53_execution_artifact.get("execution_mode") != "OFFLINE_DETERMINISTIC_PAPER_ONLY"
        or phase53_execution_artifact.get("execution_verdict") != "PASS"
        or phase53_execution_artifact.get("approval_status") != "APPROVED"
        or phase53_execution_artifact.get("approval_decision") != "APPROVE_PAPER_CAMPAIGN_PERFORMANCE"
        or phase53_execution_artifact.get("operator_id") != "demir_operator"
    ):
        reasons.append("deribit_approved_execution_telemetry_audit:phase53_metadata_invalid")
    if not _bool_fields_match(phase53_execution_artifact, _FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_approved_execution_telemetry_audit:phase53_scope_flags_invalid")
    if not _bool_fields_match(phase53_execution_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_execution_telemetry_audit:phase53_safety_flags_invalid")
    if (
        _strict_int(phase53_execution_artifact.get("hard_cap")) != DERIBIT_PAPER_SESSION_HARD_CAP
        or _strict_int(phase53_execution_artifact.get("per_session_max_trades"))
        != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        or _strict_int(phase53_execution_artifact.get("connector_ready_dialects_count")) != 1
    ):
        reasons.append("deribit_approved_execution_telemetry_audit:phase53_bounds_invalid")
    if not _counts_are_safe(phase53_execution_artifact):
        reasons.append("deribit_approved_execution_telemetry_audit:phase53_counts_invalid")
    if not _session_results_are_safe(phase53_execution_artifact.get("session_results")):
        reasons.append("deribit_approved_execution_telemetry_audit:phase53_session_results_invalid")
    return tuple(reasons)


def _phase52_rejection_reasons(phase52_approval_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase52_approval_artifact, dict):
        return ("deribit_approved_execution_telemetry_audit:phase52_approval_missing",)
    reasons: list[str] = []
    if (
        phase52_approval_artifact.get("schema_version") != "deribit_paper_campaign_performance_operator_approval.v1"
        or phase52_approval_artifact.get("phase") != "52"
        or phase52_approval_artifact.get("approval_status") != "APPROVED"
        or phase52_approval_artifact.get("approval_decision") != "APPROVE_PAPER_CAMPAIGN_PERFORMANCE"
        or phase52_approval_artifact.get("operator_id") != "demir_operator"
        or phase52_approval_artifact.get("promotion_granted") is not False
        or phase52_approval_artifact.get("campaign_execution") is not False
        or phase52_approval_artifact.get("ledger_mutated") is not False
    ):
        reasons.append("deribit_approved_execution_telemetry_audit:phase52_metadata_invalid")
    scope = phase52_approval_artifact.get("approval_scope")
    if (
        not isinstance(scope, dict)
        or scope.get("paper_only") is not True
        or scope.get("simulation_only") is not True
        or scope.get("deribit_public_market_data_only") is not True
        or scope.get("hard_cap_unchanged") is not True
        or scope.get("per_session_max_trades_unchanged") is not True
    ):
        reasons.append("deribit_approved_execution_telemetry_audit:phase52_scope_invalid")
    if not _bool_fields_match(phase52_approval_artifact, _FALSE_SCOPE_FIELDS, False):
        reasons.append("deribit_approved_execution_telemetry_audit:phase52_scope_flags_invalid")
    if not _bool_fields_match(phase52_approval_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_approved_execution_telemetry_audit:phase52_safety_flags_invalid")
    if _strict_int(phase52_approval_artifact.get("connector_ready_dialects_count")) != 1:
        reasons.append("deribit_approved_execution_telemetry_audit:phase52_connector_ready_dialects_invalid")
    return tuple(reasons)


def _counts_are_safe(phase53_execution_artifact: dict[str, object]) -> bool:
    sessions_requested = _strict_int(phase53_execution_artifact.get("sessions_requested"))
    sessions_attempted = _strict_int(phase53_execution_artifact.get("sessions_attempted"))
    sessions_accepted = _strict_int(phase53_execution_artifact.get("sessions_accepted"))
    sessions_rejected = _strict_int(phase53_execution_artifact.get("sessions_rejected"))
    trades_requested = _strict_int(phase53_execution_artifact.get("aggregate_trades_requested"))
    trades_filled = _strict_int(phase53_execution_artifact.get("aggregate_trades_filled"))
    ledger_mutations = _strict_int(phase53_execution_artifact.get("aggregate_ledger_mutations"))
    if None in (
        sessions_requested,
        sessions_attempted,
        sessions_accepted,
        sessions_rejected,
        trades_requested,
        trades_filled,
        ledger_mutations,
    ):
        return False
    session_totals = _session_result_totals(phase53_execution_artifact.get("session_results"))
    if session_totals is None:
        return False
    session_count, session_trades_requested, session_trades_filled, session_trades_rejected = session_totals
    return (
        sessions_requested == DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS
        and sessions_attempted == sessions_requested
        and sessions_accepted == sessions_requested
        and sessions_rejected == 0
        and trades_requested == sessions_requested * DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        and trades_requested >= trades_filled >= 0
        and ledger_mutations == trades_filled
        and session_count == sessions_requested
        and session_trades_requested == trades_requested
        and session_trades_filled == trades_filled
        and session_trades_rejected == 0
        and _strict_bool(phase53_execution_artifact.get("duplicate_mutation_blocked")) is True
    )


def _session_result_totals(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list):
        return None
    totals = [0, 0, 0]
    for item in value:
        if not isinstance(item, dict):
            return None
        requested = _strict_int(item.get("trades_requested"))
        filled = _strict_int(item.get("trades_filled"))
        rejected = _strict_int(item.get("trades_rejected"))
        if None in (requested, filled, rejected):
            return None
        totals[0] += requested
        totals[1] += filled
        totals[2] += rejected
    return (len(value), totals[0], totals[1], totals[2])


def _session_results_are_safe(value: object) -> bool:
    if not isinstance(value, list) or len(value) != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS:
        return False
    for item in value:
        if (
            not isinstance(item, dict)
            or _strict_bool(item.get("accepted")) is not True
            or _strict_bool(item.get("ledger_mutated")) is not True
        ):
            return False
        requested = _strict_int(item.get("trades_requested"))
        attempted = _strict_int(item.get("trades_attempted"))
        filled = _strict_int(item.get("trades_filled"))
        rejected = _strict_int(item.get("trades_rejected"))
        if (
            None in (requested, attempted, filled, rejected)
            or requested != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
            or attempted != requested
            or filled != requested
            or rejected != 0
            or item.get("rejection_reasons") != []
        ):
            return False
    return True


def _artifact_payload(
    phase53_execution_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    source = phase53_execution_artifact if isinstance(phase53_execution_artifact, dict) else {}
    payload = {field: source.get(field) for field in _PAYLOAD_FIELDS}
    sessions_requested = _strict_int(source.get("sessions_requested")) or 0
    sessions_accepted = _strict_int(source.get("sessions_accepted")) or 0
    sessions_rejected = _strict_int(source.get("sessions_rejected")) or 0
    trades_requested = _strict_int(source.get("aggregate_trades_requested")) or 0
    trades_filled = _strict_int(source.get("aggregate_trades_filled")) or 0
    ledger_mutations = _strict_int(source.get("aggregate_ledger_mutations")) or 0
    return {
        "schema_version": "deribit_approved_paper_performance_execution_telemetry_audit.v1",
        "phase": "54",
        "source": DERIBIT_APPROVED_EXECUTION_TELEMETRY_AUDIT_ID,
        "source_phase53_execution": DERIBIT_PHASE53_EXECUTION,
        "source_phase52_approval": DERIBIT_PHASE52_APPROVAL,
        "telemetry_audit_verdict": "PASS" if accepted else "FAIL_CLOSED",
        **payload,
        "execution_metrics": {
            "fill_rate": _safe_ratio(trades_filled, trades_requested),
            "rejection_rate": _safe_ratio(sessions_rejected, sessions_requested),
            "ledger_mutation_rate": _safe_ratio(ledger_mutations, trades_filled),
            "session_acceptance_rate": _safe_ratio(sessions_accepted, sessions_requested),
            "avg_fills_per_session": _safe_ratio(trades_filled, sessions_requested),
        },
        "safety_metrics": {
            "live_scope": False,
            "shadow_scope": False,
            "scheduler_scope": False,
            "auto_loop_scope": False,
            "private_api_scope": False,
            "execution_adapter_scope": False,
            "strategy_scope": False,
        },
        "promotion_granted": False,
        "ready_for_live": False,
        "ready_for_shadow": False,
        **{field: source.get(field) for field in _TRUE_SAFETY_FIELDS},
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "report_only": True,
        "campaign_execution_replayed": False,
        "session_execution_replayed": False,
        "run_execution_replayed": False,
        "ledger_mutated": False,
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "policy_refs": [
            "APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53A.md",
            "APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54A.md",
        ],
        "next_blocker": DERIBIT_PHASE54_NEXT_BLOCKER if accepted else DERIBIT_PHASE54_FALLBACK_BLOCKER,
    }


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(_strict_bool(payload.get(field)) is expected for field in fields)


def _strict_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _strict_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = [
    "DERIBIT_APPROVED_EXECUTION_TELEMETRY_AUDIT_ID",
    "DERIBIT_PHASE53_EXECUTION",
    "DERIBIT_PHASE52_APPROVAL",
    "DERIBIT_PHASE54_NEXT_BLOCKER",
    "DeribitApprovedExecutionTelemetryAuditResult",
    "audit_deribit_approved_execution_telemetry",
]
