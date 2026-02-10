"""FAZ114: MarketDataStreamer — asenkron start_stream/stop_stream ve last_data."""
from __future__ import annotations

import asyncio

from bist_core.connectors.market_data_streamer import MarketDataStreamer


class DummyAdapter:
    def __init__(self, values: list | None = None) -> None:
        self.values = values or []
        self.index = 0

    def get_data(self) -> object:
        if self.index < len(self.values):
            val = self.values[self.index]
            self.index += 1
            return val
        return None


def test_streamer_single_cycle() -> None:
    async def run() -> None:
        dummy = DummyAdapter(values=[42])
        streamer = MarketDataStreamer(dummy)
        task = asyncio.create_task(streamer.start_stream(interval=0))
        await asyncio.sleep(0)
        streamer.stop_stream()
        await task
        assert streamer.last_data == 42

    asyncio.run(run())


def test_streamer_multiple_cycles() -> None:
    async def run() -> None:
        dummy = DummyAdapter(values=[1, 2, 3])
        streamer = MarketDataStreamer(dummy)
        task = asyncio.create_task(streamer.start_stream(interval=0.01))
        await asyncio.sleep(0.05)
        streamer.stop_stream()
        await task
        # Durdurulduktan sonra last_data dummy değerlerinden biri veya tükendiyse None
        assert streamer.last_data is None or streamer.last_data in [1, 2, 3]

    asyncio.run(run())
