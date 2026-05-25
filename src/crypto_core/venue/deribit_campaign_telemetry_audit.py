from __future__ import annotations

from typing import NamedTuple

# fmt: off
from crypto_core.venue.deribit_bounded_paper_campaign import (
    DERIBIT_APPROVAL_DECISION,
    DERIBIT_APPROVAL_SCOPE,
    DERIBIT_APPROVAL_STATUS,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS,
    DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION,
    DERIBIT_PHASE47_APPROVAL,
)

# fmt: on
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_CAMPAIGN_TELEMETRY_AUDIT_ID = "deribit_bounded_paper_campaign_telemetry_audit_v1"
DERIBIT_PHASE48_CAMPAIGN_EXECUTION = "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json"
DERIBIT_PHASE49_NEXT_BLOCKER = "PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_NOT_READY"
# fmt: off
_POLICY_REFS = ("BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_48A.md", "BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49A.md")
_PHASE48_TRUE_FIELDS = tuple("simulation_only duplicate_mutation_blocked no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal".split())
_PHASE48_FALSE_FIELDS = ("live_ready", "live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled")
_APPROVAL_SCOPE_TRUE_FIELDS = tuple("public_market_data_only paper_only simulation_only explicit_operator_triggered".split())
_APPROVAL_SCOPE_FALSE_FIELDS = ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled")
_APPROVAL_SAFETY_FIELDS = tuple("no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_scheduler no_automatic_paper_loop no_shadow no_live".split())
_PAYLOAD_FIELDS = tuple((
    "campaign_execution_verdict sessions_requested sessions_attempted sessions_accepted sessions_rejected "
    "aggregate_trades_requested aggregate_trades_filled aggregate_ledger_mutations duplicate_mutation_blocked "
    "hard_cap per_session_max_trades max_campaign_sessions simulation_only live_ready scheduler_enabled "
    "auto_loop_enabled shadow_enabled live_enabled no_private_api no_credentials no_exchange_orders "
    "no_execution_adapter no_strategy_signal"
).split())
# fmt: on
_SESSION_REASON = "deribit_hard_capped_paper_session:accepted"


class DeribitCampaignTelemetryAuditResult(NamedTuple):
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    artifact_payload: dict[str, object]


def run_deribit_campaign_telemetry_audit(
    campaign_artifact: object, approval_artifact: object
) -> DeribitCampaignTelemetryAuditResult:
    reasons = tuple(
        dict.fromkeys(
            (
                *_campaign_rejection_reasons(campaign_artifact),
                *_approval_rejection_reasons(approval_artifact),
                *(
                    ()
                    if len(connector_ready_dialects()) == 1
                    else ("deribit_campaign_telemetry_audit:connector_ready_dialects_mismatch",)
                ),
            )
        )
    )
    accepted = not reasons
    reason_code = "deribit_campaign_telemetry_audit:accepted" if accepted else reasons[0]
    return DeribitCampaignTelemetryAuditResult(
        accepted, reason_code, reasons, _artifact_payload(campaign_artifact, accepted, reason_code, reasons)
    )


def _campaign_rejection_reasons(campaign_artifact: object) -> tuple[str, ...]:
    if not isinstance(campaign_artifact, dict):
        return ("deribit_campaign_telemetry_audit:phase48_artifact_missing",)
    reasons: list[str] = []
    # fmt: off
    if (campaign_artifact.get("schema_version") != "deribit_bounded_repeated_paper_campaign_execution.v1" or campaign_artifact.get("phase") != "48" or campaign_artifact.get("source") != DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID or campaign_artifact.get("source_phase47_approval") != DERIBIT_PHASE47_APPROVAL or campaign_artifact.get("approval_status") != DERIBIT_APPROVAL_STATUS or campaign_artifact.get("approval_decision") != DERIBIT_APPROVAL_DECISION or campaign_artifact.get("campaign_execution_verdict") != "PASS"):
        reasons.append("deribit_campaign_telemetry_audit:phase48_metadata_invalid")
    if (not _bool_fields_match(campaign_artifact, _PHASE48_TRUE_FIELDS, True) or not _bool_fields_match(campaign_artifact, _PHASE48_FALSE_FIELDS, False)):
        reasons.append("deribit_campaign_telemetry_audit:phase48_scope_flags_invalid")
    if (_strict_int(campaign_artifact.get("connector_ready_dialects_count")) != 1 or _strict_int(campaign_artifact.get("hard_cap")) != DERIBIT_PAPER_SESSION_HARD_CAP or _strict_int(campaign_artifact.get("per_session_max_trades")) != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION or _strict_int(campaign_artifact.get("max_campaign_sessions")) != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS):
        reasons.append("deribit_campaign_telemetry_audit:phase48_bounds_invalid")
    # fmt: on
    if not _campaign_counts_are_safe(campaign_artifact):
        reasons.append("deribit_campaign_telemetry_audit:phase48_counts_invalid")
    if not _session_results_are_safe(campaign_artifact.get("session_results")):
        reasons.append("deribit_campaign_telemetry_audit:phase48_session_results_invalid")
    return tuple(reasons)


def _approval_rejection_reasons(approval_artifact: object) -> tuple[str, ...]:
    if not isinstance(approval_artifact, dict):
        return ("deribit_campaign_telemetry_audit:approval_artifact_missing",)
    reasons: list[str] = []
    # fmt: off
    if (approval_artifact.get("approval_status") != DERIBIT_APPROVAL_STATUS or approval_artifact.get("approval_decision") != DERIBIT_APPROVAL_DECISION or approval_artifact.get("approval_scope") != DERIBIT_APPROVAL_SCOPE or approval_artifact.get("bounded_repeated_paper_campaign_approved") is not True or approval_artifact.get("operator_approval_executed") is not True or approval_artifact.get("promotion_granted") is not False or _strict_int(approval_artifact.get("connector_ready_dialects_count")) != 1):
        reasons.append("deribit_campaign_telemetry_audit:approval_metadata_invalid")
    # fmt: on
    scope = approval_artifact.get("campaign_scope")
    bounds = approval_artifact.get("campaign_bounds")
    safety = approval_artifact.get("safety_flags")
    if (
        not isinstance(scope, dict)
        or scope.get("venue") != "deribit"
        or not _bool_fields_match(scope, _APPROVAL_SCOPE_TRUE_FIELDS, True)
        or not _bool_fields_match(scope, _APPROVAL_SCOPE_FALSE_FIELDS, False)
    ):
        reasons.append("deribit_campaign_telemetry_audit:approval_scope_flags_invalid")
    if not isinstance(bounds, dict) or (
        _strict_int(bounds.get("hard_cap")) != DERIBIT_PAPER_SESSION_HARD_CAP
        or _strict_int(bounds.get("per_session_max_trades")) != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
        or _strict_int(bounds.get("max_sessions_approved")) != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS
        or _strict_int(bounds.get("max_total_paper_trades_approved")) != 6
    ):
        reasons.append("deribit_campaign_telemetry_audit:approval_bounds_invalid")
    if not isinstance(safety, dict) or not _bool_fields_match(safety, _APPROVAL_SAFETY_FIELDS, True):
        reasons.append("deribit_campaign_telemetry_audit:approval_safety_flags_invalid")
    return tuple(reasons)


def _campaign_counts_are_safe(campaign_artifact: dict[str, object]) -> bool:
    # fmt: off
    sessions_requested, sessions_attempted, sessions_accepted, sessions_rejected, trades_requested, trades_filled, ledger_mutations = (_strict_int(campaign_artifact.get("sessions_requested")), _strict_int(campaign_artifact.get("sessions_attempted")), _strict_int(campaign_artifact.get("sessions_accepted")), _strict_int(campaign_artifact.get("sessions_rejected")), _strict_int(campaign_artifact.get("aggregate_trades_requested")), _strict_int(campaign_artifact.get("aggregate_trades_filled")), _strict_int(campaign_artifact.get("aggregate_ledger_mutations")))
    if None in (sessions_requested, sessions_attempted, sessions_accepted, sessions_rejected, trades_requested, trades_filled, ledger_mutations):
        return False
    return sessions_requested == DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS and sessions_attempted == sessions_requested and sessions_accepted == sessions_requested and sessions_rejected == 0 and trades_requested == sessions_requested * DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION and trades_filled == trades_requested and ledger_mutations == trades_filled
    # fmt: on


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
        requested, attempted, filled, rejected = (
            _strict_int(item.get("trades_requested")),
            _strict_int(item.get("trades_attempted")),
            _strict_int(item.get("trades_filled")),
            _strict_int(item.get("trades_rejected")),
        )
        if (
            None in (requested, attempted, filled, rejected)
            or requested != attempted
            or attempted != filled
            or rejected != 0
        ):
            return False
        if (
            requested > DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
            or item.get("reason_code") != _SESSION_REASON
            or item.get("rejection_reasons") != []
        ):
            return False
    return True


def _artifact_payload(
    campaign_artifact: object, accepted: bool, reason_code: str, rejection_reasons: tuple[str, ...]
) -> dict[str, object]:
    campaign = campaign_artifact if isinstance(campaign_artifact, dict) else {}
    payload = {field: campaign.get(field) for field in _PAYLOAD_FIELDS}
    return {
        "schema_version": "deribit_bounded_paper_campaign_telemetry_audit.v1",
        "phase": "49",
        "source": DERIBIT_CAMPAIGN_TELEMETRY_AUDIT_ID,
        "source_phase48_campaign_execution": DERIBIT_PHASE48_CAMPAIGN_EXECUTION,
        "source_phase47_approval": DERIBIT_PHASE47_APPROVAL,
        **payload,
        "audit_verdict": "PASS" if accepted else "FAIL_CLOSED",
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "report_only": True,
        "campaign_execution_replayed": False,
        "session_execution_replayed": False,
        "run_execution_replayed": False,
        "reason_code": reason_code,
        "rejection_reasons": list(rejection_reasons),
        "policy_refs": list(_POLICY_REFS),
        "next_blocker": DERIBIT_PHASE49_NEXT_BLOCKER if accepted else "CAMPAIGN_TELEMETRY_AUDIT_NOT_READY",
    }


# fmt: off
def _bool_fields_match(payload: dict[str, object], fields: tuple[str, ...], expected: bool) -> bool:
    return all(_strict_bool(payload.get(field)) is expected for field in fields)
def _strict_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
def _strict_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
__all__ = ["DERIBIT_CAMPAIGN_TELEMETRY_AUDIT_ID", "DERIBIT_PHASE48_CAMPAIGN_EXECUTION", "DERIBIT_PHASE49_NEXT_BLOCKER", "DeribitCampaignTelemetryAuditResult", "run_deribit_campaign_telemetry_audit"]
# fmt: on
