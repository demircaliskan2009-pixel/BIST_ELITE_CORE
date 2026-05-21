from __future__ import annotations

import math
from dataclasses import dataclass, replace

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_paper_fill_model import DERIBIT_PAPER_FILL_MODEL_ID, DeribitPaperFillResult
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentDecision,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
)

DERIBIT_PAPER_LEDGER_ID = "deribit_paper_ledger_v1"
REALIZED_PNL_ON_CLOSE_ONLY = "REALIZED_PNL_ON_CLOSE_ONLY"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
_SCOPE_MARKERS = frozenset(
    {"account", "auth", "credential", "exchange_order", "live", "private", "route", "shadow", "token", "withdraw"}
)
_POLICY_REFS = (
    "DERIBIT_PAPER_FEED_PIPELINE_33A.md",
    "PAPER_SIMULATOR_FILL_MODEL_34A.md",
    "PAPER_ORDER_INTENT_RISK_GATE_35A.md",
    "PAPER_LEDGER_FILL_APPLICATION_36A.md",
)


@dataclass(frozen=True)
class DeribitPaperLedgerIntentReference:
    intent_id: str
    idempotency_key: str
    request_id: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    side: DeribitPaperOrderIntentSide
    quantity: float
    limit_price: float
    simulation_only: bool


@dataclass(frozen=True)
class DeribitPaperLedgerAuditEntry:
    entry_id: str
    fill_id: str
    request_id: str
    idempotency_key: str
    side: DeribitPaperOrderIntentSide
    symbol: str
    canonical_symbol: str
    fill_qty: float
    fill_price: float
    realized_pnl_delta: float
    resulting_position_qty: float
    resulting_average_entry_price: float | None


@dataclass(frozen=True)
class DeribitPaperLedgerState:
    ledger_id: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    cash_balance: float
    position_qty: float
    average_entry_price: float | None
    realized_pnl: float
    applied_fill_ids: tuple[str, ...] = ()
    applied_request_ids: tuple[str, ...] = ()
    applied_idempotency_keys: tuple[str, ...] = ()
    audit_entries: tuple[DeribitPaperLedgerAuditEntry, ...] = ()
    accounting_policy: str = REALIZED_PNL_ON_CLOSE_ONLY
    fees_policy: str = NOT_IMPLEMENTED
    slippage_policy: str = NOT_IMPLEMENTED
    margin_policy: str = NOT_IMPLEMENTED
    funding_policy: str = NOT_IMPLEMENTED
    policy_refs: tuple[str, ...] = _POLICY_REFS


@dataclass(frozen=True)
class DeribitPaperLedgerApplyResult:
    accepted: bool
    ledger_state: DeribitPaperLedgerState | None
    audit_entry: DeribitPaperLedgerAuditEntry | None
    rejection_reasons: tuple[str, ...]
    ledger_mutated: bool


def build_deribit_paper_ledger_state(
    *,
    initial_cash_balance: float,
    venue_id: VenueId = VenueId.DERIBIT,
    symbol: str,
    canonical_symbol: str,
    ledger_id: str | None = None,
) -> DeribitPaperLedgerState:
    resolved_ledger_id = ledger_id or f"{DERIBIT_PAPER_LEDGER_ID}:{symbol}"
    if venue_id is not VenueId.DERIBIT or not _non_empty(symbol) or not _non_empty(canonical_symbol):
        raise ValueError("deribit paper ledger state requires explicit Deribit instrument identity")
    if not _finite_non_negative(initial_cash_balance) or not _non_empty(resolved_ledger_id):
        raise ValueError("deribit paper ledger state requires explicit non-negative initial cash")
    return DeribitPaperLedgerState(
        ledger_id=resolved_ledger_id,
        venue_id=venue_id,
        symbol=symbol,
        canonical_symbol=canonical_symbol,
        cash_balance=float(initial_cash_balance),
        position_qty=0.0,
        average_entry_price=None,
        realized_pnl=0.0,
    )


def normalize_deribit_paper_ledger_intent_reference(
    intent: object,
    decision: object,
) -> DeribitPaperLedgerIntentReference | None:
    if not isinstance(intent, DeribitPaperOrderIntent) or not isinstance(decision, DeribitPaperOrderIntentDecision):
        return None
    fill_request = decision.fill_request
    if (
        decision.accepted is not True
        or fill_request is None
        or decision.kill_switch_active is not False
        or fill_request.simulation_only is not True
        or intent.simulation_only is not True
        or intent.order_style is not DeribitPaperOrderStyle.LIMIT
        or fill_request.request_id != intent.intent_id
        or fill_request.quantity != intent.quantity
        or fill_request.limit_price != intent.limit_price
        or _contains_scope_marker(intent.intent_id)
        or _contains_scope_marker(intent.idempotency_key)
    ):
        return None
    return DeribitPaperLedgerIntentReference(
        intent_id=intent.intent_id,
        idempotency_key=intent.idempotency_key,
        request_id=fill_request.request_id,
        venue_id=intent.venue_id,
        symbol=intent.symbol,
        canonical_symbol=intent.canonical_symbol,
        side=intent.side,
        quantity=intent.quantity,
        limit_price=float(intent.limit_price or 0.0),
        simulation_only=True,
    )


def apply_deribit_paper_fill_to_ledger(
    ledger_state: object,
    intent_reference: object,
    fill_result: object,
    *,
    kill_switch_active: bool | None = None,
) -> DeribitPaperLedgerApplyResult:
    state = ledger_state if isinstance(ledger_state, DeribitPaperLedgerState) else None
    reasons = _rejection_reasons(ledger_state, intent_reference, fill_result, kill_switch_active=kill_switch_active)
    if reasons:
        return DeribitPaperLedgerApplyResult(False, state, None, reasons, False)

    assert state is not None
    assert isinstance(intent_reference, DeribitPaperLedgerIntentReference)
    assert isinstance(fill_result, DeribitPaperFillResult)
    assert fill_result.simulated_qty is not None
    assert fill_result.simulated_price is not None
    assert fill_result.fill_id is not None
    new_qty, new_avg, realized_delta = _apply_position(
        state.position_qty,
        state.average_entry_price,
        intent_reference.side,
        fill_result.simulated_qty,
        fill_result.simulated_price,
    )
    entry = DeribitPaperLedgerAuditEntry(
        entry_id=f"{DERIBIT_PAPER_LEDGER_ID}:{fill_result.fill_id}",
        fill_id=fill_result.fill_id,
        request_id=intent_reference.request_id,
        idempotency_key=intent_reference.idempotency_key,
        side=intent_reference.side,
        symbol=state.symbol,
        canonical_symbol=state.canonical_symbol,
        fill_qty=fill_result.simulated_qty,
        fill_price=fill_result.simulated_price,
        realized_pnl_delta=realized_delta,
        resulting_position_qty=new_qty,
        resulting_average_entry_price=new_avg,
    )
    next_state = replace(
        state,
        cash_balance=state.cash_balance + realized_delta,
        position_qty=new_qty,
        average_entry_price=new_avg,
        realized_pnl=state.realized_pnl + realized_delta,
        applied_fill_ids=state.applied_fill_ids + (fill_result.fill_id,),
        applied_request_ids=state.applied_request_ids + (intent_reference.request_id,),
        applied_idempotency_keys=state.applied_idempotency_keys + (intent_reference.idempotency_key,),
        audit_entries=state.audit_entries + (entry,),
    )
    return DeribitPaperLedgerApplyResult(True, next_state, entry, (), True)
