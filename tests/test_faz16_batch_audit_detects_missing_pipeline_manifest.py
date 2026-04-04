from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_batch_audit_detects_missing_pipeline_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    outdir = tmp_path / "runs"
    outdir.mkdir(parents=True)
    index = {
        "schema_version": 2,
        "start_day": "2099-01-01",
        "end_day": "2099-01-01",
        "outdir": str(outdir),
        "calendar": {"file": None, "ignore": True},
        "resume": {"enabled": False, "rerun_failed": False, "max_failures": 0},
        "stopped_early": False,
        "stop_reason": "",
        "days": [
            {
                "day": "2099-01-01",
                "status": "ok",
                "exit_code": 0,
                "pipeline_manifest_path": str(outdir / "2099-01-01" / "_pipeline_manifest.json"),
                "calendar": {"ok": True, "reason": "ignored", "errors": []},
                "notes": [],
            }
        ],
        "summary": {"total": 1, "ran": 1, "skipped_calendar": 0, "skipped_ok_existing": 0, "errors": 0},
        "runtime_ms": 0,
        "provenance": {"cli_args": {}},
    }
    (outdir / "_index_manifest.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "batch-audit",
            "--outdir",
            str(outdir),
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
    audit = json.loads((outdir / "_audit_manifest.json").read_text(encoding="utf-8"))
    assert audit["errors"]
