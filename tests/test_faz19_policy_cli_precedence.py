from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from bist_core.services import snapshot_integrity


def test_policy_cli_precedence(tmp_path: Path) -> None:
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

    policy_a = tmp_path / "policy_a.json"
    policy_b = tmp_path / "policy_b.json"
    policy_a.write_text(
        json.dumps({"schema_version": 1, "rules": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    policy_b.write_text(
        json.dumps(
            {"schema_version": 1, "rules": [{"id": "max", "type": "max_notional", "max_notional": 10}]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    env["BIST_CORE_POLICY_FILE"] = str(policy_a)

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
            str(policy_b),
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
    assert policy["file"] == str(policy_b)
    assert policy["hash"]["algo"] == "sha256"
    assert policy["hash"]["value"] == snapshot_integrity.compute_sha256(policy_b)
    assert re.fullmatch(r"[0-9a-f]{64}", policy["hash"]["value"])
