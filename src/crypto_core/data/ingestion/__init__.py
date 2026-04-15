"""ingestion package exports."""

from crypto_core.data.ingestion.data_ingestor import DataIngestor, EventCallback
from crypto_core.data.ingestion.websocket_client import MessageCallback, WebSocketClient, WebSocketConfig

__all__ = [
    "WebSocketClient",
    "WebSocketConfig",
    "MessageCallback",
    "DataIngestor",
    "EventCallback",
]
