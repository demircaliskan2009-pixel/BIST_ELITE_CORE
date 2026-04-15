"""Tests for OHLCVBuilder — multi-timeframe bar construction from trade stream.

Covers:
- First trade opens a new bar
- Bar accumulates high/low/close/volume correctly
- Bar closes when trade timestamp enters new period
- Closed bar is emitted via callback
- Multiple intervals build simultaneously
- UTC-alignment of bar boundaries
- Determinism: same input → same bars
"""

from __future__ import annotations

from typing import List

import pytest

from crypto_core.data.models.ohlcv import OHLCVBar
from crypto_core.data.processing.ohlcv_builder import OHLCVBuilder, _bar_open_time
from tests.crypto_core.data.fixtures.trade_replay import make_trade, make_trade_sequence


# ──────────────────────────────────────────────────────────────────
# Bar open time alignment
# ──────────────────────────────────────────────────────────────────

class TestBarOpenTime:
    def test_1m_alignment(self):
        # 1m = 60_000_000_000 ns
        interval_ns = 60_000_000_000
        ts = 1_700_000_000_500_000_000  # mid-minute
        expected = (ts // interval_ns) * interval_ns
        assert _bar_open_time(ts, interval_ns) == expected

    def test_boundary_exactly_on_bar_start(self):
        interval_ns = 60_000_000_000
        ts = 1_700_000_040_000_000_000  # exact minute boundary (1_700_000_040 % 60 == 0)
        assert _bar_open_time(ts, interval_ns) == ts


# ──────────────────────────────────────────────────────────────────
# Single interval
# ──────────────────────────────────────────────────────────────────

class TestSingleInterval:
    _START_NS = 1_700_000_000_000_000_000
    _1M_NS = 60_000_000_000

    def _builder(self, closed_bars: List[OHLCVBar] = None) -> OHLCVBuilder:
        if closed_bars is None:
            closed_bars = []
        return OHLCVBuilder(
            symbol="BTCUSDT",
            exchange="binance",
            intervals=["1m"],
            on_bar_closed=closed_bars.append,
        )

    def test_first_trade_opens_bar(self):
        builder = self._builder()
        t = make_trade("1", price=50_000.0, timestamp_ns=self._START_NS)
        builder.on_trade(t)
        bar = builder.current_bar("1m")
        assert bar is not None
        assert bar.open_price == 50_000.0
        assert not bar.is_closed

    def test_bar_accumulates_high_low(self):
        builder = self._builder()
        t1 = make_trade("1", price=50_000.0, timestamp_ns=self._START_NS, sequence_no=1)
        t2 = make_trade("2", price=51_000.0, timestamp_ns=self._START_NS + 1_000_000_000, sequence_no=2)
        t3 = make_trade("3", price=49_000.0, timestamp_ns=self._START_NS + 2_000_000_000, sequence_no=3)
        builder.on_trade(t1)
        builder.on_trade(t2)
        builder.on_trade(t3)
        bar = builder.current_bar("1m")
        assert bar.high_price == 51_000.0
        assert bar.low_price == 49_000.0
        assert bar.close_price == 49_000.0
        assert bar.trade_count == 3

    def test_bar_closes_on_new_period(self):
        closed: List[OHLCVBar] = []
        builder = self._builder(closed)
        # Align to a clean minute boundary
        bar_open_ns = (self._START_NS // self._1M_NS) * self._1M_NS
        next_period_ns = bar_open_ns + self._1M_NS  # start of next minute

        t1 = make_trade("1", price=50_000.0, timestamp_ns=bar_open_ns, sequence_no=1)
        t2 = make_trade("2", price=51_000.0, timestamp_ns=next_period_ns, sequence_no=2)
        builder.on_trade(t1)
        builder.on_trade(t2)

        assert len(closed) == 1
        assert closed[0].is_closed
        assert closed[0].open_price == 50_000.0

    def test_volume_accumulates_correctly(self):
        builder = self._builder()
        t1 = make_trade("1", price=50_000.0, qty=0.1, timestamp_ns=self._START_NS, sequence_no=1)
        t2 = make_trade("2", price=50_000.0, qty=0.2, timestamp_ns=self._START_NS + 1_000_000_000, sequence_no=2)
        builder.on_trade(t1)
        builder.on_trade(t2)
        bar = builder.current_bar("1m")
        assert abs(bar.volume - 0.3) < 1e-9

    def test_no_bar_before_trades(self):
        builder = self._builder()
        assert builder.current_bar("1m") is None


# ──────────────────────────────────────────────────────────────────
# Multiple intervals
# ──────────────────────────────────────────────────────────────────

class TestMultipleIntervals:
    _START_NS = 1_700_000_000_000_000_000
    _1M_NS = 60_000_000_000
    _5M_NS = 300_000_000_000

    def test_both_intervals_accumulate(self):
        builder = OHLCVBuilder(
            symbol="BTCUSDT",
            exchange="binance",
            intervals=["1m", "5m"],
        )
        t = make_trade("1", price=50_000.0, timestamp_ns=self._START_NS)
        builder.on_trade(t)
        assert builder.current_bar("1m") is not None
        assert builder.current_bar("5m") is not None

    def test_1m_closes_before_5m(self):
        closed_1m: List[OHLCVBar] = []
        closed_5m: List[OHLCVBar] = []
        builder = OHLCVBuilder(
            symbol="BTCUSDT",
            exchange="binance",
            intervals=["1m", "5m"],
            on_bar_closed=lambda bar: (closed_1m if bar.interval == "1m" else closed_5m).append(bar),
        )
        bar_open_ns = (self._START_NS // self._1M_NS) * self._1M_NS
        next_1m_ns = bar_open_ns + self._1M_NS

        t1 = make_trade("1", price=50_000.0, timestamp_ns=bar_open_ns, sequence_no=1)
        # jump to next 1m but still within same 5m bar
        t2 = make_trade("2", price=51_000.0, timestamp_ns=next_1m_ns, sequence_no=2)

        builder.on_trade(t1)
        builder.on_trade(t2)

        assert len(closed_1m) == 1
        assert len(closed_5m) == 0  # 5m bar still open


# ──────────────────────────────────────────────────────────────────
# Determinism
# ──────────────────────────────────────────────────────────────────

class TestDeterminism:
    _START_NS = 1_700_000_000_000_000_000

    def test_same_input_produces_same_bars(self):
        trades = make_trade_sequence(100, start_ns=self._START_NS)

        closed_a: List[OHLCVBar] = []
        builder_a = OHLCVBuilder("BTCUSDT", "binance", intervals=["1m"], on_bar_closed=closed_a.append)
        for t in trades:
            builder_a.on_trade(t)

        closed_b: List[OHLCVBar] = []
        builder_b = OHLCVBuilder("BTCUSDT", "binance", intervals=["1m"], on_bar_closed=closed_b.append)
        for t in trades:
            builder_b.on_trade(t)

        assert len(closed_a) == len(closed_b)
        for a, b in zip(closed_a, closed_b):
            assert a == b


# ──────────────────────────────────────────────────────────────────
# Invalid interval rejected
# ──────────────────────────────────────────────────────────────────

class TestInvalidInterval:
    def test_unsupported_interval_raises(self):
        with pytest.raises(ValueError, match="unsupported intervals"):
            OHLCVBuilder("BTCUSDT", "binance", intervals=["99m"])
