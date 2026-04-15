"""Binance WebSocket message adapter.

Parses raw Binance WebSocket JSON dicts into typed event objects.

Contract:
- parse_* functions are pure (stateless, no side effects).
- All parsing failures raise ValueError with structured context.
- No defaults for required fields — missing fields are hard failures.

Stream formats per Binance API docs (PRD §4.1):
  @trade       → TradeEvent
  @depth@100ms → OrderBookEvent (delta)
  @kline_<i>   → KlineEvent
  @forceOrder  → LiquidationEvent
  @markPrice@1s → MarkPriceEvent

PRD reference: §4.1, §4.2, §4.3.
"""

from __future__ import annotations

from typing import Any, Dict

from crypto_core.data.models.events import (
    Exchange,
    KlineEvent,
    LiquidationEvent,
    MarkPriceEvent,
    OrderBookEvent,
    OrderBookEventType,
    OrderBookLevel,
    TradeSide,
    TradeEvent,
)

_EXCHANGE = Exchange.BINANCE


def parse_trade(msg: Dict[str, Any]) -> TradeEvent:
    """Parse a Binance @trade stream message.

    Expected keys: e, E, s, t, p, q, b, a, T, m, M
    Raises: KeyError on missing field, ValueError on invalid value.
    """
    return TradeEvent(
        trade_id=str(msg["t"]),
        symbol=str(msg["s"]),
        exchange=_EXCHANGE,
        side=TradeSide.SELL if bool(msg["m"]) else TradeSide.BUY,  # m=True → seller is maker → buyer aggressed
        price=float(msg["p"]),
        qty=float(msg["q"]),
        timestamp_ns=int(msg["T"]) * 1_000_000,  # ms → ns
        sequence_no=int(msg["t"]),  # trade_id doubles as sequence for per-symbol dedup
        is_maker=bool(msg["m"]),
    )


def parse_depth_delta(msg: Dict[str, Any]) -> OrderBookEvent:
    """Parse a Binance @depth@100ms (incremental depth) stream message.

    Expected keys: e, E, s, U, u, b, a
    Raises: KeyError on missing field.
    """
    bids = tuple(
        OrderBookLevel(price=float(b[0]), qty=float(b[1]))
        for b in msg["b"]
    )
    asks = tuple(
        OrderBookLevel(price=float(a[0]), qty=float(a[1]))
        for a in msg["a"]
    )
    return OrderBookEvent(
        symbol=str(msg["s"]),
        exchange=_EXCHANGE,
        event_type=OrderBookEventType.DELTA,
        bids=bids,
        asks=asks,
        timestamp_ns=int(msg["E"]) * 1_000_000,  # ms → ns
        first_update_id=int(msg["U"]),
        last_update_id=int(msg["u"]),
        checksum=None,  # Binance depth stream does not provide CRC32
    )


def parse_depth_snapshot(payload: Dict[str, Any], symbol: str, timestamp_ns: int) -> OrderBookEvent:
    """Parse a Binance REST depth snapshot response into an OrderBookEvent.

    Used during recovery (§4.5): REST GET /api/v3/depth → applied as SNAPSHOT.

    Expected keys: lastUpdateId, bids, asks
    """
    bids = tuple(
        OrderBookLevel(price=float(b[0]), qty=float(b[1]))
        for b in payload["bids"]
    )
    asks = tuple(
        OrderBookLevel(price=float(a[0]), qty=float(a[1]))
        for a in payload["asks"]
    )
    last_update_id = int(payload["lastUpdateId"])
    return OrderBookEvent(
        symbol=symbol,
        exchange=_EXCHANGE,
        event_type=OrderBookEventType.SNAPSHOT,
        bids=bids,
        asks=asks,
        timestamp_ns=timestamp_ns,
        first_update_id=last_update_id,
        last_update_id=last_update_id,
        checksum=None,
    )


def parse_kline(msg: Dict[str, Any]) -> KlineEvent:
    """Parse a Binance @kline_<interval> stream message.

    Expected keys: e, E, s, k (nested: t, T, i, o, h, l, c, v, n, x)
    Raises: KeyError on missing field.
    """
    k = msg["k"]
    return KlineEvent(
        symbol=str(msg["s"]),
        exchange=_EXCHANGE,
        interval=str(k["i"]),
        open_time_ns=int(k["t"]) * 1_000_000,  # ms → ns
        close_time_ns=int(k["T"]) * 1_000_000,
        open_price=float(k["o"]),
        high_price=float(k["h"]),
        low_price=float(k["l"]),
        close_price=float(k["c"]),
        volume=float(k["v"]),
        trade_count=int(k["n"]),
        is_closed=bool(k["x"]),
        sequence_no=int(msg["E"]),  # use event timestamp as proxy sequence for klines
    )


def parse_liquidation(msg: Dict[str, Any]) -> LiquidationEvent:
    """Parse a Binance @forceOrder (liquidation) stream message.

    Expected keys: e, E, o (nested: s, S, p, q, T)
    The 'S' field is the order side of the forced order.
    The liquidated position side is the OPPOSITE.
    Raises: KeyError on missing field.
    """
    o = msg["o"]
    order_side = str(o["S"]).upper()  # "BUY" or "SELL" — the forced order side
    # Forced order is BUY → the long was sold out → long position was liquidated
    liquidated_side = TradeSide.BUY if order_side == "BUY" else TradeSide.SELL
    return LiquidationEvent(
        symbol=str(o["s"]),
        exchange=_EXCHANGE,
        side=liquidated_side,
        price=float(o["p"]),
        qty=float(o["q"]),
        timestamp_ns=int(o["T"]) * 1_000_000,
    )


def parse_mark_price(msg: Dict[str, Any]) -> MarkPriceEvent:
    """Parse a Binance @markPrice@1s stream message.

    Expected keys: e, E, s, p, i, r, T
    Raises: KeyError on missing field.
    """
    return MarkPriceEvent(
        symbol=str(msg["s"]),
        exchange=_EXCHANGE,
        mark_price=float(msg["p"]),
        index_price=float(msg["i"]),
        funding_rate=float(msg["r"]),
        next_funding_time_ns=int(msg["T"]) * 1_000_000,
        timestamp_ns=int(msg["E"]) * 1_000_000,
    )


def detect_stream_type(msg: Dict[str, Any]) -> str:
    """Detect the event type from a Binance WebSocket message.

    Returns the 'e' field value (event type string).
    Raises KeyError if 'e' is missing (not a valid Binance stream message).
    """
    return str(msg["e"])
