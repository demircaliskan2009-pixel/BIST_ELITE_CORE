from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_ask_fail_closed_output():
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
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    assert stdout, "stdout boş olmamalı"
    assert "güvenli mod" in stdout.lower()
    assert "RuntimeWarning" not in stderr
