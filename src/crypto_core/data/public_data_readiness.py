from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.market_data_journal import (
    PublicMarketDataReplayCursor,
    PublicMarketDataReplayResult,
    replay_cursor_ready,
)
from crypto_core.data.order_book import (
    OrderBookApplyResult,
    OrderBookState,
    order_book_state_ready,
)
from crypto_core.data.public_feed_policy import (
    PublicFeedPolicy,
    evaluate_public_feed_gate,
    public_feed_gate_ready,
)
from crypto_core.venue.contracts import PublicFeedHealth, PublicFeedType, VenueId


class PublicDataReadinessError(ValueError):
    """Raised when public data readiness payloads are malformed."""


@dataclass(frozen=True)
class PublicDataReadinessInput:
    policy: PublicFeedPolicy
    health: PublicFeedHealth | None
    replay_cursor: PublicMarketDataReplayCursor | None
    replay_result: PublicMarketDataReplayResult | None
    order_book_state: OrderBookState | None
    order_book_result: OrderBookApplyResult | None
    now_ns: int | None = None


@dataclass(frozen=True)
class PublicDataReadinessSnapshot:
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    order_book_ready: bool
    replay_ready: bool
    feed_gate_ready: bool
    accepted_for_paper: bool
    rejection_reasons: tuple[str, ...]
    last_sequence_id: int | None
    last_event_time_ns: int | None
    last_receive_time_ns: int | None


def build_public_data_readiness_snapshot(
    readiness_input: PublicDataReadinessInput,
) -> PublicDataReadinessSnapshot:
    if not isinstance(readiness_input, PublicDataReadinessInput):
        raise PublicDataReadinessError("readiness input must be PublicDataReadinessInput")
    policy = readiness_input.policy
    if not isinstance(policy, PublicFeedPolicy):
        raise PublicDataReadinessError("policy must be PublicFeedPolicy")

    gate = evaluate_public_feed_gate(
        policy,
        health=readiness_input.health,
        replay_cursor=readiness_input.replay_cursor,
        replay_result=readiness_input.replay_result,
        order_book_state=readiness_input.order_book_state,
        order_book_result=readiness_input.order_book_result,
        now_ns=readiness_input.now_ns,
    )
    cursor = _effective_cursor(readiness_input)
    state = _effective_order_book_state(readiness_input)
    replay_ready = replay_cursor_ready(cursor)
    order_book_ready = True if not policy.require_order_book else order_book_state_ready(state)

    reasons: list[str] = list(gate.rejection_reasons)
    if not replay_ready:
        reasons.append("public_data:replay_not_ready")
    if policy.require_order_book and not order_book_ready:
        reasons.append("public_data:order_book_not_ready")
    reasons.extend(_replay_reasons(readiness_input))
    reasons.extend(_order_book_reasons(readiness_input))
    normalized_reasons = tuple(dict.fromkeys(reasons))

    feed_ready = public_feed_gate_ready(gate)
    return PublicDataReadinessSnapshot(
        venue_id=policy.venue_id,
        symbol=policy.symbol,
        canonical_symbol=policy.canonical_symbol,
        feed_type=policy.feed_type,
        order_book_ready=order_book_ready,
        replay_ready=replay_ready,
        feed_gate_ready=feed_ready,
        accepted_for_paper=feed_ready and replay_ready and order_book_ready and normalized_reasons == (),
        rejection_reasons=normalized_reasons,
        last_sequence_id=_last_sequence_id(cursor, state),
        last_event_time_ns=_last_event_time_ns(readiness_input.health, cursor),
        last_receive_time_ns=readiness_input.health.last_receive_time_ns
        if isinstance(readiness_input.health, PublicFeedHealth)
        else None,
    )


def public_data_ready_for_paper(snapshot: PublicDataReadinessSnapshot | None) -> bool:
    return (
        isinstance(snapshot, PublicDataReadinessSnapshot)
        and snapshot.accepted_for_paper is True
        and snapshot.feed_gate_ready is True
        and snapshot.replay_ready is True
        and snapshot.order_book_ready is True
        and snapshot.rejection_reasons == ()
    )


def public_data_readiness_snapshot_to_dict(snapshot: PublicDataReadinessSnapshot) -> dict[str, object]:
    return {
        "venue_id": snapshot.venue_id.value,
        "symbol": snapshot.symbol,
        "canonical_symbol": snapshot.canonical_symbol,
        "feed_type": snapshot.feed_type.value,
        "order_book_ready": snapshot.order_book_ready,
        "replay_ready": snapshot.replay_ready,
        "feed_gate_ready": snapshot.feed_gate_ready,
        "accepted_for_paper": snapshot.accepted_for_paper,
        "rejection_reasons": list(snapshot.rejection_reasons),
        "last_sequence_id": snapshot.last_sequence_id,
        "last_event_time_ns": snapshot.last_event_time_ns,
        "last_receive_time_ns": snapshot.last_receive_time_ns,
    }


def public_data_readiness_snapshot_from_dict(data: object) -> PublicDataReadinessSnapshot:
    payload = _mapping(data)
    return PublicDataReadinessSnapshot(
        venue_id=_venue_id(payload.get("venue_id")),
        symbol=_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_feed_type(payload.get("feed_type")),
        order_book_ready=_bool(payload.get("order_book_ready"), "order_book_ready"),
        replay_ready=_bool(payload.get("replay_ready"), "replay_ready"),
        feed_gate_ready=_bool(payload.get("feed_gate_ready"), "feed_gate_ready"),
        accepted_for_paper=_bool(payload.get("accepted_for_paper"), "accepted_for_paper"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        last_sequence_id=_optional_non_negative_int(payload.get("last_sequence_id"), "last_sequence_id"),
        last_event_time_ns=_optional_positive_int(payload.get("last_event_time_ns"), "last_event_time_ns"),
        last_receive_time_ns=_optional_positive_int(payload.get("last_receive_time_ns"), "last_receive_time_ns"),
    )


def _effective_cursor(readiness_input: PublicDataReadinessInput) -> PublicMarketDataReplayCursor | None:
    if readiness_input.replay_cursor is not None:
        return readiness_input.replay_cursor
    if isinstance(readiness_input.replay_result, PublicMarketDataReplayResult):
        return readiness_input.replay_result.cursor
    return None


def _effective_order_book_state(readiness_input: PublicDataReadinessInput) -> OrderBookState | None:
    if readiness_input.order_book_state is not None:
        return readiness_input.order_book_state
    if isinstance(readiness_input.order_book_result, OrderBookApplyResult):
        return readiness_input.order_book_result.state
    return None


def _replay_reasons(readiness_input: PublicDataReadinessInput) -> tuple[str, ...]:
    reasons: list[str] = []
    cursor = _effective_cursor(readiness_input)
    if isinstance(cursor, PublicMarketDataReplayCursor):
        reasons.extend(cursor.rejection_reasons)
    result = readiness_input.replay_result
    if isinstance(result, PublicMarketDataReplayResult):
        reasons.extend(result.rejection_reasons)
    return tuple(dict.fromkeys(reasons))


def _order_book_reasons(readiness_input: PublicDataReadinessInput) -> tuple[str, ...]:
    reasons: list[str] = []
    state = _effective_order_book_state(readiness_input)
    if isinstance(state, OrderBookState):
        reasons.extend(state.rejection_reasons)
    result = readiness_input.order_book_result
    if isinstance(result, OrderBookApplyResult):
        reasons.extend(result.rejection_reasons)
    return tuple(dict.fromkeys(reasons))


def _last_sequence_id(cursor: PublicMarketDataReplayCursor | None, state: OrderBookState | None) -> int | None:
    if isinstance(state, OrderBookState):
        return state.last_sequence_id
    if isinstance(cursor, PublicMarketDataReplayCursor):
        return cursor.last_sequence_id
    return None


def _last_event_time_ns(
    health: PublicFeedHealth | None,
    cursor: PublicMarketDataReplayCursor | None,
) -> int | None:
    if isinstance(health, PublicFeedHealth):
        return health.last_event_time_ns
    if isinstance(cursor, PublicMarketDataReplayCursor):
        return cursor.last_event_time_ns
    return None


def _mapping(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicDataReadinessError("public data readiness payload must be a mapping")
    return data


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicDataReadinessError("venue_id is unsupported") from exc
    raise PublicDataReadinessError("venue_id is malformed")


def _feed_type(value: object) -> PublicFeedType:
    if isinstance(value, PublicFeedType):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedType(value)
        except ValueError as exc:
            raise PublicDataReadinessError("feed_type is unsupported") from exc
    raise PublicDataReadinessError("feed_type is malformed")


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PublicDataReadinessError(f"{field_name} must be a non-empty string")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicDataReadinessError(f"{field_name} must be a boolean")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PublicDataReadinessError(f"{field_name} must be a positive integer")
    return value


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PublicDataReadinessError(f"{field_name} must be a non-negative integer")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicDataReadinessError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicDataReadinessError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "PublicDataReadinessError",
    "PublicDataReadinessInput",
    "PublicDataReadinessSnapshot",
    "build_public_data_readiness_snapshot",
    "public_data_readiness_snapshot_from_dict",
    "public_data_readiness_snapshot_to_dict",
    "public_data_ready_for_paper",
]
