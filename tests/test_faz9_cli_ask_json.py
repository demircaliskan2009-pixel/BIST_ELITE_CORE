from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_ask_json_lines_all(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / "snapshots"
    day_dir = snapshots_dir / "2099-01-01"
    day_dir.mkdir(parents=True)
    snapshot_path = day_dir / "snapshot.csv"
    snapshot_path.write_text(
        "symbol,close\nAAA,10.0\nBBB,20.0\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshots_dir)

    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "ask",
        "AAA",
        "--day",
        "2099-01-01",
        "--all",
        "--json",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    stdout = result.stdout.strip()
    assert stdout, "stdout boş olmamalı"

    lines = [line for line in stdout.splitlines() if line.strip()]
    assert len(lines) == 2

    for line in lines:
        payload = json.loads(line)
        assert payload["symbol"] in {"AAA", "BBB"}
        assert payload["day"] == "2099-01-01"
        assert set(payload.keys()) == {
            "symbol",
            "day",
            "decision_raw",
            "score",
            "signals",
            "plan",
            "text",
        }
