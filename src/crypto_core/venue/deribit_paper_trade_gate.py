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
            ledger_mutated=False,
            reason_code="deribit_paper_trade_gate:intent_reference_unavailable",
            rejection_reasons=("deribit_paper_trade_gate:intent_reference_unavailable",),
            operator_trigger=operator_trigger,
            run_id=operator_trigger.run_id,
            request_id=fill_request.request_id,
            fill_id=fill_result.fill_id,
            ledger_state=ledger_state,
            before_summary=before_summary,
            after_summary=before_summary,
        )

    ledger_result = apply_deribit_paper_fill_to_ledger(
        ledger_state,
        intent_reference,
        fill_result,
        kill_switch_active=kill_switch_active,
    )
    after_summary = _ledger_summary(ledger_result.ledger_state) or before_summary
    if ledger_result.accepted is not True or ledger_result.ledger_state is None:
        rejection_reasons = tuple(
            dict.fromkeys(
                (
                    "deribit_paper_trade_gate:ledger_application_rejected",
                    *ledger_result.rejection_reasons,
                )
            )
        )
        reason_code = ledger_result.rejection_reasons[0] if ledger_result.rejection_reasons else rejection_reasons[0]
        return _result(
            accepted=False,
            filled=True,
            ledger_mutated=False,
            reason_code=reason_code,
            rejection_reasons=rejection_reasons,
            operator_trigger=operator_trigger,
            run_id=operator_trigger.run_id,
            request_id=fill_request.request_id,
            fill_id=fill_result.fill_id,
            ledger_state=ledger_result.ledger_state,
            before_summary=before_summary,
            after_summary=after_summary,
        )

    return _result(
        accepted=True,
        filled=True,
        ledger_mutated=True,
        reason_code="deribit_paper_trade_gate:accepted_fill_applied",
        rejection_reasons=(),
        operator_trigger=operator_trigger,
        run_id=operator_trigger.run_id,
        request_id=fill_request.request_id,
        fill_id=fill_result.fill_id,
        ledger_state=ledger_result.ledger_state,
        before_summary=before_summary,
        after_summary=after_summary,
    )


def deribit_paper_trade_gate_result_to_dict(result: DeribitPaperTradeGateResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "filled": result.filled,
        "ledger_mutated": result.ledger_mutated,
        "reason_code": result.reason_code,
        "rejection_reasons": list(result.rejection_reasons),
        "run_id": result.run_id,
        "request_id": result.request_id,
        "fill_id": result.fill_id,
        "ledger_state_present": result.ledger_state is not None,
        "before_ledger_summary": _ledger_summary_to_dict(result.before_ledger_summary),
        "after_ledger_summary": _ledger_summary_to_dict(result.after_ledger_summary),
        "audit_record": deribit_paper_trade_gate_audit_record_to_dict(result.audit_record),
    }


def deribit_paper_trade_gate_audit_record_to_dict(
    record: DeribitPaperTradeGateAuditRecord,
) -> dict[str, object]:
    return {
        "audit_id": record.audit_id,
        "operator_id": record.operator_id,
        "run_id": record.run_id,
        "idempotency_key": record.idempotency_key,
        "request_id": record.request_id,
        "fill_id": record.fill_id,
        "accepted": record.accepted,
        "filled": record.filled,
        "ledger_mutated": record.ledger_mutated,
        "reason_code": record.reason_code,
        "rejection_reasons": list(record.rejection_reasons),
        "before_ledger_summary": _ledger_summary_to_dict(record.before_ledger_summary),
        "after_ledger_summary": _ledger_summary_to_dict(record.after_ledger_summary),
        "policy_refs": list(record.policy_refs),
    }


def _rejection_reasons(
    operator_trigger: object,
    intent: object,
    decision: object,
    fill_request: object,
    frame: object,
    ledger_state: object,
    *,
    kill_switch_active: bool,
    now_ns: int | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(_operator_trigger_rejection_reasons(operator_trigger))
    reasons.extend(_intent_rejection_reasons(intent))
    reasons.extend(_decision_rejection_reasons(decision))
    reasons.extend(_fill_request_rejection_reasons(fill_request))
    reasons.extend(_frame_rejection_reasons(frame, now_ns=now_ns))
    reasons.extend(_ledger_state_rejection_reasons(ledger_state))

    if not isinstance(kill_switch_active, bool):
        reasons.append("deribit_paper_trade_gate:kill_switch_flag_invalid")
    elif kill_switch_active is True:
        reasons.append("deribit_paper_trade_gate:kill_switch_active")

    if not isinstance(intent, DeribitPaperOrderIntent) or not isinstance(decision, DeribitPaperOrderIntentDecision):
        return tuple(dict.fromkeys(reasons))
    if not isinstance(fill_request, DeribitPaperFillRequest) or not isinstance(
        operator_trigger, DeribitPaperTradeOperatorTrigger
    ):
        return tuple(dict.fromkeys(reasons))
    if not isinstance(ledger_state, DeribitPaperLedgerState) or not isinstance(frame, DeribitPaperFeedFrame):
        return tuple(dict.fromkeys(reasons))

    if decision.fill_request is None or decision.fill_request != fill_request:
        reasons.append("deribit_paper_trade_gate:fill_request_mismatch")
    if operator_trigger.run_id != fill_request.request_id:
        reasons.append("deribit_paper_trade_gate:run_id_request_id_mismatch")
    if operator_trigger.idempotency_key != intent.idempotency_key:
        reasons.append("deribit_paper_trade_gate:trigger_idempotency_mismatch")
    if fill_request.request_id != intent.intent_id:
        reasons.append("deribit_paper_trade_gate:intent_request_mismatch")
    if fill_request.quantity != intent.quantity:
        reasons.append("deribit_paper_trade_gate:request_quantity_mismatch")
    if fill_request.limit_price != intent.limit_price:
        reasons.append("deribit_paper_trade_gate:request_limit_price_mismatch")
    if frame.venue_id is not intent.venue_id:
        reasons.append("deribit_paper_trade_gate:frame_intent_venue_mismatch")
    if frame.symbol != intent.symbol or frame.canonical_symbol != intent.canonical_symbol:
        reasons.append("deribit_paper_trade_gate:frame_intent_instrument_mismatch")
    if ledger_state.symbol != intent.symbol or ledger_state.canonical_symbol != intent.canonical_symbol:
        reasons.append("deribit_paper_trade_gate:ledger_intent_instrument_mismatch")
    if operator_trigger.run_id in ledger_state.applied_request_ids:
        reasons.append("deribit_paper_trade_gate:duplicate_run_id")
    if operator_trigger.idempotency_key in ledger_state.applied_idempotency_keys:
        reasons.append("deribit_paper_trade_gate:duplicate_gate_idempotency_key")

    return tuple(dict.fromkeys(reasons))


def _operator_trigger_rejection_reasons(operator_trigger: object) -> tuple[str, ...]:
    if not isinstance(operator_trigger, DeribitPaperTradeOperatorTrigger):
        return ("deribit_paper_trade_gate:operator_trigger_malformed",)

    reasons: list[str] = []
    if not _non_empty(operator_trigger.operator_id):
        reasons.append("deribit_paper_trade_gate:operator_id_missing")
    if not _non_empty(operator_trigger.run_id):
        reasons.append("deribit_paper_trade_gate:run_id_missing")
    if not _non_empty(operator_trigger.idempotency_key):
        reasons.append("deribit_paper_trade_gate:idempotency_key_missing")
    if operator_trigger.simulation_only is not True:
        reasons.append("deribit_paper_trade_gate:not_simulation_only")
    if operator_trigger.live_enabled is not False:
        reasons.append("deribit_paper_trade_gate:live_enabled")
    if operator_trigger.shadow_enabled is not False:
        reasons.append("deribit_paper_trade_gate:shadow_enabled")
    if operator_trigger.auto_loop_enabled is not False:
        reasons.append("deribit_paper_trade_gate:auto_loop_enabled")
    if _contains_scope_marker(operator_trigger.operator_id) or _contains_scope_marker(operator_trigger.run_id):
        reasons.append("deribit_paper_trade_gate:operator_trigger_scope_invalid")
    if _contains_scope_marker(operator_trigger.idempotency_key):
        reasons.append("deribit_paper_trade_gate:operator_trigger_scope_invalid")
    return tuple(dict.fromkeys(reasons))


def _intent_rejection_reasons(intent: object) -> tuple[str, ...]:
    if not isinstance(intent, DeribitPaperOrderIntent):
        return ("deribit_paper_trade_gate:intent_malformed",)

    reasons: list[str] = []
    if intent.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_paper_trade_gate:intent_venue_mismatch")
    if intent.simulation_only is not True:
        reasons.append("deribit_paper_trade_gate:intent_not_simulation_only")
    if intent.live_trading_requested is not False:
        reasons.append("deribit_paper_trade_gate:intent_live_requested")
    if intent.shadow_trading_requested is not False:
        reasons.append("deribit_paper_trade_gate:intent_shadow_requested")
    return tuple(dict.fromkeys(reasons))


def _decision_rejection_reasons(decision: object) -> tuple[str, ...]:
    if not isinstance(decision, DeribitPaperOrderIntentDecision):
        return ("deribit_paper_trade_gate:decision_malformed",)

    reasons: list[str] = []
    if decision.accepted is not True:
        reasons.append("deribit_paper_trade_gate:intent_decision_rejected")
    if decision.fill_request is None:
        reasons.append("deribit_paper_trade_gate:fill_request_missing")
    if decision.kill_switch_active is not False:
        reasons.append("deribit_paper_trade_gate:intent_kill_switch_not_clear")
    if decision.exchange_order_ready is not False or decision.venue_submission_ready is not False:
        reasons.append("deribit_paper_trade_gate:decision_scope_invalid")
    if decision.trade_ready is not False or decision.paper_execution_loop_ready is not False:
        reasons.append("deribit_paper_trade_gate:decision_scope_invalid")
    if decision.ledger_mutation_ready is not False or decision.position_mutation_ready is not False:
        reasons.append("deribit_paper_trade_gate:decision_scope_invalid")
    if decision.strategy_signal_ready is not False:
        reasons.append("deribit_paper_trade_gate:decision_scope_invalid")
    if decision.live_trading_ready is not False or decision.shadow_trading_ready is not False:
        reasons.append("deribit_paper_trade_gate:decision_scope_invalid")
    return tuple(dict.fromkeys(reasons))


def _fill_request_rejection_reasons(fill_request: object) -> tuple[str, ...]:
    if not isinstance(fill_request, DeribitPaperFillRequest):
        return ("deribit_paper_trade_gate:fill_request_malformed",)

    reasons: list[str] = []
    if not _non_empty(fill_request.request_id):
        reasons.append("deribit_paper_trade_gate:fill_request_id_missing")
    if fill_request.simulation_only is not True:
        reasons.append("deribit_paper_trade_gate:fill_request_not_simulation_only")
    return tuple(dict.fromkeys(reasons))


def _frame_rejection_reasons(frame: object, *, now_ns: int | None) -> tuple[str, ...]:
    if not isinstance(frame, DeribitPaperFeedFrame):
        return ("deribit_paper_trade_gate:frame_malformed",)

    reasons: list[str] = []
    if frame.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_paper_trade_gate:frame_venue_mismatch")
    if frame.feed_type is not PublicFeedType.L2_ORDERBOOK:
        reasons.append("deribit_paper_trade_gate:frame_feed_type_mismatch")
    if frame.read_only_market_data is not True or frame.accepted_for_paper_input is not True:
        reasons.append("deribit_paper_trade_gate:frame_not_accepted")
    if frame.paper_execution_ready is not False or frame.trade_ready is not False:
        reasons.append("deribit_paper_trade_gate:frame_scope_invalid")
    if not _non_empty(frame.symbol) or not _non_empty(frame.canonical_symbol):
        reasons.append("deribit_paper_trade_gate:frame_instrument_missing")
    if _contains_scope_marker(frame.frame_id) or _contains_scope_marker(frame.source):
        reasons.append("deribit_paper_trade_gate:frame_scope_invalid")
    if now_ns is not None and not _positive_int(now_ns):
        reasons.append("deribit_paper_trade_gate:now_ns_invalid")
    return tuple(dict.fromkeys(reasons))


def _ledger_state_rejection_reasons(ledger_state: object) -> tuple[str, ...]:
    if not isinstance(ledger_state, DeribitPaperLedgerState):
        return ("deribit_paper_trade_gate:ledger_state_missing",)

    reasons: list[str] = []
    if ledger_state.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_paper_trade_gate:ledger_state_invalid")
    if not _non_empty(ledger_state.symbol) or not _non_empty(ledger_state.canonical_symbol):
        reasons.append("deribit_paper_trade_gate:ledger_state_invalid")
    return tuple(dict.fromkeys(reasons))


def _result(
    *,
    accepted: bool,
    filled: bool,
    ledger_mutated: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    operator_trigger: object,
    run_id: str | None,
    request_id: str | None,
    fill_id: str | None,
    ledger_state: DeribitPaperLedgerState | None,
    before_summary: DeribitPaperTradeLedgerSummary | None,
    after_summary: DeribitPaperTradeLedgerSummary | None,
) -> DeribitPaperTradeGateResult:
    operator_id = (
        operator_trigger.operator_id if isinstance(operator_trigger, DeribitPaperTradeOperatorTrigger) else None
    )
    idempotency_key = (
        operator_trigger.idempotency_key if isinstance(operator_trigger, DeribitPaperTradeOperatorTrigger) else None
    )
    audit_record = DeribitPaperTradeGateAuditRecord(
        audit_id=f"{DERIBIT_PAPER_TRADE_GATE_ID}:{run_id or 'missing-run'}:{reason_code}",
        operator_id=operator_id,
        run_id=run_id,
        idempotency_key=idempotency_key,
        request_id=request_id,
        fill_id=fill_id,
        accepted=accepted,
        filled=filled,
        ledger_mutated=ledger_mutated,
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        before_ledger_summary=before_summary,
        after_ledger_summary=after_summary,
    )
    return DeribitPaperTradeGateResult(
        accepted=accepted,
        filled=filled,
        ledger_mutated=ledger_mutated,
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        run_id=run_id,
        request_id=request_id,
        fill_id=fill_id,
        ledger_state=ledger_state,
        before_ledger_summary=before_summary,
        after_ledger_summary=after_summary,
        audit_record=audit_record,
    )


def _ledger_summary(ledger_state: object) -> DeribitPaperTradeLedgerSummary | None:
    if not isinstance(ledger_state, DeribitPaperLedgerState):
        return None
    return DeribitPaperTradeLedgerSummary(
        ledger_id=ledger_state.ledger_id,
        symbol=ledger_state.symbol,
        canonical_symbol=ledger_state.canonical_symbol,
        cash_balance=ledger_state.cash_balance,
        position_qty=ledger_state.position_qty,
        average_entry_price=ledger_state.average_entry_price,
        realized_pnl=ledger_state.realized_pnl,
        applied_fill_count=len(ledger_state.applied_fill_ids),
        applied_request_count=len(ledger_state.applied_request_ids),
        applied_idempotency_count=len(ledger_state.applied_idempotency_keys),
        audit_entry_count=len(ledger_state.audit_entries),
    )


def _ledger_summary_to_dict(summary: DeribitPaperTradeLedgerSummary | None) -> dict[str, object] | None:
    if summary is None:
        return None
    return {
        "ledger_id": summary.ledger_id,
        "symbol": summary.symbol,
        "canonical_symbol": summary.canonical_symbol,
        "cash_balance": summary.cash_balance,
        "position_qty": summary.position_qty,
        "average_entry_price": summary.average_entry_price,
        "realized_pnl": summary.realized_pnl,
        "applied_fill_count": summary.applied_fill_count,
        "applied_request_count": summary.applied_request_count,
        "applied_idempotency_count": summary.applied_idempotency_count,
        "audit_entry_count": summary.audit_entry_count,
    }


def _contains_scope_marker(value: object) -> bool:
    return isinstance(value, str) and any(marker in value.lower() for marker in _SCOPE_MARKERS)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


__all__ = [
    "DERIBIT_PAPER_TRADE_GATE_ID",
    "DeribitPaperTradeGateAuditRecord",
    "DeribitPaperTradeGateResult",
    "DeribitPaperTradeLedgerSummary",
    "DeribitPaperTradeOperatorTrigger",
    "deribit_paper_trade_gate_audit_record_to_dict",
    "deribit_paper_trade_gate_result_to_dict",
    "run_deribit_paper_trade_gate",
]
