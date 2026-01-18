from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_ca_ingest_strict_exitcode(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    input_path = tmp_path / "actions.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"symbol":"AAA","effective_date":"2099-01-02","kind":"split","ratio":2,"ts":"2099-01-01T10:00:00Z","source":"offline_file"}',
                '{"symbol":"","effective_date":"2099-01-02","kind":"split","ratio":2,"ts":"2099-01-01T10:00:00Z","source":"offline_file"}',
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
            "corporate-actions",
            "ingest",
            "--day",
            "2099-01-01",
            "--input",
            str(input_path),
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
    manifest = json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["errors"] > 0
