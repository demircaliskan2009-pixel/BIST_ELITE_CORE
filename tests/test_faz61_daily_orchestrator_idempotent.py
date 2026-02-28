"""
FAZ61: CLI bist_core cli daily run --day --outdir [--live/--paper].
Tests: idempotent run (verify hash or reuse), no overwrite of differing artifacts; tmp dirs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_daily_run(
    day: str,
    outdir: Path,
    snapshot_dir: Path,
    live: bool = False,
    paper: bool = False,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_dir)
    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "daily",
        "run",
        "--day",
        day,
        "--outdir",
        str(outdir),
    ]
    if live:
        cmd.append("--live")
    if paper:
        cmd.append("--paper")
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


def test_faz61_daily_run_requires_day_and_outdir(tmp_path: Path) -> None:
    """Missing --day or --outdir -> non-zero exit (parser or daily run)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    # Missing --outdir
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "daily", "run", "--day", "2099-01-01"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    # Missing --day
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "daily", "run", "--outdir", str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0


def test_faz61_daily_run_first_run_creates_manifest(tmp_path: Path) -> None:
    """First run with snapshot creates pipeline manifest under outdir."""
    day = "2099-01-15"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / f"{day}.csv").write_text(
        "symbol,date,close\nAAA,2099-01-15,10\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    r = _run_daily_run(day, outdir, snap_dir)
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    # Manifest in one of the deterministic locations
    for candidate in (
        outdir / day / "pipeline_manifest.json",
        outdir / "pipeline_manifest.json",
        outdir / "_pipeline_manifest.json",
    ):
        if candidate.is_file():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            assert data.get("day") == day
            assert "snapshot_hash" in data or "stages" in data
            return
    pytest.fail("No pipeline_manifest.json found under outdir")


def test_faz61_daily_run_second_run_reuses_idempotent(tmp_path: Path) -> None:
    """Second run with same snapshot reuses existing artifacts (hash match); exit 0."""
    day = "2099-01-16"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / f"{day}.csv").write_text(
        "symbol,date,close\nBBB,2099-01-16,20\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    r1 = _run_daily_run(day, outdir, snap_dir)
    assert r1.returncode == 0, f"first run: stderr:\n{r1.stderr}"
    r2 = _run_daily_run(day, outdir, snap_dir)
    assert r2.returncode == 0, f"second run (reuse): stderr:\n{r2.stderr}"


def test_faz61_daily_run_differing_snapshot_exit_2(tmp_path: Path) -> None:
    """Existing manifest with snapshot_hash X and current snapshot hash != X -> exit 2 (do not overwrite)."""
    day = "2099-01-17"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / f"{day}.csv").write_text(
        "symbol,date,close\nCCC,2099-01-17,30\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / day).mkdir(parents=True, exist_ok=True)
    # Pre-create manifest with a snapshot_hash that will NOT match current file hash
    manifest = {
        "schema_version": 2,
        "day": day,
        "snapshot_hash": {"algo": "sha256", "value": "fake_hash_does_not_match"},
        "stages": {},
    }
    (outdir / day / "pipeline_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    r = _run_daily_run(day, outdir, snap_dir)
    assert r.returncode == 2
    assert "differ" in r.stderr.lower() or "overwrite" in r.stderr.lower() or "hash" in r.stderr.lower()


def test_faz61_daily_run_accepts_live_paper_flags(tmp_path: Path) -> None:
    """CLI accepts --paper; pipeline runs; execute may succeed or be blocked by risk gate in minimal env."""
    day = "2099-01-18"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / f"{day}.csv").write_text(
        "symbol,date,close\nDDD,2099-01-18,40\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    r = _run_daily_run(day, outdir, snap_dir, paper=True)
    # Pipeline runs; execute may return 0 or 2 (e.g. risk gate denied in minimal env)
    assert r.returncode in (0, 2)
    # Manifest must exist (pipeline ran)
    assert (outdir / day / "pipeline_manifest.json").is_file() or (outdir / "pipeline_manifest.json").is_file()
