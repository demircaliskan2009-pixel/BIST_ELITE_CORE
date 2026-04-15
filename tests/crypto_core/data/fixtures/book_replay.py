"""OrderBookReplay — deterministic order book snapshot + delta replay fixture.

Generates reproducible OrderBookEvent sequences for testing OrderBookManager.
All factory functions are pure.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from crypto_core.data.models.events import (
    Exchange,
    OrderBookEvent,
    OrderBookEventType,
    OrderBookLevel,
)

_DEFAULT_SYMBOL = "BTCUSDT"
_DEFAULT_EXCHANGE = Exchange.BINANCE
_DEFAULT_START_NS = 1_700_000_000_000_000_000


def make_snapshot(
    symbol: str = _DEFAULT_SYMBOL,
    exchange: Exchange = _DEFAULT_EXCHANGE,
    bids: Optional[List[Tuple[float, float]]] = None,
    asks: Optional[List[Tuple[float, float]]] = None,
    last_update_id: int = 100,
    timestamp_ns: int = _DEFAULT_START_NS,
) -> OrderBookEvent:
    """Build a well-formed SNAPSHOT OrderBookEvent.

    Defaults to a simple 3-level book around 50,000.
    """
    default_bids: List[Tuple[float, float]] = bids if bids is not None else [
        (49_999.0, 1.0),
        (49_998.0, 2.0),
        (49_997.0, 3.0),
    ]
    default_asks: List[Tuple[float, float]] = asks if asks is not None else [
        (50_001.0, 1.0),
        (50_002.0, 2.0),
        (50_003.0, 3.0),
    ]
    return OrderBookEvent(
        symbol=symbol,
        exchange=exchange,
        event_type=OrderBookEventType.SNAPSHOT,
        bids=tuple(OrderBookLevel(price=p, qty=q) for p, q in default_bids),
        asks=tuple(OrderBookLevel(price=p, qty=q) for p, q in default_asks),
        timestamp_ns=timestamp_ns,
        first_update_id=last_update_id,
        last_update_id=last_update_id,
        checksum=None,
    )


def make_delta(
    symbol: str = _DEFAULT_SYMBOL,
    exchange: Exchange = _DEFAULT_EXCHANGE,
    bids: Optional[List[Tuple[float, float]]] = None,
    asks: Optional[List[Tuple[float, float]]] = None,
    first_update_id: int = 101,
    last_update_id: int = 101,
    timestamp_ns: int = _DEFAULT_START_NS + 100_000_000,
    checksum: Optional[int] = None,
) -> OrderBookEvent:
    """Build a well-formed DELTA OrderBookEvent.

    qty=0.0 entries represent level removals (standard delta semantics).
    """
    return OrderBookEvent(
        symbol=symbol,
        exchange=exchange,
        event_type=OrderBookEventType.DELTA,
        bids=tuple(OrderBookLevel(price=p, qty=q) for p, q in (bids or [])),
        asks=tuple(OrderBookLevel(price=p, qty=q) for p, q in (asks or [])),
        timestamp_ns=timestamp_ns,
        first_update_id=first_update_id,
        last_update_id=last_update_id,
        checksum=checksum,
    )


def make_delta_sequence(
    count: int,
    symbol: str = _DEFAULT_SYMBOL,
    exchange: Exchange = _DEFAULT_EXCHANGE,
    base_update_id: int = 101,
    start_ns: int = _DEFAULT_START_NS + 100_000_000,
    interval_ns: int = 100_000_000,  # 100ms
) -> List[OrderBookEvent]:
    """Generate a gap-free sequence of empty delta events (no level changes).

    Useful for testing OrderBookManager sequence tracking without altering prices.
    """
    events: List[OrderBookEvent] = []
    for i in range(count):
        uid = base_update_id + i
        events.append(
            OrderBookEvent(
                symbol=symbol,
                exchange=exchange,
                event_type=OrderBookEventType.DELTA,
                bids=(),
                asks=(),
                timestamp_ns=start_ns + i * interval_ns,
                first_update_id=uid,
                last_update_id=uid,
                checksum=None,
            )
        )
    return events
