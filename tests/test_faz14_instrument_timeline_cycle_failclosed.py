from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_instrument_timeline_cycle_failclosed(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    instruments_dir = tmp_path / "instruments" / "2099-01-01"
    instruments_dir.mkdir(parents=True)
    (instruments_dir / "instruments.jsonl").write_text(
        '{"symbol":"AAA","isin":"TRAAA","name":"AAA","status":"active","source":"offline","ts":"2099-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )

    ca_dir = tmp_path / "corporate_actions" / "2099-01-01"
    ca_dir.mkdir(parents=True)
    (ca_dir / "actions.jsonl").write_text(
        "\n".join(
            [
                '{"symbol":"AAA","effective_date":"2099-01-01","kind":"symbol_change","old_symbol":"AAA","new_symbol":"BBB","ts":"2099-01-01T01:00:00Z","source":"offline"}',
                '{"symbol":"BBB","effective_date":"2099-01-01","kind":"symbol_change","old_symbol":"BBB","new_symbol":"AAA","ts":"2099-01-01T02:00:00Z","source":"offline"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    outdir = tmp_path / "universe" / "2099-01-01"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "instruments",
            "timeline",
            "--day",
            "2099-01-01",
            "--instruments-dir",
            str(instruments_dir),
            "--ca-dir",
            str(ca_dir),
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
    assert manifest["errors"] > 0

    outdir_strict = tmp_path / "universe_strict" / "2099-01-01"
    result_strict = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "instruments",
            "timeline",
            "--day",
            "2099-01-01",
            "--instruments-dir",
            str(instruments_dir),
            "--ca-dir",
            str(ca_dir),
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
