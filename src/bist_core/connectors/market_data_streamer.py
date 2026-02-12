"""
FAZ114: MarketDataStreamer — periyodik MarketDataProvider polling, tick buffer, sembol bazlı abonelik.
Downstream (strategy, execution) get_pending_ticks() veya last_snapshot ile kullanabilir.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple

from bist_core.market_data.base import MarketDataProvider


class MarketDataStreamer:
    """
    Periodically polls a MarketDataProvider and buffers new tick data.
    Supports subscription per symbol; downstream components consume via get_pending_ticks() or last_snapshot.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        day: str = "today",
    ) -> None:
        self._provider = provider
        self._day = day
        self._subscribed: Set[str] = set()
        self._last_prices: Dict[str, float] = {}
        self._tick_buffer: List[Tuple[str, float]] = []
        self._running = False
        self.last_snapshot: Optional[Dict[str, float]] = None
        # Backward compatibility: same shape as before for adapters used as provider-wrapped
        self.last_data: Optional[Dict[str, float]] = None

    def subscribe(self, symbol: str) -> None:
        """Subscribe to ticks for one symbol."""
        self._subscribed.add(symbol.strip().upper())

    def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from one symbol."""
        self._subscribed.discard(symbol.strip().upper())

    def subscribe_symbols(self, symbols: List[str]) -> None:
        """Subscribe to multiple symbols."""
        for s in symbols:
            self.subscribe(s)

    def subscribed_symbols(self) -> Set[str]:
        """Return current set of subscribed symbols (copy)."""
        return set(self._subscribed)

    def get_pending_ticks(self) -> List[Tuple[str, float]]:
        """
        Return and clear buffered ticks for subscribed symbols.
        If no symbols are subscribed, returns all buffered ticks (for backward compatibility).
        Each item is (symbol, price).
        """
        if not self._tick_buffer:
            return []
        if self._subscribed:
            out = [(s, p) for s, p in self._tick_buffer if s in self._subscribed]
            self._tick_buffer = [(s, p) for s, p in self._tick_buffer if s not in self._subscribed]
        else:
            out = list(self._tick_buffer)
            self._tick_buffer = []
        return out

    async def start_stream(self, interval: float = 1.0) -> None:
        """Periodically poll the provider and buffer new tick data; runs until stop_stream()."""
        self._running = True
        while self._running:
            try:
                close_map = self._provider.close_map(self._day)
            except Exception:
                close_map = {}
            if isinstance(close_map, dict):
                self.last_snapshot = dict(close_map)
                self.last_data = self.last_snapshot
                for symbol, price in close_map.items():
                    if self._last_prices.get(symbol) != price:
                        self._tick_buffer.append((symbol, price))
                        self._last_prices[symbol] = price
            await asyncio.sleep(interval)

    def stop_stream(self) -> None:
        """Stop the polling loop."""
        self._running = False
