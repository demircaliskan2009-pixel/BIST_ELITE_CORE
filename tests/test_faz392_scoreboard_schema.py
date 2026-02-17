"""FAZ392: Scoreboard (backtest metrics) schema_version, day, params, metrics keys, empty run."""
from __future__ import annotations

import json
from pathlib import Path

from bist_core.services.backtest import run_backtest


def test_faz392_scoreboard_schema_version(tmp_path: Path) -> None:
    """Backtest metrics.json has schema_version, day (date_from/date_to), params (strategy, top_n), metrics keys."""
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / "2099-01-01").mkdir(parents=True)
    (snapshot_root / "2099-01-01" / "snapshot.csv").write_text(
        "symbol,close\nA,10.0\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    result = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-01-01",
        date_to="2099-01-01",
        outdir=outdir,
        strategy="equal_weight",
        top_n=10,
    )
    assert result.get("error") is None
    metrics_path = outdir / "backtest" / "metrics.json"
    assert metrics_path.is_file()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics.get("schema_version") == 1
    assert "date_from" in metrics
    assert "date_to" in metrics
    assert metrics.get("strategy") == "equal_weight"
    assert metrics.get("top_n") == 10
    required = {"schema_version", "date_from", "date_to", "num_days", "strategy", "top_n"}
    assert required.issubset(metrics.keys())


def test_faz392_scoreboard_empty_metrics(tmp_path: Path) -> None:
    """No snapshots in range -> empty run; metrics still valid schema (num_days=0 or no symbols)."""
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / "2099-02-01").mkdir(parents=True)
    (snapshot_root / "2099-02-01" / "snapshot.csv").write_text(
        "symbol,close\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    result = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-02-01",
        date_to="2099-02-01",
        outdir=outdir,
        strategy="equal_weight",
        top_n=10,
    )
    assert result.get("error") is None
    metrics_path = outdir / "backtest" / "metrics.json"
    assert metrics_path.is_file()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics.get("schema_version") == 1
    assert metrics.get("date_from") == "2099-02-01"
    assert metrics.get("date_to") == "2099-02-01"
    assert "num_days" in metrics
    assert "total_fills" in metrics
