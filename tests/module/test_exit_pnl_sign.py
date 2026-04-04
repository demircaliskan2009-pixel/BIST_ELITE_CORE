"""Exit PnL sign: long/short fractional return and reason vs pnl assertions."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.live.execution_runtime import PaperExecution
from bist_core.live.state_store import LiveState
from bist_core.live.trade_logger import TradeLogger


def test_paper_exit_long_target_profitable() -> None:
    st = LiveState()
    pe = PaperExecution(st)
    assert (
        pe.execute("L", "enter", 100.0, volatility=0.001, edge_score=0.65)
        is not None
    )
    r = pe.execute(
        "L",
        "exit",
        110.0,
        volatility=0.001,
        reason="target_hit|test",
    )
    assert r is not None
    assert float(r["pnl"]) > 0


def test_paper_exit_short_target_profitable() -> None:
    st = LiveState()
    pe = PaperExecution(st)
    assert (
        pe.execute(
            "S",
            "enter",
            100.0,
            volatility=0.001,
            position_side="short",
            edge_score=0.65,
        )
        is not None
    )
    r = pe.execute(
        "S",
        "exit",
        90.0,
        volatility=0.001,
        reason="target_hit|test",
    )
    assert r is not None
    assert float(r["pnl"]) > 0


def test_paper_exit_long_stop_loss_loss() -> None:
    st = LiveState()
    pe = PaperExecution(st)
    assert (
        pe.execute("L2", "enter", 100.0, volatility=0.001, edge_score=0.65)
        is not None
    )
    r = pe.execute(
        "L2",
        "exit",
        90.0,
        volatility=0.001,
        reason="stop_loss|test",
    )
    assert r is not None
    assert float(r["pnl"]) < 0


def test_paper_exit_target_hit_negative_raises() -> None:
    st = LiveState()
    pe = PaperExecution(st)
    assert (
        pe.execute("L3", "enter", 100.0, volatility=0.001, edge_score=0.65)
        is not None
    )
    with pytest.raises(RuntimeError, match="INVALID PNL: target_hit"):
        pe.execute(
            "L3",
            "exit",
            90.0,
            volatility=0.001,
            reason="target_hit|test",
        )


def test_trade_logger_csv_target_hit_sign(tmp_path: Path) -> None:
    log_path = tmp_path / "t.csv"
    tl = TradeLogger(str(log_path))
    assert tl.log_new_trade(
        {
            "symbol": "Z",
            "action": "enter_long",
            "entry": 100.0,
            "stop_loss": 90.0,
            "target": 110.0,
            "edge_score": 0.1,
            "confidence": 0.5,
        }
    )
    assert tl.update_trade("Z", 110.0, reason="target_hit")
    rows = tl._read_rows()
    closed = [r for r in rows if "CLOSED" in str(r.get("status", "")).upper()]
    assert len(closed) == 1
    assert "CLOSED_WIN" in closed[0]["status"]


def test_trade_logger_target_hit_bad_raises(tmp_path: Path) -> None:
    log_path = tmp_path / "t2.csv"
    tl = TradeLogger(str(log_path))
    assert tl.log_new_trade(
        {
            "symbol": "Y",
            "action": "enter_long",
            "entry": 100.0,
            "stop_loss": 90.0,
            "target": 110.0,
            "edge_score": 0.1,
            "confidence": 0.5,
        }
    )
    with pytest.raises(RuntimeError, match="INVALID PNL: target_hit"):
        tl.update_trade("Y", 90.0, reason="target_hit")


def test_performance_tracker_short_win_is_positive() -> None:
    from datetime import datetime, timezone

    from bist_core.live.performance_tracker import PerformanceTracker

    t = PerformanceTracker()
    ts = datetime.now(timezone.utc)
    t.on_entry("SH", 100.0, 1.0, ts, side="short")
    t.on_exit("SH", 90.0, ts)
    m = t.compute_metrics()
    assert m["trades"] == 1
    assert m["total_pnl"] == pytest.approx(0.1)
