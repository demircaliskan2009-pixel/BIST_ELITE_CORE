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
from crypto_core.data.ingestion.binance_snapshot_fetcher import BinanceSnapshotFetcher
from crypto_core.data.ingestion.websocket_client import WebSocketClient, WebSocketConfig
from crypto_core.data.models.events import Exchange, OrderBookEventType
from crypto_core.data.models.feed_state import ConnectionState, FeedState, RecoveryState
from crypto_core.data.recovery.delta_buffer import DeltaBuffer, SequenceGapError
from crypto_core.data.recovery.recovery_manager import RecoveryManager

logger = logging.getLogger(__name__)

# Callback from DataIngestor to the EventRouter (or any upstream consumer).
# Receives a fully-parsed typed event object.
EventCallback = Callable[[object], None]


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
        recovery_sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._on_event = on_event
        self._ws_factory = ws_factory
        self._recovery_sleep_fn = recovery_sleep_fn  # None → time.sleep (default)
        self._feeds: dict[str, FeedState] = {}  # feed_key → FeedState
        self._clients: dict[str, WebSocketClient] = {}  # feed_key → WebSocketClient
        self._recovery_managers: dict[str, RecoveryManager] = {}  # feed_key → RecoveryManager
        self._feed_threads: dict[str, threading.Thread] = {}  # feed_key → managed Thread
        self._feed_configs: dict[str, WebSocketConfig] = {}  # feed_key → WebSocketConfig
        self._feed_exchanges: dict[str, Exchange] = {}  # feed_key → Exchange
        self._shutdown_events: dict[str, threading.Event] = {}  # feed_key → shutdown Event
        self._delta_buffers: dict[str, DeltaBuffer] = {}  # feed_key → DeltaBuffer (Binance only)

    # ──────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────

    def register_feed(
        self,
        config: WebSocketConfig,
        exchange: Exchange,
        snapshot_http_get: Callable[..., Any] | None = None,
    ) -> str:
        """Register a new feed and create its FeedState + RecoveryManager.

        Returns the feed_key for tracking purposes.
        Does NOT connect. Call start_feed() or start_feed_managed() to connect.

        Args:
            config:           WebSocket configuration (url, symbol, ping settings).
            exchange:         Exchange enum (BINANCE or BYBIT).
            snapshot_http_get: Injectable HTTP GET callable for snapshot fetcher.
                              Used in tests to avoid real network calls.
                              If None, BinanceSnapshotFetcher uses requests.get.
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
        self._feed_configs[feed_key] = config
        self._feed_exchanges[feed_key] = exchange
        raw_callback = self._make_raw_callback(config.symbol, exchange)
        self._clients[feed_key] = self._ws_factory(config, raw_callback)

        # on_connect: update the client reference and open the delta buffer so
        # any WS delta messages arriving before the REST snapshot is applied
        # are captured in the buffer rather than dropped.
        # The supervision loop in start_feed_managed() handles spawning the
        # actual WS connect thread after recovery completes.
        def _recovery_on_connect() -> None:
            new_raw_cb = self._make_raw_callback(config.symbol, exchange)
            self._clients[feed_key] = self._ws_factory(config, new_raw_cb)
            # Open the delta buffer for this recovery cycle.
            # start_buffering() resets any leftover state from the previous cycle.
            buf = self._delta_buffers.get(feed_key)
            if buf is not None:
                buf.start_buffering()

        # Build the on_snapshot_request callback.
        # For Binance: fetch REST snapshot, emit event, advance state machine.
        # For Bybit: explicitly unsupported in Phase 7B (no REST depth endpoint).
        #
        # Forward reference: recovery_mgr_ref is filled after RecoveryManager is
        # created (list trick avoids circular dependency).
        recovery_mgr_ref: list[RecoveryManager | None] = [None]

        if exchange == Exchange.BINANCE:
            fetcher = BinanceSnapshotFetcher(
                config.symbol,
                _http_get=snapshot_http_get,
            )
            # DeltaBuffer for this feed — created once, reused across recovery cycles.
            delta_buf = DeltaBuffer()
            self._delta_buffers[feed_key] = delta_buf

            def on_snapshot_request(symbol: str, exch: str) -> None:
                rm = recovery_mgr_ref[0]
                # ── Step 1: fetch the REST snapshot ──────────────────────────────────
                snapshot_event = fetcher.fetch()  # raises on HTTP error → triggers retry

                # ── Step 2: drain buffered deltas for replay ─────────────────────────
                # Buffer was opened in _make_raw_callback the moment SNAPSHOTTING began.
                # drain_for_replay() filters stale deltas (covered by snapshot) and
                # validates the remaining sequence is contiguous.
                try:
                    replay_deltas = delta_buf.drain_for_replay(snapshot_event.last_update_id)
                except SequenceGapError as gap:
                    # Gap between snapshot and buffered deltas → recovery fail-closed.
                    logger.error(
                        "DeltaBuffer sequence gap during replay for %s:%s — %s",
                        exch,
                        symbol,
                        gap,
                    )
                    delta_buf.clear()
                    if rm is not None:
                        state = rm._feed_state
                        state.recovery_state = RecoveryState.FAILED
                    raise  # propagates to _run_recovery_loop → triggers another attempt

                # ── Step 3: emit snapshot to downstream (book manager, edge layer) ───
                self._on_event(snapshot_event)

                # ── Step 4: transition → REPLAYING ───────────────────────────────────
                if rm is not None:
                    rm.on_snapshot_received()

                # ── Step 5: replay validated deltas ──────────────────────────────────
                if replay_deltas:
                    logger.info(
                        "Replaying %d buffered deltas for %s:%s (snapshot_update_id=%d)",
                        len(replay_deltas),
                        exch,
                        symbol,
                        snapshot_event.last_update_id,
                    )
                    for delta_event in replay_deltas:
                        self._on_event(delta_event)

                # ── Step 6: clear buffer (clean slate for next cycle) ─────────────────
                delta_buf.clear()

                # ── Step 7: transition → VALIDATING → READY ──────────────────────────
                if rm is not None:
                    rm.on_stream_caught_up()
                    rm.on_validation_passed()
        else:
            # Bybit REST snapshot is not part of Phase 7C scope.
            def on_snapshot_request(symbol: str, exch: str) -> None:  # type: ignore[misc]
                raise NotImplementedError(
                    f"REST snapshot not supported for exchange={exch} "
                    f"(symbol={symbol}). Phase 7B supports Binance Futures only."
                )

        self._recovery_managers[feed_key] = RecoveryManager(
            feed_state=feed_state,
            on_connect=_recovery_on_connect,
            on_snapshot_request=on_snapshot_request,
            sleep_fn=self._recovery_sleep_fn,
        )
        recovery_mgr_ref[0] = self._recovery_managers[feed_key]
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
        """Start the feed under continuous supervision in a background daemon thread.

        The supervision loop:
        1. Spawns a WS connect thread and waits for it to finish (disconnect).
        2. On unexpected disconnect, runs RecoveryManager.on_disconnect() which
           performs exponential-backoff reconnect + REST snapshot + state advance.
        3. After recovery, loops back and spawns a new WS connect thread.
        4. Exits only when shutdown() is called or the feed enters FAILED state.

        Returns the supervision Thread so callers can join() on shutdown if needed.

        Raises:
            RuntimeError: if feed_key is not registered.
        """
        if feed_key not in self._clients:
            raise RuntimeError(f"Feed '{feed_key}' is not registered")

        state = self._feeds[feed_key]
        recovery_mgr = self._recovery_managers[feed_key]
        shutdown_event = threading.Event()
        self._shutdown_events[feed_key] = shutdown_event

        def _ws_connect_guarded() -> None:
            """Run client.connect() and absorb any exception (logged only)."""
            try:
                self._clients[feed_key].connect()  # blocks until disconnect
            except Exception as exc:
                logger.error("Feed connect error %s: %s", feed_key, exc)

        def _run() -> None:
            """Supervision loop: connect → wait → recover → repeat."""
            while not shutdown_event.is_set():
                # (Re-)arm feed state so events flow through the callback gate.
                # After recovery, on_validation_passed() has already set these;
                # setting them here is idempotent and correct for the initial start.
                state.connection_state = ConnectionState.CONNECTED
                state.recovery_state = RecoveryState.READY

                ws_thread = threading.Thread(
                    target=_ws_connect_guarded,
                    daemon=True,
                    name=f"ws-{feed_key}-{state.reconnect_attempt}",
                )
                ws_thread.start()
                ws_thread.join()  # block until WS disconnects or errors

                if shutdown_event.is_set():
                    break

                # Permanent failure or clean stop → exit supervision.
                if state.connection_state in (
                    ConnectionState.FAILED,
                    ConnectionState.DISCONNECTED,
                ):
                    break
                if state.recovery_state == RecoveryState.FAILED:
                    break

                # Unexpected disconnect — run recovery.
                # on_disconnect() is synchronous:
                #   - exponential backoff
                #   - _recovery_on_connect() updates self._clients[feed_key]
                #   - on_snapshot_request() fetches REST snapshot, emits event,
                #     advances state machine to READY
                # After return, self._clients[feed_key] is the new client and
                # state.recovery_state == READY.
                logger.warning("Feed %s disconnected unexpectedly — triggering recovery", feed_key)
                recovery_mgr.on_disconnect()
                # Loop continues → re-arm states → spawn new WS thread.

        t = threading.Thread(target=_run, daemon=True, name=f"supervision-{feed_key}")
        self._feed_threads[feed_key] = t
        t.start()
        logger.info("Feed started (managed): %s", feed_key)
        return t

    def stop_feed(self, feed_key: str) -> None:
        """Disconnect the WebSocketClient for the given feed (clean stop)."""
        if feed_key in self._feeds:
            self._feeds[feed_key].connection_state = ConnectionState.DISCONNECTED
        if feed_key in self._clients:
            self._clients[feed_key].disconnect()
        # Clear any open delta buffer so it does not leak state.
        buf = self._delta_buffers.get(feed_key)
        if buf is not None and buf.is_active():
            buf.clear()

    def shutdown(self, feed_key: str) -> None:
        """Signal the supervision loop to stop and disconnect the feed.

        After this call the supervision Thread will exit its loop on the next
        iteration.  Call Thread.join() on the value returned by start_feed_managed()
        to wait for the supervision thread to finish.
        """
        event = self._shutdown_events.get(feed_key)
        if event is not None:
            event.set()
        self.stop_feed(feed_key)

    def shutdown_all(self) -> None:
        """Shutdown all registered feeds."""
        for feed_key in list(self._feeds):
            self.shutdown(feed_key)

    def get_feed_state(self, feed_key: str) -> FeedState | None:
        """Returns FeedState for the given feed_key, or None if unknown."""
        return self._feeds.get(feed_key)

    # ──────────────────────────────────────────────────────────────
    # Internal message routing
    # ──────────────────────────────────────────────────────────────

    def _make_raw_callback(self, symbol: str, exchange: Exchange) -> Callable[[dict], None]:
        """Returns a closure that routes raw WS dicts through the adapter.

        Routing rules during recovery:
          SNAPSHOTTING:
            - OrderBookEvent(DELTA) → buffered in DeltaBuffer (for replay after snapshot)
            - All other events     → dropped (out-of-sequence, not safe to emit)
          REPLAYING / VALIDATING:
            - All events           → dropped (replay is in progress synchronously)
          FAILED:
            - All events           → dropped
          IDLE / READY:
            - All events           → forwarded to on_event

        This replaces the Phase 7B blanket-drop policy for SNAPSHOTTING state.
        """

        def on_raw_message(msg: dict[str, Any]) -> None:
            feed_key = self._make_feed_key(symbol, exchange)
            state = self._feeds.get(feed_key)
            if state is None:
                logger.warning("Received message for unregistered feed: %s", feed_key)
                return

            rs = state.recovery_state

            # ── SNAPSHOTTING: buffer depth deltas; drop everything else ──────────
            if rs == RecoveryState.SNAPSHOTTING:
                # Only buffer order-book deltas — other stream types (trade, kline,
                # mark-price, liquidation) are stateless ticks and can safely be
                # dropped during recovery without affecting book state.
                try:
                    events = self._parse_message(msg, exchange, symbol)
                except (KeyError, ValueError) as exc:
                    logger.error("Parse error on %s: %s — msg=%r", feed_key, exc, msg)
                    return

                buf = self._delta_buffers.get(feed_key)
                for event in events:
                    if (
                        hasattr(event, "event_type")
                        and event.event_type == OrderBookEventType.DELTA
                        and buf is not None
                        and buf.is_active()
                    ):
                        try:
                            buf.push(event)
                        except OverflowError as oe:
                            # Buffer overflow → fail-closed: mark feed FAILED.
                            logger.error(
                                "DeltaBuffer overflow for %s — marking FAILED: %s",
                                feed_key,
                                oe,
                            )
                            state.recovery_state = RecoveryState.FAILED
                    else:
                        logger.debug(
                            "Dropping non-delta event during SNAPSHOTTING (%s): %s",
                            feed_key,
                            type(event).__name__,
                        )
                return

            # ── REPLAYING / VALIDATING / FAILED: drop all events ─────────────────
            if rs in (
                RecoveryState.REPLAYING,
                RecoveryState.VALIDATING,
                RecoveryState.FAILED,
            ):
                logger.debug("Dropping event during recovery (%s): %s", rs, feed_key)
                return

            # ── IDLE / READY: normal forward path ────────────────────────────────
            try:
                events = self._parse_message(msg, exchange, symbol)
                for event in events:
                    state.last_event_ts_ns = _extract_ts(event)
                    self._on_event(event)
            except (KeyError, ValueError) as exc:
                logger.error("Parse error on %s: %s — msg=%r", feed_key, exc, msg)

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
