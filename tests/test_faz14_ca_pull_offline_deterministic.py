from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_ca_pull_offline_deterministic(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    input_path = tmp_path / "actions.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"symbol":"AAA","effective_date":"2099-01-02","kind":"split","ratio":2,"ts":"2099-01-01T10:00:00Z","source":"offline_file"}',
                '{"symbol":"BBB","effective_date":"2099-01-01","kind":"reverse_split","ratio":3,"ts":"2099-01-01T09:00:00Z","source":"offline_file"}',
                '{"symbol":"CCC","effective_date":"2099-01-03","kind":"invalid_kind","ts":"2099-01-01T08:00:00Z","source":"offline_file"}',
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
    lines = (outdir / "actions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    order = [(r["effective_date"], r["symbol"], r["kind"]) for r in records]
    assert order == sorted(order)
    manifest = json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["errors"] == 1
