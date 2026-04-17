"""DataIngestor — orchestrates WebSocket connections and routes messages.

Responsibilities:
1. Manage WebSocketClient lifecycle (connect, disconnect, reconnect hand-off).
2. Parse raw exchange messages via exchange adapters.
3. Pass parsed typed events to EventRouter.
4. Track FeedState per (symbol, exchange, stream_type).
5. Trigger stale-data checks on heartbeat.

This class does NOT validate event semantics — that is DataValidator's job.
This class does NOT process or store events — that is EventRouter's job.

Determinism: same message sequence → same event routing → same downstream state.
PRD reference: §4.1, §4.5 Recovery Protocol.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from crypto_core.data.ingestion import binance_adapter, bybit_adapter
from crypto_core.data.ingestion.websocket_client import WebSocketClient, WebSocketConfig
from crypto_core.data.models.events import Exchange
from crypto_core.data.models.feed_state import ConnectionState, FeedState, RecoveryState
from crypto_core.data.recovery.recovery_manager import RecoveryManager

logger = logging.getLogger(__name__)

# Callback from DataIngestor to the EventRouter (or any upstream consumer).
# Receives a fully-parsed typed event object.
EventCallback = Callable[[object], None]

# Recovery states that must gate event emission downstream.
# IDLE = initial startup → events pass (no recovery in flight).
# READY = connected and validated → events pass.
# SNAPSHOTTING/REPLAYING/VALIDATING = recovery in flight → DROP events.
# FAILED = feed in unsafe state → DROP events.
_BLOCKED_RECOVERY_STATES: frozenset[RecoveryState] = frozenset(
    {
        RecoveryState.SNAPSHOTTING,
        RecoveryState.REPLAYING,
        RecoveryState.VALIDATING,
        RecoveryState.FAILED,
    }
)


class DataIngestor:
    """Entry point for the data ingestion pipeline.

    For each (symbol, exchange) pair, DataIngestor:
    - Holds one WebSocketClient reference.
    - Maintains FeedState.
    - Parses raw messages into typed events via the exchange adapter.
    - Calls on_event for every successfully parsed event.

    on_event is injected at construction so the ingestor is decoupled from
    the downstream processing layer (EventRouter).

    Constructor args:
        on_event: callback that receives every parsed typed event.
        ws_factory: injectable factory that creates WebSocketClient instances.
                    Defaults to None (must be injected before calling start()).
    """

    def __init__(
        self,
        on_event: EventCallback,
        ws_factory: Callable[[WebSocketConfig, Callable[[dict], None]], WebSocketClient] | None = None,
    ) -> None:
        self._on_event = on_event
        self._ws_factory = ws_factory
        self._feeds: dict[str, FeedState] = {}  # feed_key → FeedState
        self._clients: dict[str, WebSocketClient] = {}  # feed_key → WebSocketClient
        self._recovery_managers: dict[str, RecoveryManager] = {}  # feed_key → RecoveryManager
        self._feed_threads: dict[str, threading.Thread] = {}  # feed_key → managed Thread

    # ──────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────

    def register_feed(self, config: WebSocketConfig, exchange: Exchange) -> str:
        """Register a new feed and create its FeedState + RecoveryManager.

        Returns the feed_key for tracking purposes.
        Does NOT connect. Call start_feed() or start_feed_managed() to connect.
        """
        if self._ws_factory is None:
            raise RuntimeError("ws_factory must be set before registering feeds")

        feed_key = self._make_feed_key(config.symbol, exchange)
        feed_state = FeedState(
            symbol=config.symbol,
            exchange=exchange.value,
            stream_type="multi",
        )
        self._feeds[feed_key] = feed_state
        raw_callback = self._make_raw_callback(config.symbol, exchange)
        self._clients[feed_key] = self._ws_factory(config, raw_callback)

        # Wire RecoveryManager. on_connect is non-blocking: it creates a new
        # client instance and starts it in a daemon thread so _run_recovery_loop()
        # can proceed to request the snapshot without waiting for a disconnect.
        def _recovery_on_connect() -> None:
            new_raw_cb = self._make_raw_callback(config.symbol, exchange)
            self._clients[feed_key] = self._ws_factory(config, new_raw_cb)
            t = threading.Thread(
                target=self._clients[feed_key].connect,
                daemon=True,
                name=f"feed-{feed_key}-reconnect-{feed_state.reconnect_attempt}",
            )
            t.start()

        self._recovery_managers[feed_key] = RecoveryManager(
            feed_state=feed_state,
            on_connect=_recovery_on_connect,
            on_snapshot_request=lambda _sym, _exch: None,  # Phase 7A: REST snapshot wired in 7B
        )
        logger.info("Registered feed: %s", feed_key)
        return feed_key

    def start_feed(self, feed_key: str) -> None:
        """Connect the WebSocketClient for the registered feed (synchronous).

        Sets CONNECTED + READY before calling connect() so that events emitted
        during connect() (e.g. from WebSocketSimulator in tests) pass through
        the recovery-state gate in _make_raw_callback.

        For production use, prefer start_feed_managed() which runs connect()
        in a daemon thread and triggers RecoveryManager on disconnect.

        Raises:
            RuntimeError: if feed_key is not registered.
        """
        if feed_key not in self._clients:
            raise RuntimeError(f"Feed '{feed_key}' is not registered")
        state = self._feeds[feed_key]
        # Set live state BEFORE connect() so events flow during message replay
        # (relevant for WebSocketSimulator which replays synchronously inside connect()).
        state.connection_state = ConnectionState.CONNECTED
        state.recovery_state = RecoveryState.READY
        self._clients[feed_key].connect()
        logger.info("Feed started (sync): %s", feed_key)

    def start_feed_managed(self, feed_key: str) -> threading.Thread:
        """Start the feed in a background daemon thread with automatic recovery.

        When connect() returns (connection closed), RecoveryManager.on_disconnect()
        is triggered to run exponential-backoff reconnect + snapshot protocol.

        Returns the Thread so callers can join() on shutdown if needed.

        Raises:
            RuntimeError: if feed_key is not registered.
        """
        if feed_key not in self._clients:
            raise RuntimeError(f"Feed '{feed_key}' is not registered")

        state = self._feeds[feed_key]
        recovery_mgr = self._recovery_managers[feed_key]

        def _run() -> None:
            state.connection_state = ConnectionState.CONNECTED
            state.recovery_state = RecoveryState.READY
            try:
                self._clients[feed_key].connect()  # blocks until disconnect
            except Exception as exc:
                logger.error("Feed connect error %s: %s", feed_key, exc)

            # connect() returned → connection closed (clean or error).
            if state.connection_state != ConnectionState.DISCONNECTED:
                logger.warning("Feed %s disconnected unexpectedly — triggering recovery", feed_key)
                recovery_mgr.on_disconnect()

        t = threading.Thread(target=_run, daemon=True, name=f"feed-{feed_key}")
        self._feed_threads[feed_key] = t
        t.start()
        logger.info("Feed started (managed): %s", feed_key)
        return t

    def stop_feed(self, feed_key: str) -> None:
        """Disconnect the WebSocketClient for the given feed."""
        if feed_key in self._clients:
            self._clients[feed_key].disconnect()
            self._feeds[feed_key].connection_state = ConnectionState.DISCONNECTED

    def get_feed_state(self, feed_key: str) -> FeedState | None:
        """Returns FeedState for the given feed_key, or None if unknown."""
        return self._feeds.get(feed_key)

    # ──────────────────────────────────────────────────────────────
    # Internal message routing
    # ──────────────────────────────────────────────────────────────

    def _make_raw_callback(self, symbol: str, exchange: Exchange) -> Callable[[dict], None]:
        """Returns a closure that routes raw WS dicts through the adapter.

        Events are dropped (not forwarded) while recovery_state is in one of
        the active-recovery states (SNAPSHOTTING, REPLAYING, VALIDATING, FAILED).
        This prevents stale or out-of-sequence data from reaching the edge layer
        during a reconnect recovery cycle (PRD §4.5).
        """

        def on_raw_message(msg: dict[str, Any]) -> None:
            feed_key = self._make_feed_key(symbol, exchange)
            state = self._feeds.get(feed_key)
            if state is None:
                logger.warning("Received message for unregistered feed: %s", feed_key)
                return
            # Gate: drop events during active recovery (data may be out of sequence).
            if state.recovery_state in _BLOCKED_RECOVERY_STATES:
                logger.debug("Dropping event during recovery (%s): %s", state.recovery_state, feed_key)
                return
            try:
                events = self._parse_message(msg, exchange, symbol)
                for event in events:
                    state.last_event_ts_ns = _extract_ts(event)
                    self._on_event(event)
            except (KeyError, ValueError) as exc:
                logger.error("Parse error on %s: %s — msg=%r", feed_key, exc, msg)
                # parse errors are logged but do NOT crash the callback
                # the feed continues; validation layer will catch upstream issues

        return on_raw_message

    def _parse_message(self, msg: dict[str, Any], exchange: Exchange, symbol: str) -> list:
        """Dispatch raw dict to the correct exchange adapter.

        Returns a list of parsed typed event objects (usually 1, sometimes multiple
        for batch trade messages etc.).
        """
        if exchange == Exchange.BINANCE:
            return _parse_binance(msg, symbol)
        if exchange == Exchange.BYBIT:
            return _parse_bybit(msg, symbol)
        raise ValueError(f"Unsupported exchange: {exchange}")

    @staticmethod
    def _make_feed_key(symbol: str, exchange: Exchange) -> str:
        return f"{exchange.value}:{symbol}"


# ──────────────────────────────────────────────────────────────────────
# Exchange-specific dispatch (module-level helpers, easily unit-tested)
# ──────────────────────────────────────────────────────────────────────


def _parse_binance(msg: dict[str, Any], symbol: str) -> list:
    """Route a Binance message to the correct adapter parser."""
    event_type = msg.get("e", "")
    if event_type == "trade":
        return [binance_adapter.parse_trade(msg)]
    if event_type == "depthUpdate":
        return [binance_adapter.parse_depth_delta(msg)]
    if event_type == "kline":
        return [binance_adapter.parse_kline(msg)]
    if event_type == "forceOrder":
        return [binance_adapter.parse_liquidation(msg)]
    if event_type == "markPriceUpdate":
        return [binance_adapter.parse_mark_price(msg)]
    logger.debug("Unhandled Binance event type '%s' for %s", event_type, symbol)
    return []


def _parse_bybit(msg: dict[str, Any], symbol: str) -> list:
    """Route a Bybit V5 message to the correct adapter parser."""
    topic = str(msg.get("topic", ""))
    if topic.startswith("publicTrade."):
        events = []
        for entry in msg.get("data", []):
            events.append(bybit_adapter.parse_trade(entry, topic))
        return events
    if topic.startswith("orderbook."):
        return [bybit_adapter.parse_orderbook(msg)]
    if topic.startswith("kline."):
        parts = topic.split(".")
        interval = parts[1] if len(parts) > 2 else "1m"
        events = []
        for entry in msg.get("data", []):
            events.append(bybit_adapter.parse_kline(entry, symbol, interval))
        return events
    if topic.startswith("liquidation."):
        events = []
        for entry in msg.get("data", []):
            events.append(bybit_adapter.parse_liquidation(entry))
        return events
    logger.debug("Unhandled Bybit topic '%s' for %s", topic, symbol)
    return []


def _extract_ts(event: object) -> int:
    """Extract timestamp_ns from any event type for FeedState tracking."""
    return getattr(event, "timestamp_ns", 0)
