"""PaperTracker — equity and winrate."""

from __future__ import annotations

from bist_core.analysis.paper_tracker import PaperTracker


def test_record_and_stats() -> None:
    p = PaperTracker()
    p.record("X", 10.0, 11.0, 100.0, "test")
    s = p.stats()
    assert s["total_trades"] == 1
    assert s["winrate"] == 1.0
    assert s["equity"] == 100_000.0 + 100.0


def test_record_invalid_skips() -> None:
    p = PaperTracker()
    p.record("X", 0.0, 10.0, 1.0, "x")
    assert p.stats()["total_trades"] == 0


def test_pnl_override() -> None:
    p = PaperTracker()
    p.record("X", 10.0, 12.0, 1.0, "x", pnl=5.0)
    assert p.trades[0]["pnl"] == 5.0
