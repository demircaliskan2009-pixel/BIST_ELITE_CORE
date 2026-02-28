from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_events_ingest_strict_and_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"symbol":"AAA","ts":"2099-01-01T10:00:00Z","kind":"KAP","title":"A1"}',
                '{"symbol":"BBB","ts":"2099-01-01T11:00:00Z","kind":"KAP"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    outdir = tmp_path / "out" / "2099-01-01"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "events",
            "ingest",
            "--day",
            "2099-01-01",
            "--input",
            str(input_path),
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

    manifest = json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))
    required_keys = {
        "schema_version",
        "day",
        "input",
        "outdir",
        "total_in",
        "accepted",
        "rejected",
        "duplicates",
        "errors",
        "runtime_ms",
        "provenance",
    }
    assert required_keys.issubset(manifest.keys())
    assert manifest["accepted"] == 1
    assert manifest["rejected"] == 1
    assert manifest["errors"]
    assert "error_marker" in manifest["errors"][0]

    outdir_strict = tmp_path / "out_strict" / "2099-01-01"
    result_strict = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "events",
            "ingest",
            "--day",
            "2099-01-01",
            "--input",
            str(input_path),
            "--outdir",
            str(outdir_strict),
            "--strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result_strict.returncode == 2
    manifest_strict = json.loads((outdir_strict / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest_strict["rejected"] == 1
