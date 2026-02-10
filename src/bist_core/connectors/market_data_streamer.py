"""
FAZ114: MarketDataStreamer — Sürekli canlı veri toplamak için adaptör üzerinden asenkron akış.
Adaptörün get_data() belirtilen aralıklarla çağrılır; son veri last_data'da tutulur.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional


class MarketDataStreamer:
    """Adaptörden belirtilen aralıklarla veri toplayan asenkron streamer. stop_stream() ile durdurulur."""

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter
        self.last_data: Optional[Any] = None
        self._running = False

    async def start_stream(self, interval: float = 1.0) -> None:
        """Veriyi belirtilen aralıklarla asenkron olarak toplamaya başlar."""
        self._running = True
        while self._running:
            data = self.adapter.get_data()
            self.last_data = data
            await asyncio.sleep(interval)

    def stop_stream(self) -> None:
        """Veri akışını durdurur."""
        self._running = False
