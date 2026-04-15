"""Stateless validation rules for data events.

All functions are pure (no side effects, no state).
All failures raise ValidationError — never return False, never log-and-continue.

Usage: called by DataValidator; not called directly by processors.

PRD reference: §4.2, §4.3, §4.4 (NT-D01–NT-D05 halt conditions).
"""

from __future__ import annotations

from crypto_core.data.models.events import OrderBookEvent, TradeEvent
from crypto_core.data.validation.errors import ValidationError, ValidationErrorCode

# ──────────────────────────────────────────────────────────────────
# Trade event rules
# ──────────────────────────────────────────────────────────────────


def validate_trade_fields(event: TradeEvent) -> None:
    """Validate required fields on a TradeEvent.

    Raises ValidationError on any field violation.
    """
    if not event.trade_id:
        raise ValidationError(
            ValidationErrorCode.MISSING_FIELD,
            "TradeEvent.trade_id is empty",
            {"symbol": event.symbol, "exchange": event.exchange},
        )
    if not event.symbol:
        raise ValidationError(
            ValidationErrorCode.MISSING_FIELD,
            "TradeEvent.symbol is empty",
            {"trade_id": event.trade_id},
        )
    if event.price <= 0.0:
        raise ValidationError(
            ValidationErrorCode.INVALID_PRICE,
            f"TradeEvent price {event.price} <= 0 for trade_id={event.trade_id}",
            {"trade_id": event.trade_id, "price": event.price},
        )
    if event.qty < 0.0:
        raise ValidationError(
            ValidationErrorCode.INVALID_QTY,
            f"TradeEvent qty {event.qty} < 0 for trade_id={event.trade_id}",
            {"trade_id": event.trade_id, "qty": event.qty},
        )
    if event.timestamp_ns <= 0:
        raise ValidationError(
            ValidationErrorCode.MISSING_FIELD,
            f"TradeEvent timestamp_ns {event.timestamp_ns} is not positive",
            {"trade_id": event.trade_id},
        )


def validate_trade_clock(
    event: TradeEvent,
    wall_clock_ns: int,
    drift_threshold_ns: int = 5_000_000_000,
) -> None:
    """Detect unreasonable clock drift between event timestamp and wall clock.

    Default drift threshold: 5 seconds.
    Raises ValidationError(CLOCK_DRIFT) if |event.timestamp_ns - wall_clock_ns| > threshold.
    """
    drift = abs(event.timestamp_ns - wall_clock_ns)
    if drift > drift_threshold_ns:
        raise ValidationError(
            ValidationErrorCode.CLOCK_DRIFT,
            f"TradeEvent clock drift {drift / 1e9:.3f}s exceeds threshold "
            f"{drift_threshold_ns / 1e9:.3f}s for trade_id={event.trade_id}",
            {
                "trade_id": event.trade_id,
                "event_ts_ns": event.timestamp_ns,
                "wall_clock_ns": wall_clock_ns,
                "drift_ns": drift,
            },
        )


# ──────────────────────────────────────────────────────────────────
# Order book event rules
# ──────────────────────────────────────────────────────────────────


def validate_order_book_fields(event: OrderBookEvent) -> None:
    """Validate required fields on an OrderBookEvent.

    Raises ValidationError on any field violation.
    """
    if not event.symbol:
        raise ValidationError(
            ValidationErrorCode.MISSING_FIELD,
            "OrderBookEvent.symbol is empty",
            {"exchange": str(event.exchange)},
        )
    if event.timestamp_ns <= 0:
        raise ValidationError(
            ValidationErrorCode.MISSING_FIELD,
            f"OrderBookEvent timestamp_ns {event.timestamp_ns} is not positive",
            {"symbol": event.symbol},
        )
    if event.last_update_id < event.first_update_id:
        raise ValidationError(
            ValidationErrorCode.BOOK_INCONSISTENCY,
            f"OrderBookEvent last_update_id {event.last_update_id} < first_update_id {event.first_update_id}",
            {"symbol": event.symbol, "first": event.first_update_id, "last": event.last_update_id},
        )
    for level in event.bids:
        if level.price <= 0.0:
            raise ValidationError(
                ValidationErrorCode.INVALID_PRICE,
                f"OrderBook bid level price {level.price} <= 0 for {event.symbol}",
                {"symbol": event.symbol, "price": level.price},
            )
        if level.qty < 0.0:
            raise ValidationError(
                ValidationErrorCode.INVALID_QTY,
                f"OrderBook bid level qty {level.qty} < 0 for {event.symbol}",
                {"symbol": event.symbol, "qty": level.qty},
            )
    for level in event.asks:
        if level.price <= 0.0:
            raise ValidationError(
                ValidationErrorCode.INVALID_PRICE,
                f"OrderBook ask level price {level.price} <= 0 for {event.symbol}",
                {"symbol": event.symbol, "price": level.price},
            )
        if level.qty < 0.0:
            raise ValidationError(
                ValidationErrorCode.INVALID_QTY,
                f"OrderBook ask level qty {level.qty} < 0 for {event.symbol}",
                {"symbol": event.symbol, "qty": level.qty},
            )
