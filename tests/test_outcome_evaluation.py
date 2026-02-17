"""Outcome evaluation for strategies — deterministic, offline, fail-closed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.advisory.outcome import (
    OUTCOME_SCHEMA_VERSION,
    evaluate_strategy,
    evaluate_and_append_outcomes,
)


def test_outcome_no_plan_returns_hold(tmp_path: Path) -> None:
    """Log entry without plan returns HOLD outcome."""
    log_entry = {"symbol": "AAA", "day": "2025-01-15", "strategy_detail": {}}
    snap = tmp_path / "snapshots"
    snap.mkdir()
    (snap / "2025-01-15").mkdir()
    (snap / "2025-01-15" / "snapshot.csv").write_text("symbol,close\nAAA,100.0\n", encoding="utf-8")

    outcome = evaluate_strategy(log_entry, snap)
    assert outcome is not None
    assert outcome["status"] == "HOLD"
    assert outcome["reason"] == "no_plan"
    assert outcome["symbol"] == "AAA"
    assert outcome["day"] == "2025-01-15"
    assert outcome["schema_version"] == OUTCOME_SCHEMA_VERSION
    assert "r_multiple" not in outcome or outcome.get("r_multiple") is None


def test_outcome_stop_hit_first(tmp_path: Path) -> None:
    """When low hits stop before high hits target, outcome is loss, R=-1."""
    # Day 1: close 100 (entry). Day 2: low 95 (stop at 96), high 98. Stop hit first.
    snap = tmp_path / "snapshots"
    (snap / "2025-01-15").mkdir(parents=True)
    (snap / "2025-01-16").mkdir(parents=True)
    (snap / "2025-01-15" / "snapshot.csv").write_text(
        "symbol,close,high,low\nAAA,100.0,101.0,99.0\n", encoding="utf-8"
    )
    (snap / "2025-01-16" / "snapshot.csv").write_text(
        "symbol,close,high,low\nAAA,97.0,98.0,95.0\n", encoding="utf-8"
    )

    log_entry = {
        "symbol": "AAA",
        "day": "2025-01-15",
        "strategy_detail": {
            "plan": {"entry": 101.0, "stop": 96.0, "t1": 105.0},
        },
    }
    outcome = evaluate_strategy(log_entry, snap)
    assert outcome is not None
    assert outcome["status"] == "loss"
    assert outcome["reason"] == "stop_hit"
    assert outcome["r_multiple"] == -1.0
    assert outcome["exit_price"] == 96.0
    assert outcome["exit_day"] == "2025-01-16"
    assert outcome["days_held"] == 1


def test_outcome_target_hit(tmp_path: Path) -> None:
    """When high hits target before low hits stop, outcome is win."""
    (tmp_path / "2025-01-15").mkdir(parents=True)
    (tmp_path / "2025-01-16").mkdir(parents=True)
    (tmp_path / "2025-01-15" / "snapshot.csv").write_text(
        "symbol,close,high,low\nAAA,100.0,101.0,99.0\n", encoding="utf-8"
    )
    (tmp_path / "2025-01-16" / "snapshot.csv").write_text(
        "symbol,close,high,low\nAAA,106.0,108.0,104.0\n", encoding="utf-8"
    )

    log_entry = {
        "symbol": "AAA",
        "day": "2025-01-15",
        "strategy_detail": {
            "plan": {"entry": 101.0, "stop": 96.0, "t1": 105.0},
        },
    }
    outcome = evaluate_strategy(log_entry, tmp_path)
    assert outcome is not None
    assert outcome["status"] == "win"
    assert outcome["reason"] == "target_hit"
    assert outcome["exit_price"] == 105.0
    assert outcome["exit_day"] == "2025-01-16"
    assert outcome["days_held"] == 1
    # R = (105 - 100) / (100 - 96) = 5/4 = 1.25 (entry_fill=100 from bar0.close)
    assert outcome["r_multiple"] == pytest.approx(1.25, rel=1e-3)


def test_outcome_no_bars_returns_hold(tmp_path: Path) -> None:
    """Missing snapshot for entry day returns HOLD."""
    log_entry = {
        "symbol": "XXX",
        "day": "2025-01-15",
        "strategy_detail": {"plan": {"entry": 100.0, "stop": 95.0, "t1": 108.0}},
    }
    outcome = evaluate_strategy(log_entry, tmp_path)
    assert outcome is not None
    assert outcome["status"] == "HOLD"
    assert outcome["reason"] == "no_bars"


def test_outcome_schema_required_keys(tmp_path: Path) -> None:
    """Outcome has required schema keys."""
    (tmp_path / "2025-01-15").mkdir(parents=True)
    (tmp_path / "2025-01-15" / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\n", encoding="utf-8"
    )
    log_entry = {
        "symbol": "AAA",
        "day": "2025-01-15",
        "strategy_detail": {"plan": {"entry": 101.0, "stop": 96.0, "t1": 105.0}},
    }
    outcome = evaluate_strategy(log_entry, tmp_path)
    assert outcome is not None
    required = {"schema_version", "symbol", "day", "status", "reason"}
    assert set(outcome.keys()) >= required


def test_evaluate_and_append_outcomes(tmp_path: Path) -> None:
    """evaluate_and_append_outcomes reads strategies, writes outcomes."""
    snap = tmp_path / "snapshots"
    (snap / "2025-01-15").mkdir(parents=True)
    (snap / "2025-01-16").mkdir(parents=True)
    (snap / "2025-01-15" / "snapshot.csv").write_text(
        "symbol,close,high,low\nAAA,100.0,101.0,99.0\n", encoding="utf-8"
    )
    (snap / "2025-01-16" / "snapshot.csv").write_text(
        "symbol,close,high,low\nAAA,106.0,108.0,104.0\n", encoding="utf-8"
    )

    strategies_path = tmp_path / "strategies.jsonl"
    strategies_path.write_text(
        json.dumps({
            "symbol": "AAA",
            "day": "2025-01-15",
            "strategy_detail": {"plan": {"entry": 101.0, "stop": 96.0, "t1": 105.0}},
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    outcomes_path = tmp_path / "outcomes.jsonl"
    count = evaluate_and_append_outcomes(strategies_path, snap, outcomes_path=outcomes_path)
    assert count == 1
    assert outcomes_path.exists()
    lines = [ln.strip() for ln in outcomes_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["status"] == "win"
    assert rec["symbol"] == "AAA"
