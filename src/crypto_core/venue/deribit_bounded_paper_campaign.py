from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crypto_core.venue.deribit_hard_capped_paper_session import (
    DERIBIT_PAPER_SESSION_HARD_CAP,
    DeribitHardCappedPaperSessionResult,
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
    return _result(
        request=request,
        approval_artifact=approval_artifact,
        accepted=False,
        reason_code=reasons[0] if reasons else "deribit_bounded_paper_campaign:not_ready",
        rejection_reasons=reasons if reasons else ("deribit_bounded_paper_campaign:not_ready",),
        session_results=(),
        final_ledger_state=initial_ledger,
        before_summary=before_summary,
        after_summary=before_summary,
        sessions_requested=_raw_session_count(session_fixtures),
        aggregate_trades_requested=_raw_trade_count(session_fixtures),
    )


def deribit_bounded_paper_campaign_audit_record_to_dict(record: DeribitBoundedPaperCampaignAuditRecord) -> dict[str, object]:
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
    }


def deribit_bounded_paper_campaign_result_to_dict(result: DeribitBoundedPaperCampaignResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "campaign_id": result.campaign_id,
        "sessions_requested": result.sessions_requested,
        "sessions_attempted": result.sessions_attempted,
        "audit_record": deribit_bounded_paper_campaign_audit_record_to_dict(result.audit_record),
        "artifact_payload": result.artifact_payload,
    }


def _request_rejection_reasons(request: object) -> tuple[str, ...]:
    return ()


def _approval_rejection_reasons(approval_artifact: object) -> tuple[str, ...]:
    return ()


def _ledger_state_rejection_reasons(ledger_state: object) -> tuple[str, ...]:
    return ()


def _session_fixture_rejection_reasons(
    request: object,
    approval_artifact: object,
    normalized_fixtures: tuple[DeribitBoundedPaperCampaignSessionFixture, ...],
    raw_session_fixtures: object,
    ledger_state: object,
) -> tuple[str, ...]:
    return ()


def _kill_switch_rejection_reasons(kill_switch_active: object) -> tuple[str, ...]:
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
    audit_record = DeribitBoundedPaperCampaignAuditRecord(
        audit_id=f"{DERIBIT_BOUNDED_PAPER_CAMPAIGN_ID}:{getattr(request, 'campaign_id', 'missing-campaign')}:{reason_code}",
        operator_id=getattr(request, "operator_id", None),
        campaign_id=getattr(request, "campaign_id", None),
        approval_status=approval_artifact.get("approval_status") if isinstance(approval_artifact, dict) else None,
        approval_decision=approval_artifact.get("approval_decision") if isinstance(approval_artifact, dict) else None,
        sessions_requested=sessions_requested,
        sessions_attempted=len(session_results),
        sessions_accepted=0,
        sessions_rejected=0,
        aggregate_trades_requested=aggregate_trades_requested,
        aggregate_trades_filled=0,
        aggregate_ledger_mutations=0,
        ledger_mutated=False,
        reason_code=reason_code,
        rejection_reasons=rejection_reasons,
        before_ledger_summary=before_summary,
        after_ledger_summary=after_summary,
    )
    return DeribitBoundedPaperCampaignResult(
        accepted=accepted,
        campaign_id=getattr(request, "campaign_id", None),
        sessions_requested=sessions_requested,
        sessions_attempted=len(session_results),
        sessions_accepted=0,
        sessions_rejected=0,
        aggregate_trades_requested=aggregate_trades_requested,
        aggregate_trades_filled=0,
        aggregate_ledger_mutations=0,
        ledger_mutated=False,
        reason_code=reason_code,
        rejection_reasons=rejection_reasons,
        session_results=session_results,
        final_ledger_state=final_ledger_state,
        before_ledger_summary=before_summary,
        after_ledger_summary=after_summary,
        audit_record=audit_record,
        artifact_payload={"reason_code": reason_code, "rejection_reasons": list(rejection_reasons)},
    )


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
