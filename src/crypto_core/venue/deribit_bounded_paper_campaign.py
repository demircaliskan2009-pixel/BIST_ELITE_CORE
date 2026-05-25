from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import (
    DERIBIT_PAPER_SESSION_HARD_CAP,
    DeribitHardCappedPaperSessionRequest,
    DeribitHardCappedPaperSessionResult,
    run_deribit_hard_capped_paper_session,
)
from crypto_core.venue.deribit_paper_ledger import DeribitPaperLedgerState
from crypto_core.venue.deribit_paper_run_harness import DeribitPaperRunHarnessInputs
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID = "deribit_bounded_paper_campaign_v1"
DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS = 3
DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION = 2
DERIBIT_PHASE46_PROPOSAL = "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_46B.json"
DERIBIT_PHASE47_APPROVAL = "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_47B.json"
DERIBIT_PHASE44_REPORT_PACK = "docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json"
DERIBIT_PHASE48_NEXT_BLOCKER = "CAMPAIGN_TELEMETRY_AUDIT_NOT_READY"
DERIBIT_APPROVED_REVIEWER_ID = "demir_operator"
DERIBIT_APPROVED_REVIEWED_AT_ISO = "2026-05-25T10:04:41Z"
DERIBIT_APPROVAL_DECISION = "APPROVE_BOUNDED_REPEATED_PAPER_CAMPAIGN"
DERIBIT_APPROVAL_STATUS = "APPROVED"
DERIBIT_APPROVAL_SCOPE = (
    "Deribit public-market-data-only, paper-only, simulation-only, no private API, no credentials, "
    "no exchange orders, no execution adapter, no scheduler, no auto-loop, no shadow/live, "
    "hard_cap=3, per_session_max_trades=2"
)

_POLICY_REFS = (
    "HARD_CAPPED_PAPER_SESSION_GATE_42A.md",
    "DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_EXECUTION_47A.md",
    "BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_48A.md",
)
_SCOPE_MARKERS = frozenset(
    {
        "account",
        "auth",
        "balance",
        "credential",
        "exchange_order",
        "execution",
        "live",
        "private",
        "route",
        "scheduler",
        "shadow",
        "signal",
        "strategy",
        "token",
        "withdraw",
    }
)


@dataclass(frozen=True)
class DeribitBoundedPaperCampaignRequest:
    operator_id: str
    campaign_id: str
    idempotency_key: str
    simulation_only: bool
    approved_campaign: bool
    hard_cap: int = DERIBIT_PAPER_SESSION_HARD_CAP
    per_session_max_trades: int = DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
    max_campaign_sessions: int = DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS
    live_enabled: bool = False
    shadow_enabled: bool = False
    auto_loop_enabled: bool = False
    scheduler_enabled: bool = False


@dataclass(frozen=True)
class DeribitBoundedPaperCampaignSessionFixture:
    session_id: str
    idempotency_key: str
    trade_inputs: tuple[DeribitPaperRunHarnessInputs, ...]


@dataclass(frozen=True)
class DeribitBoundedPaperCampaignAuditRecord:
    audit_id: str
    operator_id: str | None
    campaign_id: str | None
    approval_status: str | None
    approval_decision: str | None
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
    before_ledger_summary: dict[str, object] | None
    after_ledger_summary: dict[str, object] | None
    policy_refs: tuple[str, ...] = _POLICY_REFS


@dataclass(frozen=True)
class DeribitBoundedPaperCampaignResult:
    accepted: bool
    campaign_id: str | None
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
    audit_record: DeribitBoundedPaperCampaignAuditRecord
    artifact_payload: dict[str, object]


def run_deribit_bounded_paper_campaign(
    request: object,
    approval_artifact: object,
    session_fixtures: object,
    ledger_state: object,
    *,
    kill_switch_active: bool = False,
    now_ns: int | None = None,
) -> DeribitBoundedPaperCampaignResult:
    normalized_fixtures = _normalized_session_fixtures(session_fixtures)
    initial_ledger = ledger_state if isinstance(ledger_state, DeribitPaperLedgerState) else None
    before_summary = _ledger_summary_to_dict(initial_ledger)
    reasons = tuple(
        dict.fromkeys(
            (
                *_request_rejection_reasons(request),
                *_approval_rejection_reasons(approval_artifact),
                *_ledger_state_rejection_reasons(ledger_state),
                *_session_fixture_rejection_reasons(
                    request,
                    approval_artifact,
                    normalized_fixtures,
                    session_fixtures,
                    ledger_state,
                ),
                *_kill_switch_rejection_reasons(kill_switch_active),
                *_connector_rejection_reasons(),
            )
        )
    )
    sessions_requested = _raw_session_count(session_fixtures)
    aggregate_trades_requested = _raw_trade_count(session_fixtures)
    if reasons:
        return _result(
            request=request,
            approval_artifact=approval_artifact,
            accepted=False,
            reason_code=reasons[0],
            rejection_reasons=reasons,
            session_results=(),
            final_ledger_state=initial_ledger,
            before_summary=before_summary,
            after_summary=before_summary,
            sessions_requested=sessions_requested,
            aggregate_trades_requested=aggregate_trades_requested,
        )

    assert isinstance(request, DeribitBoundedPaperCampaignRequest)
    assert isinstance(approval_artifact, dict)
    assert isinstance(initial_ledger, DeribitPaperLedgerState)

    current_ledger = initial_ledger
    session_results: list[DeribitHardCappedPaperSessionResult] = []
    for fixture in normalized_fixtures:
        trade_inputs = tuple(replace(item, ledger_state=current_ledger) for item in fixture.trade_inputs)
        session_request = DeribitHardCappedPaperSessionRequest(
            operator_id=request.operator_id,
            session_id=fixture.session_id,
            idempotency_key=fixture.idempotency_key,
            simulation_only=True,
            live_enabled=False,
            shadow_enabled=False,
            auto_loop_enabled=False,
            scheduler_enabled=False,
            max_session_trades=request.per_session_max_trades,
        )
        session_result = run_deribit_hard_capped_paper_session(
            session_request,
            trade_inputs,
            kill_switch_active=False,
            now_ns=now_ns,
        )
        session_results.append(session_result)
        if session_result.accepted is not True:
            rejection_reasons = tuple(
                dict.fromkeys(
                    (
                        "deribit_bounded_paper_campaign:session_rejected",
                        session_result.reason_code,
                        *session_result.rejection_reasons,
                    )
                )
            )
            after_summary = _ledger_summary_to_dict(current_ledger)
            return _result(
                request=request,
                approval_artifact=approval_artifact,
                accepted=False,
                reason_code=session_result.reason_code,
                rejection_reasons=rejection_reasons,
                session_results=tuple(session_results),
                final_ledger_state=current_ledger,
                before_summary=before_summary,
                after_summary=after_summary,
                sessions_requested=len(normalized_fixtures),
                aggregate_trades_requested=sum(len(item.trade_inputs) for item in normalized_fixtures),
            )
        assert session_result.final_ledger_state is not None
        current_ledger = session_result.final_ledger_state

    current_ledger = _record_campaign_markers(current_ledger, request)
    after_summary = _ledger_summary_to_dict(current_ledger)
    return _result(
        request=request,
        approval_artifact=approval_artifact,
        accepted=True,
        reason_code="deribit_bounded_paper_campaign:accepted",
        rejection_reasons=(),
        session_results=tuple(session_results),
        final_ledger_state=current_ledger,
        before_summary=before_summary,
        after_summary=after_summary,
        sessions_requested=len(normalized_fixtures),
        aggregate_trades_requested=sum(len(item.trade_inputs) for item in normalized_fixtures),
    )


def deribit_bounded_paper_campaign_audit_record_to_dict(
    record: DeribitBoundedPaperCampaignAuditRecord,
) -> dict[str, object]:
    return {
        "audit_id": record.audit_id,
        "operator_id": record.operator_id,
        "campaign_id": record.campaign_id,
        "approval_status": record.approval_status,
        "approval_decision": record.approval_decision,
        "sessions_requested": record.sessions_requested,
        "sessions_attempted": record.sessions_attempted,
        "sessions_accepted": record.sessions_accepted,
        "sessions_rejected": record.sessions_rejected,
        "aggregate_trades_requested": record.aggregate_trades_requested,
        "aggregate_trades_filled": record.aggregate_trades_filled,
        "aggregate_ledger_mutations": record.aggregate_ledger_mutations,
        "ledger_mutated": record.ledger_mutated,
        "reason_code": record.reason_code,
        "rejection_reasons": list(record.rejection_reasons),
        "before_ledger_summary": record.before_ledger_summary,
        "after_ledger_summary": record.after_ledger_summary,
        "policy_refs": list(record.policy_refs),
    }


def deribit_bounded_paper_campaign_result_to_dict(result: DeribitBoundedPaperCampaignResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "campaign_id": result.campaign_id,
        "sessions_requested": result.sessions_requested,
        "sessions_attempted": result.sessions_attempted,
        "sessions_accepted": result.sessions_accepted,
        "sessions_rejected": result.sessions_rejected,
        "aggregate_trades_requested": result.aggregate_trades_requested,
        "aggregate_trades_filled": result.aggregate_trades_filled,
        "aggregate_ledger_mutations": result.aggregate_ledger_mutations,
        "ledger_mutated": result.ledger_mutated,
        "reason_code": result.reason_code,
        "rejection_reasons": list(result.rejection_reasons),
        "before_ledger_summary": result.before_ledger_summary,
        "after_ledger_summary": result.after_ledger_summary,
        "audit_record": deribit_bounded_paper_campaign_audit_record_to_dict(result.audit_record),
        "artifact_payload": result.artifact_payload,
    }


def _request_rejection_reasons(request: object) -> tuple[str, ...]:
    if not isinstance(request, DeribitBoundedPaperCampaignRequest):
        return ("deribit_bounded_paper_campaign:request_malformed",)

    reasons: list[str] = []
    if not _non_empty(request.operator_id):
        reasons.append("deribit_bounded_paper_campaign:operator_id_missing")
    if not _non_empty(request.campaign_id):
        reasons.append("deribit_bounded_paper_campaign:campaign_id_missing")
    if not _non_empty(request.idempotency_key):
        reasons.append("deribit_bounded_paper_campaign:idempotency_key_missing")
    if request.simulation_only is not True:
        reasons.append("deribit_bounded_paper_campaign:not_simulation_only")
    if request.approved_campaign is not True:
        reasons.append("deribit_bounded_paper_campaign:campaign_not_approved")
    if request.live_enabled is not False:
        reasons.append("deribit_bounded_paper_campaign:live_enabled")
    if request.shadow_enabled is not False:
        reasons.append("deribit_bounded_paper_campaign:shadow_enabled")
    if request.auto_loop_enabled is not False:
        reasons.append("deribit_bounded_paper_campaign:auto_loop_enabled")
    if request.scheduler_enabled is not False:
        reasons.append("deribit_bounded_paper_campaign:scheduler_enabled")
    if request.hard_cap != DERIBIT_PAPER_SESSION_HARD_CAP:
        reasons.append("deribit_bounded_paper_campaign:hard_cap_mismatch")
    if request.per_session_max_trades != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION:
        reasons.append("deribit_bounded_paper_campaign:per_session_max_trades_mismatch")
    if (
        not isinstance(request.max_campaign_sessions, int)
        or isinstance(request.max_campaign_sessions, bool)
        or request.max_campaign_sessions <= 0
    ):
        reasons.append("deribit_bounded_paper_campaign:max_campaign_sessions_invalid")
    elif request.max_campaign_sessions > DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS:
        reasons.append("deribit_bounded_paper_campaign:max_campaign_sessions_exceeds_bound")
    if (
        _contains_scope_marker(request.operator_id)
        or _contains_scope_marker(request.campaign_id)
        or _contains_scope_marker(request.idempotency_key)
    ):
        reasons.append("deribit_bounded_paper_campaign:request_scope_invalid")
    return tuple(dict.fromkeys(reasons))


def _approval_rejection_reasons(approval_artifact: object) -> tuple[str, ...]:
    if not isinstance(approval_artifact, dict):
        return ("deribit_bounded_paper_campaign:approval_artifact_missing",)

    reasons: list[str] = []
    if approval_artifact.get("source_phase46_operator_proposal") != DERIBIT_PHASE46_PROPOSAL:
        reasons.append("deribit_bounded_paper_campaign:approval_source_phase46_mismatch")
    if approval_artifact.get("source_phase44_report_pack") != DERIBIT_PHASE44_REPORT_PACK:
        reasons.append("deribit_bounded_paper_campaign:approval_source_phase44_mismatch")
    if approval_artifact.get("approval_status") != DERIBIT_APPROVAL_STATUS:
        reasons.append("deribit_bounded_paper_campaign:approval_status_not_approved")
    if approval_artifact.get("approval_decision") != DERIBIT_APPROVAL_DECISION:
        reasons.append("deribit_bounded_paper_campaign:approval_decision_mismatch")
    if approval_artifact.get("reviewer_id") != DERIBIT_APPROVED_REVIEWER_ID:
        reasons.append("deribit_bounded_paper_campaign:approval_reviewer_mismatch")
    if approval_artifact.get("reviewed_at_iso") != DERIBIT_APPROVED_REVIEWED_AT_ISO:
        reasons.append("deribit_bounded_paper_campaign:approval_reviewed_at_mismatch")
    if approval_artifact.get("approval_scope") != DERIBIT_APPROVAL_SCOPE:
        reasons.append("deribit_bounded_paper_campaign:approval_scope_mismatch")
    if approval_artifact.get("bounded_repeated_paper_campaign_approved") is not True:
        reasons.append("deribit_bounded_paper_campaign:approval_flag_not_true")
    if approval_artifact.get("operator_approval_executed") is not True:
        reasons.append("deribit_bounded_paper_campaign:approval_not_executed")
    if approval_artifact.get("promotion_granted") is not False:
        reasons.append("deribit_bounded_paper_campaign:promotion_granted")
    if approval_artifact.get("campaign_execution_status") != "NOT_EXECUTED":
        reasons.append("deribit_bounded_paper_campaign:campaign_already_executed")
    if approval_artifact.get("session_execution_status") != "NOT_EXECUTED":
        reasons.append("deribit_bounded_paper_campaign:session_already_executed")
    if approval_artifact.get("run_execution_status") != "NOT_EXECUTED":
        reasons.append("deribit_bounded_paper_campaign:run_already_executed")
    scope = approval_artifact.get("campaign_scope")
    if not isinstance(scope, dict):
        reasons.append("deribit_bounded_paper_campaign:approval_campaign_scope_missing")
        scope = {}
    if scope.get("venue") != "deribit":
        reasons.append("deribit_bounded_paper_campaign:approval_venue_mismatch")
    if scope.get("public_market_data_only") is not True:
        reasons.append("deribit_bounded_paper_campaign:approval_public_market_data_only_not_true")
    if scope.get("paper_only") is not True:
        reasons.append("deribit_bounded_paper_campaign:approval_paper_only_not_true")
    if scope.get("simulation_only") is not True:
        reasons.append("deribit_bounded_paper_campaign:approval_simulation_only_not_true")
    if scope.get("explicit_operator_triggered") is not True:
        reasons.append("deribit_bounded_paper_campaign:approval_explicit_trigger_not_true")
    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        if scope.get(field) is not False:
            reasons.append(f"deribit_bounded_paper_campaign:approval_{field}")
    bounds = approval_artifact.get("campaign_bounds")
    if not isinstance(bounds, dict):
        reasons.append("deribit_bounded_paper_campaign:approval_campaign_bounds_missing")
        bounds = {}
    if bounds.get("hard_cap") != DERIBIT_PAPER_SESSION_HARD_CAP:
        reasons.append("deribit_bounded_paper_campaign:approval_hard_cap_mismatch")
    if bounds.get("per_session_max_trades") != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION:
        reasons.append("deribit_bounded_paper_campaign:approval_per_session_max_trades_mismatch")
    if bounds.get("max_sessions_approved") != DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS:
        reasons.append("deribit_bounded_paper_campaign:approval_max_sessions_mismatch")
    if bounds.get("max_total_paper_trades_approved") != (
        DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS * DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION
    ):
        reasons.append("deribit_bounded_paper_campaign:approval_max_total_trades_mismatch")
    safety = approval_artifact.get("safety_flags")
    if not isinstance(safety, dict):
        reasons.append("deribit_bounded_paper_campaign:approval_safety_flags_missing")
        safety = {}
    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_strategy_signal",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_shadow",
        "no_live",
    ):
        if safety.get(field) is not True:
            reasons.append(f"deribit_bounded_paper_campaign:approval_{field}_not_true")
    if approval_artifact.get("connector_ready_dialects_count") != 1:
        reasons.append("deribit_bounded_paper_campaign:approval_connector_ready_count_mismatch")
    return tuple(dict.fromkeys(reasons))


def _ledger_state_rejection_reasons(ledger_state: object) -> tuple[str, ...]:
    if not isinstance(ledger_state, DeribitPaperLedgerState):
        return ("deribit_bounded_paper_campaign:ledger_state_missing",)

    reasons: list[str] = []
    if ledger_state.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_bounded_paper_campaign:ledger_state_invalid")
    if not _non_empty(ledger_state.symbol) or not _non_empty(ledger_state.canonical_symbol):
        reasons.append("deribit_bounded_paper_campaign:ledger_state_invalid")
    return tuple(dict.fromkeys(reasons))


def _session_fixture_rejection_reasons(
    request: object,
    approval_artifact: object,
    normalized_fixtures: tuple[DeribitBoundedPaperCampaignSessionFixture, ...],
    raw_session_fixtures: object,
    ledger_state: object,
) -> tuple[str, ...]:
    if not isinstance(raw_session_fixtures, Sequence) or isinstance(raw_session_fixtures, str | bytes):
        return ("deribit_bounded_paper_campaign:session_fixtures_missing",)
    if not normalized_fixtures:
        return ("deribit_bounded_paper_campaign:session_fixtures_missing",)

    reasons: list[str] = []
    if len(normalized_fixtures) != len(raw_session_fixtures):
        reasons.append("deribit_bounded_paper_campaign:session_fixture_malformed")
    if not isinstance(request, DeribitBoundedPaperCampaignRequest):
        return tuple(dict.fromkeys(reasons))
    if not isinstance(ledger_state, DeribitPaperLedgerState):
        return tuple(dict.fromkeys(reasons))
    if len(normalized_fixtures) > request.max_campaign_sessions:
        reasons.append("deribit_bounded_paper_campaign:session_count_exceeds_campaign_bound")
    if isinstance(approval_artifact, dict):
        bounds = approval_artifact.get("campaign_bounds")
        if isinstance(bounds, dict):
            max_sessions_approved = _strict_int(bounds.get("max_sessions_approved"))
            max_total_trades_approved = _strict_int(bounds.get("max_total_paper_trades_approved"))
            if request.operator_id != approval_artifact.get("reviewer_id"):
                reasons.append("deribit_bounded_paper_campaign:operator_approval_mismatch")
            if request.hard_cap != bounds.get("hard_cap"):
                reasons.append("deribit_bounded_paper_campaign:hard_cap_approval_mismatch")
            if request.per_session_max_trades != bounds.get("per_session_max_trades"):
                reasons.append("deribit_bounded_paper_campaign:per_session_max_trades_approval_mismatch")
            if max_sessions_approved is None:
                reasons.append("deribit_bounded_paper_campaign:approval_max_sessions_invalid")
            elif request.max_campaign_sessions > max_sessions_approved:
                reasons.append("deribit_bounded_paper_campaign:max_campaign_sessions_exceeds_approval")
            if max_total_trades_approved is None:
                reasons.append("deribit_bounded_paper_campaign:approval_max_total_trades_invalid")
            elif sum(len(item.trade_inputs) for item in normalized_fixtures) > max_total_trades_approved:
                reasons.append("deribit_bounded_paper_campaign:aggregate_trade_count_exceeds_approval")
    if request.campaign_id in ledger_state.applied_request_ids:
        reasons.append("deribit_bounded_paper_campaign:duplicate_campaign_id")
    if request.idempotency_key in ledger_state.applied_idempotency_keys:
        reasons.append("deribit_bounded_paper_campaign:duplicate_campaign_idempotency_key")
    session_ids = tuple(item.session_id for item in normalized_fixtures)
    session_idempotency_keys = tuple(item.idempotency_key for item in normalized_fixtures)
    if any(not _non_empty(item.session_id) for item in normalized_fixtures):
        reasons.append("deribit_bounded_paper_campaign:session_id_missing")
    if any(not _non_empty(item.idempotency_key) for item in normalized_fixtures):
        reasons.append("deribit_bounded_paper_campaign:session_idempotency_key_missing")
    if any(_contains_scope_marker(item.session_id) for item in normalized_fixtures) or any(
        _contains_scope_marker(item.idempotency_key) for item in normalized_fixtures
    ):
        reasons.append("deribit_bounded_paper_campaign:session_scope_invalid")
    if len(set(session_ids)) != len(session_ids):
        reasons.append("deribit_bounded_paper_campaign:duplicate_session_id")
    if len(set(session_idempotency_keys)) != len(session_idempotency_keys):
        reasons.append("deribit_bounded_paper_campaign:duplicate_session_idempotency_key")
    if any(item.session_id in ledger_state.applied_request_ids for item in normalized_fixtures):
        reasons.append("deribit_bounded_paper_campaign:duplicate_session_id")
    if any(item.idempotency_key in ledger_state.applied_idempotency_keys for item in normalized_fixtures):
        reasons.append("deribit_bounded_paper_campaign:duplicate_session_idempotency_key")
    for fixture in normalized_fixtures:
        if not fixture.trade_inputs:
            reasons.append("deribit_bounded_paper_campaign:session_trade_inputs_missing")
        if len(fixture.trade_inputs) > request.per_session_max_trades:
            reasons.append("deribit_bounded_paper_campaign:session_trade_count_exceeds_session_bound")
        if len(fixture.trade_inputs) > request.hard_cap:
            reasons.append("deribit_bounded_paper_campaign:session_trade_count_exceeds_hard_cap")
        if any(not isinstance(item, DeribitPaperRunHarnessInputs) for item in fixture.trade_inputs):
            reasons.append("deribit_bounded_paper_campaign:session_trade_input_malformed")
    trade_inputs = tuple(item for fixture in normalized_fixtures for item in fixture.trade_inputs)
    if any(not isinstance(item, DeribitPaperRunHarnessInputs) for item in trade_inputs):
        return tuple(dict.fromkeys(reasons))
    request_ids = tuple(item.fill_request.request_id for item in trade_inputs)
    trade_idempotency_keys = tuple(item.intent.idempotency_key for item in trade_inputs)
    if len(set(request_ids)) != len(request_ids):
        reasons.append("deribit_bounded_paper_campaign:duplicate_trade_request_id")
    if len(set(trade_idempotency_keys)) != len(trade_idempotency_keys):
        reasons.append("deribit_bounded_paper_campaign:duplicate_trade_idempotency_key")
    if any(request_id in ledger_state.applied_request_ids for request_id in request_ids):
        reasons.append("deribit_bounded_paper_campaign:duplicate_trade_request_id")
    if any(key in ledger_state.applied_idempotency_keys for key in trade_idempotency_keys):
        reasons.append("deribit_bounded_paper_campaign:duplicate_trade_idempotency_key")
    return tuple(dict.fromkeys(reasons))


def _kill_switch_rejection_reasons(kill_switch_active: object) -> tuple[str, ...]:
    if not isinstance(kill_switch_active, bool):
        return ("deribit_bounded_paper_campaign:kill_switch_flag_invalid",)
    if kill_switch_active is True:
        return ("deribit_bounded_paper_campaign:kill_switch_active",)
    return ()


def _connector_rejection_reasons() -> tuple[str, ...]:
    if len(connector_ready_dialects()) != 1:
        return ("deribit_bounded_paper_campaign:connector_ready_dialects_mismatch",)
    return ()


def _normalized_session_fixtures(session_fixtures: object) -> tuple[DeribitBoundedPaperCampaignSessionFixture, ...]:
    if not isinstance(session_fixtures, Sequence) or isinstance(session_fixtures, str | bytes):
        return ()
    return tuple(item for item in session_fixtures if isinstance(item, DeribitBoundedPaperCampaignSessionFixture))


def _raw_session_count(session_fixtures: object) -> int:
    if not isinstance(session_fixtures, Sequence) or isinstance(session_fixtures, str | bytes):
        return 0
    return len(session_fixtures)


def _raw_trade_count(session_fixtures: object) -> int:
    if not isinstance(session_fixtures, Sequence) or isinstance(session_fixtures, str | bytes):
        return 0
    total = 0
    for fixture in session_fixtures:
        if isinstance(fixture, DeribitBoundedPaperCampaignSessionFixture):
            total += len(fixture.trade_inputs)
    return total


def _result(
    *,
    request: object,
    approval_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    session_results: tuple[DeribitHardCappedPaperSessionResult, ...],
    final_ledger_state: DeribitPaperLedgerState | None,
    before_summary: dict[str, object] | None,
    after_summary: dict[str, object] | None,
    sessions_requested: int,
    aggregate_trades_requested: int,
) -> DeribitBoundedPaperCampaignResult:
    sessions_attempted = len(session_results)
    sessions_accepted = sum(1 for item in session_results if item.accepted)
    sessions_rejected = sum(1 for item in session_results if item.accepted is not True)
    aggregate_trades_filled = sum(item.trades_filled for item in session_results)
    aggregate_ledger_mutations = sum(item.trades_filled for item in session_results)
    ledger_mutated = aggregate_ledger_mutations > 0
    audit_record = DeribitBoundedPaperCampaignAuditRecord(
        audit_id=f"{DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID}:{getattr(request, 'campaign_id', 'missing-campaign')}:{reason_code}",
        operator_id=getattr(request, "operator_id", None),
        campaign_id=getattr(request, "campaign_id", None),
        approval_status=approval_artifact.get("approval_status") if isinstance(approval_artifact, dict) else None,
        approval_decision=approval_artifact.get("approval_decision") if isinstance(approval_artifact, dict) else None,
        sessions_requested=sessions_requested,
        sessions_attempted=sessions_attempted,
        sessions_accepted=sessions_accepted,
        sessions_rejected=sessions_rejected,
        aggregate_trades_requested=aggregate_trades_requested,
        aggregate_trades_filled=aggregate_trades_filled,
        aggregate_ledger_mutations=aggregate_ledger_mutations,
        ledger_mutated=ledger_mutated,
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        before_ledger_summary=before_summary,
        after_ledger_summary=after_summary,
    )
    return DeribitBoundedPaperCampaignResult(
        accepted=accepted,
        campaign_id=getattr(request, "campaign_id", None),
        sessions_requested=sessions_requested,
        sessions_attempted=sessions_attempted,
        sessions_accepted=sessions_accepted,
        sessions_rejected=sessions_rejected,
        aggregate_trades_requested=aggregate_trades_requested,
        aggregate_trades_filled=aggregate_trades_filled,
        aggregate_ledger_mutations=aggregate_ledger_mutations,
        ledger_mutated=ledger_mutated,
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        session_results=session_results,
        final_ledger_state=final_ledger_state,
        before_ledger_summary=before_summary,
        after_ledger_summary=after_summary,
        audit_record=audit_record,
        artifact_payload=_artifact_payload(
            request=request,
            approval_artifact=approval_artifact,
            accepted=accepted,
            reason_code=reason_code,
            rejection_reasons=rejection_reasons,
            sessions_requested=sessions_requested,
            sessions_attempted=sessions_attempted,
            sessions_accepted=sessions_accepted,
            sessions_rejected=sessions_rejected,
            aggregate_trades_requested=aggregate_trades_requested,
            aggregate_trades_filled=aggregate_trades_filled,
            aggregate_ledger_mutations=aggregate_ledger_mutations,
            ledger_mutated=ledger_mutated,
            session_results=session_results,
            before_summary=before_summary,
            after_summary=after_summary,
        ),
    )


def _artifact_payload(
    *,
    request: object,
    approval_artifact: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    sessions_requested: int,
    sessions_attempted: int,
    sessions_accepted: int,
    sessions_rejected: int,
    aggregate_trades_requested: int,
    aggregate_trades_filled: int,
    aggregate_ledger_mutations: int,
    ledger_mutated: bool,
    session_results: tuple[DeribitHardCappedPaperSessionResult, ...],
    before_summary: dict[str, object] | None,
    after_summary: dict[str, object] | None,
) -> dict[str, object]:
    request_is_valid = isinstance(request, DeribitBoundedPaperCampaignRequest)
    approval_is_valid = isinstance(approval_artifact, dict)
    return {
        "schema_version": "deribit_bounded_repeated_paper_campaign_execution.v1",
        "phase": "48",
        "source": DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID,
        "source_phase47_approval": DERIBIT_PHASE47_APPROVAL,
        "source_phase46_proposal": DERIBIT_PHASE46_PROPOSAL,
        "source_phase44_report_pack": DERIBIT_PHASE44_REPORT_PACK,
        "campaign_id": request.campaign_id if request_is_valid else None,
        "operator_id": request.operator_id if request_is_valid else None,
        "idempotency_key_sha256": _sha256(request.idempotency_key)
        if request_is_valid and _non_empty(request.idempotency_key)
        else None,
        "approval_status": approval_artifact.get("approval_status") if approval_is_valid else None,
        "approval_decision": approval_artifact.get("approval_decision") if approval_is_valid else None,
        "simulation_only": request.simulation_only if request_is_valid else None,
        "live_enabled": request.live_enabled if request_is_valid else None,
        "shadow_enabled": request.shadow_enabled if request_is_valid else None,
        "auto_loop_enabled": request.auto_loop_enabled if request_is_valid else None,
        "scheduler_enabled": request.scheduler_enabled if request_is_valid else None,
        "hard_cap": request.hard_cap if request_is_valid else None,
        "per_session_max_trades": request.per_session_max_trades if request_is_valid else None,
        "max_campaign_sessions": request.max_campaign_sessions if request_is_valid else None,
        "sessions_requested": sessions_requested,
        "sessions_attempted": sessions_attempted,
        "sessions_accepted": sessions_accepted,
        "sessions_rejected": sessions_rejected,
        "aggregate_trades_requested": aggregate_trades_requested,
        "aggregate_trades_filled": aggregate_trades_filled,
        "aggregate_ledger_mutations": aggregate_ledger_mutations,
        "ledger_mutated": ledger_mutated,
        "duplicate_mutation_blocked": True,
        "reason_code": reason_code,
        "rejection_reasons": list(dict.fromkeys(rejection_reasons)),
        "session_results": [_session_result_summary(item) for item in session_results],
        "before_ledger_summary": before_summary,
        "after_ledger_summary": after_summary,
        "no_private_api": True,
        "no_credentials": True,
        "no_exchange_orders": True,
        "no_execution_adapter": True,
        "no_order_routing": True,
        "no_strategy_signal": True,
        "no_scheduler": True,
        "no_automatic_paper_loop": True,
        "no_shadow": True,
        "no_live": True,
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "campaign_execution_verdict": "PASS" if accepted else "FAIL_CLOSED",
        "live_ready": False,
        "policy_refs": list(_POLICY_REFS),
        "next_blocker": DERIBIT_PHASE48_NEXT_BLOCKER
        if accepted
        else "BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_NOT_READY",
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


def _ledger_summary_to_dict(ledger_state: DeribitPaperLedgerState | None) -> dict[str, object] | None:
    if not isinstance(ledger_state, DeribitPaperLedgerState):
        return None
    return {
        "ledger_id": ledger_state.ledger_id,
        "symbol": ledger_state.symbol,
        "canonical_symbol": ledger_state.canonical_symbol,
        "cash_balance": ledger_state.cash_balance,
        "position_qty": ledger_state.position_qty,
        "average_entry_price": ledger_state.average_entry_price,
        "realized_pnl": ledger_state.realized_pnl,
        "applied_fill_count": len(ledger_state.applied_fill_ids),
        "applied_request_count": len(ledger_state.applied_request_ids),
        "applied_idempotency_count": len(ledger_state.applied_idempotency_keys),
        "audit_entry_count": len(ledger_state.audit_entries),
    }


def _record_campaign_markers(
    ledger_state: DeribitPaperLedgerState,
    request: DeribitBoundedPaperCampaignRequest,
) -> DeribitPaperLedgerState:
    return replace(
        ledger_state,
        applied_request_ids=ledger_state.applied_request_ids + (request.campaign_id,),
        applied_idempotency_keys=ledger_state.applied_idempotency_keys + (request.idempotency_key,),
    )


def _contains_scope_marker(value: object) -> bool:
    return isinstance(value, str) and any(marker in value.lower() for marker in _SCOPE_MARKERS)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _strict_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "DERIBIT_APPROVAL_DECISION",
    "DERIBIT_APPROVAL_SCOPE",
    "DERIBIT_APPROVAL_STATUS",
    "DERIBIT_APPROVED_REVIEWED_AT_ISO",
    "DERIBIT_APPROVED_REVIEWER_ID",
    "DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID",
    "DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_SESSIONS",
    "DERIBIT_BOUNDED_PAPER_CAMPAIGN_MAX_TRADES_PER_SESSION",
    "DERIBIT_PHASE44_REPORT_PACK",
    "DERIBIT_PHASE46_PROPOSAL",
    "DERIBIT_PHASE47_APPROVAL",
    "DERIBIT_PHASE48_NEXT_BLOCKER",
    "DeribitBoundedPaperCampaignAuditRecord",
    "DeribitBoundedPaperCampaignRequest",
    "DeribitBoundedPaperCampaignResult",
    "DeribitBoundedPaperCampaignSessionFixture",
    "deribit_bounded_paper_campaign_audit_record_to_dict",
    "deribit_bounded_paper_campaign_result_to_dict",
    "run_deribit_bounded_paper_campaign",
]
