from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_rules_explain_deterministic(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": [
                    {
                        "id": "max_notional",
                        "type": "max_notional",
                        "max_notional": 100.0,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "rules",
        "explain",
        "--file",
        str(rules_path),
        "--symbol",
        "AAA",
        "--price",
        "1.0",
        "--side",
        "BUY",
        "--qty",
        "1.0",
        "--day",
        "2099-01-01",
    ]
    first = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    second = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
