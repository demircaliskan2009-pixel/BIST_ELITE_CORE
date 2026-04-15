"""WebSocketSimulator — deterministic WebSocketClient implementation for tests.

Implements the WebSocketClient ABC and replays a pre-defined sequence of
raw JSON dicts as if they came from an exchange WebSocket connection.

Usage:
    msgs = [
        {"e": "trade", "s": "BTCUSDT", "t": 1, "p": "50000.0", ...},
        {"e": "depthUpdate", "s": "BTCUSDT", ...},
    ]
    sim = WebSocketSimulator(config=cfg, on_message=my_handler, messages=msgs)
    sim.connect()   # replays all messages synchronously, then returns

This lets tests run fully in-process with no network or threading.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from crypto_core.data.ingestion.websocket_client import MessageCallback, WebSocketClient, WebSocketConfig


class WebSocketSimulator(WebSocketClient):
    """Deterministic WebSocketClient that replays a fixed message sequence.

    All messages are replayed synchronously in connect().
    connect() returns after all messages are delivered.

    is_connected() returns True between connect() and disconnect() only.
    send() records all outbound messages for assertion in tests.
    """

    def __init__(
        self,
        config: WebSocketConfig,
        on_message: MessageCallback,
        messages: Optional[List[dict]] = None,
    ) -> None:
        super().__init__(config, on_message)
        self._messages: List[dict] = messages if messages is not None else []
        self._sent: List[dict] = []
        self._connected: bool = False
        self._connect_call_count: int = 0
        self._disconnect_call_count: int = 0

    def connect(self) -> None:
        """Replay all messages synchronously then mark as not connected."""
        self._connected = True
        self._connect_call_count += 1
        for msg in self._messages:
            self._on_message(msg)
        self._connected = False

    def disconnect(self) -> None:
        """Mark as disconnected."""
        self._connected = False
        self._disconnect_call_count += 1

    def is_connected(self) -> bool:
        return self._connected

    def send(self, message: dict) -> None:
        """Record the outbound message for test assertion."""
        self._sent.append(message)

    # Test helpers

    def add_message(self, msg: dict) -> None:
        """Append a message to the replay queue (before connect() is called)."""
        self._messages.append(msg)

    @property
    def sent_messages(self) -> List[dict]:
        """All messages sent via send() since instantiation."""
        return list(self._sent)

    @property
    def connect_call_count(self) -> int:
        return self._connect_call_count

    @property
    def disconnect_call_count(self) -> int:
        return self._disconnect_call_count
