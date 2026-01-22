from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_eod_orders_failclosed_when_blocked(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day = "2099-01-05"
    day_dir = snapshot_root / day
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": [
                    {
                        "id": "trading_disabled",
                        "type": "trading_disabled",
                        "enabled": True,
                        "action": "deny",
                        "reason": "trading_disabled",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    outdir = tmp_path / "run_out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--emit-orders",
            "--policy-file",
            str(policy_path),
            "--strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 2
    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    orders_stage = manifest["stages"]["orders"]
    assert orders_stage["ok"] == 0
    assert "blocked_by_policy" in orders_stage["notes"]
