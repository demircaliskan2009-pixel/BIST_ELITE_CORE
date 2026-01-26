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


def test_registry_persists_to_bist_core_home(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    csv_root = tmp_path / "csvs"
    csv_root.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_HOME"] = str(home)

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

    reg_path = home / "registry.json"
    assert reg_path.exists()

    payload = json.loads(reg_path.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == 1
    ds = payload.get("datasets") or {}
    assert "eq_daily" in ds
