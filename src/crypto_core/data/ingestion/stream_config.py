"""Stream configuration and URL builders for Binance Futures and Bybit V5.

Centralises all exchange-specific WebSocket endpoint constants and
subscription-building logic in one auditable location.

PRD reference: §4.1 WebSocket Architecture.
"""

from __future__ import annotations

# ── Binance Futures ──────────────────────────────────────────────────────────

BINANCE_FUTURES_WS_BASE: str = "wss://fstream.binance.com/stream"

# Standard live-like paper runtime streams (PRD §4.1 + §1.3 + §1.9).
BINANCE_STANDARD_STREAMS: list[str] = [
    "trade",  # §4.3  — trade tick stream
    "depth@100ms",  # §4.2  — order book delta (100ms)
    "kline_1m",  # §4.1  — 1-minute OHLCV
    "forceOrder",  # §1.3  — liquidation intelligence
    "markPrice@1s",  # §1.9  — mark price + funding rate (1s)
]


def build_binance_futures_url(
    symbol: str,
    stream_types: list[str] | None = None,
) -> str:
    """Build a Binance Futures combined WebSocket stream URL.

    Args:
        symbol:       Uppercase instrument symbol, e.g. "BTCUSDT".
        stream_types: List of stream suffixes, e.g. ["trade", "depth@100ms"].
                      Defaults to BINANCE_STANDARD_STREAMS.

    Returns:
        Combined stream URL.
        Example:
          build_binance_futures_url("BTCUSDT") →
          "wss://fstream.binance.com/stream?streams=btcusdt@trade/btcusdt@depth@100ms/..."

    Raises:
        ValueError: if symbol is empty or stream_types is an empty list.
    """
    if not symbol:
        raise ValueError("symbol must be non-empty")
    streams = stream_types if stream_types is not None else BINANCE_STANDARD_STREAMS
    if not streams:
        raise ValueError("stream_types must contain at least one stream")
    sym = symbol.lower()
    stream_string = "/".join(f"{sym}@{st}" for st in streams)
    return f"{BINANCE_FUTURES_WS_BASE}?streams={stream_string}"


# ── Bybit V5 ─────────────────────────────────────────────────────────────────

BYBIT_LINEAR_WS_BASE: str = "wss://stream.bybit.com/v5/public/linear"

# Standard Bybit V5 topic prefixes for live-like paper runtime (PRD §4.1 secondary).
BYBIT_STANDARD_TOPICS: list[str] = [
    "publicTrade",  # §4.3  — trade tick stream
    "orderbook.50",  # §4.2  — order book (50 levels, snapshot + delta)
    "kline.1",  # §4.1  — 1-minute OHLCV
    "liquidation",  # §1.3  — liquidation intelligence
    "tickers",  # §1.9  — mark price + funding rate (inside ticker)
]


def build_bybit_subscribe_msg(
    symbol: str,
    topics: list[str] | None = None,
) -> dict:
    """Build a Bybit V5 subscribe message for the given symbol.

    Args:
        symbol: Uppercase instrument symbol, e.g. "BTCUSDT".
        topics: List of Bybit V5 topic prefixes.
                Defaults to BYBIT_STANDARD_TOPICS.

    Returns:
        dict suitable for json.dumps and WebSocketClient.send().
        Example: {"op": "subscribe", "args": ["publicTrade.BTCUSDT", ...]}

    Raises:
        ValueError: if symbol is empty or topics is an empty list.
    """
    if not symbol:
        raise ValueError("symbol must be non-empty")
    topic_list = topics if topics is not None else BYBIT_STANDARD_TOPICS
    if not topic_list:
        raise ValueError("topics must contain at least one topic")
    args = [f"{t}.{symbol}" for t in topic_list]
    return {"op": "subscribe", "args": args}
