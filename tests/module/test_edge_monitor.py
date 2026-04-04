"""EdgeMonitor — history and summary."""

from __future__ import annotations

from bist_core.analysis.edge_monitor import EdgeMonitor


def test_summary_empty() -> None:
    m = EdgeMonitor()
    assert m.summary() == {}


def test_log_and_summary() -> None:
    m = EdgeMonitor()
    m.log(10, 0.05)
    s = m.summary()
    assert s["edges"] == 10
    assert s["avg_exp"] == 0.05
    assert s["trend"] == "up"


def test_trend_flat() -> None:
    m = EdgeMonitor()
    m.log(5, 0.0)
    assert m.summary()["trend"] == "flat"
