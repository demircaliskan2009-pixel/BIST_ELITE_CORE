from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.market_data_journal import replay_cursor_ready
from crypto_core.data.order_book import (
    OrderBookApplyResult,
    OrderBookState,
    apply_order_book_delta,
    build_order_book_state_from_snapshot,
    order_book_state_rejection_reasons,
)
from crypto_core.venue.contracts import PublicMarketDataEvent
from crypto_core.venue.deribit_public_data_quality import DeribitPublicDataQualityResult
from crypto_core.venue.deribit_public_feed_ingest import DeribitPublicFeedIngestResult


@dataclass(frozen=True)
class DeribitOrderBookReplayEvent:
    quality_result: DeribitPublicDataQualityResult
    ingest_result: DeribitPublicFeedIngestResult


@dataclass(frozen=True)
class DeribitOrderBookReplayResult:
    accepted: bool
    state: OrderBookState | None
    order_book_result: OrderBookApplyResult | None
    applied_event_count: int
    rejection_reasons: tuple[str, ...]


def replay_deribit_order_book_events(
    events: object,
    *,
    initial_state: OrderBookState | None = None,
) -> DeribitOrderBookReplayResult:
    if not isinstance(events, tuple) or not events:
        return _result(
            state=initial_state,
            order_book_result=None,
            applied_event_count=0,
            rejection_reasons=("deribit_order_book_replay:events_empty",),
        )

    state = initial_state
    if state is not None:
        state_reasons = order_book_state_rejection_reasons(state)
        if state_reasons:
            return _result(
                state=state,
                order_book_result=None,
                applied_event_count=0,
                rejection_reasons=("deribit_order_book_replay:initial_state_rejected", *state_reasons),
            )

    applied_event_count = 0
    last_apply_result: OrderBookApplyResult | None = None
    for entry in events:
        entry_reasons = _event_rejection_reasons(entry, state)
        if entry_reasons:
            return _result(
                state=state,
                order_book_result=last_apply_result,
                applied_event_count=applied_event_count,
                rejection_reasons=entry_reasons,
            )

        assert isinstance(entry, DeribitOrderBookReplayEvent)
        quality_result = entry.quality_result
        if quality_result.order_book_snapshot is not None:
            apply_result = build_order_book_state_from_snapshot(quality_result.order_book_snapshot)
        else:
            assert state is not None
            assert quality_result.order_book_delta is not None
            apply_result = apply_order_book_delta(state, quality_result.order_book_delta)

        if apply_result.applied is not True or apply_result.state is None:
            return _result(
                state=state,
                order_book_result=apply_result,
                applied_event_count=applied_event_count,
                rejection_reasons=apply_result.rejection_reasons,
            )

        state = apply_result.state
        last_apply_result = apply_result
        applied_event_count += 1

    return _result(
        state=state,
        order_book_result=last_apply_result,
        applied_event_count=applied_event_count,
        rejection_reasons=(),
    )


def _event_rejection_reasons(
    entry: object,
    current_state: OrderBookState | None,
) -> tuple[str, ...]:
    if not isinstance(entry, DeribitOrderBookReplayEvent):
        return ("deribit_order_book_replay:event_malformed",)

    reasons: list[str] = []
    quality_result = entry.quality_result
    ingest_result = entry.ingest_result

    if quality_result.accepted is not True:
        reasons.append("deribit_order_book_replay:quality_gate_rejected")
        reasons.extend(quality_result.rejection_reasons)
    if ingest_result.accepted is not True:
        reasons.append("deribit_order_book_replay:ingest_rejected")
        reasons.extend(ingest_result.rejection_reasons)

    market_event = quality_result.market_event
    if not isinstance(market_event, PublicMarketDataEvent):
        reasons.append("deribit_order_book_replay:market_event_missing")

    plan = ingest_result.ingest_plan
    if plan is None:
        reasons.append("deribit_order_book_replay:ingest_plan_missing")

    nested_ingest_result = ingest_result.ingest_result
    if nested_ingest_result is None:
        reasons.append("deribit_order_book_replay:ingest_result_missing")
        return tuple(dict.fromkeys(reasons))
    if nested_ingest_result.accepted is not True:
        reasons.append("deribit_order_book_replay:ingest_result_not_accepted")
        reasons.extend(nested_ingest_result.rejection_reasons)

    replay_result = nested_ingest_result.replay_result
    if replay_result is None:
        reasons.append("deribit_order_book_replay:journal_replay_missing")
        return tuple(dict.fromkeys(reasons))
    if replay_result.applied is not True or replay_result.rejection_reasons:
        reasons.append("deribit_order_book_replay:journal_replay_not_ready")
        reasons.extend(replay_result.rejection_reasons)

    cursor = replay_result.cursor
    if not replay_cursor_ready(cursor):
        reasons.append("deribit_order_book_replay:journal_cursor_not_ready")

    if isinstance(market_event, PublicMarketDataEvent) and cursor is not None:
        if cursor.venue_id != market_event.venue_id:
            reasons.append("deribit_order_book_replay:ingest_event_identity_mismatch")
        if cursor.symbol != market_event.symbol or cursor.canonical_symbol != market_event.canonical_symbol:
            reasons.append("deribit_order_book_replay:ingest_event_identity_mismatch")
        if cursor.last_sequence_id != market_event.sequence_id:
            reasons.append("deribit_order_book_replay:ingest_sequence_mismatch")
    if isinstance(market_event, PublicMarketDataEvent) and plan is not None:
        policy = plan.policy
        if (
            policy.venue_id != market_event.venue_id
            or policy.symbol != market_event.symbol
            or policy.canonical_symbol != market_event.canonical_symbol
            or policy.feed_type != market_event.feed_type
        ):
            reasons.append("deribit_order_book_replay:plan_event_identity_mismatch")

    snapshot = quality_result.order_book_snapshot
    delta = quality_result.order_book_delta
    if snapshot is not None and delta is not None:
        reasons.append("deribit_order_book_replay:book_contract_ambiguous")
    elif snapshot is None and delta is None:
        reasons.append("deribit_order_book_replay:book_contract_missing")
    elif snapshot is not None and current_state is not None:
        reasons.append("deribit_order_book_replay:unexpected_snapshot")
    elif delta is not None and current_state is None:
        reasons.append("deribit_order_book_replay:snapshot_required")

    if current_state is not None and isinstance(market_event, PublicMarketDataEvent):
        if (
            current_state.venue_id != market_event.venue_id
            or current_state.symbol != market_event.symbol
            or current_state.canonical_symbol != market_event.canonical_symbol
        ):
            reasons.append("deribit_order_book_replay:state_event_identity_mismatch")

    return tuple(dict.fromkeys(reasons))


def _result(
    *,
    state: OrderBookState | None,
    order_book_result: OrderBookApplyResult | None,
    applied_event_count: int,
    rejection_reasons: tuple[str, ...] | list[str],
) -> DeribitOrderBookReplayResult:
    normalized_reasons = tuple(dict.fromkeys(rejection_reasons))
    return DeribitOrderBookReplayResult(
        accepted=normalized_reasons == ()
        and state is not None
        and order_book_result is not None
        and order_book_result.applied is True,
        state=state,
        order_book_result=order_book_result,
        applied_event_count=applied_event_count,
        rejection_reasons=normalized_reasons,
    )
