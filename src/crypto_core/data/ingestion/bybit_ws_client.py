"""BybitWebSocketClient — concrete Bybit V5 linear WebSocket transport.

Connects to wss://stream.bybit.com/v5/public/linear, sends the V5 subscribe
message on open, and dispatches every inbound topic-bearing JSON dict to the
injected on_message callback.

Bybit V5 message format (passed to on_message):
    {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": 1699999999000,
        "data": [...]
    }

Pong / subscription-confirmation messages (no "topic" field) are filtered
before dispatch — they are not forwarded to on_message.

Implements the WebSocketClient ABC — use WebSocketSimulator for tests.

Features:
- Subscribe message sent automatically on open (built from config.stream_types).
- Ping/pong heartbeat via websocket-client at config.ping_interval_s (default 5s).
- connect() is blocking — run in a daemon thread for production use.
- disconnect() closes cleanly.
- send() serialises dict → JSON.
- Raises ConnectionError if the WebSocket layer reports a hard error.

PRD reference: §4.1 (Bybit secondary exchange), §0.2 (Bybit as failover).

Note: requires websocket-client>=1.7 (not websockets async library).
"""

from __future__ import annotations

import json
import logging

import websocket as _ws  # websocket-client (pip install websocket-client)

from crypto_core.data.ingestion.websocket_client import MessageCallback, WebSocketClient, WebSocketConfig

logger = logging.getLogger(__name__)


class BybitWebSocketClient(WebSocketClient):
    """Concrete Bybit V5 linear WebSocket client.

    connect() is blocking — call it from a daemon thread:

        client = BybitWebSocketClient(config, on_message)
        t = threading.Thread(target=client.connect, daemon=True)
        t.start()
        ...
        client.disconnect()

    config.stream_types is used to build the subscribe message on open.
    Example stream_types: ["publicTrade", "orderbook.50", "kline.1", "liquidation", "tickers"]

    Use WebSocketSimulator in tests (same ABC, replays messages synchronously).
    """

    def __init__(self, config: WebSocketConfig, on_message: MessageCallback) -> None:
        super().__init__(config, on_message)
        self._ws_app: _ws.WebSocketApp | None = None
        self._connected: bool = False
        self._connect_error: Exception | None = None

    # ──────────────────────────────────────────────────────────────
    # WebSocketClient ABC
    # ──────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Connect to Bybit V5 public linear endpoint.

        Blocking — runs until the connection drops or an error occurs.
        Sends subscribe message on open (from config.stream_types).

        Raises:
            ConnectionError: if websocket-client reports a hard error.
        """
        self._connect_error = None
        self._ws_app = _ws.WebSocketApp(
            self._config.url,
            on_open=self._on_open,
            on_message=self._on_raw_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        logger.info("BybitWebSocketClient: connecting to %s symbol=%s", self._config.url, self._config.symbol)
        self._ws_app.run_forever(
            ping_interval=int(self._config.ping_interval_s),
            ping_timeout=int(self._config.ping_timeout_s),
        )
        if self._connect_error is not None:
            raise ConnectionError(
                f"BybitWebSocketClient({self._config.symbol}): {self._connect_error}"
            ) from self._connect_error

    def disconnect(self) -> None:
        """Close the WebSocket connection cleanly."""
        self._connected = False
        if self._ws_app is not None:
            self._ws_app.close()
            logger.info(
                "BybitWebSocketClient: disconnected symbol=%s url=%s",
                self._config.symbol,
                self._config.url,
            )

    def is_connected(self) -> bool:
        return self._connected

    def send(self, message: dict) -> None:
        """Send a JSON-serialisable dict to the server.

        Raises:
            RuntimeError: if not connected.
        """
        if self._ws_app is None or not self._connected:
            raise RuntimeError(f"BybitWebSocketClient({self._config.symbol}): cannot send — not connected")
        self._ws_app.send(json.dumps(message))

    # ──────────────────────────────────────────────────────────────
    # websocket-client callbacks (internal)
    # ──────────────────────────────────────────────────────────────

    def _on_open(self, ws: _ws.WebSocketApp) -> None:
        self._connected = True
        logger.info(
            "BybitWebSocketClient: connected symbol=%s url=%s",
            self._config.symbol,
            self._config.url,
        )
        # Send subscription message immediately on open.
        sub_msg = self._build_subscribe_msg()
        ws.send(json.dumps(sub_msg))
        logger.debug("BybitWebSocketClient(%s): sent subscribe: %s", self._config.symbol, sub_msg)

    def _build_subscribe_msg(self) -> dict:
        """Build V5 subscribe message from config.stream_types."""
        args = [f"{st}.{self._config.symbol}" for st in self._config.stream_types]
        return {"op": "subscribe", "args": args}

    def _on_raw_message(self, ws: _ws.WebSocketApp, raw: str) -> None:
        """Parse JSON and dispatch to on_message.

        Bybit sends pong responses and subscription confirmations that carry
        no "topic" field — these are filtered before dispatch.
        """
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                "BybitWebSocketClient(%s): JSON decode error: %s — raw=%r",
                self._config.symbol,
                exc,
                raw[:200],
            )
            return

        # Skip pong / subscription ACK (no "topic").
        if "topic" not in msg:
            logger.debug("BybitWebSocketClient(%s): non-data message dropped: %r", self._config.symbol, msg)
            return

        self._on_message(msg)

    def _on_error(self, ws: _ws.WebSocketApp, error: Exception) -> None:
        self._connected = False
        self._connect_error = error
        logger.error(
            "BybitWebSocketClient(%s): error: %s",
            self._config.symbol,
            error,
        )

    def _on_close(
        self,
        ws: _ws.WebSocketApp,
        close_status_code: int | None,
        close_msg: str | None,
    ) -> None:
        self._connected = False
        logger.warning(
            "BybitWebSocketClient(%s): connection closed code=%s msg=%s",
            self._config.symbol,
            close_status_code,
            close_msg,
        )
