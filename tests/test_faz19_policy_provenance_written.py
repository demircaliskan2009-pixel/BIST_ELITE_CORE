from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def test_policy_provenance_written(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-02"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    policy_good = tmp_path / "policy_good.json"
    policy_good.write_text(
        json.dumps({"schema_version": 1, "rules": []}, ensure_ascii=False, indent=2),
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
            "2099-01-02",
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--policy-file",
            str(policy_good),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    policy = manifest["provenance"]["policy"]
    assert policy["hash"]["algo"] == "sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", policy["hash"]["value"])
