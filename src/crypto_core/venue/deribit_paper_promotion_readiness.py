from __future__ import annotations

from typing import NamedTuple

from crypto_core.venue.deribit_approved_execution_telemetry_audit import (
    DERIBIT_APPROVED_EXECUTION_TELEMETRY_AUDIT_ID,
    DERIBIT_PHASE54_NEXT_BLOCKER,
)
from crypto_core.venue.deribit_bounded_paper_campaign import (
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION,
)
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_PROMOTION_READINESS_ID = "deribit_paper_performance_promotion_readiness_evaluation_v1"
DERIBIT_PHASE54_TELEMETRY_AUDIT = (
    "docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54B.json"
)
DERIBIT_PHASE55_NEXT_BLOCKER = "OPERATOR_PROMOTION_REVIEW_PROPOSAL_NOT_READY"
DERIBIT_PHASE55_FALLBACK_BLOCKER = "PAPER_PERFORMANCE_PROMOTION_READINESS_NOT_READY"
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
_SOURCE_FALSE_FIELDS = (
    "promotion_granted",
    "ready_for_live",
    "ready_for_shadow",
    "campaign_execution_replayed",
    "session_execution_replayed",
    "run_execution_replayed",
    "ledger_mutated",
)
_SAFETY_METRIC_FALSE_FIELDS = (
    "live_scope",
    "shadow_scope",
    "scheduler_scope",
    "auto_loop_scope",
    "private_api_scope",
    "execution_adapter_scope",
    "strategy_scope",
)
_MINIMUM_SESSIONS_REQUIRED = 3


class DeribitPaperPromotionReadinessResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def evaluate_deribit_paper_promotion_readiness(
    phase54_telemetry_audit_artifact: object,
) -> DeribitPaperPromotionReadinessResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase54_rejection_reasons(phase54_telemetry_audit_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_paper_promotion_readiness:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_paper_promotion_readiness:accepted" if accepted else reasons[0]
    return DeribitPaperPromotionReadinessResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(phase54_telemetry_audit_artifact, accepted, reason_code, reasons),
    )


def _phase54_rejection_reasons(phase54_telemetry_audit_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase54_telemetry_audit_artifact, dict):
        return ("deribit_paper_promotion_readiness:phase54_artifact_missing",)
    reasons: list[str] = []
    if (
        phase54_telemetry_audit_artifact.get("schema_version")
        != "deribit_approved_paper_performance_execution_telemetry_audit.v1"
        or phase54_telemetry_audit_artifact.get("phase") != "54"
        or phase54_telemetry_audit_artifact.get("source") != DERIBIT_APPROVED_EXECUTION_TELEMETRY_AUDIT_ID
        or phase54_telemetry_audit_artifact.get("telemetry_audit_verdict") != "PASS"
        or phase54_telemetry_audit_artifact.get("execution_verdict") != "PASS"
        or phase54_telemetry_audit_artifact.get("next_blocker") != DERIBIT_PHASE54_NEXT_BLOCKER
    ):
        reasons.append("deribit_paper_promotion_readiness:phase54_metadata_invalid")
    if not _bool_fields_match(phase54_telemetry_audit_artifact, _SOURCE_FALSE_FIELDS, False):
        reasons.append("deribit_paper_promotion_readiness:phase54_scope_flags_invalid")
    if not _bool_fields_match(phase54_telemetry_audit_artifact, _TRUE_SAFETY_FIELDS, True):
        reasons.append("deribit_paper_promotion_readiness:phase54_safety_flags_invalid")
    safety_metrics = phase54_telemetry_audit_artifact.get("safety_metrics")
    if not isinstance(safety_metrics, dict) or not _bool_fields_match(
        safety_metrics, _SAFETY_METRIC_FALSE_FIELDS, False
    ):
        reasons.append("deribit_paper_promotion_readiness:phase54_safety_metrics_invalid")
    if (
        _strict_int(phase54_telemetry_audit_artifact.get("hard_cap")) != DERIBIT_PAPER_SESSION_HARD_CAP
        or _strict_int(phase54_telemetry_audit_artifact.get("per_session_max_trades"))
        != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        or _strict_int(phase54_telemetry_audit_artifact.get("connector_ready_dialects_count")) != 1
    ):
        reasons.append("deribit_paper_promotion_readiness:phase54_bounds_invalid")
    if not _counts_are_safe(phase54_telemetry_audit_artifact):
        reasons.append("deribit_paper_promotion_readiness:phase54_counts_invalid")
    if not _metrics_are_consistent(phase54_telemetry_audit_artifact):
        reasons.append("deribit_paper_promotion_readiness:phase54_metrics_invalid")
    return tuple(reasons)


def _counts_are_safe(phase54_telemetry_audit_artifact: dict[str, object]) -> bool:
    sessions_requested = _strict_int(phase54_telemetry_audit_artifact.get("sessions_requested"))
    sessions_attempted = _strict_int(phase54_telemetry_audit_artifact.get("sessions_attempted"))
    sessions_accepted = _strict_int(phase54_telemetry_audit_artifact.get("sessions_accepted"))
    sessions_rejected = _strict_int(phase54_telemetry_audit_artifact.get("sessions_rejected"))
    trades_requested = _strict_int(phase54_telemetry_audit_artifact.get("aggregate_trades_requested"))
    trades_filled = _strict_int(phase54_telemetry_audit_artifact.get("aggregate_trades_filled"))
    ledger_mutations = _strict_int(phase54_telemetry_audit_artifact.get("aggregate_ledger_mutations"))
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
    return (
        sessions_requested >= _MINIMUM_SESSIONS_REQUIRED
        and sessions_requested == DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS
        and sessions_attempted == sessions_requested
        and sessions_accepted == sessions_requested
        and sessions_rejected == 0
        and trades_requested == sessions_requested * DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        and trades_filled == trades_requested
        and ledger_mutations == trades_filled
        and _strict_bool(phase54_telemetry_audit_artifact.get("duplicate_mutation_blocked")) is True
    )


def _metrics_are_consistent(phase54_telemetry_audit_artifact: dict[str, object]) -> bool:
    metrics = phase54_telemetry_audit_artifact.get("execution_metrics")
    if not isinstance(metrics, dict):
        return False
    sessions_requested = _strict_int(phase54_telemetry_audit_artifact.get("sessions_requested")) or 0
    sessions_accepted = _strict_int(phase54_telemetry_audit_artifact.get("sessions_accepted")) or 0
    sessions_rejected = _strict_int(phase54_telemetry_audit_artifact.get("sessions_rejected")) or 0
    trades_requested = _strict_int(phase54_telemetry_audit_artifact.get("aggregate_trades_requested")) or 0
    trades_filled = _strict_int(phase54_telemetry_audit_artifact.get("aggregate_trades_filled")) or 0
    ledger_mutations = _strict_int(phase54_telemetry_audit_artifact.get("aggregate_ledger_mutations")) or 0
    expected = {
        "fill_rate": _safe_ratio(trades_filled, trades_requested),
        "rejection_rate": _safe_ratio(sessions_rejected, sessions_requested),
        "ledger_mutation_rate": _safe_ratio(ledger_mutations, trades_filled),
        "session_acceptance_rate": _safe_ratio(sessions_accepted, sessions_requested),
    }
    return all(metrics.get(field) == value for field, value in expected.items())


def _artifact_payload(
    phase54_telemetry_audit_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    source = phase54_telemetry_audit_artifact if isinstance(phase54_telemetry_audit_artifact, dict) else {}
    metrics = source.get("execution_metrics") if isinstance(source.get("execution_metrics"), dict) else {}
    criteria_results = _criteria_results(source)
    return {
        "schema_version": "deribit_paper_performance_promotion_readiness_evaluation.v1",
        "phase": "55",
        "source": DERIBIT_PAPER_PROMOTION_READINESS_ID,
        "source_phase54_telemetry_audit": DERIBIT_PHASE54_TELEMETRY_AUDIT,
        "promotion_readiness_verdict": "READY_FOR_OPERATOR_REVIEW" if accepted else "FAIL_CLOSED",
        "ready_for_operator_promotion_review": accepted,
        "promotion_granted": False,
        "live_ready": False,
        "shadow_ready": False,
        "scheduler_enabled": False,
        "auto_loop_enabled": False,
        "live_enabled": False,
        "shadow_enabled": False,
        "telemetry_audit_verdict": source.get("telemetry_audit_verdict"),
        "execution_verdict": source.get("execution_verdict"),
        "fill_rate": metrics.get("fill_rate"),
        "rejection_rate": metrics.get("rejection_rate"),
        "session_acceptance_rate": metrics.get("session_acceptance_rate"),
        "ledger_mutation_rate": metrics.get("ledger_mutation_rate"),
        "evaluation_criteria": {
            "minimum_sessions_required": _MINIMUM_SESSIONS_REQUIRED,
            "zero_rejected_sessions_required": True,
            "duplicate_mutation_block_required": True,
            "no_live_scope_required": True,
            "no_private_execution_scope_required": True,
        },
        "criteria_results": criteria_results,
        **{field: source.get(field) for field in _TRUE_SAFETY_FIELDS},
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "report_only": True,
        "campaign_execution_replayed": False,
        "session_execution_replayed": False,
        "run_execution_replayed": False,
        "ledger_mutated": False,
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "next_blocker": DERIBIT_PHASE55_NEXT_BLOCKER if accepted else DERIBIT_PHASE55_FALLBACK_BLOCKER,
    }


def _criteria_results(source: dict[str, object]) -> dict[str, bool]:
    safety_metrics = source.get("safety_metrics") if isinstance(source.get("safety_metrics"), dict) else {}
    return {
        "minimum_sessions_met": (_strict_int(source.get("sessions_requested")) or 0) >= _MINIMUM_SESSIONS_REQUIRED,
        "zero_rejected_sessions": _strict_int(source.get("sessions_rejected")) == 0,
        "duplicate_mutation_blocked": _strict_bool(source.get("duplicate_mutation_blocked")) is True,
        "no_live_scope": bool(
            isinstance(safety_metrics, dict)
            and safety_metrics.get("live_scope") is False
            and safety_metrics.get("shadow_scope") is False
        ),
        "no_private_execution_scope": bool(
            isinstance(safety_metrics, dict)
            and safety_metrics.get("private_api_scope") is False
            and safety_metrics.get("execution_adapter_scope") is False
            and safety_metrics.get("strategy_scope") is False
        ),
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
    "DERIBIT_PAPER_PROMOTION_READINESS_ID",
    "DERIBIT_PHASE54_TELEMETRY_AUDIT",
    "DERIBIT_PHASE55_NEXT_BLOCKER",
    "DeribitPaperPromotionReadinessResult",
    "evaluate_deribit_paper_promotion_readiness",
]
