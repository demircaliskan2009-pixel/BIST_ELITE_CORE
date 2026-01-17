from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_utf8_json_output() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "ask",
        "ASELS",
        "--day",
        "2099-01-01",
        "--json",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        env=env,
        check=False,
    )

    stdout = result.stdout.decode("utf-8", errors="replace")
    assert "G\u00fcvenli mod" in stdout
