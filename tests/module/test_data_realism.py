"""Tests for data_realism — deterministic data imperfection simulation."""

from __future__ import annotations

from bist_core.data.data_realism import (
    _bar_hash,
    apply_stale_price_lag,
    data_quality_report,
    detect_gaps,
    detect_spikes,
    opening_spread_penalty_bps,
    simulate_missing_bars,
)
from bist_core.models.ohlcv import OHLCVBar


def _make_bar(
    sym: str = "TEST",
    ts: int = 1_700_000_000,
    o: float = 100.0,
    h: float = 101.0,
    l: float = 99.0,
    c: float = 100.5,
    v: float = 1_000_000.0,
) -> OHLCVBar:
    return OHLCVBar(timestamp=ts, symbol=sym, open=o, high=h, low=l, close=c, volume=v)


def _make_series(
    n: int,
    sym: str = "TEST",
    base_close: float = 100.0,
    step: float = 0.0,
) -> list[OHLCVBar]:
    """Create n bars with monotonically increasing (or flat) closes."""
    return [
        _make_bar(
            sym=sym,
            ts=1_700_000_000 + i * 86400,
            o=base_close + i * step,
            h=base_close + i * step + 1.0,
            l=base_close + i * step - 1.0,
            c=base_close + i * step,
            v=1_000_000.0,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _bar_hash
# ---------------------------------------------------------------------------


class TestBarHash:
    def test_deterministic(self) -> None:
        bar = _make_bar()
        h1 = _bar_hash(bar, seed=42)
        h2 = _bar_hash(bar, seed=42)
        assert h1 == h2

    def test_different_seed(self) -> None:
        bar = _make_bar()
        h1 = _bar_hash(bar, seed=42)
        h2 = _bar_hash(bar, seed=99)
        assert h1 != h2

    def test_different_symbol(self) -> None:
        b1 = _make_bar(sym="AAAA")
        b2 = _make_bar(sym="BBBB")
        assert _bar_hash(b1) != _bar_hash(b2)


# ---------------------------------------------------------------------------
# simulate_missing_bars
# ---------------------------------------------------------------------------


class TestSimulateMissingBars:
    def test_zero_pct_returns_all(self) -> None:
        bars = _make_series(100)
        result = simulate_missing_bars(bars, missing_pct=0.0)
        assert len(result) == 100

    def test_drops_some_bars(self) -> None:
        bars = _make_series(500)
        result = simulate_missing_bars(bars, missing_pct=0.05)  # 5% for clear signal
        assert len(result) < 500
        assert len(result) > 400  # reasonable range

    def test_warmup_protected(self) -> None:
        """First 60 bars per symbol must NEVER be dropped."""
        bars = _make_series(200)
        result = simulate_missing_bars(bars, missing_pct=0.10)  # aggressive
        # First 60 bars should all be present
        first_60_ts = {b.timestamp for b in bars[:60]}
        result_ts = {b.timestamp for b in result}
        assert first_60_ts.issubset(result_ts)

    def test_no_consecutive_drops(self) -> None:
        """Never drop two consecutive bars for same symbol."""
        bars = _make_series(500)
        result = simulate_missing_bars(bars, missing_pct=0.10)
        result_ts = {b.timestamp for b in result}
        all_ts = [b.timestamp for b in bars]
        for i in range(1, len(all_ts)):
            if all_ts[i - 1] not in result_ts:
                # If prev was dropped, current MUST be present
                assert all_ts[i] in result_ts

    def test_deterministic(self) -> None:
        bars = _make_series(200)
        r1 = simulate_missing_bars(bars)
        r2 = simulate_missing_bars(bars)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.timestamp == b.timestamp

    def test_multi_symbol(self) -> None:
        bars_a = _make_series(100, sym="AAA")
        bars_b = _make_series(100, sym="BBB")
        combined = bars_a + bars_b
        result = simulate_missing_bars(combined, missing_pct=0.015)
        assert len(result) < 200


# ---------------------------------------------------------------------------
# detect_gaps
# ---------------------------------------------------------------------------


class TestDetectGaps:
    def test_no_gaps_flat(self) -> None:
        bars = _make_series(10)
        assert detect_gaps(bars) == []

    def test_gap_up(self) -> None:
        bars = [
            _make_bar(ts=1, c=100.0),
            _make_bar(ts=2, o=104.0, c=105.0),  # 4% gap-up
        ]
        gaps = detect_gaps(bars, threshold_pct=0.03)
        assert len(gaps) == 1
        assert gaps[0]["direction"] == "up"
        assert gaps[0]["gap_pct"] > 0.03

    def test_gap_down(self) -> None:
        bars = [
            _make_bar(ts=1, c=100.0),
            _make_bar(ts=2, o=95.0, c=96.0),  # -5% gap-down
        ]
        gaps = detect_gaps(bars, threshold_pct=0.03)
        assert len(gaps) == 1
        assert gaps[0]["direction"] == "down"

    def test_small_gap_below_threshold(self) -> None:
        bars = [
            _make_bar(ts=1, c=100.0),
            _make_bar(ts=2, o=101.0, c=101.0),  # 1% gap — below 3%
        ]
        assert detect_gaps(bars, threshold_pct=0.03) == []


# ---------------------------------------------------------------------------
# detect_spikes
# ---------------------------------------------------------------------------


class TestDetectSpikes:
    def test_no_spike_normal(self) -> None:
        bars = [_make_bar(h=101.0, l=99.0, c=100.0)]
        assert detect_spikes(bars, threshold_pct=0.08) == []

    def test_spike_detected(self) -> None:
        bars = [_make_bar(h=110.0, l=99.0, c=100.0)]  # 11% range
        spikes = detect_spikes(bars, threshold_pct=0.08)
        assert len(spikes) == 1
        assert spikes[0]["range_pct"] >= 0.08

    def test_zero_close_skipped(self) -> None:
        bars = [_make_bar(h=10.0, l=1.0, c=0.0)]
        assert detect_spikes(bars) == []


# ---------------------------------------------------------------------------
# apply_stale_price_lag
# ---------------------------------------------------------------------------


class TestStalePriceLag:
    def test_same_length(self) -> None:
        bars = _make_series(10)
        result = apply_stale_price_lag(bars)
        assert len(result) == 10

    def test_no_mutation(self) -> None:
        bars = _make_series(5)
        result = apply_stale_price_lag(bars)
        for orig, lagged in zip(bars, result):
            assert orig.close == lagged.close  # bars not modified


# ---------------------------------------------------------------------------
# opening_spread_penalty_bps
# ---------------------------------------------------------------------------


class TestOpeningSpreadPenalty:
    def test_no_gap(self) -> None:
        bar = _make_bar(o=100.0)
        penalty = opening_spread_penalty_bps(bar, prev_close=100.0)
        assert penalty >= 5.0  # base opening spread
        assert penalty <= 10.0  # no gap → just base

    def test_gap_increases_penalty(self) -> None:
        bar = _make_bar(o=105.0)
        penalty = opening_spread_penalty_bps(bar, prev_close=100.0)
        assert penalty > 5.0  # gap adds extra

    def test_cap_at_30(self) -> None:
        bar = _make_bar(o=120.0)  # 20% gap
        penalty = opening_spread_penalty_bps(bar, prev_close=100.0)
        assert penalty == 30.0  # capped

    def test_zero_prev_close(self) -> None:
        bar = _make_bar(o=100.0)
        assert opening_spread_penalty_bps(bar, prev_close=0.0) == 0.0

    def test_zero_open(self) -> None:
        bar = _make_bar(o=0.0)
        assert opening_spread_penalty_bps(bar, prev_close=100.0) == 0.0


# ---------------------------------------------------------------------------
# data_quality_report
# ---------------------------------------------------------------------------


class TestDataQualityReport:
    def test_clean_data(self) -> None:
        bars = _make_series(50)
        report = data_quality_report(bars)
        assert report["total_bars"] == 50
        assert report["symbols"] == 1
        assert report["gaps_detected"] == 0
        assert report["spikes_detected"] == 0
        assert report["zero_volume_bars"] == 0
        assert report["duplicate_bars"] == 0

    def test_detects_zero_volume(self) -> None:
        bars = [_make_bar(v=0.0), _make_bar(ts=2, v=100.0)]
        report = data_quality_report(bars)
        assert report["zero_volume_bars"] == 1

    def test_detects_duplicates(self) -> None:
        b = _make_bar()
        report = data_quality_report([b, b])
        assert report["duplicate_bars"] == 1

    def test_multi_symbol_count(self) -> None:
        bars = _make_series(10, sym="AAA") + _make_series(10, sym="BBB")
        report = data_quality_report(bars)
        assert report["symbols"] == 2
