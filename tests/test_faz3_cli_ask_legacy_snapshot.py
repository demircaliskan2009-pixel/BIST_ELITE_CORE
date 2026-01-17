from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_ask_legacy_snapshot(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nASELS,\n",
        encoding="utf-8",
    )

    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "ask",
            "ASELS",
            "--day",
            "2099-01-01",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.stdout.strip()
    assert "güvenli mod" in result.stdout.lower()
    assert "RuntimeWarning" not in result.stderr
