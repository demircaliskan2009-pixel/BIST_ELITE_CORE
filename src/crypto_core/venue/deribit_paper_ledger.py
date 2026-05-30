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


def _rejection_reasons(
    ledger_state: object,
    intent_reference: object,
    fill_result: object,
    *,
    kill_switch_active: bool | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not isinstance(ledger_state, DeribitPaperLedgerState):
        reasons.append("deribit_paper_ledger:absent_required_ledger_state")
    else:
        if (
            ledger_state.venue_id is not VenueId.DERIBIT
            or not _non_empty(ledger_state.symbol)
            or not _non_empty(ledger_state.canonical_symbol)
        ):
            reasons.append("deribit_paper_ledger:ledger_state_invalid")
        if _contains_scope_marker(ledger_state.ledger_id) or not _finite_non_negative(ledger_state.cash_balance):
            reasons.append("deribit_paper_ledger:ledger_state_invalid")
        if ledger_state.position_qty == 0.0 and ledger_state.average_entry_price is not None:
            reasons.append("deribit_paper_ledger:ledger_state_invalid")
        if ledger_state.position_qty != 0.0 and not _positive_float(ledger_state.average_entry_price):
            reasons.append("deribit_paper_ledger:ledger_state_invalid")
    if not isinstance(intent_reference, DeribitPaperLedgerIntentReference):
        reasons.append("deribit_paper_ledger:intent_reference_malformed")
    else:
        if (
            intent_reference.venue_id is not VenueId.DERIBIT
            or not _non_empty(intent_reference.intent_id)
            or not _non_empty(intent_reference.request_id)
            or not _non_empty(intent_reference.idempotency_key)
            or not _non_empty(intent_reference.symbol)
            or not _non_empty(intent_reference.canonical_symbol)
            or not _positive_float(intent_reference.quantity)
            or not _positive_float(intent_reference.limit_price)
            or intent_reference.simulation_only is not True
            or _contains_scope_marker(intent_reference.intent_id)
            or _contains_scope_marker(intent_reference.idempotency_key)
        ):
            reasons.append("deribit_paper_ledger:intent_reference_invalid")
    if kill_switch_active is not None and not isinstance(kill_switch_active, bool):
        reasons.append("deribit_paper_ledger:kill_switch_flag_invalid")
    elif kill_switch_active is True:
        reasons.append("deribit_paper_ledger:kill_switch_active")
    if not isinstance(fill_result, DeribitPaperFillResult):
        reasons.append("deribit_paper_ledger:fill_result_malformed")
        return tuple(dict.fromkeys(reasons))
    if fill_result.accepted is not True:
        return tuple(
            dict.fromkeys([*reasons, "deribit_paper_ledger:fill_result_rejected", *fill_result.rejection_reasons])
        )
    if fill_result.filled is not True:
        return tuple(dict.fromkeys([*reasons, "deribit_paper_ledger:no_fill_result"]))
    if (
        not _non_empty(fill_result.fill_id)
        or fill_result.venue_id is not VenueId.DERIBIT
        or not _positive_float(fill_result.simulated_qty)
        or not _positive_float(fill_result.simulated_price)
        or not _positive_int(fill_result.source_event_time_ns)
        or not _positive_int(fill_result.source_receive_time_ns)
        or not _non_negative_int(fill_result.source_sequence_id)
        or fill_result.source_receive_time_ns < fill_result.source_event_time_ns
        or fill_result.venue_submission_ready is not False
        or fill_result.trade_ready is not False
        or fill_result.position_mutation_ready is not False
        or fill_result.strategy_signal_ready is not False
        or _contains_scope_marker(fill_result.fill_id)
        or _contains_scope_marker(fill_result.reason_code)
    ):
        reasons.append("deribit_paper_ledger:fill_result_invalid")
    if isinstance(ledger_state, DeribitPaperLedgerState) and isinstance(
        intent_reference, DeribitPaperLedgerIntentReference
    ):
        if (
            ledger_state.symbol != intent_reference.symbol
            or ledger_state.canonical_symbol != intent_reference.canonical_symbol
            or fill_result.symbol != ledger_state.symbol
            or fill_result.canonical_symbol != ledger_state.canonical_symbol
        ):
            reasons.append("deribit_paper_ledger:instrument_mismatch")
        if intent_reference.request_id in ledger_state.applied_request_ids:
            reasons.append("deribit_paper_ledger:duplicate_request_id")
        if intent_reference.idempotency_key in ledger_state.applied_idempotency_keys:
            reasons.append("deribit_paper_ledger:duplicate_idempotency_key")
        if fill_result.fill_id in ledger_state.applied_fill_ids:
            reasons.append("deribit_paper_ledger:duplicate_fill_id")
        if not fill_result.fill_id.startswith(f"{DERIBIT_PAPER_FILL_MODEL_ID}:{intent_reference.request_id}:seq:"):
            reasons.append("deribit_paper_ledger:fill_request_mismatch")
        if fill_result.simulated_qty is not None and fill_result.simulated_qty > intent_reference.quantity:
            reasons.append("deribit_paper_ledger:fill_qty_exceeds_intent")
        if fill_result.simulated_price is not None:
            if (
                intent_reference.side is DeribitPaperOrderIntentSide.BUY
                and fill_result.simulated_price > intent_reference.limit_price
            ):
                reasons.append("deribit_paper_ledger:buy_limit_breached")
            if (
                intent_reference.side is DeribitPaperOrderIntentSide.SELL
                and fill_result.simulated_price < intent_reference.limit_price
            ):
                reasons.append("deribit_paper_ledger:sell_limit_breached")
    return tuple(dict.fromkeys(reasons))


def _apply_position(
    position_qty: float,
    average_entry_price: float | None,
    side: DeribitPaperOrderIntentSide,
    fill_qty: float,
    fill_price: float,
) -> tuple[float, float | None, float]:
    if position_qty == 0.0 or average_entry_price is None:
        return (fill_qty if side is DeribitPaperOrderIntentSide.BUY else -fill_qty, fill_price, 0.0)
    if position_qty > 0.0 and side is DeribitPaperOrderIntentSide.BUY:
        total_qty = position_qty + fill_qty
        avg = ((position_qty * average_entry_price) + (fill_qty * fill_price)) / total_qty
        return total_qty, avg, 0.0
    if position_qty < 0.0 and side is DeribitPaperOrderIntentSide.SELL:
        total_qty = abs(position_qty) + fill_qty
        avg = ((abs(position_qty) * average_entry_price) + (fill_qty * fill_price)) / total_qty
        return -total_qty, avg, 0.0
    if position_qty > 0.0:
        close_qty = min(position_qty, fill_qty)
        realized = (fill_price - average_entry_price) * close_qty
        remainder = position_qty - fill_qty
        return (
            (remainder, average_entry_price, realized)
            if remainder > 0.0
            else ((0.0, None, realized) if remainder == 0.0 else (remainder, fill_price, realized))
        )
    close_qty = min(abs(position_qty), fill_qty)
    realized = (average_entry_price - fill_price) * close_qty
    remainder = abs(position_qty) - fill_qty
    return (
        (-remainder, average_entry_price, realized)
        if remainder > 0.0
        else ((0.0, None, realized) if remainder == 0.0 else (-remainder, fill_price, realized))
    )


def _contains_scope_marker(value: object) -> bool:
    return isinstance(value, str) and any(marker in value.lower() for marker in _SCOPE_MARKERS)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_float(value: object) -> bool:
    return (
        isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value)) and value > 0.0
    )


def _finite_non_negative(value: object) -> bool:
    return (
        isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value)) and value >= 0.0
    )
