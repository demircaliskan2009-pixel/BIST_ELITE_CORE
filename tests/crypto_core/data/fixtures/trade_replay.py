"""TradeReplay — deterministic trade stream replay fixture.

Generates a reproducible sequence of TradeEvent objects.
Used for testing TradeStreamProcessor, OHLCVBuilder, and DataValidator.

All factory functions are pure (given the same arguments, produce the same events).
"""

from __future__ import annotations

from crypto_core.data.models.events import Exchange, TradeEvent, TradeSide

# Default test parameters.
_DEFAULT_SYMBOL = "BTCUSDT"
_DEFAULT_EXCHANGE = Exchange.BINANCE
_DEFAULT_START_NS = 1_700_000_000_000_000_000  # 2023-11-14T22:13:20Z UTC
_DEFAULT_TRADE_INTERVAL_NS = 100_000_000  # 100ms between trades


def make_trade(
    trade_id: str,
    symbol: str = _DEFAULT_SYMBOL,
    exchange: Exchange = _DEFAULT_EXCHANGE,
    price: float = 50_000.0,
    qty: float = 0.01,
    timestamp_ns: int = _DEFAULT_START_NS,
    sequence_no: int = 1,
    side: TradeSide = TradeSide.BUY,
    is_maker: bool = False,
) -> TradeEvent:
    """Factory for a single TradeEvent with explicit parameters."""
    return TradeEvent(
        trade_id=trade_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        price=price,
        qty=qty,
        timestamp_ns=timestamp_ns,
        sequence_no=sequence_no,
        is_maker=is_maker,
    )


def make_trade_sequence(
    count: int,
    symbol: str = _DEFAULT_SYMBOL,
    exchange: Exchange = _DEFAULT_EXCHANGE,
    start_price: float = 50_000.0,
    price_step: float = 1.0,
    qty: float = 0.01,
    start_ns: int = _DEFAULT_START_NS,
    interval_ns: int = _DEFAULT_TRADE_INTERVAL_NS,
    start_sequence: int = 1,
    side: TradeSide = TradeSide.BUY,
) -> list[TradeEvent]:
    """Generate a deterministic sequence of count TradeEvents.

    Each trade increments: trade_id, sequence_no, timestamp_ns, and price.
    Identical arguments always produce identical output (pure function).
    """
    events: list[TradeEvent] = []
    for i in range(count):
        trade_id = str(start_sequence + i)
        events.append(
            TradeEvent(
                trade_id=trade_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                price=start_price + i * price_step,
                qty=qty,
                timestamp_ns=start_ns + i * interval_ns,
                sequence_no=start_sequence + i,
                is_maker=False,
            )
        )
    return events


def make_duplicate_trade(base: TradeEvent) -> TradeEvent:
    """Return an exact copy of base (same trade_id).

    Used to test deduplication in TradeStreamProcessor.
    """
    return base


def make_out_of_order_trade(base: TradeEvent, earlier_ns: int) -> TradeEvent:
    """Return a copy of base with an earlier timestamp and lower sequence_no.

    Used to test out-of-order rejection in DataValidator.
    """
    return TradeEvent(
        trade_id=str(int(base.trade_id) - 1),
        symbol=base.symbol,
        exchange=base.exchange,
        side=base.side,
        price=base.price,
        qty=base.qty,
        timestamp_ns=earlier_ns,
        sequence_no=base.sequence_no - 1,
        is_maker=base.is_maker,
    )
