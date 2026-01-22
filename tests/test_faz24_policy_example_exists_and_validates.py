from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_policy_example_exists_and_validates(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    example_path = repo_root / "src" / "bist_core" / "policy" / "bist_ruleset.example.json"
    assert example_path.exists()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "rules",
            "validate",
            "--file",
            str(example_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
