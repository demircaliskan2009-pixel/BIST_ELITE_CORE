from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.deribit_paper_feed import DeribitPaperFeedFrame
from crypto_core.venue.deribit_paper_fill_model import (
    DeribitPaperFillRequest,
    DeribitPaperFillSide,
    DeribitPaperFillStyle,
)
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_DIALECT_ID
from crypto_core.venue.public_feed_dialects import get_public_feed_dialect

DERIBIT_PAPER_ORDER_INTENT_GATE_ID = "deribit_paper_order_intent_gate_v1"

ACCOUNTING_LEDGER_NOT_READY = "NOT_READY_FOR_LEDGER_MUTATION"
ACCOUNTING_PRECHECK_ONLY = "ACCOUNTING_STATE_PRESENT_PRECHECK_ONLY"

_POLICY_REFS = (
    "DERIBIT_PAPER_FEED_PIPELINE_33A.md",
    "PAPER_SIMULATOR_FILL_MODEL_34A.md",
    "PAPER_ORDER_INTENT_RISK_GATE_35A.md",
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
        "order_id",
        "position",
        "private",
        "route",
        "shadow",
        "signature",
        "token",
        "withdraw",
    }
)


class DeribitPaperOrderIntentSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class DeribitPaperOrderStyle(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    POST_ONLY = "POST_ONLY"
    IOC = "IOC"
    FOK = "FOK"


@dataclass(frozen=True)
class DeribitPaperOrderIntent:
    intent_id: str
    idempotency_key: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    side: DeribitPaperOrderIntentSide
    order_style: DeribitPaperOrderStyle
    quantity: float
    limit_price: float | None
    simulation_only: bool
    live_trading_requested: bool = False
    shadow_trading_requested: bool = False
    leverage: float | None = None
    margin_mode: str | None = None
    time_in_force: str | None = None


@dataclass(frozen=True)
class DeribitPaperPreFillRiskPolicy:
    policy_id: str = "deribit_phase35_prefill_risk_v1"
    max_order_qty: float = 1.0
    max_order_notional: float = 50_000.0
    require_accounting_state: bool = False


@dataclass(frozen=True)
class DeribitPaperOrderIntentDecision:
    accepted: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    fill_request: DeribitPaperFillRequest | None
    risk_checks: tuple[str, ...]
    intent_notional: float | None
    kill_switch_active: bool
    accounting_gate_status: str
    accounting_state_present: bool
    policy_refs: tuple[str, ...]
    exchange_order_ready: bool
    venue_submission_ready: bool
    trade_ready: bool
    paper_execution_loop_ready: bool
    ledger_mutation_ready: bool
    position_mutation_ready: bool
    strategy_signal_ready: bool
    live_trading_ready: bool
    shadow_trading_ready: bool


def validate_deribit_paper_order_intent(
    frame: object,
    intent: object,
    *,
    policy: DeribitPaperPreFillRiskPolicy | None = None,
    kill_switch_active: bool = False,
    accounting_state_present: bool = False,
    now_ns: int | None = None,
) -> DeribitPaperOrderIntentDecision:
    resolved_policy: object = policy if policy is not None else DeribitPaperPreFillRiskPolicy()
    frame_reasons = list(_frame_rejection_reasons(frame, now_ns=now_ns))
    intent_reasons = list(_intent_rejection_reasons(intent, frame))
    policy_reasons = list(_policy_rejection_reasons(resolved_policy))
    gate_reasons = list(
        _prefill_gate_rejection_reasons(
            intent,
            resolved_policy,
            kill_switch_active=kill_switch_active,
            accounting_state_present=accounting_state_present,
        )
    )
    reasons = tuple(dict.fromkeys((*frame_reasons, *intent_reasons, *policy_reasons, *gate_reasons)))
    risk_checks = _risk_checks(
        intent,
        resolved_policy,
        kill_switch_active=kill_switch_active,
        accounting_state_present=accounting_state_present,
    )
    accounting_status = _accounting_gate_status(accounting_state_present)
    if reasons:
        return _decision(
            intent,
            accepted=False,
            reason_code=reasons[0],
            rejection_reasons=reasons,
            risk_checks=risk_checks,
            kill_switch_active=kill_switch_active,
            accounting_gate_status=accounting_status,
            accounting_state_present=accounting_state_present,
        )

    assert isinstance(intent, DeribitPaperOrderIntent)
    return _decision(
        intent,
        accepted=True,
        reason_code="deribit_paper_order_intent:accepted_for_fill_model_request",
        rejection_reasons=(),
        fill_request=_fill_request_from_intent(intent),
        risk_checks=risk_checks,
        kill_switch_active=kill_switch_active,
        accounting_gate_status=accounting_status,
        accounting_state_present=accounting_state_present,
    )


def deribit_paper_order_intent_decision_to_dict(
    decision: DeribitPaperOrderIntentDecision,
) -> dict[str, object]:
    fill_request = decision.fill_request
    return {
        "accepted": decision.accepted,
        "reason_code": decision.reason_code,
        "rejection_reasons": list(decision.rejection_reasons),
        "fill_request": None
        if fill_request is None
        else {
            "request_id": fill_request.request_id,
            "side": fill_request.side.value,
            "style": fill_request.style.value,
            "quantity": fill_request.quantity,
            "limit_price": fill_request.limit_price,
            "simulation_only": fill_request.simulation_only,
        },
        "risk_checks": list(decision.risk_checks),
        "intent_notional": decision.intent_notional,
        "kill_switch_active": decision.kill_switch_active,
        "accounting_gate_status": decision.accounting_gate_status,
        "accounting_state_present": decision.accounting_state_present,
        "policy_refs": list(decision.policy_refs),
        "exchange_order_ready": decision.exchange_order_ready,
        "venue_submission_ready": decision.venue_submission_ready,
        "trade_ready": decision.trade_ready,
        "paper_execution_loop_ready": decision.paper_execution_loop_ready,
        "ledger_mutation_ready": decision.ledger_mutation_ready,
        "position_mutation_ready": decision.position_mutation_ready,
        "strategy_signal_ready": decision.strategy_signal_ready,
        "live_trading_ready": decision.live_trading_ready,
        "shadow_trading_ready": decision.shadow_trading_ready,
    }


def _frame_rejection_reasons(frame: object, *, now_ns: int | None) -> tuple[str, ...]:
    if not isinstance(frame, DeribitPaperFeedFrame):
        return ("deribit_paper_order_intent:frame_malformed",)

    reasons: list[str] = []
    if frame.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_paper_order_intent:venue_mismatch")
    if frame.feed_type is not PublicFeedType.L2_ORDERBOOK:
        reasons.append("deribit_paper_order_intent:feed_type_mismatch")
    if frame.read_only_market_data is not True or frame.accepted_for_paper_input is not True:
        reasons.append("deribit_paper_order_intent:frame_not_accepted")
    if frame.paper_execution_ready is not False or frame.trade_ready is not False:
        reasons.append("deribit_paper_order_intent:frame_scope_invalid")
    if not _non_empty(frame.symbol) or not _non_empty(frame.canonical_symbol):
        reasons.append("deribit_paper_order_intent:instrument_missing")
    if not _positive_int(frame.event_time_ns) or not _positive_int(frame.receive_time_ns):
        reasons.append("deribit_paper_order_intent:timestamp_invalid")
    elif frame.receive_time_ns < frame.event_time_ns:
        reasons.append("deribit_paper_order_intent:received_before_event")
    if not _non_negative_int(frame.sequence_id):
        reasons.append("deribit_paper_order_intent:sequence_invalid")
    if _contains_scope_marker(frame.frame_id) or _contains_scope_marker(frame.source):
        reasons.append("deribit_paper_order_intent:scope_contamination")
    reasons.extend(_book_rejection_reasons(frame))
    reasons.extend(_timing_rejection_reasons(frame, now_ns=now_ns))
    return tuple(dict.fromkeys(reasons))


def _book_rejection_reasons(frame: DeribitPaperFeedFrame) -> tuple[str, ...]:
    reasons: list[str] = []
    if not _positive_float(frame.best_bid_price) or not _positive_float(frame.best_ask_price):
        reasons.append("deribit_paper_order_intent:best_price_invalid")
    if not _positive_float(frame.best_bid_quantity) or not _positive_float(frame.best_ask_quantity):
        reasons.append("deribit_paper_order_intent:best_quantity_invalid")
    if frame.best_bid_price >= frame.best_ask_price:
        reasons.append("deribit_paper_order_intent:book_crossed")
    if not isinstance(frame.bid_levels, tuple) or not frame.bid_levels:
        reasons.append("deribit_paper_order_intent:bid_levels_missing")
    if not isinstance(frame.ask_levels, tuple) or not frame.ask_levels:
        reasons.append("deribit_paper_order_intent:ask_levels_missing")
    return tuple(dict.fromkeys(reasons))


def _timing_rejection_reasons(frame: DeribitPaperFeedFrame, *, now_ns: int | None) -> tuple[str, ...]:
    if now_ns is None:
        return ()
    if not _positive_int(now_ns):
        return ("deribit_paper_order_intent:now_ns_invalid",)
    try:
        spec = get_public_feed_dialect(DERIBIT_PUBLIC_BOOK_DIALECT_ID)
    except ValueError:
        return ("deribit_paper_order_intent:dialect_not_ready",)
    reasons: list[str] = []
    if now_ns - frame.event_time_ns > spec.max_staleness_ns:
        reasons.append("deribit_paper_order_intent:stale_frame")
    if now_ns - frame.receive_time_ns > spec.max_receive_lag_ns:
        reasons.append("deribit_paper_order_intent:receive_lag_breach")
    return tuple(dict.fromkeys(reasons))


def _intent_rejection_reasons(intent: object, frame: object) -> tuple[str, ...]:
    if not isinstance(intent, DeribitPaperOrderIntent):
        return ("deribit_paper_order_intent:intent_malformed",)

    reasons: list[str] = []
    if not _non_empty(intent.intent_id):
        reasons.append("deribit_paper_order_intent:intent_id_missing")
    if not _non_empty(intent.idempotency_key):
        reasons.append("deribit_paper_order_intent:idempotency_key_missing")
    if _contains_scope_marker(intent.intent_id) or _contains_scope_marker(intent.idempotency_key):
        reasons.append("deribit_paper_order_intent:scope_contamination")
    if intent.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_paper_order_intent:venue_mismatch")
    if isinstance(frame, DeribitPaperFeedFrame):
        if intent.symbol != frame.symbol or intent.canonical_symbol != frame.canonical_symbol:
            reasons.append("deribit_paper_order_intent:instrument_mismatch")
    if not isinstance(intent.side, DeribitPaperOrderIntentSide):
        reasons.append("deribit_paper_order_intent:side_invalid")
    if not isinstance(intent.order_style, DeribitPaperOrderStyle):
        reasons.append("deribit_paper_order_intent:style_invalid")
    elif intent.order_style is not DeribitPaperOrderStyle.LIMIT:
        reasons.append("deribit_paper_order_intent:non_limit_style_not_supported")
    if intent.simulation_only is not True:
        reasons.append("deribit_paper_order_intent:not_simulation_only")
    if intent.live_trading_requested is not False or intent.shadow_trading_requested is not False:
        reasons.append("deribit_paper_order_intent:live_or_shadow_requested")
    if not _positive_float(intent.quantity):
        reasons.append("deribit_paper_order_intent:quantity_invalid")
    if intent.order_style is DeribitPaperOrderStyle.LIMIT and not _positive_float(intent.limit_price):
        reasons.append("deribit_paper_order_intent:limit_price_invalid")
    if intent.leverage is not None:
        reasons.append("deribit_paper_order_intent:leverage_not_supported")
    if intent.margin_mode is not None:
        reasons.append("deribit_paper_order_intent:margin_not_supported")
    if intent.time_in_force is not None:
        reasons.append("deribit_paper_order_intent:time_in_force_not_supported")
    return tuple(dict.fromkeys(reasons))


def _policy_rejection_reasons(policy: object) -> tuple[str, ...]:
    if not isinstance(policy, DeribitPaperPreFillRiskPolicy):
        return ("deribit_paper_order_intent:policy_malformed",)
    reasons: list[str] = []
    if not _non_empty(policy.policy_id):
        reasons.append("deribit_paper_order_intent:policy_id_missing")
    if not _positive_float(policy.max_order_qty):
        reasons.append("deribit_paper_order_intent:max_order_qty_invalid")
    if not _positive_float(policy.max_order_notional):
        reasons.append("deribit_paper_order_intent:max_order_notional_invalid")
    if not isinstance(policy.require_accounting_state, bool):
        reasons.append("deribit_paper_order_intent:accounting_policy_invalid")
    return tuple(dict.fromkeys(reasons))


def _prefill_gate_rejection_reasons(
    intent: object,
    policy: object,
    *,
    kill_switch_active: bool,
    accounting_state_present: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not isinstance(kill_switch_active, bool):
        reasons.append("deribit_paper_order_intent:kill_switch_flag_invalid")
    elif kill_switch_active:
        reasons.append("deribit_paper_order_intent:kill_switch_active")
    if not isinstance(accounting_state_present, bool):
        reasons.append("deribit_paper_order_intent:accounting_state_flag_invalid")
    if not isinstance(intent, DeribitPaperOrderIntent) or not isinstance(policy, DeribitPaperPreFillRiskPolicy):
        return tuple(dict.fromkeys(reasons))

    if _positive_float(intent.quantity) and intent.quantity > policy.max_order_qty:
        reasons.append("deribit_paper_order_intent:max_order_qty_breached")
    notional = _intent_notional(intent)
    if notional is not None and notional > policy.max_order_notional:
        reasons.append("deribit_paper_order_intent:max_order_notional_breached")
    if policy.require_accounting_state and accounting_state_present is not True:
        reasons.append("deribit_paper_order_intent:accounting_state_required")
    return tuple(dict.fromkeys(reasons))


def _risk_checks(
    intent: object,
    policy: object,
    *,
    kill_switch_active: bool,
    accounting_state_present: bool,
) -> tuple[str, ...]:
    checks: list[str] = []
    checks.append("kill_switch_clear" if kill_switch_active is False else "kill_switch_blocking")
    if not isinstance(policy, DeribitPaperPreFillRiskPolicy):
        checks.append("policy_malformed")
        checks.append("ledger_mutation_disabled")
        checks.append("slippage_fee_policy_not_implemented")
        return tuple(dict.fromkeys(checks))
    if isinstance(intent, DeribitPaperOrderIntent):
        if _positive_float(intent.quantity) and intent.quantity <= policy.max_order_qty:
            checks.append("max_order_qty_passed")
        notional = _intent_notional(intent)
        if notional is not None and notional <= policy.max_order_notional:
            checks.append("max_order_notional_passed")
    checks.append("accounting_state_present" if accounting_state_present is True else "accounting_not_ready_for_ledger")
    checks.append("ledger_mutation_disabled")
    checks.append("slippage_fee_policy_not_implemented")
    return tuple(dict.fromkeys(checks))


def _fill_request_from_intent(intent: DeribitPaperOrderIntent) -> DeribitPaperFillRequest:
    return DeribitPaperFillRequest(
        request_id=intent.intent_id,
        side=DeribitPaperFillSide.BUY if intent.side is DeribitPaperOrderIntentSide.BUY else DeribitPaperFillSide.SELL,
        style=DeribitPaperFillStyle.LIMIT,
        quantity=intent.quantity,
        limit_price=intent.limit_price,
        simulation_only=True,
    )


def _decision(
    intent: object,
    *,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    risk_checks: tuple[str, ...],
    kill_switch_active: bool,
    accounting_gate_status: str,
    accounting_state_present: bool,
    fill_request: DeribitPaperFillRequest | None = None,
) -> DeribitPaperOrderIntentDecision:
    return DeribitPaperOrderIntentDecision(
        accepted=accepted,
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        fill_request=fill_request,
        risk_checks=risk_checks,
        intent_notional=_intent_notional(intent),
        kill_switch_active=kill_switch_active,
        accounting_gate_status=accounting_gate_status,
        accounting_state_present=accounting_state_present,
        policy_refs=_POLICY_REFS,
        exchange_order_ready=False,
        venue_submission_ready=False,
        trade_ready=False,
        paper_execution_loop_ready=False,
        ledger_mutation_ready=False,
        position_mutation_ready=False,
        strategy_signal_ready=False,
        live_trading_ready=False,
        shadow_trading_ready=False,
    )


def _intent_notional(intent: object) -> float | None:
    if not isinstance(intent, DeribitPaperOrderIntent):
        return None
    if not _positive_float(intent.quantity) or not _positive_float(intent.limit_price):
        return None
    return float(intent.quantity) * float(intent.limit_price)


def _accounting_gate_status(accounting_state_present: bool) -> str:
    return ACCOUNTING_PRECHECK_ONLY if accounting_state_present is True else ACCOUNTING_LEDGER_NOT_READY


def _contains_scope_marker(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in _SCOPE_MARKERS)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_float(value: object) -> bool:
    return (
        isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value)) and value > 0.0
    )


__all__ = [
    "ACCOUNTING_LEDGER_NOT_READY",
    "ACCOUNTING_PRECHECK_ONLY",
    "DERIBIT_PAPER_ORDER_INTENT_GATE_ID",
    "DeribitPaperOrderIntent",
    "DeribitPaperOrderIntentDecision",
    "DeribitPaperOrderIntentSide",
    "DeribitPaperOrderStyle",
    "DeribitPaperPreFillRiskPolicy",
    "deribit_paper_order_intent_decision_to_dict",
    "validate_deribit_paper_order_intent",
]
