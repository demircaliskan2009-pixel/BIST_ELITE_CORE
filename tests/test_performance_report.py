"""Performance report — win-rate, avg R, max DD, equity curve. Deterministic."""
from __future__ import annotations

import json
from pathlib import Path

from bist_core.advisory.performance import (
    PERFORMANCE_SCHEMA_VERSION,
    build_performance_report,
    write_performance_csv,
    write_performance_json,
)


def test_performance_empty_outcomes_returns_zeros(tmp_path: Path) -> None:
    """Missing or empty outcomes => zeros, empty curve."""
    report = build_performance_report(outcomes_path=tmp_path / "nonexistent.jsonl")
    assert report["trade_count"] == 0
    assert report["win_rate"] == 0.0
    assert report["avg_r"] == 0.0
    assert report["total_r"] == 0.0
    assert report["max_dd"] == 0.0
    assert report["equity_curve"] == []
    assert report["schema_version"] == PERFORMANCE_SCHEMA_VERSION


def test_performance_known_results(tmp_path: Path) -> None:
    """Fixture: 3 wins (R=1), 2 losses (R=-1) => win_rate 0.6, avg_r 0.2, total_r 1."""
    outcomes = [
        {"symbol": "A", "day": "2025-01-01", "status": "win", "r_multiple": 1.0, "exit_day": "2025-01-05"},
        {"symbol": "B", "day": "2025-01-02", "status": "loss", "r_multiple": -1.0, "exit_day": "2025-01-06"},
        {"symbol": "C", "day": "2025-01-03", "status": "win", "r_multiple": 1.0, "exit_day": "2025-01-07"},
        {"symbol": "D", "day": "2025-01-04", "status": "loss", "r_multiple": -1.0, "exit_day": "2025-01-08"},
        {"symbol": "E", "day": "2025-01-05", "status": "win", "r_multiple": 1.0, "exit_day": "2025-01-09"},
    ]
    path = tmp_path / "outcomes.jsonl"
    path.write_text("\n".join(json.dumps(o) for o in outcomes) + "\n", encoding="utf-8")

    report = build_performance_report(outcomes_path=path)
    assert report["trade_count"] == 5
    assert report["win_count"] == 3
    assert report["loss_count"] == 2
    assert report["win_rate"] == 0.6
    assert report["avg_r"] == 0.2
    assert report["total_r"] == 1.0
    assert len(report["equity_curve"]) == 5


def test_performance_hold_excluded(tmp_path: Path) -> None:
    """HOLD outcomes excluded from metrics."""
    outcomes = [
        {"symbol": "A", "day": "2025-01-01", "status": "HOLD", "reason": "no_plan"},
        {"symbol": "B", "day": "2025-01-02", "status": "win", "r_multiple": 1.0, "exit_day": "2025-01-06"},
    ]
    path = tmp_path / "outcomes.jsonl"
    path.write_text("\n".join(json.dumps(o) for o in outcomes) + "\n", encoding="utf-8")

    report = build_performance_report(outcomes_path=path)
    assert report["trade_count"] == 1
    assert report["win_count"] == 1
    assert report["win_rate"] == 1.0
    assert report["avg_r"] == 1.0
    assert report["total_r"] == 1.0


def test_performance_max_dd(tmp_path: Path) -> None:
    """Max drawdown from equity curve."""
    outcomes = [
        {"symbol": "A", "day": "2025-01-01", "status": "win", "r_multiple": 2.0, "exit_day": "2025-01-05"},
        {"symbol": "B", "day": "2025-01-02", "status": "loss", "r_multiple": -3.0, "exit_day": "2025-01-06"},
        {"symbol": "C", "day": "2025-01-03", "status": "win", "r_multiple": 1.0, "exit_day": "2025-01-07"},
    ]
    path = tmp_path / "outcomes.jsonl"
    path.write_text("\n".join(json.dumps(o) for o in outcomes) + "\n", encoding="utf-8")

    report = build_performance_report(outcomes_path=path)
    assert report["trade_count"] == 3
    assert report["total_r"] == 0.0
    assert report["max_dd"] == 3.0


def test_performance_write_csv(tmp_path: Path) -> None:
    """write_performance_csv produces valid CSV."""
    report = {
        "trade_count": 2,
        "win_count": 1,
        "loss_count": 1,
        "win_rate": 0.5,
        "avg_r": 0.0,
        "total_r": 0.0,
        "max_dd": 0.0,
    }
    out = tmp_path / "report.csv"
    write_performance_csv(report, out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "win_rate,0.5" in text
    assert "trade_count,2" in text


def test_performance_write_json(tmp_path: Path) -> None:
    """write_performance_json produces valid JSON."""
    report = {"trade_count": 1, "win_rate": 1.0, "avg_r": 0.5}
    out = tmp_path / "report.json"
    write_performance_json(report, out)
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["trade_count"] == 1
    assert loaded["win_rate"] == 1.0
