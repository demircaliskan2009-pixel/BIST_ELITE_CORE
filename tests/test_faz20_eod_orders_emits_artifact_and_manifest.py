from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_eod_orders_emits_artifact_and_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day = "2099-01-03"
    day_dir = snapshot_root / day
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\n",
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
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 0
    orders_path = outdir / "orders" / "orders_intent.json"
    assert orders_path.exists()
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["day"] == day
    assert isinstance(payload["orders"], list)

    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    orders_stage = manifest["stages"]["orders"]
    assert orders_stage["path"] == str(orders_path)
    assert orders_stage["total"] == 1
    assert orders_stage["ok"] == 1
    assert "no_advice" in orders_stage["notes"]
