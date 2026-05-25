from __future__ import annotations

from dataclasses import dataclass

from crypto_core.venue.deribit_hard_capped_paper_session import (
    DERIBIT_PAPER_SESSION_HARD_CAP,
    DeribitHardCappedPaperSessionResult,
)
from crypto_core.venue.deribit_paper_ledger import DeribitPaperLedgerState
from crypto_core.venue.deribit_paper_run_harness import DeribitPaperRunHarnessInputs

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
