from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_dossier_build_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nASELS,\nTHYAO,\n",
        encoding="utf-8",
    )

    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "dossier",
            "build",
            "--day",
            "2099-01-01",
            "--all",
            "--outdir",
            str(outdir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 0
    files = list(outdir.glob("*.json"))
    assert files

    payload = json.loads(files[0].read_text(encoding="utf-8"))
    required_keys = {
        "schema_version",
        "symbol",
        "day",
        "decision_raw",
        "score",
        "signals",
        "plan",
        "text",
        "capabilities",
        "provenance",
        "error_marker",
    }
    assert required_keys.issubset(payload.keys())
    assert "Güvenli mod" in payload["text"]
    assert "RuntimeWarning" not in result.stderr
