"""FAZ39: Walk-forward backtest — deterministic windows, gate fail behavior, artifacts exist."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz39_deterministic_windows(tmp_path: Path) -> None:
    """Same walk-forward config produces same window splits and per-window metrics."""
    from bist_core.services.backtest import walk_forward, _walk_forward_windows
    from datetime import date as Date

    # Deterministic window splits
    windows = _walk_forward_windows(Date(2099, 7, 1), Date(2099, 7, 10), window_days=3, step_days=2)
    assert len(windows) >= 2
    assert windows[0][0].isoformat() == "2099-07-01"
    assert windows[0][1].isoformat() == "2099-07-03"
    assert windows[1][0].isoformat() == "2099-07-03"
    assert windows[1][1].isoformat() == "2099-07-05"

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-07-01", "2099-07-02", "2099-07-03", "2099-07-04", "2099-07-05", "2099-07-06"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nA,10.0\nB,20.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    run_config = {
        "snapshot_root": snapshot_root,
        "date_from": "2099-07-01",
        "date_to": "2099-07-06",
        "outdir": outdir,
        "strategy": "equal_weight",
        "top_n": 2,
        "window": 3,
        "step": 2,
        "min_trades": None,
        "max_dd": None,
        "strict": False,
    }
    result1 = walk_forward(run_config)
    result2 = walk_forward(run_config)
    assert result1["num_windows"] == result2["num_windows"]
    assert result1["gates_passed"] == result2["gates_passed"]
    a1 = result1["aggregate"]
    a2 = result2["aggregate"]
    assert a1["total_fills"] == a2["total_fills"]
    assert a1["worst_max_drawdown"] == a2["worst_max_drawdown"]
    assert a1["mean_return"] == a2["mean_return"]


def test_faz39_gate_fail_strict_exit_nonzero_artifacts_written(tmp_path: Path) -> None:
    """When gate fails and --strict: exit nonzero but manifest + metrics still written."""
    from bist_core.services.backtest import walk_forward

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-07-10", "2099-07-11"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nX,1.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    # min_trades=1000 will fail (we get few fills in 2 days)
    run_config = {
        "snapshot_root": snapshot_root,
        "date_from": "2099-07-10",
        "date_to": "2099-07-11",
        "outdir": outdir,
        "strategy": "equal_weight",
        "top_n": 10,
        "window": 2,
        "step": 1,
        "min_trades": 1000,
        "max_dd": None,
        "strict": True,
    }
    result = walk_forward(run_config)
    assert result["gates_passed"] is False
    assert result["exit_code"] == 2
    wf_dir = outdir / "backtest" / "walk_forward"
    assert (wf_dir / "manifest.json").is_file()
    assert (wf_dir / "aggregate_metrics.json").is_file()
    assert (outdir / "backtest" / "_walk_forward_manifest.json").is_file()
    loaded = json.loads((wf_dir / "aggregate_metrics.json").read_text(encoding="utf-8"))
    assert loaded.get("gates_passed") is False
    assert loaded.get("total_fills", 0) < 1000


def test_faz39_artifacts_exist(tmp_path: Path) -> None:
    """Walk-forward writes manifest + aggregate_metrics + windows/<from>_<to>/ in deterministic locations."""
    from bist_core.services.backtest import walk_forward

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-07-20", "2099-07-21", "2099-07-22"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nY,5.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    run_config = {
        "snapshot_root": snapshot_root,
        "date_from": "2099-07-20",
        "date_to": "2099-07-22",
        "outdir": outdir,
        "strategy": "equal_weight",
        "top_n": 5,
        "window": 2,
        "step": 1,
        "strict": False,
    }
    result = walk_forward(run_config)
    wf_dir = outdir / "backtest" / "walk_forward"
    assert (wf_dir / "manifest.json").is_file()
    assert (wf_dir / "aggregate_metrics.json").is_file()
    assert (wf_dir / "_manifest.json").is_file()
    assert (outdir / "backtest" / "_walk_forward_manifest.json").is_file()
    manifest = json.loads((wf_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("walk_forward") is True
    assert "windows" in manifest
    assert "aggregate" in manifest
    windows_dir = wf_dir / "windows"
    assert windows_dir.is_dir()
    for w in result.get("windows", []):
        key = f"{w['date_from']}_{w['date_to']}"
        win_dir = windows_dir / key
        assert win_dir.is_dir()
        assert (win_dir / "backtest" / "metrics.json").is_file()
        assert (win_dir / "backtest" / "equity_curve.csv").is_file()


def test_faz39_cli_walk_forward_strict_gate_fail(tmp_path: Path) -> None:
    """CLI --walk-forward --strict with failing gate: exit code 2, artifacts written."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-07-30", "2099-07-31"]:
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
            "2099-07-30",
            "--to",
            "2099-07-31",
            "--outdir",
            str(outdir),
            "--snapshot-root",
            str(snapshot_root),
            "--walk-forward",
            "--window",
            "2",
            "--step",
            "1",
            "--min-trades",
            "99999",
            "--strict",
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 2
    out = json.loads(result.stdout)
    assert out.get("gates_passed") is False
    assert out.get("exit_code") == 2
    assert (outdir / "backtest" / "walk_forward" / "manifest.json").is_file()
    assert (outdir / "backtest" / "walk_forward" / "aggregate_metrics.json").is_file()
