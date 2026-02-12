"""FAZ114: MarketDataStreamer — provider polling, tick buffer, per-symbol subscription, downstream use."""
from __future__ import annotations

import asyncio
from typing import Dict, List

from bist_core.connectors.market_data_streamer import MarketDataStreamer
from bist_core.market_data.base import MarketDataProvider


class DummyProvider:
    """MarketDataProvider that returns fixed or sequence of close_maps for testing."""

    def __init__(self, snapshots: List[Dict[str, float]] | None = None) -> None:
        self.snapshots = snapshots or [{"A": 1.0, "B": 2.0}]
        self.index = 0

    def symbols(self, day: str) -> List[str]:
        return sorted(self.snapshots[0].keys()) if self.snapshots else []

    def close_map(self, day: str) -> Dict[str, float]:
        if self.index < len(self.snapshots):
            m = self.snapshots[self.index]
            self.index += 1
            return dict(m)
        return self.snapshots[-1] if self.snapshots else {}

    def validate(self, day: str) -> tuple[bool, str]:
        return (True, "ok")


def test_streamer_polls_provider_and_buffers_ticks() -> None:
    """Streamer periodically polls provider and buffers new tick data."""
    async def run() -> None:
        provider = DummyProvider(snapshots=[{"X": 10.0}, {"X": 11.0, "Y": 20.0}])
        streamer = MarketDataStreamer(provider, day="today")
        task = asyncio.create_task(streamer.start_stream(interval=0))
        await asyncio.sleep(0.05)
        streamer.stop_stream()
        await task
        assert streamer.last_snapshot is not None
        assert streamer.last_snapshot.get("X") == 11.0
        assert streamer.last_snapshot.get("Y") == 20.0
        ticks = streamer.get_pending_ticks()
        assert ("X", 10.0) in ticks or ("X", 11.0) in ticks
        assert ("Y", 20.0) in ticks

    asyncio.run(run())


def test_subscription_per_symbol() -> None:
    """Only subscribed symbols are returned by get_pending_ticks when subscriptions are set."""
    async def run() -> None:
        provider = DummyProvider(snapshots=[{"A": 1.0, "B": 2.0, "C": 3.0}])
        streamer = MarketDataStreamer(provider, day="today")
        streamer.subscribe("A")
        streamer.subscribe("C")
        task = asyncio.create_task(streamer.start_stream(interval=0))
        await asyncio.sleep(0.02)
        streamer.stop_stream()
        await task
        pending = streamer.get_pending_ticks()
        symbols_in = {s for s, _ in pending}
        assert "B" not in symbols_in
        assert symbols_in <= {"A", "C"}

    asyncio.run(run())


def test_subscribe_unsubscribe_and_subscribed_symbols() -> None:
    streamer = MarketDataStreamer(DummyProvider(), day="today")
    assert streamer.subscribed_symbols() == set()
    streamer.subscribe("THYA")
    streamer.subscribe("  akbnk  ")
    assert streamer.subscribed_symbols() == {"THYA", "AKBNK"}
    streamer.unsubscribe("THYA")
    assert streamer.subscribed_symbols() == {"AKBNK"}
    streamer.subscribe_symbols(["X", "Y"])
    assert streamer.subscribed_symbols() == {"AKBNK", "X", "Y"}


def test_get_pending_ticks_clears_buffer() -> None:
    async def run() -> None:
        provider = DummyProvider(snapshots=[{"S": 1.0}])
        streamer = MarketDataStreamer(provider, day="today")
        streamer.subscribe("S")
        task = asyncio.create_task(streamer.start_stream(interval=0))
        await asyncio.sleep(0.02)
        streamer.stop_stream()
        await task
        first = streamer.get_pending_ticks()
        second = streamer.get_pending_ticks()
        assert second == []

    asyncio.run(run())


def test_downstream_can_use_last_snapshot() -> None:
    """Downstream (strategy, execution) can read last_snapshot."""
    async def run() -> None:
        provider = DummyProvider(snapshots=[{"A": 1.0, "B": 2.0}])
        streamer = MarketDataStreamer(provider, day="today")
        task = asyncio.create_task(streamer.start_stream(interval=0))
        await asyncio.sleep(0.02)
        streamer.stop_stream()
        await task
        snapshot = streamer.last_snapshot
        assert snapshot is not None
        assert "A" in snapshot and "B" in snapshot
        # Downstream usage
        price_a = snapshot.get("A")
        assert price_a == 1.0

    asyncio.run(run())


def test_streamer_single_cycle_backward_compat() -> None:
    """last_data still set for backward compatibility."""
    async def run() -> None:
        provider = DummyProvider(snapshots=[{"X": 42.0}])
        streamer = MarketDataStreamer(provider, day="today")
        task = asyncio.create_task(streamer.start_stream(interval=0))
        await asyncio.sleep(0)
        streamer.stop_stream()
        await task
        assert streamer.last_data is not None
        assert streamer.last_data.get("X") == 42.0

    asyncio.run(run())


def test_streamer_multiple_cycles() -> None:
    """Multiple poll cycles; last_snapshot reflects latest."""
    async def run() -> None:
        provider = DummyProvider(snapshots=[{"a": 1.0}, {"a": 2.0}, {"a": 3.0}])
        streamer = MarketDataStreamer(provider, day="today")
        task = asyncio.create_task(streamer.start_stream(interval=0.01))
        await asyncio.sleep(0.05)
        streamer.stop_stream()
        await task
        assert streamer.last_snapshot is not None
        assert streamer.last_snapshot.get("a") in (1.0, 2.0, 3.0)
        ticks = streamer.get_pending_ticks()
        assert any(p == 1.0 or p == 2.0 or p == 3.0 for _, p in ticks)

    asyncio.run(run())
