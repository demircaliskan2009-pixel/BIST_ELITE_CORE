"""FAZ53: Advisory generator (outdir/advice/<day>/advice_records.jsonl, schema v1, deterministic)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_advice_generator_writes_deterministic_path_and_content(tmp_path: Path) -> None:
    """generate_advice writes outdir/advice/<day>/advice_records.jsonl; content stable sort by symbol; schema v1."""
    from bist_core.advisory.generate import generate_advice

    day = "2099-03-01"
    snap_root = tmp_path / "snap"
    (snap_root / day).mkdir(parents=True)
    (snap_root / day / "snapshot.csv").write_text(
        "symbol,date,close\nAAA,2099-03-01,10.5\nBBB,2099-03-01,20.0\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    result1 = generate_advice(day, snap_root, outdir)
    result2 = generate_advice(day, snap_root, outdir)

    path = Path(result1["path"]) / "advice_records.jsonl"
    assert path.is_file(), f"expected {path}"
    assert path == outdir / "advice" / day / "advice_records.jsonl"

    lines1 = path.read_text(encoding="utf-8").strip().split("\n")
    lines2 = path.read_text(encoding="utf-8").strip().split("\n")
    assert lines1 == lines2, "two runs must produce identical content"

    records = [json.loads(ln) for ln in lines1]
    assert len(records) >= 2
    symbols = [r["symbol"] for r in records]
    assert symbols == sorted(symbols), "records must be sorted by symbol"
    for r in records:
        assert "symbol" in r and "score" in r and "side" in r and "reason" in r
        assert "inputs" in r and "close" in r["inputs"]
        assert isinstance(r["score"], (int, float))
        assert r["side"] in ("BUY", "SELL", "HOLD")

    assert result1["total"] == result2["total"]
    assert result1["path"] == str(outdir / "advice" / day)


def test_cli_eod_advice_writes_advice_records_jsonl(tmp_path: Path) -> None:
    """CLI eod advice --day --outdir writes outdir/advice/<day>/advice_records.jsonl."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    day = "2099-03-02"
    snap_root = tmp_path / "snap"
    (snap_root / day).mkdir(parents=True)
    (snap_root / day / "snapshot.csv").write_text(
        "symbol,date,close\nX,2099-03-02,100\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    outdir = tmp_path / "out"
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "advice",
            "--day",
            day,
            "--outdir",
            str(outdir),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, f"stdout: {p.stdout}\nstderr: {p.stderr}"

    path = outdir / "advice" / day / "advice_records.jsonl"
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert rec.get("symbol") and "score" in rec and "side" in rec and "inputs" in rec


def test_eod_run_advice_stage_writes_deterministic_path(tmp_path: Path) -> None:
    """eod run writes advice to outdir/advice/<day>/advice_records.jsonl; manifest includes path + counts."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    day = "2099-03-03"
    snap_root = tmp_path / "snap"
    (snap_root / day).mkdir(parents=True)
    (snap_root / day / "snapshot.csv").write_text(
        "symbol,date,close\nA,2099-03-03,1.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    outdir = tmp_path / "out"
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, f"stdout: {p.stdout}\nstderr: {p.stderr}"

    path = outdir / "advice" / day / "advice_records.jsonl"
    assert path.is_file()
    manifest_path = outdir / day / "pipeline_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    advice_stage = manifest.get("stages", {}).get("advice", {})
    assert "path" in advice_stage
    assert "advice_records.jsonl" in advice_stage["path"] or advice_stage["path"].endswith("advice/" + day)
    assert "total" in advice_stage
    assert advice_stage["total"] >= 1
