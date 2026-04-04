from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_events_ingest_dedupe(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"symbol":"AAA","ts":"2099-01-01T10:00:00Z","kind":"KAP","title":"A1"}',
                '{"symbol":"AAA","ts":"2099-01-01T10:00:00Z","kind":"KAP","title":"A1"}',
                '{"symbol":"BBB","ts":"2099-01-01T09:00:00Z","kind":"KAP","title":"B1"}',
                '{"symbol":"CCC","ts":"2099-01-01T08:00:00Z","kind":"KAP","title":"C1"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    outdir = tmp_path / "out" / "2099-01-01"
    result_first = subprocess.run(
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
    assert result_first.returncode == 0

    manifest_first = json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest_first["total_in"] == 4
    assert manifest_first["accepted"] == 3
    assert manifest_first["duplicates"] == 1

    lines_first = (outdir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines_first) == 3

    result_second = subprocess.run(
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
    assert result_second.returncode == 0

    manifest_second = json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest_second["accepted"] == 0
    assert manifest_second["duplicates"] == 4

    lines_second = (outdir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines_second == lines_first
