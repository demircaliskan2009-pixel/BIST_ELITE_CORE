"""FAZ51: Research cache (atomic jsonl under outdir/<day>/research/)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_research_cache_writes_index_and_entries(tmp_path: Path) -> None:
    """build_research_cache writes research_index.json + entries.jsonl; stub returns 2 items."""
    from bist_core.research.cache import build_research_cache

    day = "2099-06-01"
    outdir = tmp_path / "out"
    result = build_research_cache(day, outdir, source="kap", offline=True)

    research_dir = outdir / day / "research"
    assert research_dir.is_dir()
    index_path = research_dir / "research_index.json"
    entries_path = research_dir / "entries.jsonl"
    assert index_path.is_file()
    assert entries_path.is_file()

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["day"] == day
    assert index["source"] == "kap"
    assert index["count"] == 2
    assert index["errors"] == 0
    assert "path" in index
    assert "provenance" in index
    assert len(index["provenance"]) == 2

    lines = entries_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        row = json.loads(line)
        assert "id" in row and "source" in row

    assert result["count"] == 2
    assert result["errors"] == 0
    assert result["path"] == str(research_dir)


def test_cli_eod_research_writes_deterministic_paths(tmp_path: Path) -> None:
    """CLI eod research --day --outdir writes research_index.json + entries.jsonl."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    day = "2099-06-02"
    outdir = tmp_path / "out"
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "research",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--source",
            "kap",
            "--offline",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, f"stdout: {p.stdout}\nstderr: {p.stderr}"

    research_dir = outdir / day / "research"
    assert (research_dir / "research_index.json").is_file()
    assert (research_dir / "entries.jsonl").is_file()


def test_eod_run_with_research_adds_stage_and_provenance(tmp_path: Path) -> None:
    """eod run --research adds stages[research] and provenance.research to manifest."""
    repo_root = Path(__file__).resolve().parents[1]
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True)
    day = "2099-06-03"
    (snap_dir / day).mkdir(parents=True)
    (snap_dir / day / "snapshot.csv").write_text(
        "symbol,date,close\nX,2099-06-03,100\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_dir)

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
            "--research",
            "--research-source",
            "kap",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, f"stdout: {p.stdout}\nstderr: {p.stderr}"

    manifest_path = outdir / day / "pipeline_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "stages" in manifest
    assert "research" in manifest["stages"]
    research_stage = manifest["stages"]["research"]
    assert research_stage.get("count") == 2
    assert research_stage.get("path")
    assert "provenance" in manifest
    assert "research" in manifest["provenance"]
    assert isinstance(manifest["provenance"]["research"], list)
    assert len(manifest["provenance"]["research"]) == 2

    assert (outdir / day / "research" / "research_index.json").is_file()
    assert (outdir / day / "research" / "entries.jsonl").is_file()
