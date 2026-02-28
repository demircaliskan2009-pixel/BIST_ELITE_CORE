"""FAZ388: Scan artifact schema_version, generated_at, required keys, empty scan valid."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_scan_json(tmp_path: Path, day: str, csv_content: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--top-n", "10", "--json", *extra_args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def test_faz388_scan_artifact_schema_version(tmp_path: Path) -> None:
    """Scan --json has schema_version, generated_at, day, ranked with required keys."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\nAAA,100,101,99,100,1000000,50000000\n"
    result = _run_scan_json(tmp_path, "2099-01-10", csv)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data.get("schema_version") == 1
    assert "generated_at" in data
    assert data.get("day") == "2099-01-10"
    assert "ranked" in data
    ranked = data["ranked"]
    assert isinstance(ranked, list)
    assert len(ranked) >= 1
    for item in ranked:
        assert "symbol" in item
        assert "score" in item
        assert "rationale" in item


def test_faz388_scan_empty_schema(tmp_path: Path) -> None:
    """Empty scan (no symbols) returns valid JSON with empty ranked list."""
    csv = "symbol,close\n"
    result = _run_scan_json(tmp_path, "2099-01-11", csv)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data.get("schema_version") == 1
    assert "generated_at" in data
    assert data.get("day") == "2099-01-11"
    assert data.get("ranked") == []


def test_faz388_scan_artifact_deterministic_keys(tmp_path: Path) -> None:
    """Excluding generated_at, artifact has stable key order (schema_version, generated_at, day, ranked)."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\nBBB,50,51,49,50,1000000,50000000\n"
    result = _run_scan_json(tmp_path, "2099-01-12", csv)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    keys = list(data.keys())
    assert keys == ["schema_version", "generated_at", "day", "ranked"]
    for line in data["ranked"]:
        assert list(line.keys()) == ["symbol", "score", "rationale"]
