"""processing package exports."""

from crypto_core.data.processing.book_manager import BookUpdateCallback, OrderBookManager
from crypto_core.data.processing.event_router import EventHandler, EventRouter
from crypto_core.data.processing.ohlcv_builder import BarClosedCallback, OHLCVBuilder
from crypto_core.data.processing.trade_processor import TradeStreamProcessor, ValidatedTradeCallback

__all__ = [
    "EventRouter",
    "EventHandler",
    "TradeStreamProcessor",
    "ValidatedTradeCallback",
    "OrderBookManager",
    "BookUpdateCallback",
    "OHLCVBuilder",
    "BarClosedCallback",
]
