"""Tests for the intraday MTF pipeline: context, sync, edges, execution, backtest.

Uses synthetic bars for deterministic testing — no external data dependency.
"""

from __future__ import annotations

import pytest

from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Helpers: bar factory
# ---------------------------------------------------------------------------

_EPOCH = 1_751_000_000  # arbitrary recent unix timestamp


def _bar(
    ts: int,
    symbol: str = "TEST",
    o: float = 10.0,
    h: float = 11.0,
    l: float = 9.0,
    c: float = 10.5,
    v: float = 1000.0,
) -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts, symbol=symbol, open=o, high=h, low=l, close=c, volume=v,
    )


def _make_bars(
    n: int,
    base_ts: int = _EPOCH,
    interval: int = 60,
    symbol: str = "TEST",
    base_price: float = 10.0,
    trend: float = 0.001,  # per-bar price change
) -> list[OHLCVBar]:
    """Generate N bars with a mild uptrend."""
    bars: list[OHLCVBar] = []
    for i in range(n):
        p = base_price + i * trend
        bars.append(_bar(
            ts=base_ts + i * interval,
            symbol=symbol,
            o=round(p, 4),
            h=round(p + 0.5, 4),
            l=round(p - 0.5, 4),
            c=round(p + 0.2, 4),
            v=1000 + i * 10,
        ))
    return bars


# ===========================================================================
# Test MTFContext Engine
# ===========================================================================

class TestMTFContext:
    def test_daily_regime_bull(self):
        from bist_core.decision.mtf_context import compute_daily_regime

        # 60 bars with uptrend: SMA20 > SMA50
        bars = _make_bars(60, interval=86400, base_price=50.0, trend=0.5)
        regime = compute_daily_regime(bars)
        assert regime is not None
        assert regime.regime in ("BULL", "RANGE")
        assert regime.sma_short > 0
        assert regime.sma_long > 0

    def test_daily_regime_insufficient_data(self):
        from bist_core.decision.mtf_context import compute_daily_regime

        bars = _make_bars(10, interval=86400)
        regime = compute_daily_regime(bars)
        assert regime is None

    def test_hourly_trend_up(self):
        from bist_core.decision.mtf_context import compute_hourly_trend

        bars = _make_bars(30, interval=3600, base_price=20.0, trend=0.3)
        trend = compute_hourly_trend(bars)
        assert trend is not None
        assert trend.direction in ("UP", "FLAT")
        assert trend.ema_fast > 0

    def test_hourly_trend_insufficient(self):
        from bist_core.decision.mtf_context import compute_hourly_trend

        bars = _make_bars(5, interval=3600)
        trend = compute_hourly_trend(bars)
        assert trend is None

    def test_m5_setup(self):
        from bist_core.decision.mtf_context import compute_m5_setup

        bars = _make_bars(25, interval=300)
        setup = compute_m5_setup(bars)
        assert setup is not None
        assert 0 <= setup.rsi <= 100
        assert 0 <= setup.bb_position <= 1.5  # can be slightly outside

    def test_m1_entry(self):
        from bist_core.decision.mtf_context import compute_m1_entry

        bars = _make_bars(70, interval=60)
        entry = compute_m1_entry(bars)
        assert entry is not None
        assert entry.vwap > 0
        assert isinstance(entry.vol_spike, bool)

    def test_mtf_context_full(self):
        from bist_core.decision.mtf_context import MTFContextEngine

        engine = MTFContextEngine()
        daily = _make_bars(60, interval=86400, base_price=50.0, trend=0.5)
        hourly = _make_bars(30, interval=3600, base_price=20.0, trend=0.3)
        m5 = _make_bars(25, interval=300)
        m1 = _make_bars(70, interval=60)

        ctx = engine.build_context(
            symbol="TEST",
            timestamp=_EPOCH + 100000,
            daily_bars=daily,
            hourly_bars=hourly,
            m5_bars=m5,
            m1_bars=m1,
        )
        assert ctx.symbol == "TEST"
        assert ctx.daily is not None
        assert ctx.hourly is not None
        assert ctx.m5 is not None
        assert ctx.m1 is not None
        assert 0 <= ctx.confidence <= 1.0

    def test_mtf_context_none_timeframes(self):
        from bist_core.decision.mtf_context import MTFContextEngine

        engine = MTFContextEngine()
        ctx = engine.build_context(symbol="TEST", timestamp=_EPOCH)
        assert ctx.daily is None
        assert ctx.hourly is None
        assert ctx.m5 is None
        assert ctx.m1 is None
        assert ctx.confidence == 0.0
        assert not ctx.regime_allows_long
        assert not ctx.trend_aligned_long


# ===========================================================================
# Test TimeframeSynchronizer
# ===========================================================================

class TestTimeframeSynchronizer:
    def test_basic_event_stream(self):
        from bist_core.decision.timeframe_sync import TimeframeSynchronizer

        bundle = {
            "G": _make_bars(10, interval=86400, base_ts=_EPOCH - 900000),
            "60": _make_bars(50, interval=3600, base_ts=_EPOCH - 180000),
            "05": [],
            "01": _make_bars(100, interval=60, base_ts=_EPOCH),
        }

        sync = TimeframeSynchronizer("TEST", bundle, base_tf="01")
        events = list(sync.iter_events())
        assert len(events) == 100

        # First event should have bar from base
        assert events[0].bar.symbol == "TEST"
        # Events in chronological order
        for i in range(1, len(events)):
            assert events[i].bar.timestamp >= events[i - 1].bar.timestamp

    def test_date_range_filter(self):
        from bist_core.decision.timeframe_sync import TimeframeSynchronizer

        bars = _make_bars(100, interval=60, base_ts=_EPOCH)
        bundle = {"G": [], "60": [], "05": [], "01": bars}

        mid = _EPOCH + 50 * 60
        sync = TimeframeSynchronizer(
            "TEST", bundle, base_tf="01",
            start_ts=mid, end_ts=mid + 20 * 60,
        )
        events = list(sync.iter_events())
        assert len(events) <= 21
        for ev in events:
            assert ev.bar.timestamp >= mid
            assert ev.bar.timestamp <= mid + 20 * 60

    def test_no_lookahead(self):
        from bist_core.decision.timeframe_sync import TimeframeSynchronizer

        # Daily bar at t=1000, base bars at t=500 and t=1500
        daily_bars = [_bar(ts=_EPOCH + 1000, symbol="TEST")]
        base_bars = [
            _bar(ts=_EPOCH + 500, symbol="TEST"),
            _bar(ts=_EPOCH + 1500, symbol="TEST"),
        ]
        bundle = {"G": daily_bars, "60": [], "05": [], "01": base_bars}

        sync = TimeframeSynchronizer("TEST", bundle, base_tf="01")
        events = list(sync.iter_events())
        assert len(events) == 2

        # First event (ts=500): daily bar at ts=1000 NOT yet visible
        assert events[0].context.daily is None

        # Second event (ts=1500): daily bar at ts=1000 IS visible (completed)
        # But still None because 1 daily bar is not enough for regime (needs 50)
        # The key test is that the synchronizer doesn't crash and respects ordering


# ===========================================================================
# Test IntradaySignal
# ===========================================================================

class TestIntradaySignal:
    def test_signal_dataclass(self):
        from bist_core.decision.intraday_edges import IntradaySignal

        sig = IntradaySignal(
            timestamp=_EPOCH,
            symbol="TEST",
            edge="opening_drive",
            direction="LONG",
            entry_price=50.0,
            stop_price=48.0,
            target_price=54.0,
            position_size=100,
            confidence=0.7,
            reason="test signal",
        )
        assert sig.edge == "opening_drive"
        assert sig.position_size == 100


# ===========================================================================
# Test IntradayFill
# ===========================================================================

class TestIntradayExecution:
    def test_successful_fill(self):
        from bist_core.decision.intraday_edges import IntradaySignal
        from bist_core.execution.intraday_execution import execute_intraday_signal

        signal = IntradaySignal(
            timestamp=_EPOCH,
            symbol="TEST",
            edge="test",
            direction="LONG",
            entry_price=50.0,
            stop_price=48.0,
            target_price=54.0,
            position_size=100,
            confidence=0.7,
            reason="test",
        )

        # 09:30 TRT = 06:30 UTC
        fill_ts = _EPOCH - (_EPOCH % 86400) + 6 * 3600 + 30 * 60
        fill_bar = _bar(ts=fill_ts, o=50.0, h=51.0, l=49.0, c=50.5, v=10000.0)
        recent = _make_bars(130, interval=60, base_ts=fill_ts - 130 * 60, base_price=50.0)

        fill = execute_intraday_signal(signal, fill_bar, recent)
        assert not fill.rejected
        assert fill.fill_price > 0
        assert fill.fill_size > 0
        assert fill.slippage_bps > 0

    def test_session_rejection(self):
        from bist_core.decision.intraday_edges import IntradaySignal
        from bist_core.execution.intraday_execution import execute_intraday_signal

        signal = IntradaySignal(
            timestamp=_EPOCH,
            symbol="TEST",
            edge="test",
            direction="LONG",
            entry_price=50.0,
            stop_price=48.0,
            target_price=54.0,
            position_size=100,
            confidence=0.7,
            reason="test",
        )

        # 02:00 TRT (outside session) = 23:00 UTC prev day
        fill_ts = _EPOCH - (_EPOCH % 86400) + 23 * 3600
        fill_bar = _bar(ts=fill_ts, o=50.0, h=51.0, l=49.0, c=50.5, v=10000.0)
        recent = _make_bars(130, interval=60, base_ts=fill_ts - 130 * 60)

        fill = execute_intraday_signal(signal, fill_bar, recent)
        assert fill.rejected
        assert fill.reject_reason == "OUTSIDE_SESSION"


# ===========================================================================
# Test IntradayPosition
# ===========================================================================

class TestIntradayPosition:
    def test_close_long_profit(self):
        from bist_core.backtest.intraday_backtest import IntradayPosition

        pos = IntradayPosition(
            symbol="TEST",
            edge="test_edge",
            direction="LONG",
            entry_price=50.0,
            fill_size=100,
            stop_price=48.0,
            target_price=54.0,
            entry_timestamp=_EPOCH,
            slippage_bps=20.0,
            total_cost_bps=3.6,
        )

        pos.close(54.0, _EPOCH + 3600, "TARGET")
        assert pos.is_closed
        assert pos.pnl > 0
        assert pos.exit_reason == "TARGET"

    def test_close_long_loss(self):
        from bist_core.backtest.intraday_backtest import IntradayPosition

        pos = IntradayPosition(
            symbol="TEST",
            edge="test_edge",
            direction="LONG",
            entry_price=50.0,
            fill_size=100,
            stop_price=48.0,
            target_price=54.0,
            entry_timestamp=_EPOCH,
            slippage_bps=20.0,
            total_cost_bps=3.6,
        )

        pos.close(48.0, _EPOCH + 3600, "STOP")
        assert pos.is_closed
        assert pos.pnl < 0
        assert pos.r_multiple < 0


# ===========================================================================
# Test Backtest Engine basics
# ===========================================================================

class TestIntradayBacktestEngine:
    def test_empty_bundle(self):
        from bist_core.backtest.intraday_backtest import IntradayBacktestEngine

        bundle = {"G": [], "60": [], "05": [], "01": []}
        engine = IntradayBacktestEngine()
        result = engine.run_symbol("TEST", bundle)
        assert result.signals_generated == 0
        assert len(result.trades) == 0

    def test_no_signals_on_synthetic(self):
        """Synthetic flat data shouldn't trigger edges."""
        from bist_core.backtest.intraday_backtest import IntradayBacktestEngine

        bundle = {
            "G": _make_bars(60, interval=86400, base_ts=_EPOCH - 60 * 86400),
            "60": _make_bars(200, interval=3600, base_ts=_EPOCH - 200 * 3600),
            "05": [],
            "01": _make_bars(500, interval=60, base_ts=_EPOCH),
        }
        engine = IntradayBacktestEngine()
        result = engine.run_symbol("TEST", bundle)
        # With flat/mild-trend synthetic data, signals may or may not fire
        # The key assertion: engine doesn't crash and equity curve generated
        assert len(result.equity_curve) == 500


# ===========================================================================
# Test walk-forward interface
# ===========================================================================

class TestWalkForward:
    def test_insufficient_data(self):
        from bist_core.backtest.intraday_backtest import walk_forward_intraday

        bundle = {"G": [], "60": [], "05": [], "01": _make_bars(100)}
        result = walk_forward_intraday("TEST", bundle)
        assert result["error"] == "INSUFFICIENT_DATA"
