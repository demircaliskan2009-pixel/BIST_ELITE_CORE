"""Connectors: KAP, Matriks terminal, market data streamer, order bridge and other disclosure/data ingesters (fixture-first, no network in tests)."""
from bist_core.connectors.kap import ingest_from_html, ingest_from_json, normalize_to_knowledge_doc
from bist_core.connectors.market_data_streamer import MarketDataStreamer
from bist_core.connectors.matriks_terminal_adapter import MatriksMarketDataProvider, MatriksTerminalAdapter
from bist_core.connectors.order_bridge_base import OrderBridgeInterface
from bist_core.connectors.order_bridge_dll import OrderBridge, OrderBridgeDLL

__all__ = [
    "ingest_from_html",
    "ingest_from_json",
    "normalize_to_knowledge_doc",
    "MarketDataStreamer",
    "MatriksMarketDataProvider",
    "MatriksTerminalAdapter",
    "OrderBridge",
    "OrderBridgeDLL",
    "OrderBridgeInterface",
]
