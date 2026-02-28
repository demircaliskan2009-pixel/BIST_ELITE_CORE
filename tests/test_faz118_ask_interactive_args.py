"""FAZ118-STEP2: Ask command --interactive, --horizon, --risk, --capital, --max-loss-tl."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_ask(cmd_extra: list[str], env: dict | None = None, snap_dir: str | None = None) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parents[1]
    e = os.environ.copy()
    e["PYTHONPATH"] = str(repo_root / "src")
    if snap_dir:
        e["BIST_CORE_SNAPSHOT_DIR"] = snap_dir
    if env:
        e.update(env)
    cmd = [sys.executable, "-m", "bist_core.cli", "ask", "AAA", "--day", "2099-01-01"] + cmd_extra
    return subprocess.run(cmd, capture_output=True, text=True, env=e, timeout=15)


def test_faz118_ask_accepts_new_args_non_interactive(tmp_path: Path) -> None:
    """Ask parser accepts --horizon, --risk, --capital, --max-loss-tl; non-interactive flow unchanged."""
    snap = tmp_path / "snap"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text("symbol,close\nAAA,10.0\n", encoding="utf-8")

    r = _run_ask(
        ["--horizon", "short", "--risk", "low", "--capital", "100000", "--max-loss-tl", "5000"],
        snap_dir=str(snap),
    )
    assert r.returncode == 0
    assert "AAA" in r.stdout or "PASS" in r.stdout or "BUY" in r.stdout or "WATCH" in r.stdout


def test_faz118_ask_bist_out_of_scope_exit_2() -> None:
    """Invalid symbol format (too short) -> BIST kapsamı dışı, exit 2."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "X", "--day", "2099-01-01"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert r.returncode == 2
    assert "BIST kapsamı dışı" in r.stderr


def test_faz118_ask_params_in_output_when_provided(tmp_path: Path) -> None:
    """When --horizon/--risk/--capital/--max-loss-tl given, params appear in output."""
    snap = tmp_path / "snap"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text("symbol,close\nAAA,10.0\n", encoding="utf-8")

    r = _run_ask(
        ["--horizon", "mid", "--risk", "med", "--capital", "50000", "--max-loss-tl", "2500"],
        snap_dir=str(snap),
    )
    assert r.returncode == 0
    assert "horizon=mid" in r.stdout
    assert "risk=med" in r.stdout
    assert "50000" in r.stdout or "50" in r.stdout
    assert "2500" in r.stdout or "25" in r.stdout
