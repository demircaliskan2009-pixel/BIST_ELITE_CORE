from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def test_cli_data_register_list_snapshot(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    csv_root = tmp_path / "csvs"
    out = tmp_path / "out" / "snap.csv"
    csv_root.mkdir(parents=True, exist_ok=True)

    # minimal deterministic csv (single day)
    (csv_root / "part1.csv").write_text(
        "symbol,date,close\nAAA,2025-01-02,10.0\n",
        encoding="utf-8",
        newline="\n",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_HOME"] = str(home)
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")

    cp = _run_cli(
        [
            "data",
            "register",
            "--name",
            "eq_daily",
            "--path",
            str(csv_root),
            "--format",
            "csv",
            "--symbol-col",
            "symbol",
            "--date-col",
            "date",
        ],
        env,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr

    cp2 = _run_cli(["data", "list", "--json"], env)
    assert cp2.returncode == 0, cp2.stdout + "\n" + cp2.stderr
    payload = json.loads(cp2.stdout)
    assert "eq_daily" in (payload.get("datasets") or {})

    out.parent.mkdir(parents=True, exist_ok=True)
    cp3 = _run_cli(
        ["data", "snapshot", "--name", "eq_daily", "--day", "2025-01-02", "--out", str(out)],
        env,
    )
    assert cp3.returncode == 0, cp3.stdout + "\n" + cp3.stderr
    assert out.exists()
    txt = out.read_text(encoding="utf-8", errors="replace")
    assert "AAA" in txt
