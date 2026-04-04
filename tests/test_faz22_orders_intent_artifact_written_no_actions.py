from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_orders_intent_artifact_written_no_actions(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day = "2099-02-01"
    day_dir = snapshot_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

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
            "--orders-strategy",
            "deny_all",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0

    orders_path = outdir / "orders" / day / "orders_intent.json"
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    assert payload["strategy"]["name"] == "deny_all"
    assert payload["actions"] == []
    assert "no_actions" in payload["notes"]

    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    orders_stage = manifest["stages"]["orders"]
    assert orders_stage["path"] == str(orders_path)
    assert "no_actions" in orders_stage["notes"]
