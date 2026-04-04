from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_instrument_timeline_basic(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    instruments_dir = tmp_path / "instruments" / "2099-01-01"
    instruments_dir.mkdir(parents=True)
    (instruments_dir / "instruments.jsonl").write_text(
        "\n".join(
            [
                '{"symbol":"AAA","isin":"TRAAA","name":"AAA","status":"active","source":"offline","ts":"2099-01-01T00:00:00Z"}',
                '{"symbol":"BBB","isin":"TRBBB","name":"BBB","status":"active","source":"offline","ts":"2099-01-01T00:00:00Z"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ca_dir = tmp_path / "corporate_actions" / "2099-01-01"
    ca_dir.mkdir(parents=True)
    (ca_dir / "actions.jsonl").write_text(
        "\n".join(
            [
                '{"symbol":"AAA","effective_date":"2099-01-01","kind":"symbol_change","old_symbol":"AAA","new_symbol":"CCC","ts":"2099-01-01T01:00:00Z","source":"offline"}',
                '{"symbol":"BBB","effective_date":"2099-01-01","kind":"isin_change","old_isin":"TRBBB","new_isin":"TRBBB2","ts":"2099-01-01T02:00:00Z","source":"offline"}',
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
    timeline = json.loads((outdir / "timeline.json").read_text(encoding="utf-8"))
    assert timeline["alias_map"]["AAA"] == "CCC"
    resolved_symbols = [r["symbol"] for r in timeline["resolved"]]
    assert "CCC" in resolved_symbols
    ccc_entry = [r for r in timeline["resolved"] if r["symbol"] == "CCC"][0]
    assert "AAA" in ccc_entry["aliases"]
    assert timeline["errors"] == []
