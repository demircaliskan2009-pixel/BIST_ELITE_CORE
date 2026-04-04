"""PerformanceTracker — alpha phase PnL and reward."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bist_core.live.performance_tracker import PerformanceTracker


def test_performance_tracker_empty_metrics() -> None:
    t = PerformanceTracker()
    m = t.compute_metrics()
    assert m["trades"] == 0
    assert m["total_pnl"] == 0


def test_performance_tracker_entry_exit_metrics() -> None:
    t = PerformanceTracker()
    ts = datetime.now(timezone.utc)
    t.on_entry("ASELS", 100.0, 1.0, ts)
    t.on_exit("ASELS", 110.0, ts)
    m = t.compute_metrics()
    assert m["trades"] == 1
    assert m["winrate"] == 1.0
    assert m["total_pnl"] == pytest.approx(0.1)
    assert "expectancy" in m


def test_performance_tracker_multiple_trades() -> None:
    t = PerformanceTracker()
    ts = datetime.now(timezone.utc)
    t.on_entry("A", 50.0, 1.0, ts)
    t.on_exit("A", 55.0, ts)
    t.on_entry("B", 100.0, 0.5, ts)
    t.on_exit("B", 94.0, ts)
    m = t.compute_metrics()
    assert m["trades"] == 2
    assert m["winrate"] == 0.5
    assert m["total_pnl"] == pytest.approx((55.0 - 50.0) / 50.0 + (94.0 - 100.0) / 100.0)
    assert "expectancy" in m
