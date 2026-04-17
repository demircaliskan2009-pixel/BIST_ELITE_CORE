"""BinanceWebSocketClient — concrete Binance Futures WebSocket transport.

Connects to the Binance Futures combined-stream endpoint, unwraps the
combined-stream envelope, and dispatches raw event dicts to the injected
on_message callback.

Combined stream URL format:
    wss://fstream.binance.com/stream?streams=btcusdt@trade/btcusdt@depth@100ms/...

Combined stream envelope (unwrapped before dispatch):
    {"stream": "btcusdt@trade", "data": {"e": "trade", "s": "BTCUSDT", ...}}
                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                         This dict is passed to on_message.

Implements the WebSocketClient ABC — use WebSocketSimulator for tests.

Features:
- Ping/pong heartbeat at config.ping_interval_s (default 5s, PRD §4.5).
- ping_timeout: connection declared dead after config.ping_timeout_s (default 15s).
- connect() is blocking — run in a daemon thread for production use.
- disconnect() closes the connection cleanly.
- send() serialises dict → JSON and writes to the server.
- Raises ConnectionError if the WebSocket layer reports a hard error.

PRD reference: §4.1 WebSocket Architecture, §4.5 Recovery Protocol.

Note: requires websocket-client>=1.7 (not websockets async library).
"""

from __future__ import annotations

import json
import logging

import websocket as _ws  # websocket-client (pip install websocket-client)

from crypto_core.data.ingestion.websocket_client import MessageCallback, WebSocketClient, WebSocketConfig

logger = logging.getLogger(__name__)


class BinanceWebSocketClient(WebSocketClient):
    """Concrete Binance Futures WebSocket client.

    connect() is blocking — call it from a daemon thread:

        client = BinanceWebSocketClient(config, on_message)
        t = threading.Thread(target=client.connect, daemon=True)
        t.start()
        ...
        client.disconnect()

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
        """Connect to the Binance Futures combined-stream endpoint.

        Blocking — runs until the connection drops or an error occurs.
        After return, the connection is closed.

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
        logger.info("BinanceWebSocketClient: connecting to %s symbol=%s", self._config.url, self._config.symbol)
        self._ws_app.run_forever(
            ping_interval=int(self._config.ping_interval_s),
            ping_timeout=int(self._config.ping_timeout_s),
        )
        if self._connect_error is not None:
            raise ConnectionError(
                f"BinanceWebSocketClient({self._config.symbol}): {self._connect_error}"
            ) from self._connect_error

    def disconnect(self) -> None:
        """Close the WebSocket connection cleanly."""
        self._connected = False
        if self._ws_app is not None:
            self._ws_app.close()
            logger.info(
                "BinanceWebSocketClient: disconnected symbol=%s url=%s",
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
            raise RuntimeError(f"BinanceWebSocketClient({self._config.symbol}): cannot send — not connected")
        self._ws_app.send(json.dumps(message))

    # ──────────────────────────────────────────────────────────────
    # websocket-client callbacks (internal)
    # ──────────────────────────────────────────────────────────────

    def _on_open(self, ws: _ws.WebSocketApp) -> None:
        self._connected = True
        logger.info(
            "BinanceWebSocketClient: connected symbol=%s url=%s",
            self._config.symbol,
            self._config.url,
        )

    def _on_raw_message(self, ws: _ws.WebSocketApp, raw: str) -> None:
        """Unwrap combined-stream envelope and dispatch to on_message.

        Combined stream frame:  {"stream": "btcusdt@trade", "data": {...}}
        Single stream frame:    {"e": "trade", ...}

        Only the inner event dict is passed to on_message.
        """
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                "BinanceWebSocketClient(%s): JSON decode error: %s — raw=%r",
                self._config.symbol,
                exc,
                raw[:200],
            )
            return

        # Unwrap combined-stream envelope.
        payload: dict = msg["data"] if ("data" in msg and "stream" in msg) else msg
        self._on_message(payload)

    def _on_error(self, ws: _ws.WebSocketApp, error: Exception) -> None:
        self._connected = False
        self._connect_error = error
        logger.error(
            "BinanceWebSocketClient(%s): error: %s",
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
            "BinanceWebSocketClient(%s): connection closed code=%s msg=%s",
            self._config.symbol,
            close_status_code,
            close_msg,
        )
