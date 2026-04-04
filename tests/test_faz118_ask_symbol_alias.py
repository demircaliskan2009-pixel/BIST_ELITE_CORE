"""FAZ118-HOTFIX-TRNUM+UX: ask --symbol QNBFK alias."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_faz118_ask_symbol_alias_accepts_flag(tmp_path: Path) -> None:
    """argparse: ask --symbol QNBFK --day 2099-02-01 kabul eder."""
    snap = tmp_path / "snap"
    (snap / "2099-02-01").mkdir(parents=True)
    (snap / "2099-02-01" / "snapshot.csv").write_text("symbol,close\nQNBFK,10.0\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap)

    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "--symbol", "QNBFK", "--day", "2099-02-01"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert r.returncode == 0
    assert "QNBFK" in r.stdout or "PASS" in r.stdout or "BUY" in r.stdout or "WATCH" in r.stdout


def test_faz118_ask_positional_still_works(tmp_path: Path) -> None:
    """ask QNBFK (positional) hâlâ çalışır."""
    snap = tmp_path / "snap"
    (snap / "2099-02-01").mkdir(parents=True)
    (snap / "2099-02-01" / "snapshot.csv").write_text("symbol,close\nQNBFK,10.0\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap)

    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "QNBFK", "--day", "2099-02-01"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert r.returncode == 0
    assert "QNBFK" in r.stdout or "PASS" in r.stdout
