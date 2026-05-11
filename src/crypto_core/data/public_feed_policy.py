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
from crypto_core.venue.contracts import PublicFeedHealth, PublicFeedType, VenueId


class PublicFeedPolicyError(ValueError):
    """Raised when public feed policy payloads are malformed."""


@dataclass(frozen=True)
class PublicFeedPolicy:
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    max_staleness_ns: int
    max_receive_lag_ns: int
    require_replay_cursor: bool = True
    require_order_book: bool = True
    reject_on_gap: bool = True
    reject_on_resync: bool = True
    reject_on_stale: bool = True


@dataclass(frozen=True)
class PublicFeedGateDecision:
    accepted: bool
    venue_id: VenueId | None
    symbol: str | None
    canonical_symbol: str | None
    feed_type: PublicFeedType | None
    rejection_reasons: tuple[str, ...]
    health_present: bool
    replay_cursor_ready: bool
    order_book_ready: bool
    gap_detected: bool
    stale_detected: bool
    resync_required: bool
    evaluated_at_ns: int | None


def public_feed_policy_rejection_reasons(policy: PublicFeedPolicy | object) -> tuple[str, ...]:
    if policy is None:
        return ("public_feed:policy_missing",)
    if not isinstance(policy, PublicFeedPolicy):
        return ("public_feed:policy_malformed",)

    reasons: list[str] = []
    if not isinstance(policy.venue_id, VenueId):
        reasons.append("public_feed:venue_missing")
    if not _non_empty(policy.symbol) or not _non_empty(policy.canonical_symbol):
        reasons.append("public_feed:symbol_missing")
    if not isinstance(policy.feed_type, PublicFeedType):
        reasons.append("public_feed:policy_malformed")
    if not _positive_int(policy.max_staleness_ns):
        reasons.append("public_feed:invalid_staleness")
    if not _positive_int(policy.max_receive_lag_ns):
        reasons.append("public_feed:invalid_receive_lag")
    for field_name in (
        "require_replay_cursor",
        "require_order_book",
        "reject_on_gap",
        "reject_on_resync",
        "reject_on_stale",
    ):
        if not isinstance(getattr(policy, field_name), bool):
            reasons.append("public_feed:policy_malformed")
    return tuple(dict.fromkeys(reasons))


def evaluate_public_feed_gate(
    policy: PublicFeedPolicy | object,
    *,
    health: PublicFeedHealth | None = None,
    replay_cursor: PublicMarketDataReplayCursor | None = None,
    replay_result: PublicMarketDataReplayResult | None = None,
    order_book_state: OrderBookState | None = None,
    order_book_result: OrderBookApplyResult | None = None,
    now_ns: int | None = None,
) -> PublicFeedGateDecision:
    policy_reasons = list(public_feed_policy_rejection_reasons(policy))
    if not isinstance(policy, PublicFeedPolicy):
        return _decision(
            policy,
            policy_reasons,
            health_present=False,
            replay_cursor_is_ready=False,
            order_book_is_ready=False,
            evaluated_at_ns=_valid_now_ns(now_ns),
        )

    reasons = list(policy_reasons)
    gap_detected = False
    stale_detected = False
    resync_required = False

    if not isinstance(health, PublicFeedHealth):
        reasons.append("public_feed:health_missing")
        health_present = False
    else:
        health_present = True
        reasons.extend(_health_rejection_reasons(policy, health, now_ns=now_ns))
        gap_detected = health.gap_detected
        stale_detected = health.stale
        resync_required = health.resync_required

    effective_cursor = replay_cursor
    if isinstance(replay_result, PublicMarketDataReplayResult):
        if effective_cursor is None:
            effective_cursor = replay_result.cursor
        if not replay_result.applied or replay_result.rejection_reasons:
            reasons.append("public_feed:replay_rejected")
        if replay_result.gap_detected and policy.reject_on_gap:
            reasons.append("public_feed:gap_detected")
        if replay_result.stale_detected and policy.reject_on_stale:
            reasons.append("public_feed:stale")
        if replay_result.resync_required and policy.reject_on_resync:
            reasons.append("public_feed:resync_required")
        gap_detected = gap_detected or replay_result.gap_detected
        stale_detected = stale_detected or replay_result.stale_detected
        resync_required = resync_required or replay_result.resync_required
    elif replay_result is not None:
        reasons.append("public_feed:replay_rejected")

    if policy.require_replay_cursor and effective_cursor is None:
        reasons.append("public_feed:replay_cursor_missing")
    replay_cursor_is_ready = replay_cursor_ready(effective_cursor)
    if effective_cursor is not None:
        reasons.extend(_cursor_rejection_reasons(policy, effective_cursor))
        if not replay_cursor_is_ready:
            reasons.append("public_feed:replay_cursor_not_ready")

    effective_order_book = order_book_state
    if isinstance(order_book_result, OrderBookApplyResult):
        if effective_order_book is None:
            effective_order_book = order_book_result.state
        if not order_book_result.applied or order_book_result.rejection_reasons:
            reasons.append("public_feed:order_book_rejected")
        if order_book_result.gap_detected and policy.reject_on_gap:
            reasons.append("public_feed:gap_detected")
        if order_book_result.resync_required and policy.reject_on_resync:
            reasons.append("public_feed:resync_required")
        gap_detected = gap_detected or order_book_result.gap_detected
        resync_required = resync_required or order_book_result.resync_required
    elif order_book_result is not None:
        reasons.append("public_feed:order_book_rejected")

    if policy.require_order_book and effective_order_book is None:
        reasons.append("public_feed:order_book_missing")
    order_book_is_ready = order_book_state_ready(effective_order_book)
    if effective_order_book is not None:
        reasons.extend(_order_book_rejection_reasons(policy, effective_order_book))
        if not order_book_is_ready:
            reasons.append("public_feed:order_book_not_ready")

    normalized_reasons = tuple(dict.fromkeys(reasons))
    return _decision(
        policy,
        normalized_reasons,
        health_present=health_present,
        replay_cursor_is_ready=replay_cursor_is_ready,
        order_book_is_ready=order_book_is_ready,
        gap_detected=gap_detected,
        stale_detected=stale_detected,
        resync_required=resync_required,
        evaluated_at_ns=_valid_now_ns(now_ns),
    )


def public_feed_gate_ready(decision: PublicFeedGateDecision | None) -> bool:
    return (
        isinstance(decision, PublicFeedGateDecision) and decision.accepted is True and decision.rejection_reasons == ()
    )


def public_feed_policy_to_dict(policy: PublicFeedPolicy) -> dict[str, object]:
    return {
        "venue_id": policy.venue_id.value,
        "symbol": policy.symbol,
        "canonical_symbol": policy.canonical_symbol,
        "feed_type": policy.feed_type.value,
        "max_staleness_ns": policy.max_staleness_ns,
        "max_receive_lag_ns": policy.max_receive_lag_ns,
        "require_replay_cursor": policy.require_replay_cursor,
        "require_order_book": policy.require_order_book,
        "reject_on_gap": policy.reject_on_gap,
        "reject_on_resync": policy.reject_on_resync,
        "reject_on_stale": policy.reject_on_stale,
    }


def public_feed_policy_from_dict(data: object) -> PublicFeedPolicy:
    payload = _mapping(data, "public feed policy payload")
    return PublicFeedPolicy(
        venue_id=_venue_id(payload.get("venue_id")),
        symbol=_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_feed_type(payload.get("feed_type")),
        max_staleness_ns=_positive_int_field(payload.get("max_staleness_ns"), "max_staleness_ns"),
        max_receive_lag_ns=_positive_int_field(payload.get("max_receive_lag_ns"), "max_receive_lag_ns"),
        require_replay_cursor=_bool(payload.get("require_replay_cursor", True), "require_replay_cursor"),
        require_order_book=_bool(payload.get("require_order_book", True), "require_order_book"),
        reject_on_gap=_bool(payload.get("reject_on_gap", True), "reject_on_gap"),
        reject_on_resync=_bool(payload.get("reject_on_resync", True), "reject_on_resync"),
        reject_on_stale=_bool(payload.get("reject_on_stale", True), "reject_on_stale"),
    )


def public_feed_gate_decision_to_dict(decision: PublicFeedGateDecision) -> dict[str, object]:
    return {
        "accepted": decision.accepted,
        "venue_id": None if decision.venue_id is None else decision.venue_id.value,
        "symbol": decision.symbol,
        "canonical_symbol": decision.canonical_symbol,
        "feed_type": None if decision.feed_type is None else decision.feed_type.value,
        "rejection_reasons": list(decision.rejection_reasons),
        "health_present": decision.health_present,
        "replay_cursor_ready": decision.replay_cursor_ready,
        "order_book_ready": decision.order_book_ready,
        "gap_detected": decision.gap_detected,
        "stale_detected": decision.stale_detected,
        "resync_required": decision.resync_required,
        "evaluated_at_ns": decision.evaluated_at_ns,
    }


def public_feed_gate_decision_from_dict(data: object) -> PublicFeedGateDecision:
    payload = _mapping(data, "public feed gate decision payload")
    return PublicFeedGateDecision(
        accepted=_bool(payload.get("accepted"), "accepted"),
        venue_id=_optional_venue_id(payload.get("venue_id")),
        symbol=_optional_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_optional_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_optional_feed_type(payload.get("feed_type")),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
        health_present=_bool(payload.get("health_present"), "health_present"),
        replay_cursor_ready=_bool(payload.get("replay_cursor_ready"), "replay_cursor_ready"),
        order_book_ready=_bool(payload.get("order_book_ready"), "order_book_ready"),
        gap_detected=_bool(payload.get("gap_detected"), "gap_detected"),
        stale_detected=_bool(payload.get("stale_detected"), "stale_detected"),
        resync_required=_bool(payload.get("resync_required"), "resync_required"),
        evaluated_at_ns=_optional_positive_int(payload.get("evaluated_at_ns"), "evaluated_at_ns"),
    )


def _health_rejection_reasons(
    policy: PublicFeedPolicy,
    health: PublicFeedHealth,
    *,
    now_ns: int | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if health.venue_id != policy.venue_id:
        reasons.append("public_feed:venue_mismatch")
    if health.symbol != policy.symbol:
        reasons.append("public_feed:symbol_mismatch")
    if health.feed_type != policy.feed_type:
        reasons.append("public_feed:feed_type_mismatch")
    if not health.healthy:
        reasons.append("public_feed:unhealthy")
    if health.stale and policy.reject_on_stale:
        reasons.append("public_feed:stale")
    if health.gap_detected and policy.reject_on_gap:
        reasons.append("public_feed:gap_detected")
    if health.resync_required and policy.reject_on_resync:
        reasons.append("public_feed:resync_required")
    if _positive_int(now_ns):
        if now_ns - health.last_event_time_ns > policy.max_staleness_ns and policy.reject_on_stale:
            reasons.append("public_feed:stale")
        if now_ns - health.last_receive_time_ns > policy.max_receive_lag_ns:
            reasons.append("public_feed:receive_lag_exceeded")
    elif now_ns is not None:
        reasons.append("public_feed:invalid_receive_lag")
    reasons.extend(health.rejection_reasons)
    return tuple(dict.fromkeys(reasons))


def _cursor_rejection_reasons(
    policy: PublicFeedPolicy,
    cursor: PublicMarketDataReplayCursor,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if cursor.venue_id != policy.venue_id:
        reasons.append("public_feed:venue_mismatch")
    if cursor.symbol != policy.symbol or cursor.canonical_symbol != policy.canonical_symbol:
        reasons.append("public_feed:symbol_mismatch")
    return tuple(dict.fromkeys(reasons))


def _order_book_rejection_reasons(
    policy: PublicFeedPolicy,
    state: OrderBookState,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if state.venue_id != policy.venue_id:
        reasons.append("public_feed:venue_mismatch")
    if state.symbol != policy.symbol or state.canonical_symbol != policy.canonical_symbol:
        reasons.append("public_feed:symbol_mismatch")
    return tuple(dict.fromkeys(reasons))


def _decision(
    policy: PublicFeedPolicy | object,
    reasons: tuple[str, ...] | list[str],
    *,
    health_present: bool,
    replay_cursor_is_ready: bool,
    order_book_is_ready: bool,
    gap_detected: bool = False,
    stale_detected: bool = False,
    resync_required: bool = False,
    evaluated_at_ns: int | None = None,
) -> PublicFeedGateDecision:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return PublicFeedGateDecision(
        accepted=normalized_reasons == (),
        venue_id=policy.venue_id
        if isinstance(policy, PublicFeedPolicy) and isinstance(policy.venue_id, VenueId)
        else None,
        symbol=policy.symbol if isinstance(policy, PublicFeedPolicy) and isinstance(policy.symbol, str) else None,
        canonical_symbol=(
            policy.canonical_symbol
            if isinstance(policy, PublicFeedPolicy) and isinstance(policy.canonical_symbol, str)
            else None
        ),
        feed_type=(
            policy.feed_type
            if isinstance(policy, PublicFeedPolicy) and isinstance(policy.feed_type, PublicFeedType)
            else None
        ),
        rejection_reasons=normalized_reasons,
        health_present=health_present,
        replay_cursor_ready=replay_cursor_is_ready,
        order_book_ready=order_book_is_ready,
        gap_detected=gap_detected,
        stale_detected=stale_detected,
        resync_required=resync_required,
        evaluated_at_ns=evaluated_at_ns,
    )


def _mapping(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PublicFeedPolicyError(f"{name} must be a mapping")
    return data


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicFeedPolicyError("venue_id is unsupported") from exc
    raise PublicFeedPolicyError("venue_id is malformed")


def _optional_venue_id(value: object) -> VenueId | None:
    if value is None:
        return None
    return _venue_id(value)


def _feed_type(value: object) -> PublicFeedType:
    if isinstance(value, PublicFeedType):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedType(value)
        except ValueError as exc:
            raise PublicFeedPolicyError("feed_type is unsupported") from exc
    raise PublicFeedPolicyError("feed_type is malformed")


def _optional_feed_type(value: object) -> PublicFeedType | None:
    if value is None:
        return None
    return _feed_type(value)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string(value: object, field_name: str) -> str:
    if not _non_empty(value):
        raise PublicFeedPolicyError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_field(value: object, field_name: str) -> int:
    if not _positive_int(value):
        raise PublicFeedPolicyError(f"{field_name} must be a positive integer")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int_field(value, field_name)


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicFeedPolicyError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicFeedPolicyError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(reason, str) or not reason for reason in result):
        raise PublicFeedPolicyError(f"{field_name} must contain non-empty strings")
    return result


def _valid_now_ns(now_ns: int | None) -> int | None:
    return now_ns if _positive_int(now_ns) else None


__all__ = [
    "PublicFeedGateDecision",
    "PublicFeedPolicy",
    "PublicFeedPolicyError",
    "evaluate_public_feed_gate",
    "public_feed_gate_decision_from_dict",
    "public_feed_gate_decision_to_dict",
    "public_feed_gate_ready",
    "public_feed_policy_from_dict",
    "public_feed_policy_rejection_reasons",
    "public_feed_policy_to_dict",
]
