from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from crypto_core.venue.contracts import (
    OrderBookDelta,
    OrderBookLevel,
    OrderBookSnapshot,
    VenueId,
    order_book_level_from_dict,
    order_book_level_to_dict,
)


class OrderBookReconstructionError(ValueError):
    """Raised when order book reconstruction payloads are malformed."""


@dataclass(frozen=True)
class OrderBookState:
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    last_sequence_id: int
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    checksum: str | None
    depth: int
    source: str
    healthy: bool
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_state_shape(self)


@dataclass(frozen=True)
class OrderBookApplyResult:
    applied: bool
    state: OrderBookState | None
    rejection_reasons: tuple[str, ...]
    resync_required: bool
    gap_detected: bool

    def __post_init__(self) -> None:
        if not isinstance(self.applied, bool):
            raise OrderBookReconstructionError("applied must be a boolean")
        if self.state is not None and not isinstance(self.state, OrderBookState):
            raise OrderBookReconstructionError("state must be OrderBookState or None")
        if not isinstance(self.rejection_reasons, tuple) or any(
            not isinstance(reason, str) or not reason for reason in self.rejection_reasons
        ):
            raise OrderBookReconstructionError("rejection_reasons must be a tuple of non-empty strings")
        if not isinstance(self.resync_required, bool) or not isinstance(self.gap_detected, bool):
            raise OrderBookReconstructionError("resync_required and gap_detected must be booleans")


def build_order_book_state_from_snapshot(snapshot: OrderBookSnapshot) -> OrderBookApplyResult:
    reasons = _snapshot_rejection_reasons(snapshot)
    if reasons:
        return _rejected(reasons, state=None)

    bids = _normalize_side(snapshot.bids, descending=True)
    asks = _normalize_side(snapshot.asks, descending=False)
    checksum = snapshot.checksum
    if checksum is not None and checksum != _book_checksum(bids, asks):
        return _rejected(("order_book:checksum_mismatch",), state=None)

    state = OrderBookState(
        venue_id=snapshot.venue_id,
        symbol=snapshot.symbol,
        canonical_symbol=snapshot.canonical_symbol,
        last_sequence_id=snapshot.sequence_id,
        bids=bids,
        asks=asks,
        checksum=checksum,
        depth=snapshot.depth,
        source=snapshot.source,
        healthy=True,
        rejection_reasons=(),
    )
    return OrderBookApplyResult(
        applied=True,
        state=state,
        rejection_reasons=(),
        resync_required=False,
        gap_detected=False,
    )


def apply_order_book_delta(state: OrderBookState, delta: OrderBookDelta) -> OrderBookApplyResult:
    state_reasons = order_book_state_rejection_reasons(state)
    if state_reasons:
        return _rejected(state_reasons, state=state)

    reasons = _delta_rejection_reasons(state, delta)
    if reasons:
        return _rejected(
            reasons,
            state=state,
            resync_required=_requires_resync(reasons),
            gap_detected=any(reason in reasons for reason in _GAP_REASONS),
        )

    bid_map = {level.price: level.quantity for level in state.bids}
    ask_map = {level.price: level.quantity for level in state.asks}
    apply_reasons = _apply_updates(bid_map, delta.bid_updates)
    apply_reasons.extend(_apply_updates(ask_map, delta.ask_updates))
    if apply_reasons:
        return _rejected(tuple(dict.fromkeys(apply_reasons)), state=state, resync_required=True)

    bids = tuple(OrderBookLevel(price=price, quantity=qty) for price, qty in sorted(bid_map.items(), reverse=True))
    asks = tuple(OrderBookLevel(price=price, quantity=qty) for price, qty in sorted(ask_map.items()))
    book_reasons = _book_rejection_reasons(bids, asks)
    if book_reasons:
        return _rejected(book_reasons, state=state, resync_required=True)

    checksum = delta.checksum
    if checksum is not None and checksum != _book_checksum(bids, asks):
        return _rejected(("order_book:checksum_mismatch",), state=state, resync_required=True)

    next_state = OrderBookState(
        venue_id=state.venue_id,
        symbol=state.symbol,
        canonical_symbol=state.canonical_symbol,
        last_sequence_id=delta.final_update_id,
        bids=bids,
        asks=asks,
        checksum=checksum,
        depth=min(state.depth, len(bids), len(asks)),
        source=delta.source,
        healthy=True,
        rejection_reasons=(),
    )
    return OrderBookApplyResult(
        applied=True,
        state=next_state,
        rejection_reasons=(),
        resync_required=False,
        gap_detected=False,
    )


def order_book_state_rejection_reasons(state: OrderBookState | None) -> tuple[str, ...]:
    if state is None:
        return ("order_book:state_missing",)
    if not isinstance(state, OrderBookState):
        return ("order_book:state_malformed",)

    reasons: list[str] = []
    if not state.healthy:
        reasons.append("order_book:unhealthy")
    reasons.extend(state.rejection_reasons)
    reasons.extend(_state_content_rejection_reasons(state))
    return tuple(dict.fromkeys(reasons))


def order_book_state_ready(state: OrderBookState | None) -> bool:
    return not order_book_state_rejection_reasons(state)


def order_book_state_to_dict(state: OrderBookState) -> dict[str, object]:
    return {
        "venue_id": state.venue_id.value,
        "symbol": state.symbol,
        "canonical_symbol": state.canonical_symbol,
        "last_sequence_id": state.last_sequence_id,
        "bids": [order_book_level_to_dict(level) for level in state.bids],
        "asks": [order_book_level_to_dict(level) for level in state.asks],
        "checksum": state.checksum,
        "depth": state.depth,
        "source": state.source,
        "healthy": state.healthy,
        "rejection_reasons": list(state.rejection_reasons),
    }


def order_book_state_from_dict(data: object) -> OrderBookState:
    if not isinstance(data, dict):
        raise OrderBookReconstructionError("order_book_state payload must be a mapping")
    return OrderBookState(
        venue_id=_venue_id_from_payload(data.get("venue_id")),
        symbol=_non_empty_string(data.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(data.get("canonical_symbol"), "canonical_symbol"),
        last_sequence_id=_non_negative_int(data.get("last_sequence_id"), "last_sequence_id"),
        bids=tuple(order_book_level_from_dict(level) for level in _sequence(data.get("bids"), "bids")),
        asks=tuple(order_book_level_from_dict(level) for level in _sequence(data.get("asks"), "asks")),
        checksum=_optional_string(data.get("checksum"), "checksum"),
        depth=_positive_int(data.get("depth"), "depth"),
        source=_non_empty_string(data.get("source"), "source"),
        healthy=_bool(data.get("healthy"), "healthy"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


_GAP_REASONS = frozenset(
    {
        "order_book:prev_update_id_mismatch",
        "order_book:sequence_gap",
        "order_book:stale_delta",
    }
)


def _snapshot_rejection_reasons(snapshot: OrderBookSnapshot) -> tuple[str, ...]:
    if not isinstance(snapshot, OrderBookSnapshot):
        return ("order_book:snapshot_malformed",)
    reasons = _header_rejection_reasons(
        snapshot.venue_id,
        snapshot.symbol,
        snapshot.canonical_symbol,
        snapshot.sequence_id,
        snapshot.source,
    )
    reasons.extend(_side_rejection_reasons(snapshot.bids, "bids", descending=True, allow_zero=False, allow_empty=False))
    reasons.extend(
        _side_rejection_reasons(snapshot.asks, "asks", descending=False, allow_zero=False, allow_empty=False)
    )
    reasons.extend(_book_rejection_reasons(snapshot.bids, snapshot.asks))
    if not isinstance(snapshot.depth, int) or isinstance(snapshot.depth, bool) or snapshot.depth <= 0:
        reasons.append("order_book:invalid_depth")
    elif (
        isinstance(snapshot.bids, tuple)
        and isinstance(snapshot.asks, tuple)
        and snapshot.depth
        > min(
            len(snapshot.bids),
            len(snapshot.asks),
        )
    ):
        reasons.append("order_book:invalid_depth")
    return tuple(dict.fromkeys(reasons))


def _delta_rejection_reasons(state: OrderBookState, delta: OrderBookDelta) -> tuple[str, ...]:
    if not isinstance(delta, OrderBookDelta):
        return ("order_book:delta_malformed",)
    reasons = _header_rejection_reasons(
        delta.venue_id,
        delta.symbol,
        delta.canonical_symbol,
        delta.final_update_id,
        delta.source,
    )
    if delta.venue_id != state.venue_id:
        reasons.append("order_book:venue_mismatch")
    if delta.symbol != state.symbol or delta.canonical_symbol != state.canonical_symbol:
        reasons.append("order_book:symbol_mismatch")
    if delta.prev_update_id != state.last_sequence_id:
        reasons.append("order_book:prev_update_id_mismatch")
    if delta.first_update_id != state.last_sequence_id + 1:
        reasons.append("order_book:sequence_gap")
    if delta.final_update_id < delta.first_update_id:
        reasons.append("order_book:invalid_sequence")
    if delta.final_update_id <= state.last_sequence_id:
        reasons.append("order_book:stale_delta")
    reasons.extend(
        _side_rejection_reasons(delta.bid_updates, "bid_updates", descending=True, allow_zero=True, allow_empty=True)
    )
    reasons.extend(
        _side_rejection_reasons(delta.ask_updates, "ask_updates", descending=False, allow_zero=True, allow_empty=True)
    )
    if not delta.bid_updates and not delta.ask_updates:
        reasons.append("order_book:no_updates")
    return tuple(dict.fromkeys(reasons))


def _state_content_rejection_reasons(state: OrderBookState) -> tuple[str, ...]:
    reasons = _header_rejection_reasons(
        state.venue_id,
        state.symbol,
        state.canonical_symbol,
        state.last_sequence_id,
        state.source,
    )
    reasons.extend(_side_rejection_reasons(state.bids, "bids", descending=True, allow_zero=False, allow_empty=False))
    reasons.extend(_side_rejection_reasons(state.asks, "asks", descending=False, allow_zero=False, allow_empty=False))
    reasons.extend(_book_rejection_reasons(state.bids, state.asks))
    if not isinstance(state.depth, int) or isinstance(state.depth, bool) or state.depth <= 0:
        reasons.append("order_book:invalid_depth")
    return tuple(dict.fromkeys(reasons))


def _header_rejection_reasons(
    venue_id: object,
    symbol: object,
    canonical_symbol: object,
    sequence_id: object,
    source: object,
) -> list[str]:
    reasons: list[str] = []
    if not isinstance(venue_id, VenueId):
        reasons.append("order_book:venue_malformed")
    if not isinstance(symbol, str) or not symbol:
        reasons.append("order_book:symbol_missing")
    if not isinstance(canonical_symbol, str) or not canonical_symbol:
        reasons.append("order_book:canonical_symbol_missing")
    if not isinstance(sequence_id, int) or isinstance(sequence_id, bool) or sequence_id < 0:
        reasons.append("order_book:invalid_sequence")
    if not isinstance(source, str) or not source:
        reasons.append("order_book:source_missing")
    return reasons


def _side_rejection_reasons(
    levels: object,
    side_name: str,
    *,
    descending: bool,
    allow_zero: bool,
    allow_empty: bool,
) -> list[str]:
    reasons: list[str] = []
    if not isinstance(levels, tuple):
        return [f"order_book:{side_name}_empty"]
    if not levels:
        return [] if allow_empty else [f"order_book:{side_name}_empty"]
    prices: list[float] = []
    previous_price: float | None = None
    for level in levels:
        if not isinstance(level, OrderBookLevel):
            reasons.append(f"order_book:{side_name}_malformed")
            continue
        if not _finite_positive(level.price):
            reasons.append(f"order_book:{side_name}_invalid_price")
        if allow_zero:
            if not _finite_non_negative(level.quantity):
                reasons.append(f"order_book:{side_name}_invalid_quantity")
        elif not _finite_positive(level.quantity):
            reasons.append(f"order_book:{side_name}_invalid_quantity")
        if previous_price is not None:
            if descending and level.price >= previous_price:
                reasons.append(f"order_book:{side_name}_not_descending")
            if not descending and level.price <= previous_price:
                reasons.append(f"order_book:{side_name}_not_ascending")
        previous_price = level.price
        prices.append(level.price)
    if len(prices) != len(set(prices)):
        reasons.append(f"order_book:{side_name}_duplicate_price")
    return reasons


def _book_rejection_reasons(bids: object, asks: object) -> tuple[str, ...]:
    if not isinstance(bids, tuple) or not isinstance(asks, tuple) or not bids or not asks:
        return ("order_book:empty_side",)
    if not all(isinstance(level, OrderBookLevel) for level in bids + asks):
        return ("order_book:level_malformed",)
    if max(level.price for level in bids) >= min(level.price for level in asks):
        return ("order_book:crossed",)
    return ()


def _normalize_side(levels: tuple[OrderBookLevel, ...], *, descending: bool) -> tuple[OrderBookLevel, ...]:
    return tuple(sorted(levels, key=lambda level: level.price, reverse=descending))


def _apply_updates(book: dict[float, float], updates: tuple[OrderBookLevel, ...]) -> list[str]:
    reasons: list[str] = []
    seen: set[float] = set()
    for update in updates:
        if update.price in seen:
            reasons.append("order_book:duplicate_update_price")
            continue
        seen.add(update.price)
        if update.quantity == 0.0:
            if update.price not in book:
                reasons.append("order_book:delete_missing_level")
            else:
                del book[update.price]
        else:
            book[update.price] = update.quantity
    return reasons


def _book_checksum(bids: tuple[OrderBookLevel, ...], asks: tuple[OrderBookLevel, ...]) -> str:
    payload = "|".join(
        [*(f"B:{level.price:.12g}:{level.quantity:.12g}" for level in bids)]
        + [*(f"A:{level.price:.12g}:{level.quantity:.12g}" for level in asks)]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rejected(
    reasons: tuple[str, ...],
    *,
    state: OrderBookState | None,
    resync_required: bool = False,
    gap_detected: bool = False,
) -> OrderBookApplyResult:
    return OrderBookApplyResult(
        applied=False,
        state=state,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        resync_required=resync_required,
        gap_detected=gap_detected,
    )


def _requires_resync(reasons: tuple[str, ...]) -> bool:
    return any(reason in reasons for reason in _GAP_REASONS) or any(
        reason
        in {
            "order_book:checksum_mismatch",
            "order_book:crossed",
            "order_book:empty_side",
            "order_book:delete_missing_level",
        }
        for reason in reasons
    )


def _validate_state_shape(state: OrderBookState) -> None:
    reasons = _state_content_rejection_reasons(state)
    if reasons:
        raise OrderBookReconstructionError(";".join(reasons))
    if not isinstance(state.healthy, bool):
        raise OrderBookReconstructionError("healthy must be a boolean")
    if not isinstance(state.rejection_reasons, tuple) or any(
        not isinstance(reason, str) or not reason for reason in state.rejection_reasons
    ):
        raise OrderBookReconstructionError("rejection_reasons must be a tuple of non-empty strings")


def _finite_positive(value: object) -> bool:
    return (
        isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value)) and value > 0.0
    )


def _finite_non_negative(value: object) -> bool:
    return (
        isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value)) and value >= 0.0
    )


def _venue_id_from_payload(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise OrderBookReconstructionError("venue_id is unsupported") from exc
    raise OrderBookReconstructionError("venue_id is malformed")


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise OrderBookReconstructionError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OrderBookReconstructionError(f"{field_name} must be a non-negative integer")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise OrderBookReconstructionError(f"{field_name} must be a positive integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise OrderBookReconstructionError(f"{field_name} must be a boolean")
    return value


def _sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, tuple | list):
        raise OrderBookReconstructionError(f"{field_name} must be a sequence")
    return tuple(value)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise OrderBookReconstructionError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise OrderBookReconstructionError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "OrderBookApplyResult",
    "OrderBookReconstructionError",
    "OrderBookState",
    "apply_order_book_delta",
    "build_order_book_state_from_snapshot",
    "order_book_state_from_dict",
    "order_book_state_ready",
    "order_book_state_rejection_reasons",
    "order_book_state_to_dict",
]
