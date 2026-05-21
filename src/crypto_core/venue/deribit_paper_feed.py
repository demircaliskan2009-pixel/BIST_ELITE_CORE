from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.market_data_journal import PublicMarketDataReplayResult
from crypto_core.data.order_book import OrderBookState, order_book_state_rejection_reasons
from crypto_core.data.public_data_readiness import (
    PublicDataReadinessInput,
    PublicDataReadinessSnapshot,
    build_public_data_readiness_snapshot,
    public_data_ready_for_paper,
)
from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.venue.contracts import PublicFeedHealth, PublicFeedType, VenueId
from crypto_core.venue.deribit_order_book_replay import DeribitOrderBookReplayResult
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_DIALECT_ID
from crypto_core.venue.public_feed_dialects import get_public_feed_dialect

DERIBIT_PAPER_FEED_INPUT_ID = "deribit_paper_feed_input_v1"

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


@dataclass(frozen=True)
class DeribitPaperFeedFrame:
    frame_id: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    event_time_ns: int
    receive_time_ns: int
    sequence_id: int
    best_bid_price: float
    best_bid_quantity: float
    best_ask_price: float
    best_ask_quantity: float
    bid_depth: int
    ask_depth: int
    book_depth: int
    bid_levels: tuple[tuple[float, float], ...]
    ask_levels: tuple[tuple[float, float], ...]
    source: str
    read_only_market_data: bool
    accepted_for_paper_input: bool
    paper_execution_ready: bool
    trade_ready: bool


@dataclass(frozen=True)
class DeribitPaperFeedResult:
    accepted: bool
    frame: DeribitPaperFeedFrame | None
    readiness_snapshot: PublicDataReadinessSnapshot | None
    rejection_reasons: tuple[str, ...]


def build_deribit_paper_feed_input(
    replay_result: object,
    *,
    now_ns: int | None = None,
) -> DeribitPaperFeedResult:
    if not isinstance(replay_result, DeribitOrderBookReplayResult):
        return _result(
            frame=None,
            readiness_snapshot=None,
            reasons=("deribit_paper_feed:replay_result_malformed",),
        )

    reasons = list(_replay_rejection_reasons(replay_result))
    if now_ns is not None and not _positive_int(now_ns):
        reasons.append("deribit_paper_feed:now_ns_invalid")

    state = replay_result.state
    if not isinstance(state, OrderBookState):
        reasons.append("deribit_paper_feed:book_state_missing")
    else:
        reasons.extend(_state_rejection_reasons(state))

    health = replay_result.last_public_feed_health
    if not isinstance(health, PublicFeedHealth):
        reasons.append("deribit_paper_feed:public_feed_health_missing")

    journal_replay = replay_result.last_journal_replay_result
    if not isinstance(journal_replay, PublicMarketDataReplayResult):
        reasons.append("deribit_paper_feed:journal_replay_missing")

    policy = _policy_for_state(state)
    if policy is None:
        reasons.append("deribit_paper_feed:policy_unresolved")

    readiness_snapshot: PublicDataReadinessSnapshot | None = None
    if (
        isinstance(state, OrderBookState)
        and isinstance(health, PublicFeedHealth)
        and isinstance(journal_replay, PublicMarketDataReplayResult)
        and isinstance(policy, PublicFeedPolicy)
    ):
        readiness_snapshot = build_public_data_readiness_snapshot(
            PublicDataReadinessInput(
                policy=policy,
                health=health,
                replay_cursor=None,
                replay_result=journal_replay,
                order_book_state=state,
                order_book_result=replay_result.order_book_result,
                now_ns=now_ns if _positive_int(now_ns) else health.last_receive_time_ns,
            )
        )
        if not public_data_ready_for_paper(readiness_snapshot):
            reasons.append("deribit_paper_feed:public_data_not_ready")
            reasons.extend(readiness_snapshot.rejection_reasons)

    normalized_reasons = tuple(dict.fromkeys(reasons))
    if (
        normalized_reasons
        or not isinstance(state, OrderBookState)
        or not isinstance(readiness_snapshot, PublicDataReadinessSnapshot)
    ):
        return _result(frame=None, readiness_snapshot=readiness_snapshot, reasons=normalized_reasons)

    return _result(
        frame=_frame_from_state(state, readiness_snapshot),
        readiness_snapshot=readiness_snapshot,
        reasons=(),
    )


def deribit_paper_feed_frame_to_dict(frame: DeribitPaperFeedFrame) -> dict[str, object]:
    return {
        "frame_id": frame.frame_id,
        "venue_id": frame.venue_id.value,
        "symbol": frame.symbol,
        "canonical_symbol": frame.canonical_symbol,
        "feed_type": frame.feed_type.value,
        "event_time_ns": frame.event_time_ns,
        "receive_time_ns": frame.receive_time_ns,
        "sequence_id": frame.sequence_id,
        "best_bid_price": frame.best_bid_price,
        "best_bid_quantity": frame.best_bid_quantity,
        "best_ask_price": frame.best_ask_price,
        "best_ask_quantity": frame.best_ask_quantity,
        "bid_depth": frame.bid_depth,
        "ask_depth": frame.ask_depth,
        "book_depth": frame.book_depth,
        "bid_levels": [list(level) for level in frame.bid_levels],
        "ask_levels": [list(level) for level in frame.ask_levels],
        "source": frame.source,
        "read_only_market_data": frame.read_only_market_data,
        "accepted_for_paper_input": frame.accepted_for_paper_input,
        "paper_execution_ready": frame.paper_execution_ready,
        "trade_ready": frame.trade_ready,
    }


def _replay_rejection_reasons(replay_result: DeribitOrderBookReplayResult) -> tuple[str, ...]:
    reasons: list[str] = []
    if replay_result.accepted is not True:
        reasons.append("deribit_paper_feed:replay_rejected")
    if replay_result.applied_event_count <= 0:
        reasons.append("deribit_paper_feed:no_replayed_events")
    if replay_result.order_book_result is None or replay_result.order_book_result.applied is not True:
        reasons.append("deribit_paper_feed:order_book_result_missing")
    elif replay_result.order_book_result.rejection_reasons:
        reasons.append("deribit_paper_feed:order_book_result_rejected")
        reasons.extend(replay_result.order_book_result.rejection_reasons)
    reasons.extend(replay_result.rejection_reasons)
    return tuple(dict.fromkeys(reasons))


def _state_rejection_reasons(state: OrderBookState) -> tuple[str, ...]:
    reasons = list(order_book_state_rejection_reasons(state))
    if state.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_paper_feed:venue_mismatch")
    if state.checksum is not None:
        reasons.append("deribit_paper_feed:checksum_unsupported")
    if _contains_scope_marker(state.source):
        reasons.append("deribit_paper_feed:scope_contamination")
    return tuple(dict.fromkeys(reasons))


def _policy_for_state(state: object) -> PublicFeedPolicy | None:
    if not isinstance(state, OrderBookState):
        return None
    try:
        spec = get_public_feed_dialect(DERIBIT_PUBLIC_BOOK_DIALECT_ID)
    except ValueError:
        return None
    if (
        spec.venue_id is not VenueId.DERIBIT
        or spec.feed_type is not PublicFeedType.L2_ORDERBOOK
        or spec.enabled_for_connector is not True
        or spec.supports_checksum is not False
        or spec.checksum_model is not FeedChecksumModel.NONE
        or spec.sequence_model is not FeedSequenceModel.SNAPSHOT_DELTA_RANGE
        or spec.max_gap_tolerance != 0
    ):
        return None
    return PublicFeedPolicy(
        venue_id=state.venue_id,
        symbol=state.symbol,
        canonical_symbol=state.canonical_symbol,
        feed_type=spec.feed_type,
        max_staleness_ns=spec.max_staleness_ns,
        max_receive_lag_ns=spec.max_receive_lag_ns,
        require_replay_cursor=True,
        require_order_book=True,
        reject_on_gap=True,
        reject_on_resync=True,
        reject_on_stale=True,
    )


def _frame_from_state(
    state: OrderBookState,
    readiness_snapshot: PublicDataReadinessSnapshot,
) -> DeribitPaperFeedFrame:
    best_bid = state.bids[0]
    best_ask = state.asks[0]
    return DeribitPaperFeedFrame(
        frame_id=f"{DERIBIT_PAPER_FEED_INPUT_ID}:{state.symbol}:seq:{state.last_sequence_id}",
        venue_id=state.venue_id,
        symbol=state.symbol,
        canonical_symbol=state.canonical_symbol,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        event_time_ns=readiness_snapshot.last_event_time_ns or 0,
        receive_time_ns=readiness_snapshot.last_receive_time_ns or 0,
        sequence_id=state.last_sequence_id,
        best_bid_price=best_bid.price,
        best_bid_quantity=best_bid.quantity,
        best_ask_price=best_ask.price,
        best_ask_quantity=best_ask.quantity,
        bid_depth=len(state.bids),
        ask_depth=len(state.asks),
        book_depth=state.depth,
        bid_levels=tuple((level.price, level.quantity) for level in state.bids),
        ask_levels=tuple((level.price, level.quantity) for level in state.asks),
        source=DERIBIT_PAPER_FEED_INPUT_ID,
        read_only_market_data=True,
        accepted_for_paper_input=True,
        paper_execution_ready=False,
        trade_ready=False,
    )


def _result(
    *,
    frame: DeribitPaperFeedFrame | None,
    readiness_snapshot: PublicDataReadinessSnapshot | None,
    reasons: tuple[str, ...] | list[str],
) -> DeribitPaperFeedResult:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return DeribitPaperFeedResult(
        accepted=normalized_reasons == () and isinstance(frame, DeribitPaperFeedFrame),
        frame=frame,
        readiness_snapshot=readiness_snapshot,
        rejection_reasons=normalized_reasons,
    )


def _contains_scope_marker(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in _SCOPE_MARKERS)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


__all__ = [
    "DERIBIT_PAPER_FEED_INPUT_ID",
    "DeribitPaperFeedFrame",
    "DeribitPaperFeedResult",
    "build_deribit_paper_feed_input",
    "deribit_paper_feed_frame_to_dict",
]
