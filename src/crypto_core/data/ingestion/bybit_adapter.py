"""Bybit WebSocket message adapter.

Parses raw Bybit V5 WebSocket JSON dicts into typed event objects.

Bybit V5 stream formats (PRD §4.1 — secondary exchange):
  topic: "publicTrade.<symbol>"       → TradeEvent
  topic: "orderbook.1.<symbol>"       → OrderBookEvent (snapshot or delta)
  topic: "orderbook.50.<symbol>"      → OrderBookEvent (snapshot or delta)
  topic: "kline.<interval>.<symbol>"  → KlineEvent
  topic: "liquidation.<symbol>"       → LiquidationEvent

PRD reference: §4.1 (Bybit as secondary), §0.2 (Bybit as failover execution).
"""

from __future__ import annotations

from typing import Any, Dict

from crypto_core.data.models.events import (
    Exchange,
    KlineEvent,
    LiquidationEvent,
    OrderBookEvent,
    OrderBookEventType,
    OrderBookLevel,
    TradeSide,
    TradeEvent,
)

_EXCHANGE = Exchange.BYBIT


def parse_trade(data: Dict[str, Any], topic: str) -> TradeEvent:
    """Parse a Bybit publicTrade.<symbol> message payload entry.

    data: single entry from the 'data' array of the WS message.
    topic: used to extract symbol when not present in data entry.
    Raises: KeyError on missing field.
    """
    symbol = str(data.get("s") or topic.split(".")[-1])
    side_str = str(data.get("S", "")).upper()
    side = TradeSide.BUY if side_str == "BUY" else TradeSide.SELL
    return TradeEvent(
        trade_id=str(data["i"]),
        symbol=symbol,
        exchange=_EXCHANGE,
        side=side,
        price=float(data["p"]),
        qty=float(data["v"]),
        timestamp_ns=int(data["T"]) * 1_000_000,
        sequence_no=int(data["i"]),
        is_maker=bool(data.get("m", False)),
    )


def parse_orderbook(msg: Dict[str, Any]) -> OrderBookEvent:
    """Parse a Bybit orderbook.<depth>.<symbol> message.

    Bybit sends 'snapshot' type for initial and 'delta' for incremental.
    msg keys: topic, type, ts, data (with s, b, a, u, seq)
    Raises: KeyError on missing field.
    """
    data = msg["data"]
    event_type_str = str(msg.get("type", "delta")).lower()
    event_type = OrderBookEventType.SNAPSHOT if event_type_str == "snapshot" else OrderBookEventType.DELTA

    bids = tuple(
        OrderBookLevel(price=float(b[0]), qty=float(b[1]))
        for b in data.get("b", [])
    )
    asks = tuple(
        OrderBookLevel(price=float(a[0]), qty=float(a[1]))
        for a in data.get("a", [])
    )
    update_id = int(data.get("u", 0))
    seq = int(data.get("seq", update_id))
    return OrderBookEvent(
        symbol=str(data["s"]),
        exchange=_EXCHANGE,
        event_type=event_type,
        bids=bids,
        asks=asks,
        timestamp_ns=int(msg["ts"]) * 1_000_000,
        first_update_id=seq,
        last_update_id=seq,
        checksum=data.get("cts"),  # Bybit provides checksum in some streams
    )


def parse_kline(data: Dict[str, Any], symbol: str, interval: str) -> KlineEvent:
    """Parse a single Bybit kline entry from data array.

    data: single entry from the 'data' array of the WS message.
    Raises: KeyError on missing field.
    """
    return KlineEvent(
        symbol=symbol,
        exchange=_EXCHANGE,
        interval=interval,
        open_time_ns=int(data["start"]) * 1_000_000,
        close_time_ns=int(data["end"]) * 1_000_000,
        open_price=float(data["open"]),
        high_price=float(data["high"]),
        low_price=float(data["low"]),
        close_price=float(data["close"]),
        volume=float(data["volume"]),
        trade_count=int(data.get("turnover", 0)),
        is_closed=bool(data.get("confirm", False)),
        sequence_no=int(data["start"]),
    )


def parse_liquidation(data: Dict[str, Any]) -> LiquidationEvent:
    """Parse a Bybit liquidation.<symbol> message payload entry.

    data: single entry from the 'data' field.
    'side' field: 'Buy' = long liquidated, 'Sell' = short liquidated.
    Raises: KeyError on missing field.
    """
    side_str = str(data.get("side", "")).capitalize()
    liquidated_side = TradeSide.BUY if side_str == "Buy" else TradeSide.SELL
    return LiquidationEvent(
        symbol=str(data["symbol"]),
        exchange=_EXCHANGE,
        side=liquidated_side,
        price=float(data["price"]),
        qty=float(data["size"]),
        timestamp_ns=int(data["updatedTime"]) * 1_000_000,
    )
