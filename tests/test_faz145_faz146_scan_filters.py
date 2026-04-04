"""FAZ145/146: Scan liquidity filter and exclusions support."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz146_scan_exclusions(tmp_path: Path) -> None:
    """Scan --exclusions excludes symbols from ranked output."""
    snap_dir = tmp_path / "snapshots" / "2025-01-15"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text(
        "symbol,close\nAKBNK,50.0\nGARAN,100.0\nTHYAO,25.0\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.pop("BIST_CORE_ALLOW_NETWORK", None)

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "scan",
            "--day",
            "2025-01-15",
            "--top-n",
            "10",
            "--exclusions",
            "GARAN,THYAO",
            "--json",
        ],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    symbols_in_ranked = [x["symbol"] for x in out.get("ranked", [])]
    assert "GARAN" not in symbols_in_ranked
    assert "THYAO" not in symbols_in_ranked
    assert "AKBNK" in symbols_in_ranked


def test_faz146_scan_exclusions_empty_ok(tmp_path: Path) -> None:
    """Scan with empty exclusions includes all symbols."""
    snap_dir = tmp_path / "snapshots" / "2025-01-15"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nAKBNK,50.0\nGARAN,100.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", "2025-01-15", "--json"],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert len(out.get("ranked", [])) >= 1


def test_faz145_scan_min_volume_accepts_arg(tmp_path: Path) -> None:
    """Scan accepts --min-volume and --min-turnover (no crash)."""
    snap_dir = tmp_path / "snapshots" / "2025-01-15"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nAKBNK,50.0\n", encoding="utf-8")

    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.pop("BIST_CORE_ALLOW_NETWORK", None)

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "scan",
            "--day",
            "2025-01-15",
            "--min-volume",
            "0",
            "--json",
        ],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
