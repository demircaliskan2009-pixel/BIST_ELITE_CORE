"""FAZ38: Backtest harness — walk-forward deterministic; metrics + equity_curve."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz38_tiny_3day_synthetic_deterministic(tmp_path: Path) -> None:
    """Tiny 3-day synthetic run is deterministic: same inputs => same metrics and equity curve."""
    from bist_core.services.backtest import run_backtest

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-06-01", "2099-06-02", "2099-06-03"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nA,10.0\nB,20.0\nC,30.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    metrics1 = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-06-01",
        date_to="2099-06-03",
        outdir=outdir,
        strategy="equal_weight",
        top_n=2,
    )
    metrics2 = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-06-01",
        date_to="2099-06-03",
        outdir=tmp_path / "out2",
        strategy="equal_weight",
        top_n=2,
    )
    assert metrics1.get("error") is None
    assert metrics2.get("error") is None
    assert metrics1["num_days"] == 3
    assert metrics2["num_days"] == 3
    assert metrics1["total_return"] == metrics2["total_return"]
    assert metrics1["final_equity"] == metrics2["final_equity"]
    assert metrics1["max_drawdown"] == metrics2["max_drawdown"]

    curve1_path = Path(metrics1["equity_curve_path"])
    curve2_path = Path(metrics2["equity_curve_path"])
    assert curve1_path.is_file()
    assert curve2_path.is_file()
    with curve1_path.open(encoding="utf-8") as handle:
        rows1 = list(csv.DictReader(handle))
    with curve2_path.open(encoding="utf-8") as handle:
        rows2 = list(csv.DictReader(handle))
    assert len(rows1) == 3
    assert len(rows2) == 3
    for r1, r2 in zip(rows1, rows2):
        assert r1["day"] == r2["day"]
        assert float(r1["equity"]) == float(r2["equity"])


def test_faz38_metrics_keys_exist(tmp_path: Path) -> None:
    """Backtest output metrics.json has required keys."""
    from bist_core.services.backtest import run_backtest

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-06-04", "2099-06-05"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nX,5.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    metrics = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-06-04",
        date_to="2099-06-05",
        outdir=outdir,
        strategy="equal_weight",
        top_n=10,
    )
    assert metrics.get("error") is None
    required = [
        "schema_version",
        "date_from",
        "date_to",
        "num_days",
        "strategy",
        "top_n",
        "initial_equity",
        "final_equity",
        "total_return",
        "max_drawdown",
        "total_fills",
        "equity_curve_path",
        "metrics_path",
    ]
    for k in required:
        assert k in metrics, f"missing key: {k}"

    backtest_dir = outdir / "backtest"
    assert (backtest_dir / "metrics.json").is_file()
    assert (backtest_dir / "equity_curve.csv").is_file()
    loaded = json.loads((backtest_dir / "metrics.json").read_text(encoding="utf-8"))
    for k in ["schema_version", "num_days", "total_return", "max_drawdown"]:
        assert k in loaded


def test_faz38_cli_backtest_run(tmp_path: Path) -> None:
    """CLI: bist_core backtest run --from --to --outdir writes backtest/metrics.json and equity_curve.csv."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-06-10", "2099-06-11"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nZ,1.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "backtest",
            "run",
            "--from",
            "2099-06-10",
            "--to",
            "2099-06-11",
            "--outdir",
            str(outdir),
            "--snapshot-root",
            str(snapshot_root),
            "--strategy",
            "equal_weight",
            "--top-n",
            "5",
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out.get("num_days") == 2
    assert "total_return" in out
    assert "metrics_path" in out
    assert "equity_curve_path" in out
    assert (outdir / "backtest" / "metrics.json").is_file()
    assert (outdir / "backtest" / "equity_curve.csv").is_file()
