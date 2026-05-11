"""Typed event models for the crypto data layer.

All event types are immutable dataclasses (frozen=True).
Every field is required — no optional fields with defaults.
Determinism guarantee: identical raw input → identical event instance.

PRD reference: §4.1 (WebSocket streams), §4.2 (order book), §4.3 (trade stream).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Exchange(str, Enum):
    """Supported exchanges per PRD §0.2."""

    BINANCE = "binance"
    BYBIT = "bybit"


class TradeSide(str, Enum):
    """Aggressor side of a trade."""

    BUY = "buy"
    SELL = "sell"


class OrderBookEventType(str, Enum):
    """Whether the OB event replaces or patches the local book."""

    SNAPSHOT = "snapshot"
    DELTA = "delta"


class StreamType(str, Enum):
    """WebSocket stream categories per PRD §4.1."""

    TRADE = "trade"
    ORDER_BOOK = "order_book"
    KLINE = "kline"
    LIQUIDATION = "liquidation"
    MARK_PRICE = "mark_price"
    FUNDING_RATE = "funding_rate"
    TICKER = "ticker"


@dataclass(frozen=True)
class TradeEvent:
    """Immutable single-trade tick event.

    Determinism: all fields required; no defaults.
    Dedup key: (exchange, symbol, trade_id).
    Sequence integrity: validated by SequenceTracker on stream_key.
    """

    trade_id: str
    symbol: str
    exchange: Exchange
    side: TradeSide
    price: float
    qty: float
    timestamp_ns: int  # nanoseconds since epoch (UTC)
    sequence_no: int
    is_maker: bool  # True = buyer is market maker


@dataclass(frozen=True)
class OrderBookLevel:
    """Single price level in the order book. Immutable."""

    price: float
    qty: float  # qty == 0 means remove this level (delta semantics)


@dataclass(frozen=True)
class OrderBookEvent:
    """Immutable order book update event (snapshot or delta).

    Snapshot: full replacement of local book.
    Delta: incremental patch applied in sequence_no order.

    Sequence rule (Binance §4.2):
      - For deltas: first_update_id must equal last_update_id_of_prev_event + 1.
    """

    symbol: str
    exchange: Exchange
    event_type: OrderBookEventType
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    timestamp_ns: int
    first_update_id: int  # U field (Binance), start of this delta's sequence range
    last_update_id: int  # u field (Binance), end of this delta's sequence range
    checksum: int | None  # CRC32 (None if exchange does not provide)


@dataclass(frozen=True)
class KlineEvent:
    """Immutable kline / candlestick event.

    is_closed == True when the bar period has ended (final bar).
    is_closed == False for in-progress bar updates.
    """

    symbol: str
    exchange: Exchange
    interval: str  # e.g. "1m", "5m", "1h"
    open_time_ns: int
    close_time_ns: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    trade_count: int
    is_closed: bool
    sequence_no: int


@dataclass(frozen=True)
class LiquidationEvent:
    """Immutable forced liquidation event (Binance forceOrder stream).

    side: the side that was liquidated (not the forced order direction).
    PRD reference: §1.3 Liquidation Intelligence System.
    """

    symbol: str
    exchange: Exchange
    side: TradeSide  # side of the position that was liquidated
    price: float
    qty: float
    timestamp_ns: int


@dataclass(frozen=True)
class MarkPriceEvent:
    """Immutable mark price + funding rate event.

    PRD reference: §1.9 Funding Rate Mean-Reversion.
    funding_rate: per-8h settlement rate.
    """

    symbol: str
    exchange: Exchange
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_time_ns: int
    timestamp_ns: int


# Convenience union type used in EventRouter dispatch
AnyEvent = object  # narrowed via isinstance checks in handlers
