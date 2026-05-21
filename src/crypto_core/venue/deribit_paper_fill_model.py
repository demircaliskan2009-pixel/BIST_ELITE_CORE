from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.deribit_paper_feed import DeribitPaperFeedFrame
from crypto_core.venue.public_feed_dialects import get_public_feed_dialect

DERIBIT_PAPER_FILL_MODEL_ID = "deribit_paper_fill_model_v1"

_POLICY_REFS = (
    "DERIBIT_PAPER_FEED_PIPELINE_33A.md",
    "DERIBIT_NEXT_BLOCKER_SUMMARY_33F.md",
    "PAPER_SIMULATOR_FILL_MODEL_34A.md",
)
_SCOPE_MARKERS = frozenset(
    {
        "account",
        "auth",
        "balance",
        "credential",
        "order_id",
        "position",
        "private",
        "signature",
        "token",
        "withdraw",
    }
)


class DeribitPaperFillSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class DeribitPaperFillStyle(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


@dataclass(frozen=True)
class DeribitPaperFillRequest:
    request_id: str
    side: DeribitPaperFillSide
    style: DeribitPaperFillStyle
    quantity: float
    limit_price: float | None
    simulation_only: bool


@dataclass(frozen=True)
class DeribitPaperFillResult:
    accepted: bool
    filled: bool
    fill_id: str | None
    reason_code: str
    simulated_price: float | None
    simulated_qty: float | None
    venue_id: VenueId | None
    symbol: str | None
    canonical_symbol: str | None
    source_event_time_ns: int | None
    source_receive_time_ns: int | None
    source_sequence_id: int | None
    policy_refs: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    venue_submission_ready: bool
    trade_ready: bool
    position_mutation_ready: bool
    strategy_signal_ready: bool


def evaluate_deribit_paper_limit_fill(
    frame: object,
    request: object,
    *,
    now_ns: int | None = None,
) -> DeribitPaperFillResult:
    frame_reasons = list(_frame_rejection_reasons(frame, now_ns=now_ns))
    request_reasons = list(_request_rejection_reasons(request))
    reasons = tuple(dict.fromkeys((*frame_reasons, *request_reasons)))
    if reasons:
        return _result(frame, accepted=False, filled=False, reason_code=reasons[0], rejection_reasons=reasons)

    assert isinstance(frame, DeribitPaperFeedFrame)
    assert isinstance(request, DeribitPaperFillRequest)
    if request.style is DeribitPaperFillStyle.MARKET:
        return _result(
            frame,
            accepted=False,
            filled=False,
            reason_code="deribit_paper_fill:market_not_implemented",
            rejection_reasons=("deribit_paper_fill:market_not_implemented",),
        )

    assert request.limit_price is not None
    if request.side is DeribitPaperFillSide.BUY:
        if request.limit_price < frame.best_ask_price:
            return _result(
                frame, accepted=True, filled=False, reason_code="deribit_paper_fill:no_fill_limit_not_crossed"
            )
        if request.quantity > frame.best_ask_quantity:
            return _result(
                frame,
                accepted=False,
                filled=False,
                reason_code="deribit_paper_fill:insufficient_top_liquidity",
                rejection_reasons=("deribit_paper_fill:insufficient_top_liquidity",),
            )
        simulated_price = frame.best_ask_price
    else:
        if request.limit_price > frame.best_bid_price:
            return _result(
                frame, accepted=True, filled=False, reason_code="deribit_paper_fill:no_fill_limit_not_crossed"
            )
        if request.quantity > frame.best_bid_quantity:
            return _result(
                frame,
                accepted=False,
                filled=False,
                reason_code="deribit_paper_fill:insufficient_top_liquidity",
                rejection_reasons=("deribit_paper_fill:insufficient_top_liquidity",),
            )
        simulated_price = frame.best_bid_price

    return _result(
        frame,
        accepted=True,
        filled=True,
        reason_code="deribit_paper_fill:filled_limit_crossed",
        simulated_price=simulated_price,
        simulated_qty=request.quantity,
        fill_id=f"{DERIBIT_PAPER_FILL_MODEL_ID}:{request.request_id}:seq:{frame.sequence_id}",
    )


def deribit_paper_fill_result_to_dict(result: DeribitPaperFillResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "filled": result.filled,
        "fill_id": result.fill_id,
        "reason_code": result.reason_code,
        "simulated_price": result.simulated_price,
        "simulated_qty": result.simulated_qty,
        "venue_id": None if result.venue_id is None else result.venue_id.value,
        "symbol": result.symbol,
        "canonical_symbol": result.canonical_symbol,
        "source_event_time_ns": result.source_event_time_ns,
        "source_receive_time_ns": result.source_receive_time_ns,
        "source_sequence_id": result.source_sequence_id,
        "policy_refs": list(result.policy_refs),
        "rejection_reasons": list(result.rejection_reasons),
        "venue_submission_ready": result.venue_submission_ready,
        "trade_ready": result.trade_ready,
        "position_mutation_ready": result.position_mutation_ready,
        "strategy_signal_ready": result.strategy_signal_ready,
    }


def _frame_rejection_reasons(frame: object, *, now_ns: int | None) -> tuple[str, ...]:
    if not isinstance(frame, DeribitPaperFeedFrame):
        return ("deribit_paper_fill:frame_malformed",)

    reasons: list[str] = []
    if frame.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_paper_fill:venue_mismatch")
    if frame.feed_type is not PublicFeedType.L2_ORDERBOOK:
        reasons.append("deribit_paper_fill:feed_type_mismatch")
    if frame.read_only_market_data is not True or frame.accepted_for_paper_input is not True:
        reasons.append("deribit_paper_fill:frame_not_accepted")
    if frame.paper_execution_ready is not False or frame.trade_ready is not False:
        reasons.append("deribit_paper_fill:frame_scope_invalid")
    if not _non_empty(frame.symbol) or not _non_empty(frame.canonical_symbol):
        reasons.append("deribit_paper_fill:instrument_missing")
    if not _positive_int(frame.event_time_ns) or not _positive_int(frame.receive_time_ns):
        reasons.append("deribit_paper_fill:timestamp_invalid")
    elif frame.receive_time_ns < frame.event_time_ns:
        reasons.append("deribit_paper_fill:received_before_event")
    if not _non_negative_int(frame.sequence_id):
        reasons.append("deribit_paper_fill:sequence_invalid")
    if not _positive_int(frame.book_depth):
        reasons.append("deribit_paper_fill:depth_invalid")
    if _contains_scope_marker(frame.frame_id) or _contains_scope_marker(frame.source):
        reasons.append("deribit_paper_fill:scope_contamination")
    reasons.extend(_book_rejection_reasons(frame))
    reasons.extend(_timing_rejection_reasons(frame, now_ns=now_ns))
    return tuple(dict.fromkeys(reasons))


def _book_rejection_reasons(frame: DeribitPaperFeedFrame) -> tuple[str, ...]:
    reasons: list[str] = []
    if not _positive_float(frame.best_bid_price) or not _positive_float(frame.best_ask_price):
        reasons.append("deribit_paper_fill:best_price_invalid")
    if not _positive_float(frame.best_bid_quantity) or not _positive_float(frame.best_ask_quantity):
        reasons.append("deribit_paper_fill:best_quantity_invalid")
    if frame.best_bid_price >= frame.best_ask_price:
        reasons.append("deribit_paper_fill:book_crossed")
    if not isinstance(frame.bid_levels, tuple) or not frame.bid_levels:
        reasons.append("deribit_paper_fill:bid_levels_missing")
    if not isinstance(frame.ask_levels, tuple) or not frame.ask_levels:
        reasons.append("deribit_paper_fill:ask_levels_missing")
    for level in (*frame.bid_levels, *frame.ask_levels):
        if (
            not isinstance(level, tuple)
            or len(level) != 2
            or not _positive_float(level[0])
            or not _positive_float(level[1])
        ):
            reasons.append("deribit_paper_fill:book_level_invalid")
            break
    return tuple(dict.fromkeys(reasons))


def _timing_rejection_reasons(frame: DeribitPaperFeedFrame, *, now_ns: int | None) -> tuple[str, ...]:
    if now_ns is None:
        return ()
    if not _positive_int(now_ns):
        return ("deribit_paper_fill:now_ns_invalid",)
    try:
        spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")
    except ValueError:
        return ("deribit_paper_fill:dialect_not_ready",)
    reasons: list[str] = []
    if now_ns - frame.event_time_ns > spec.max_staleness_ns:
        reasons.append("deribit_paper_fill:stale_frame")
    if now_ns - frame.receive_time_ns > spec.max_receive_lag_ns:
        reasons.append("deribit_paper_fill:receive_lag_breach")
    return tuple(dict.fromkeys(reasons))


def _request_rejection_reasons(request: object) -> tuple[str, ...]:
    if not isinstance(request, DeribitPaperFillRequest):
        return ("deribit_paper_fill:request_malformed",)
    reasons: list[str] = []
    if not _non_empty(request.request_id):
        reasons.append("deribit_paper_fill:request_id_missing")
    if request.simulation_only is not True:
        reasons.append("deribit_paper_fill:not_simulation_only")
    if not isinstance(request.side, DeribitPaperFillSide):
        reasons.append("deribit_paper_fill:side_invalid")
    if not isinstance(request.style, DeribitPaperFillStyle):
        reasons.append("deribit_paper_fill:style_invalid")
    if not _positive_float(request.quantity):
        reasons.append("deribit_paper_fill:quantity_invalid")
    if request.style is DeribitPaperFillStyle.LIMIT and not _positive_float(request.limit_price):
        reasons.append("deribit_paper_fill:limit_price_invalid")
    return tuple(dict.fromkeys(reasons))


def _result(
    frame: object,
    *,
    accepted: bool,
    filled: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...] = (),
    simulated_price: float | None = None,
    simulated_qty: float | None = None,
    fill_id: str | None = None,
) -> DeribitPaperFillResult:
    frame_is_valid = isinstance(frame, DeribitPaperFeedFrame)
    return DeribitPaperFillResult(
        accepted=accepted,
        filled=filled,
        fill_id=fill_id,
        reason_code=reason_code,
        simulated_price=simulated_price,
        simulated_qty=simulated_qty,
        venue_id=frame.venue_id if frame_is_valid else None,
        symbol=frame.symbol if frame_is_valid else None,
        canonical_symbol=frame.canonical_symbol if frame_is_valid else None,
        source_event_time_ns=frame.event_time_ns if frame_is_valid else None,
        source_receive_time_ns=frame.receive_time_ns if frame_is_valid else None,
        source_sequence_id=frame.sequence_id if frame_is_valid else None,
        policy_refs=_POLICY_REFS,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        venue_submission_ready=False,
        trade_ready=False,
        position_mutation_ready=False,
        strategy_signal_ready=False,
    )


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
    "DERIBIT_PAPER_FILL_MODEL_ID",
    "DeribitPaperFillRequest",
    "DeribitPaperFillResult",
    "DeribitPaperFillSide",
    "DeribitPaperFillStyle",
    "deribit_paper_fill_result_to_dict",
    "evaluate_deribit_paper_limit_fill",
]
