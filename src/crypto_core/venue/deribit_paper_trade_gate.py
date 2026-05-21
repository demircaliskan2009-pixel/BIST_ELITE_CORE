from __future__ import annotations

from dataclasses import dataclass

from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.deribit_paper_feed import DeribitPaperFeedFrame
from crypto_core.venue.deribit_paper_fill_model import DeribitPaperFillRequest, evaluate_deribit_paper_limit_fill
from crypto_core.venue.deribit_paper_ledger import (
    DeribitPaperLedgerState,
    apply_deribit_paper_fill_to_ledger,
    normalize_deribit_paper_ledger_intent_reference,
)
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentDecision,
)

DERIBIT_PAPER_TRADE_GATE_ID = "deribit_paper_trade_gate_v1"

_POLICY_REFS = (
    "DERIBIT_PAPER_FEED_PIPELINE_33A.md",
    "PAPER_SIMULATOR_FILL_MODEL_34A.md",
    "PAPER_ORDER_INTENT_RISK_GATE_35A.md",
    "PAPER_LEDGER_FILL_APPLICATION_36A.md",
    "FIRST_PAPER_TRADE_GATE_37A.md",
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
        "shadow",
        "signal",
        "strategy",
        "token",
        "withdraw",
    }
)


@dataclass(frozen=True)
class DeribitPaperTradeOperatorTrigger:
    operator_id: str
    run_id: str
    idempotency_key: str
    simulation_only: bool
    live_enabled: bool = False
    shadow_enabled: bool = False
    auto_loop_enabled: bool = False


@dataclass(frozen=True)
class DeribitPaperTradeLedgerSummary:
    ledger_id: str
    symbol: str
    canonical_symbol: str
    cash_balance: float
    position_qty: float
    average_entry_price: float | None
    realized_pnl: float
    applied_fill_count: int
    applied_request_count: int
    applied_idempotency_count: int
    audit_entry_count: int


@dataclass(frozen=True)
class DeribitPaperTradeGateAuditRecord:
    audit_id: str
    operator_id: str | None
    run_id: str | None
    idempotency_key: str | None
    request_id: str | None
    fill_id: str | None
    accepted: bool
    filled: bool
    ledger_mutated: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    before_ledger_summary: DeribitPaperTradeLedgerSummary | None
    after_ledger_summary: DeribitPaperTradeLedgerSummary | None
    policy_refs: tuple[str, ...] = _POLICY_REFS


@dataclass(frozen=True)
class DeribitPaperTradeGateResult:
    accepted: bool
    filled: bool
    ledger_mutated: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    run_id: str | None
    request_id: str | None
    fill_id: str | None
    ledger_state: DeribitPaperLedgerState | None
    before_ledger_summary: DeribitPaperTradeLedgerSummary | None
    after_ledger_summary: DeribitPaperTradeLedgerSummary | None
    audit_record: DeribitPaperTradeGateAuditRecord


def run_deribit_paper_trade_gate(
    operator_trigger: object,
    intent: object,
    decision: object,
    fill_request: object,
    frame: object,
    ledger_state: object,
    *,
    kill_switch_active: bool = False,
    now_ns: int | None = None,
) -> DeribitPaperTradeGateResult:
    run_id = operator_trigger.run_id if isinstance(operator_trigger, DeribitPaperTradeOperatorTrigger) else None
    request_id = fill_request.request_id if isinstance(fill_request, DeribitPaperFillRequest) else None
    before_summary = _ledger_summary(ledger_state)
    reasons = _rejection_reasons(
        operator_trigger,
        intent,
        decision,
        fill_request,
        frame,
        ledger_state,
        kill_switch_active=kill_switch_active,
        now_ns=now_ns,
    )
    if reasons:
        return _result(
            accepted=False,
            filled=False,
            ledger_mutated=False,
            reason_code=reasons[0],
            rejection_reasons=reasons,
            operator_trigger=operator_trigger,
            run_id=run_id,
            request_id=request_id,
            fill_id=None,
            ledger_state=ledger_state if isinstance(ledger_state, DeribitPaperLedgerState) else None,
            before_summary=before_summary,
            after_summary=before_summary,
        )

    assert isinstance(operator_trigger, DeribitPaperTradeOperatorTrigger)
    assert isinstance(intent, DeribitPaperOrderIntent)
    assert isinstance(decision, DeribitPaperOrderIntentDecision)
    assert isinstance(fill_request, DeribitPaperFillRequest)
    assert isinstance(frame, DeribitPaperFeedFrame)
    assert isinstance(ledger_state, DeribitPaperLedgerState)

    fill_result = evaluate_deribit_paper_limit_fill(frame, fill_request, now_ns=now_ns)
    if fill_result.accepted is not True:
        rejection_reasons = tuple(
            dict.fromkeys(
                (
                    "deribit_paper_trade_gate:fill_result_rejected",
                    fill_result.reason_code,
                    *fill_result.rejection_reasons,
                )
            )
        )
        return _result(
            accepted=False,
            filled=False,
            ledger_mutated=False,
            reason_code=fill_result.reason_code,
            rejection_reasons=rejection_reasons,
            operator_trigger=operator_trigger,
            run_id=operator_trigger.run_id,
            request_id=fill_request.request_id,
            fill_id=fill_result.fill_id,
            ledger_state=ledger_state,
            before_summary=before_summary,
            after_summary=before_summary,
        )

    if fill_result.filled is not True:
        return _result(
            accepted=True,
            filled=False,
            ledger_mutated=False,
            reason_code=fill_result.reason_code,
            rejection_reasons=(),
            operator_trigger=operator_trigger,
            run_id=operator_trigger.run_id,
            request_id=fill_request.request_id,
            fill_id=fill_result.fill_id,
            ledger_state=ledger_state,
            before_summary=before_summary,
            after_summary=before_summary,
        )

    intent_reference = normalize_deribit_paper_ledger_intent_reference(intent, decision)
    if intent_reference is None:
        return _result(
            accepted=False,
            filled=False,
