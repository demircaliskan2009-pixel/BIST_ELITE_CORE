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


def test_cli_data_load_json(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    registry_path = tmp_path / "registry.json"
    csv_root = tmp_path / "csvs"
    csv_root.mkdir(parents=True, exist_ok=True)

    (csv_root / "part1.csv").write_text(
        "symbol,date,close\nAAA,2025-01-01,10.0\nBBB,2025-01-02,11.0\n",
        encoding="utf-8",
        newline="\n",
    )
    (csv_root / "part2.csv").write_text(
        "symbol,date,close\nAAA,2025-01-03,12.0\n",
        encoding="utf-8",
        newline="\n",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_REGISTRY_PATH"] = str(registry_path)
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env["BIST_CORE_HOME"] = str(tmp_path / "home")

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

    cp2 = _run_cli(["data", "load", "--name", "eq_daily", "--json"], env)
    assert cp2.returncode == 0, cp2.stdout + "\n" + cp2.stderr
    payload = json.loads(cp2.stdout)
    assert payload["name"] == "eq_daily"
    assert payload["rows"] == 3
    assert "symbol" in payload["cols"]
    assert "date" in payload["cols"]
    assert "close" in payload["cols"]
    assert payload["date_min"] <= payload["date_max"]
