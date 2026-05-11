"""Abstract WebSocket client interface.

WebSocketClient is a Protocol (structural subtyping) so test simulators
can implement it without inheriting from a base class.

Design principles:
- Mockable: WebSocketSimulator implements the same Protocol.
- Stateless processing: message handling is injected via callback.
- No business logic: raw bytes/dicts go straight to adapter, then event router.

PRD reference: §4.1 WebSocket Architecture, §4.5 Recovery Protocol.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Callable

# Callback signature: (raw_message: dict) -> None
# Called by the WebSocketClient on every received message.
MessageCallback = Callable[[dict], None]


@dataclass(frozen=True)
class WebSocketConfig:
    """Immutable connection configuration for a WebSocket stream.

    Attributes:
        url:             WebSocket endpoint URL.
        symbol:          Instrument symbol (e.g. "BTCUSDT").
        stream_types:    List of StreamType values to subscribe to.
        ping_interval_s: Interval between heartbeat pings (PRD §4.5: 5s).
        ping_timeout_s:  Timeout before declaring the connection dead (PRD §4.5: 15s).
        max_reconnect_attempts: 0 = unlimited. After exhaustion → ConnectionState.FAILED.
        backoff_base_s:  Exponential backoff base (PRD §4.5: 1s, 2s, 4s, 8s, max 30s).
        backoff_max_s:   Maximum backoff cap (PRD §4.5: 30s).
    """

    url: str
    symbol: str
    stream_types: list[str] = field(default_factory=list)
    ping_interval_s: float = 5.0
    ping_timeout_s: float = 15.0
    max_reconnect_attempts: int = 0  # 0 = unlimited
    backoff_base_s: float = 1.0
    backoff_max_s: float = 30.0


class WebSocketClient(abc.ABC):
    """Abstract base for WebSocket stream clients.

    Implementations:
      - BinanceWebSocketClient  (production)
      - BybitWebSocketClient    (production)
      - WebSocketSimulator      (test fixture)

    All implementations MUST:
    - Call on_message for every received message before any processing.
    - Raise on connection failure (never swallow errors).
    - Respect ping_interval_s and ping_timeout_s from config.
    - Implement exponential backoff per config on reconnect.
    """

    def __init__(self, config: WebSocketConfig, on_message: MessageCallback) -> None:
        self._config = config
        self._on_message = on_message

    @property
    def config(self) -> WebSocketConfig:
        return self._config

    @abc.abstractmethod
    def connect(self) -> None:
        """Establish WebSocket connection and begin receiving messages.

        Blocking call for sync implementations.
        Must call on_message for every message received.
        Must not return until connection is closed or an unrecoverable error occurs.
        """

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Close the WebSocket connection cleanly."""

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Returns True if the connection is currently active."""

    @abc.abstractmethod
    def send(self, message: dict) -> None:
        """Send a JSON-serialisable message to the server."""
