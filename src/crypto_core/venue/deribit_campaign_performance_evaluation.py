from __future__ import annotations

from typing import NamedTuple

from crypto_core.venue.deribit_bounded_paper_campaign import (
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION,
)
from crypto_core.venue.deribit_campaign_telemetry_audit import (
    DERIBIT_CAMPAIGN_TELEMETRY_AUDIT_ID,
    DERIBIT_PHASE48_CAMPAIGN_EXECUTION,
)
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_CAMPAIGN_PERFORMANCE_EVALUATION_ID = "deribit_bounded_paper_campaign_performance_evaluation_v1"
DERIBIT_PHASE49_AUDIT = "docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49B.json"
DERIBIT_PHASE50_NEXT_BLOCKER = "OPERATOR_REVIEW_FOR_PAPER_PERFORMANCE_NOT_READY"
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
_SOURCE_FALSE_FIELDS = ("scheduler_enabled", "auto_loop_enabled", "live_enabled", "shadow_enabled")
_REQUIRED_SOURCE_FIELDS = (
    "audit_verdict",
    "campaign_execution_verdict",
    "sessions_requested",
    "sessions_accepted",
    "sessions_rejected",
    "aggregate_trades_requested",
    "aggregate_trades_filled",
    "aggregate_ledger_mutations",
    "duplicate_mutation_blocked",
    "hard_cap",
    "per_session_max_trades",
)


class DeribitCampaignPerformanceEvaluationResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def evaluate_deribit_campaign_performance(
    phase49_audit_artifact: object,
) -> DeribitCampaignPerformanceEvaluationResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_phase49_rejection_reasons(phase49_audit_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_campaign_performance_evaluation:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_campaign_performance_evaluation:accepted" if accepted else reasons[0]
    return DeribitCampaignPerformanceEvaluationResult(
        accepted,
        reason_code,
        reasons,
        _artifact_payload(phase49_audit_artifact, accepted, reason_code, reasons),
    )


def _phase49_rejection_reasons(phase49_audit_artifact: object) -> tuple[str, ...]:
    if not isinstance(phase49_audit_artifact, dict):
        return ("deribit_campaign_performance_evaluation:phase49_artifact_missing",)
    reasons: list[str] = []
    if (
        phase49_audit_artifact.get("schema_version") != "deribit_bounded_paper_campaign_telemetry_audit.v1"
        or phase49_audit_artifact.get("phase") != "49"
        or phase49_audit_artifact.get("source") != DERIBIT_CAMPAIGN_TELEMETRY_AUDIT_ID
        or phase49_audit_artifact.get("source_phase48_campaign_execution") != DERIBIT_PHASE48_CAMPAIGN_EXECUTION
        or phase49_audit_artifact.get("audit_verdict") != "PASS"
        or phase49_audit_artifact.get("campaign_execution_verdict") != "PASS"
    ):
        reasons.append("deribit_campaign_performance_evaluation:phase49_metadata_invalid")
    if not all(field in phase49_audit_artifact for field in _REQUIRED_SOURCE_FIELDS):
        reasons.append("deribit_campaign_performance_evaluation:phase49_required_fields_missing")
    if not _bool_fields_match(phase49_audit_artifact, _TRUE_SAFETY_FIELDS, True) or not _bool_fields_match(
        phase49_audit_artifact, _SOURCE_FALSE_FIELDS, False
    ):
        reasons.append("deribit_campaign_performance_evaluation:phase49_scope_flags_invalid")
    if (
        _strict_int(phase49_audit_artifact.get("connector_ready_dialects_count")) != 1
        or _strict_int(phase49_audit_artifact.get("hard_cap")) != DERIBIT_PAPER_SESSION_HARD_CAP
        or _strict_int(phase49_audit_artifact.get("per_session_max_trades"))
        != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
    ):
        reasons.append("deribit_campaign_performance_evaluation:phase49_bounds_invalid")
    if not _counts_are_safe(phase49_audit_artifact):
        reasons.append("deribit_campaign_performance_evaluation:phase49_counts_invalid")
    if not _policy_refs_are_safe(phase49_audit_artifact.get("policy_refs")):
        reasons.append("deribit_campaign_performance_evaluation:phase49_policy_refs_invalid")
    return tuple(reasons)


def _counts_are_safe(phase49_audit_artifact: dict[str, object]) -> bool:
    sessions_requested = _strict_int(phase49_audit_artifact.get("sessions_requested"))
    sessions_accepted = _strict_int(phase49_audit_artifact.get("sessions_accepted"))
    sessions_rejected = _strict_int(phase49_audit_artifact.get("sessions_rejected"))
    trades_requested = _strict_int(phase49_audit_artifact.get("aggregate_trades_requested"))
    trades_filled = _strict_int(phase49_audit_artifact.get("aggregate_trades_filled"))
    ledger_mutations = _strict_int(phase49_audit_artifact.get("aggregate_ledger_mutations"))
    if None in (
        sessions_requested,
        sessions_accepted,
        sessions_rejected,
        trades_requested,
        trades_filled,
        ledger_mutations,
    ):
        return False
    return (
        sessions_requested == DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS
        and sessions_accepted == sessions_requested
        and sessions_rejected == 0
        and trades_requested == sessions_requested * DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        and trades_filled == trades_requested
        and ledger_mutations == trades_filled
        and _strict_bool(phase49_audit_artifact.get("duplicate_mutation_blocked")) is True
    )


def _policy_refs_are_safe(value: object) -> bool:
    return isinstance(value, list) and value != [] and all(isinstance(item, str) for item in value)


def _artifact_payload(
    phase49_audit_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    source = phase49_audit_artifact if isinstance(phase49_audit_artifact, dict) else {}
    sessions_requested = _strict_int(source.get("sessions_requested")) or 0
    sessions_accepted = _strict_int(source.get("sessions_accepted")) or 0
    sessions_rejected = _strict_int(source.get("sessions_rejected")) or 0
    trades_requested = _strict_int(source.get("aggregate_trades_requested")) or 0
    trades_filled = _strict_int(source.get("aggregate_trades_filled")) or 0
    ledger_mutations = _strict_int(source.get("aggregate_ledger_mutations")) or 0
    performance_metrics = {
        "fill_rate": _safe_ratio(trades_filled, trades_requested),
        "reject_rate": _safe_ratio(sessions_rejected, sessions_requested),
        "ledger_mutation_count": ledger_mutations,
        "session_acceptance_rate": _safe_ratio(sessions_accepted, sessions_requested),
    }
    return {
        "schema_version": "deribit_bounded_paper_campaign_performance_evaluation.v1",
        "phase": "50",
        "source": DERIBIT_CAMPAIGN_PERFORMANCE_EVALUATION_ID,
        "source_phase49_audit": DERIBIT_PHASE49_AUDIT,
        "source_phase48_campaign_execution": source.get("source_phase48_campaign_execution"),
        "performance_evaluation_verdict": "PASS" if accepted else "FAIL_CLOSED",
        "audit_verdict": source.get("audit_verdict"),
        "campaign_execution_verdict": source.get("campaign_execution_verdict"),
        "sessions_requested": sessions_requested,
        "sessions_accepted": sessions_accepted,
        "sessions_rejected": sessions_rejected,
        "aggregate_trades_requested": trades_requested,
        "aggregate_trades_filled": trades_filled,
        "aggregate_ledger_mutations": ledger_mutations,
        "duplicate_mutation_blocked": source.get("duplicate_mutation_blocked"),
        "hard_cap": source.get("hard_cap"),
        "per_session_max_trades": source.get("per_session_max_trades"),
        "evaluation_sample_size": sessions_requested,
        "performance_metrics": performance_metrics,
        "ready_for_operator_review": accepted,
        "promotion_granted": False,
        "ready_for_live": False,
        "ready_for_shadow": False,
        "scheduler_enabled": False,
        "auto_loop_enabled": False,
        "live_enabled": False,
        "shadow_enabled": False,
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
            "BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49A.md",
            "BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50A.md",
        ],
        "next_blocker": DERIBIT_PHASE50_NEXT_BLOCKER if accepted else "PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_NOT_READY",
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
    "DERIBIT_CAMPAIGN_PERFORMANCE_EVALUATION_ID",
    "DERIBIT_PHASE49_AUDIT",
    "DERIBIT_PHASE50_NEXT_BLOCKER",
    "DeribitCampaignPerformanceEvaluationResult",
    "evaluate_deribit_campaign_performance",
]
