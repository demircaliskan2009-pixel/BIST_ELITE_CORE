"""Phase 7A — paper-live parity tests.

Validates the concrete stream orchestration layer end-to-end using the
deterministic WebSocketSimulator in place of a live exchange connection.

Coverage:
1. stream_config URL / subscription builders
2. Binance adapter: all 5 event types (trade, depth, kline, forceOrder, markPrice)
3. Bybit adapter: all 4 event types (trade, orderbook, kline, liquidation)
4. DataIngestor full pipeline — Binance: register → start → events collected
5. DataIngestor full pipeline — Bybit: register → start → events collected
6. DataIngestor multi-feed: Binance + Bybit co-existing, events attributed correctly
7. Recovery gate: events blocked during SNAPSHOTTING / REPLAYING / VALIDATING / FAILED
8. Funding + liquidation wiring: MarkPriceEvent and LiquidationEvent emitted correctly
9. Determinism: same message sequence → identical event sequence (paper-live parity)
10. DataIngestor recovery integration: RecoveryManager created on register_feed

PRD reference: §4.1, §4.2, §4.3, §4.5, §1.3, §1.9.
"""

from __future__ import annotations

import pytest

from crypto_core.data.ingestion.data_ingestor import DataIngestor
from crypto_core.data.ingestion.stream_config import (
    BINANCE_STANDARD_STREAMS,
    BYBIT_STANDARD_TOPICS,
    build_binance_futures_url,
    build_bybit_subscribe_msg,
)
from crypto_core.data.ingestion.websocket_client import WebSocketConfig
from crypto_core.data.models.events import (
    Exchange,
    KlineEvent,
    LiquidationEvent,
    MarkPriceEvent,
    OrderBookEvent,
    OrderBookEventType,
    TradeEvent,
    TradeSide,
)
from crypto_core.data.models.feed_state import ConnectionState, RecoveryState
from tests.crypto_core.data.fixtures.ws_simulator import WebSocketSimulator

# ── Shared raw message factories ──────────────────────────────────────────────

_TS_MS = 1_700_000_000_000  # 2023-11-14T22:13:20Z in ms


def _binance_trade(
    symbol: str = "BTCUSDT",
    trade_id: int = 1,
    price: str = "50000.00",
    qty: str = "0.01",
    ts_ms: int = _TS_MS,
    is_maker: bool = False,
) -> dict:
    return {
        "e": "trade",
        "E": ts_ms,
        "s": symbol,
        "t": trade_id,
        "p": price,
        "q": qty,
        "b": 100,
        "a": 200,
        "T": ts_ms,
        "m": is_maker,
        "M": True,
    }


def _binance_depth(
    symbol: str = "BTCUSDT",
    first_update_id: int = 100,
    last_update_id: int = 101,
    ts_ms: int = _TS_MS,
) -> dict:
    return {
        "e": "depthUpdate",
        "E": ts_ms,
        "s": symbol,
        "U": first_update_id,
        "u": last_update_id,
        "b": [["49999.0", "1.0"]],
        "a": [["50001.0", "0.5"]],
    }


def _binance_kline(
    symbol: str = "BTCUSDT",
    ts_ms: int = _TS_MS,
    interval: str = "1m",
    is_closed: bool = True,
) -> dict:
    return {
        "e": "kline",
        "E": ts_ms,
        "s": symbol,
        "k": {
            "t": ts_ms,
            "T": ts_ms + 60_000,
            "i": interval,
            "o": "49900.00",
            "h": "50100.00",
            "l": "49800.00",
            "c": "50000.00",
            "v": "100.0",
            "n": 500,
            "x": is_closed,
        },
    }


def _binance_force_order(
    symbol: str = "BTCUSDT",
    ts_ms: int = _TS_MS,
    side: str = "BUY",
    price: str = "48000.0",
    qty: str = "0.5",
) -> dict:
    return {
        "e": "forceOrder",
        "E": ts_ms,
        "o": {
            "s": symbol,
            "S": side,
            "p": price,
            "q": qty,
            "T": ts_ms,
        },
    }


def _binance_mark_price(
    symbol: str = "BTCUSDT",
    ts_ms: int = _TS_MS,
    mark_price: str = "50000.00",
    index_price: str = "49999.00",
    funding_rate: str = "0.0001",
    next_funding_ts_ms: int = _TS_MS + 28_800_000,
) -> dict:
    return {
        "e": "markPriceUpdate",
        "E": ts_ms,
        "s": symbol,
        "p": mark_price,
        "i": index_price,
        "r": funding_rate,
        "T": next_funding_ts_ms,
    }


def _bybit_trade(
    symbol: str = "BTCUSDT",
    trade_id: str = "229000000001",
    price: str = "50000.00",
    qty: str = "0.01",
    ts_ms: int = _TS_MS,
    side: str = "Buy",
) -> dict:
    return {
        "topic": f"publicTrade.{symbol}",
        "type": "snapshot",
        "ts": ts_ms,
        "data": [
            {
                "i": trade_id,
                "s": symbol,
                "p": price,
                "v": qty,
                "S": side,
                "T": ts_ms,
                "m": False,
            }
        ],
    }


def _bybit_orderbook(
    symbol: str = "BTCUSDT",
    ts_ms: int = _TS_MS,
    ob_type: str = "snapshot",
) -> dict:
    return {
        "topic": f"orderbook.50.{symbol}",
        "type": ob_type,
        "ts": ts_ms,
        "data": {
            "s": symbol,
            "b": [["49999.0", "1.0"]],
            "a": [["50001.0", "0.5"]],
            "u": 100,
            "seq": 200,
        },
    }


def _bybit_kline(
    symbol: str = "BTCUSDT",
    ts_ms: int = _TS_MS,
    interval: str = "1",
    is_closed: bool = True,
) -> dict:
    return {
        "topic": f"kline.{interval}.{symbol}",
        "type": "snapshot",
        "ts": ts_ms,
        "data": [
            {
                "start": ts_ms,
                "end": ts_ms + 60_000,
                "open": "49900.0",
                "high": "50100.0",
                "low": "49800.0",
                "close": "50000.0",
                "volume": "100.0",
                "turnover": "500",
                "confirm": is_closed,
            }
        ],
    }


def _bybit_liquidation(
    symbol: str = "BTCUSDT",
    ts_ms: int = _TS_MS,
    side: str = "Buy",
    price: str = "47500.0",
    size: str = "0.3",
) -> dict:
    return {
        "topic": f"liquidation.{symbol}",
        "type": "snapshot",
        "ts": ts_ms,
        "data": [
            {
                "symbol": symbol,
                "side": side,
                "price": price,
                "size": size,
                "updatedTime": ts_ms,
            }
        ],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_binance_cfg(symbol: str = "BTCUSDT") -> WebSocketConfig:
    url = build_binance_futures_url(symbol)
    return WebSocketConfig(url=url, symbol=symbol, stream_types=BINANCE_STANDARD_STREAMS)


def _make_bybit_cfg(symbol: str = "BTCUSDT") -> WebSocketConfig:
    return WebSocketConfig(
        url="wss://stream.bybit.com/v5/public/linear",
        symbol=symbol,
        stream_types=BYBIT_STANDARD_TOPICS,
    )


def _ws_factory_from_msgs(msgs: list[dict]):
    """Return a ws_factory that always yields a WebSocketSimulator with the given msgs."""

    def factory(config: WebSocketConfig, on_message):
        return WebSocketSimulator(config=config, on_message=on_message, messages=msgs)

    return factory


# ═══════════════════════════════════════════════════════════════════════════════
# 1. stream_config builders
# ═══════════════════════════════════════════════════════════════════════════════


class TestStreamConfig:
    def test_build_binance_futures_url_default_streams(self):
        url = build_binance_futures_url("BTCUSDT")
        assert url.startswith("wss://fstream.binance.com/stream?streams=")
        assert "btcusdt@trade" in url
        assert "btcusdt@depth@100ms" in url
        assert "btcusdt@kline_1m" in url
        assert "btcusdt@forceOrder" in url
        assert "btcusdt@markPrice@1s" in url

    def test_build_binance_futures_url_custom_streams(self):
        url = build_binance_futures_url("ETHUSDT", ["trade", "kline_5m"])
        assert "ethusdt@trade" in url
        assert "ethusdt@kline_5m" in url
        assert "depth" not in url

    def test_build_binance_futures_url_lowercase_symbol(self):
        url = build_binance_futures_url("BTCUSDT")
        # Symbol must be lowercase in the stream path.
        assert "BTCUSDT" not in url
        assert "btcusdt" in url

    def test_build_binance_futures_url_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            build_binance_futures_url("")

    def test_build_binance_futures_url_empty_streams_raises(self):
        with pytest.raises(ValueError, match="stream_types"):
            build_binance_futures_url("BTCUSDT", [])

    def test_build_bybit_subscribe_msg_default_topics(self):
        msg = build_bybit_subscribe_msg("BTCUSDT")
        assert msg["op"] == "subscribe"
        assert "publicTrade.BTCUSDT" in msg["args"]
        assert "orderbook.50.BTCUSDT" in msg["args"]
        assert "kline.1.BTCUSDT" in msg["args"]
        assert "liquidation.BTCUSDT" in msg["args"]
        assert "tickers.BTCUSDT" in msg["args"]

    def test_build_bybit_subscribe_msg_custom_topics(self):
        msg = build_bybit_subscribe_msg("ETHUSDT", ["publicTrade", "orderbook.50"])
        assert msg["args"] == ["publicTrade.ETHUSDT", "orderbook.50.ETHUSDT"]

    def test_build_bybit_subscribe_msg_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            build_bybit_subscribe_msg("")

    def test_build_bybit_subscribe_msg_empty_topics_raises(self):
        with pytest.raises(ValueError, match="topics"):
            build_bybit_subscribe_msg("BTCUSDT", [])


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Binance adapter — all 5 event types via DataIngestor
# ═══════════════════════════════════════════════════════════════════════════════


class TestBinanceAdapterAllEventTypes:
    """DataIngestor + binance_adapter end-to-end, one event type at a time."""

    def _collect(self, msgs: list[dict], symbol: str = "BTCUSDT") -> list:
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_binance_cfg(symbol)
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        return received

    def test_trade_event_emitted(self):
        events = self._collect([_binance_trade()])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, TradeEvent)
        assert ev.symbol == "BTCUSDT"
        assert ev.exchange == Exchange.BINANCE
        assert ev.price == 50_000.0
        assert ev.qty == 0.01
        # m=False → buyer is NOT maker → buyer aggressed → BUY side
        assert ev.side == TradeSide.BUY

    def test_trade_maker_side(self):
        events = self._collect([_binance_trade(is_maker=True)])
        assert isinstance(events[0], TradeEvent)
        assert events[0].side == TradeSide.SELL  # m=True → seller is maker → buyer aggressed → sell

    def test_depth_update_emitted(self):
        events = self._collect([_binance_depth()])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, OrderBookEvent)
        assert ev.event_type == OrderBookEventType.DELTA
        assert ev.symbol == "BTCUSDT"
        assert ev.first_update_id == 100
        assert ev.last_update_id == 101
        assert len(ev.bids) == 1
        assert len(ev.asks) == 1

    def test_kline_closed_emitted(self):
        events = self._collect([_binance_kline(is_closed=True)])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, KlineEvent)
        assert ev.is_closed is True
        assert ev.interval == "1m"
        assert ev.open_price == 49_900.0

    def test_kline_open_emitted(self):
        events = self._collect([_binance_kline(is_closed=False)])
        assert isinstance(events[0], KlineEvent)
        assert events[0].is_closed is False

    def test_force_order_emitted(self):
        events = self._collect([_binance_force_order(side="BUY")])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, LiquidationEvent)
        # BUY forced order = long position was liquidated
        assert ev.side == TradeSide.BUY
        assert ev.symbol == "BTCUSDT"
        assert ev.price == 48_000.0

    def test_force_order_sell_side(self):
        events = self._collect([_binance_force_order(side="SELL")])
        ev = events[0]
        assert isinstance(ev, LiquidationEvent)
        assert ev.side == TradeSide.SELL

    def test_mark_price_emitted(self):
        events = self._collect([_binance_mark_price()])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, MarkPriceEvent)
        assert ev.symbol == "BTCUSDT"
        assert ev.mark_price == 50_000.0
        assert ev.funding_rate == 0.0001
        assert ev.index_price == 49_999.0

    def test_mixed_stream_all_5_events(self):
        msgs = [
            _binance_trade(),
            _binance_depth(),
            _binance_kline(),
            _binance_force_order(),
            _binance_mark_price(),
        ]
        events = self._collect(msgs)
        assert len(events) == 5
        types = [type(e) for e in events]
        assert TradeEvent in types
        assert OrderBookEvent in types
        assert KlineEvent in types
        assert LiquidationEvent in types
        assert MarkPriceEvent in types

    def test_unknown_event_type_silently_dropped(self):
        msg = {"e": "unknown_event", "s": "BTCUSDT", "E": _TS_MS}
        events = self._collect([msg])
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Bybit adapter — all 4 event types via DataIngestor
# ═══════════════════════════════════════════════════════════════════════════════


class TestBybitAdapterAllEventTypes:
    def _collect(self, msgs: list[dict], symbol: str = "BTCUSDT") -> list:
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_bybit_cfg(symbol)
        feed_key = ingestor.register_feed(cfg, Exchange.BYBIT)
        ingestor.start_feed(feed_key)
        return received

    def test_trade_event_emitted(self):
        events = self._collect([_bybit_trade()])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, TradeEvent)
        assert ev.symbol == "BTCUSDT"
        assert ev.exchange == Exchange.BYBIT
        assert ev.side == TradeSide.BUY  # "Buy"

    def test_trade_sell_side(self):
        events = self._collect([_bybit_trade(side="Sell")])
        assert events[0].side == TradeSide.SELL

    def test_orderbook_snapshot_emitted(self):
        events = self._collect([_bybit_orderbook(ob_type="snapshot")])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, OrderBookEvent)
        assert ev.event_type == OrderBookEventType.SNAPSHOT
        assert ev.exchange == Exchange.BYBIT

    def test_orderbook_delta_emitted(self):
        events = self._collect([_bybit_orderbook(ob_type="delta")])
        ev = events[0]
        assert isinstance(ev, OrderBookEvent)
        assert ev.event_type == OrderBookEventType.DELTA

    def test_kline_closed_emitted(self):
        events = self._collect([_bybit_kline(is_closed=True)])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, KlineEvent)
        assert ev.is_closed is True
        assert ev.interval == "1"

    def test_liquidation_emitted(self):
        events = self._collect([_bybit_liquidation(side="Buy")])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, LiquidationEvent)
        assert ev.exchange == Exchange.BYBIT
        assert ev.side == TradeSide.BUY
        assert ev.price == 47_500.0

    def test_liquidation_sell_side(self):
        events = self._collect([_bybit_liquidation(side="Sell")])
        assert events[0].side == TradeSide.SELL

    def test_mixed_stream_all_4_events(self):
        msgs = [
            _bybit_trade(),
            _bybit_orderbook(),
            _bybit_kline(),
            _bybit_liquidation(),
        ]
        events = self._collect(msgs)
        assert len(events) == 4
        types = {type(e) for e in events}
        assert TradeEvent in types
        assert OrderBookEvent in types
        assert KlineEvent in types
        assert LiquidationEvent in types

    def test_unknown_topic_silently_dropped(self):
        msg = {"topic": "unknownTopic.BTCUSDT", "ts": _TS_MS, "data": []}
        events = self._collect([msg])
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DataIngestor multi-feed: Binance + Bybit co-existing
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiFeedOrchestration:
    def test_binance_and_bybit_feeds_independent(self):
        binance_events: list = []
        bybit_events: list = []

        def on_event(ev: object) -> None:
            if getattr(ev, "exchange", None) == Exchange.BINANCE:
                binance_events.append(ev)
            elif getattr(ev, "exchange", None) == Exchange.BYBIT:
                bybit_events.append(ev)

        binance_msgs = [_binance_trade(), _binance_mark_price()]
        bybit_msgs = [_bybit_trade(), _bybit_liquidation()]

        def ws_factory(config: WebSocketConfig, on_message):
            if config.symbol == "BTCUSDT" and "fstream" in config.url:
                return WebSocketSimulator(config=config, on_message=on_message, messages=binance_msgs)
            return WebSocketSimulator(config=config, on_message=on_message, messages=bybit_msgs)

        ingestor = DataIngestor(on_event=on_event, ws_factory=ws_factory)

        binance_cfg = _make_binance_cfg("BTCUSDT")
        bybit_cfg = _make_bybit_cfg("BTCUSDT")

        bk = ingestor.register_feed(binance_cfg, Exchange.BINANCE)
        yk = ingestor.register_feed(bybit_cfg, Exchange.BYBIT)

        ingestor.start_feed(bk)
        ingestor.start_feed(yk)

        assert len(binance_events) == 2
        assert len(bybit_events) == 2

        for ev in binance_events:
            assert ev.exchange == Exchange.BINANCE
        for ev in bybit_events:
            assert ev.exchange == Exchange.BYBIT

    def test_feed_key_format(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs([]))
        cfg = _make_binance_cfg("BTCUSDT")
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        assert feed_key == "binance:BTCUSDT"

    def test_bybit_feed_key_format(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs([]))
        cfg = _make_bybit_cfg("ETHUSDT")
        feed_key = ingestor.register_feed(cfg, Exchange.BYBIT)
        assert feed_key == "bybit:ETHUSDT"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Recovery state gate — events blocked during active recovery
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecoveryStateGate:
    """Events must be dropped while recovery_state is SNAPSHOTTING/REPLAYING/VALIDATING/FAILED."""

    def _setup_ingestor_with_msgs(self, msgs: list[dict], symbol: str = "BTCUSDT"):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_binance_cfg(symbol)
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        return ingestor, feed_key, received

    def test_events_pass_in_ready_state(self):
        ingestor, feed_key, received = self._setup_ingestor_with_msgs([_binance_trade()])
        ingestor.start_feed(feed_key)  # sets CONNECTED + READY before connect()
        assert len(received) == 1

    def test_events_pass_in_idle_state(self):
        """IDLE = initial startup, no recovery in flight → events must pass."""
        received: list = []
        msgs = [_binance_trade()]
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        # Manually set IDLE before starting (mirrors initial state).
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.recovery_state = RecoveryState.IDLE
        state.connection_state = ConnectionState.CONNECTED
        ingestor.start_feed(feed_key)
        # start_feed sets READY before calling connect(), so events flow.
        assert len(received) == 1

    def test_events_blocked_during_snapshotting(self):
        received: list = []
        msgs = [_binance_trade()]
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        # Force SNAPSHOTTING state before replaying.
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.SNAPSHOTTING
        # Manually invoke the raw callback — events must be dropped.
        ingestor._clients[feed_key].connect()  # replays via WebSocketSimulator
        assert received == []

    def test_events_blocked_during_replaying(self):
        received: list = []
        msgs = [_binance_trade()]
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.REPLAYING
        ingestor._clients[feed_key].connect()
        assert received == []

    def test_events_blocked_during_validating(self):
        received: list = []
        msgs = [_binance_trade()]
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.VALIDATING
        ingestor._clients[feed_key].connect()
        assert received == []

    def test_events_blocked_in_failed_state(self):
        received: list = []
        msgs = [_binance_trade()]
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.FAILED
        ingestor._clients[feed_key].connect()
        assert received == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Funding + liquidation upstream wiring (PRD §1.3 + §1.9)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFundingAndLiquidationWiring:
    """Ensure MarkPriceEvent (funding) and LiquidationEvent reach on_event correctly."""

    def test_mark_price_funding_rate_correct(self):
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs([_binance_mark_price(funding_rate="0.0003")]),
        )
        feed_key = ingestor.register_feed(_make_binance_cfg(), Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, MarkPriceEvent)
        assert abs(ev.funding_rate - 0.0003) < 1e-10

    def test_mark_price_next_funding_time_correct(self):
        next_funding = _TS_MS + 8 * 3600 * 1000  # +8h in ms
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs([_binance_mark_price(next_funding_ts_ms=next_funding)]),
        )
        feed_key = ingestor.register_feed(_make_binance_cfg(), Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        ev = received[0]
        assert isinstance(ev, MarkPriceEvent)
        assert ev.next_funding_time_ns == next_funding * 1_000_000

    def test_liquidation_long_position(self):
        """BUY forced order → long position liquidated."""
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs([_binance_force_order(side="BUY", price="47000.0", qty="1.0")]),
        )
        feed_key = ingestor.register_feed(_make_binance_cfg(), Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        ev = received[0]
        assert isinstance(ev, LiquidationEvent)
        assert ev.side == TradeSide.BUY
        assert ev.price == 47_000.0
        assert ev.qty == 1.0

    def test_liquidation_short_position(self):
        """SELL forced order → short position liquidated."""
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs([_binance_force_order(side="SELL", price="55000.0", qty="0.2")]),
        )
        feed_key = ingestor.register_feed(_make_binance_cfg(), Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        ev = received[0]
        assert isinstance(ev, LiquidationEvent)
        assert ev.side == TradeSide.SELL

    def test_bybit_liquidation_buy_side(self):
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs([_bybit_liquidation(side="Buy")]),
        )
        feed_key = ingestor.register_feed(_make_bybit_cfg(), Exchange.BYBIT)
        ingestor.start_feed(feed_key)
        ev = received[0]
        assert isinstance(ev, LiquidationEvent)
        assert ev.side == TradeSide.BUY

    def test_multiple_funding_events_all_emitted(self):
        msgs = [
            _binance_mark_price(ts_ms=_TS_MS),
            _binance_mark_price(ts_ms=_TS_MS + 1000),
            _binance_mark_price(ts_ms=_TS_MS + 2000),
        ]
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs(msgs),
        )
        feed_key = ingestor.register_feed(_make_binance_cfg(), Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        assert len(received) == 3
        for ev in received:
            assert isinstance(ev, MarkPriceEvent)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Paper-live parity (determinism guarantee)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPaperLiveParity:
    """Same raw message sequence → identical typed event sequence.

    This is the paper-live parity contract: the paper runtime uses
    WebSocketSimulator with the same raw messages that would arrive from
    the live exchange, producing bit-identical typed events.
    """

    def _run_ingestor(self, msgs: list[dict], exchange: Exchange) -> list:
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs(msgs))
        if exchange == Exchange.BINANCE:
            cfg = _make_binance_cfg()
        else:
            cfg = _make_bybit_cfg()
        feed_key = ingestor.register_feed(cfg, exchange)
        ingestor.start_feed(feed_key)
        return received

    def test_binance_same_msgs_same_events_twice(self):
        msgs = [_binance_trade(trade_id=i, ts_ms=_TS_MS + i * 100) for i in range(1, 6)]
        run1 = self._run_ingestor(msgs, Exchange.BINANCE)
        run2 = self._run_ingestor(msgs, Exchange.BINANCE)
        assert len(run1) == len(run2) == 5
        for e1, e2 in zip(run1, run2):
            assert e1 == e2  # frozen dataclasses support equality

    def test_bybit_same_msgs_same_events_twice(self):
        msgs = [_bybit_trade(trade_id=str(229000000001 + i), ts_ms=_TS_MS + i * 100) for i in range(1, 4)]
        run1 = self._run_ingestor(msgs, Exchange.BYBIT)
        run2 = self._run_ingestor(msgs, Exchange.BYBIT)
        assert len(run1) == len(run2) == 3
        for e1, e2 in zip(run1, run2):
            assert e1 == e2

    def test_mixed_events_order_preserved(self):
        msgs = [
            _binance_trade(trade_id=1, ts_ms=_TS_MS),
            _binance_depth(ts_ms=_TS_MS + 50),
            _binance_kline(ts_ms=_TS_MS + 100),
            _binance_mark_price(ts_ms=_TS_MS + 150),
            _binance_force_order(ts_ms=_TS_MS + 200),
        ]
        events = self._run_ingestor(msgs, Exchange.BINANCE)
        assert len(events) == 5
        # Order of arrival must be preserved.
        assert isinstance(events[0], TradeEvent)
        assert isinstance(events[1], OrderBookEvent)
        assert isinstance(events[2], KlineEvent)
        assert isinstance(events[3], MarkPriceEvent)
        assert isinstance(events[4], LiquidationEvent)

    def test_timestamp_ns_conversion_binance(self):
        """Binance timestamps are in ms; events must carry ns."""
        ts_ms = 1_700_000_000_123
        events = self._run_ingestor([_binance_trade(ts_ms=ts_ms)], Exchange.BINANCE)
        ev = events[0]
        assert isinstance(ev, TradeEvent)
        assert ev.timestamp_ns == ts_ms * 1_000_000

    def test_timestamp_ns_conversion_bybit(self):
        ts_ms = 1_700_000_000_456
        events = self._run_ingestor([_bybit_trade(ts_ms=ts_ms)], Exchange.BYBIT)
        ev = events[0]
        assert isinstance(ev, TradeEvent)
        assert ev.timestamp_ns == ts_ms * 1_000_000


# ═══════════════════════════════════════════════════════════════════════════════
# 8. DataIngestor recovery infrastructure
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataIngestorRecoveryInfrastructure:
    """Verify RecoveryManager is created and wired correctly on register_feed."""

    def test_recovery_manager_created_on_register(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs([]))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        assert feed_key in ingestor._recovery_managers

    def test_recovery_manager_bound_to_correct_feed_state(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs([]))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        feed_state = ingestor.get_feed_state(feed_key)
        rm = ingestor._recovery_managers[feed_key]
        assert rm._feed_state is feed_state  # same object reference

    def test_start_feed_sets_connected_and_ready(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs([]))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        # After start_feed() + synchronous connect() returns, state must be CONNECTED + READY.
        assert state.connection_state == ConnectionState.CONNECTED
        assert state.recovery_state == RecoveryState.READY

    def test_stop_feed_sets_disconnected(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs([]))
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        ingestor.stop_feed(feed_key)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        assert state.connection_state == ConnectionState.DISCONNECTED

    def test_unregistered_feed_start_raises(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append, ws_factory=_ws_factory_from_msgs([]))
        with pytest.raises(RuntimeError, match="not registered"):
            ingestor.start_feed("binance:NONEXISTENT")

    def test_no_ws_factory_register_raises(self):
        received: list = []
        ingestor = DataIngestor(on_event=received.append)
        cfg = _make_binance_cfg()
        with pytest.raises(RuntimeError, match="ws_factory"):
            ingestor.register_feed(cfg, Exchange.BINANCE)

    def test_feed_state_last_event_ts_updated(self):
        ts_ms = _TS_MS + 999
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs([_binance_trade(ts_ms=ts_ms)]),
        )
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        ingestor.start_feed(feed_key)
        state = ingestor.get_feed_state(feed_key)
        assert state is not None
        assert state.last_event_ts_ns == ts_ms * 1_000_000

    def test_parse_error_does_not_crash_feed(self):
        """Malformed messages must not propagate exceptions."""
        bad_msg = {"e": "trade", "s": "BTCUSDT"}  # missing required fields
        received: list = []
        ingestor = DataIngestor(
            on_event=received.append,
            ws_factory=_ws_factory_from_msgs([bad_msg, _binance_mark_price()]),
        )
        cfg = _make_binance_cfg()
        feed_key = ingestor.register_feed(cfg, Exchange.BINANCE)
        ingestor.start_feed(feed_key)  # must not raise
        # The valid message after the bad one is still emitted.
        assert len(received) == 1
        assert isinstance(received[0], MarkPriceEvent)
