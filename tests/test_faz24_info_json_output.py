from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_info_json_output() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "info",
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "registry_path" in payload
    assert "datasets" in payload
    assert "symbols" in payload
