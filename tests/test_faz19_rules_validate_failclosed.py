from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_rules_validate_failclosed(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps({"schema_version": 2, "rules": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "rules",
            "validate",
            "--file",
            str(rules_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["errors"]
