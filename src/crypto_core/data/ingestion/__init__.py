"""ingestion package exports."""

from crypto_core.data.ingestion.binance_ws_client import BinanceWebSocketClient
from crypto_core.data.ingestion.bybit_ws_client import BybitWebSocketClient
from crypto_core.data.ingestion.data_ingestor import DataIngestor, EventCallback
from crypto_core.data.ingestion.stream_config import (
    BINANCE_FUTURES_WS_BASE,
    BINANCE_STANDARD_STREAMS,
    BYBIT_LINEAR_WS_BASE,
    BYBIT_STANDARD_TOPICS,
    build_binance_futures_url,
    build_bybit_subscribe_msg,
)
from crypto_core.data.ingestion.websocket_client import MessageCallback, WebSocketClient, WebSocketConfig

__all__ = [
    # Abstract interface
    "WebSocketClient",
    "WebSocketConfig",
    "MessageCallback",
    # Concrete clients
    "BinanceWebSocketClient",
    "BybitWebSocketClient",
    # Orchestrator
    "DataIngestor",
    "EventCallback",
    # Stream configuration helpers
    "BINANCE_FUTURES_WS_BASE",
    "BINANCE_STANDARD_STREAMS",
    "BYBIT_LINEAR_WS_BASE",
    "BYBIT_STANDARD_TOPICS",
    "build_binance_futures_url",
    "build_bybit_subscribe_msg",
]
