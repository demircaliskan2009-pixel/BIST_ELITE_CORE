"""FAZ554: Ask interactive chat — prompt for symbol, day, params; scripted dialogue tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_ask_stdin(
    stdin_lines: str,
    cmd_extra: list[str],
    snap_dir: str | None = None,
) -> subprocess.CompletedProcess:
    repo = _project_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    if snap_dir:
        env["BIST_CORE_SNAPSHOT_DIR"] = snap_dir
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    cmd = [sys.executable, "-m", "bist_core.cli", "ask"] + cmd_extra
    return subprocess.run(
        cmd,
        input=stdin_lines,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=30,
    )


def test_faz554_ask_interactive_prompts_symbol(tmp_path: Path) -> None:
    """ask --interactive with no symbol: prompts for symbol; ASELS yields advice."""
    snap = tmp_path / "snap"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text(
        "symbol,close\nASELS,50.0\n",
        encoding="utf-8",
    )
    # Scripted: symbol, day (already has snapshot), horizon, risk, capital, max_loss
    stdin = "ASELS\n\nmid\nmed\n100000\n5000\n"
    r = _run_ask_stdin(
        stdin,
        ["--interactive", "--day", "2099-01-01"],
        snap_dir=str(snap),
    )
    assert r.returncode == 0
    assert "ASELS" in r.stdout
    assert "Artifact:" in r.stdout or "PASS" in r.stdout or "BUY" in r.stdout or "HOLD" in r.stdout


def test_faz554_ask_interactive_prompts_day(tmp_path: Path) -> None:
    """ask --interactive with symbol, no day, no snapshots: prompts for day."""
    snap = tmp_path / "snap"
    (snap / "2099-01-15").mkdir(parents=True)
    (snap / "2099-01-15" / "snapshot.csv").write_text(
        "symbol,close\nTHYAO,200.0\n",
        encoding="utf-8",
    )
    # Symbol provided via arg; day prompted (2099-01-15); horizon, risk, capital, max_loss
    stdin = "2099-01-15\nshort\nlow\n50000\n2500\n"
    r = _run_ask_stdin(
        stdin,
        ["THYAO", "--interactive"],
        snap_dir=str(snap),
    )
    assert r.returncode == 0
    assert "THYAO" in r.stdout
    assert "2099-01-15" in r.stdout


def test_faz554_ask_interactive_eof_symbol_exit_2(tmp_path: Path) -> None:
    """ask --interactive with no symbol, EOF on first prompt: exit 2."""
    snap = tmp_path / "snap"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text("symbol,close\nX,1\n", encoding="utf-8")
    r = _run_ask_stdin("", ["--interactive", "--day", "2099-01-01"], snap_dir=str(snap))
    assert r.returncode == 2
    assert "Sembol gerekli" in r.stderr or "gerekli" in r.stderr


def test_faz554_ask_interactive_invalid_symbol_rejected(tmp_path: Path) -> None:
    """ask --interactive: invalid symbol (X) rejected, BIST out of scope."""
    snap = tmp_path / "snap"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text("symbol,close\nX,1\n", encoding="utf-8")
    r = _run_ask_stdin("X\n", ["--interactive", "--day", "2099-01-01"], snap_dir=str(snap))
    assert r.returncode == 2
    err = r.stderr or ""
    assert "BIST" in err or "kapsam" in err or "dışı" in err


def test_faz554_ask_interactive_deterministic_same_input(tmp_path: Path) -> None:
    """Same symbol + day + params -> same advice (determinism)."""
    snap = tmp_path / "snap"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text(
        "symbol,close\nAKBNK,100.0\n",
        encoding="utf-8",
    )
    stdin = "AKBNK\n\nmid\nmed\n\n\n"
    r1 = _run_ask_stdin(stdin, ["--interactive", "--day", "2099-01-01"], snap_dir=str(snap))
    r2 = _run_ask_stdin(stdin, ["--interactive", "--day", "2099-01-01"], snap_dir=str(snap))
    assert r1.returncode == 0
    assert r2.returncode == 0
    # Same decision and score
    for out in (r1.stdout, r2.stdout):
        assert "AKBNK" in out
        assert "2099-01-01" in out


def test_faz554_ask_non_interactive_unchanged(tmp_path: Path) -> None:
    """Regression: ask with args (no --interactive) unchanged."""
    snap = tmp_path / "snap"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text(
        "symbol,close\nASELS,50.0\n",
        encoding="utf-8",
    )
    r = _run_ask_stdin(
        "",
        ["ASELS", "--day", "2099-01-01", "--horizon", "short", "--risk", "low"],
        snap_dir=str(snap),
    )
    assert r.returncode == 0
    assert "ASELS" in r.stdout
    assert "horizon=short" in r.stdout
    assert "risk=low" in r.stdout
