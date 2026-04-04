from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_instruments_pull_offline_deterministic(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"symbol":"aaa","ts":"2099-01-01T10:00:00Z","source":"offline_file"}',
                '{"symbol":"BBB","ts":"2099-01-01T11:00:00Z","source":"offline_file"}',
                '{"symbol":"","ts":"2099-01-01T12:00:00Z","source":"offline_file"}',
                '{"symbol":"CCC","listing_start":"2099-01-02","listing_end":"2099-01-01","ts":"2099-01-01T09:00:00Z","source":"offline_file"}',
                '{"symbol":"DDD","ts":"2099-01-01T08:00:00Z","source":"offline_file","isin":"tr0000"}',
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
            "instruments",
            "pull",
            "--day",
            "2099-01-01",
            "--provider",
            "offline_file",
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

    lines = (outdir / "instruments.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    symbols = [json.loads(line)["symbol"] for line in lines]
    assert symbols == sorted(symbols)

    manifest = json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["errors"] == 2
    assert manifest["total"] == 5
