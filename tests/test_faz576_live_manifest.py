"""FAZ576: Live run manifest — schema, deterministic ordering."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from tools.live_manifest import build_manifest, write_manifest


def test_live_manifest_schema(tmp_path: Path) -> None:
    """Manifest has required keys: schema_version, day, inputs, outputs, symbols, horizons, versions, sha."""
    paths = {
        "daily_scan": tmp_path / "daily_scan" / "2025-01-15",
        "ask": tmp_path / "ask" / "2025-01-15",
        "outcomes": tmp_path / "outcomes" / "2025-01-15",
        "reports": tmp_path / "reports" / "2025-01-15",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        day="2025-01-15",
        out_root=tmp_path,
        snapshot_root=tmp_path / "snapshots",
        paths=paths,
        symbols=["AAA", "BBB"],
        top_n=5,
    )

    required = {"schema_version", "day", "inputs", "outputs", "symbols", "horizons", "versions", "sha"}
    assert required.issubset(manifest.keys())
    assert manifest["schema_version"] == 1
    assert manifest["day"] == "2025-01-15"
    assert manifest["inputs"]["day"] == "2025-01-15"
    assert manifest["inputs"]["top_n"] == 5
    assert manifest["symbols"] == ["AAA", "BBB"]
    assert manifest["horizons"] == [1, 5, 20]


def test_live_manifest_deterministic_ordering(tmp_path: Path) -> None:
    """Symbols and outputs are sorted; JSON keys sorted."""
    paths = {
        "daily_scan": tmp_path / "daily_scan" / "2025-01-15",
        "ask": tmp_path / "ask" / "2025-01-15",
        "outcomes": tmp_path / "outcomes" / "2025-01-15",
        "reports": tmp_path / "reports" / "2025-01-15",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        day="2025-01-15",
        out_root=tmp_path,
        snapshot_root=tmp_path / "snapshots",
        paths=paths,
        symbols=["ZZZ", "AAA", "BBB"],
        top_n=5,
    )

    assert manifest["symbols"] == ["AAA", "BBB", "ZZZ"]
    assert manifest["outputs"] == sorted(manifest["outputs"])


def test_live_manifest_write(tmp_path: Path) -> None:
    """write_manifest writes run_manifest.json to reports dir."""
    reports_dir = tmp_path / "reports" / "2025-01-15"
    manifest = {
        "schema_version": 1,
        "day": "2025-01-15",
        "inputs": {},
        "outputs": [],
        "symbols": [],
        "horizons": [1, 5, 20],
        "versions": {"python": "3.12", "script": "live_daily_runner"},
        "sha": "abc1234",
    }
    path = write_manifest(manifest, reports_dir)
    assert path == reports_dir / "run_manifest.json"
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["day"] == "2025-01-15"
    assert loaded["sha"] == "abc1234"


def test_live_daily_writes_run_manifest(tmp_path: Path) -> None:
    """run_live_daily produces run_manifest.json in reports/<DAY>/."""
    from tools.live_daily_runner import run_live_daily

    snap = tmp_path / "snapshots"
    (snap / "2099-01-01").mkdir(parents=True)
    (snap / "2099-01-01" / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,99.0\n",
        encoding="utf-8",
    )
    out_root = tmp_path / "log"

    code, symbols, paths = run_live_daily(
        day="2099-01-01",
        top_n=2,
        out_root=out_root,
        snapshot_root=snap,
    )

    assert code == 0
    manifest_path = paths["reports"] / "run_manifest.json"
    assert manifest_path.is_file(), f"Expected run_manifest.json at {manifest_path}"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["day"] == "2099-01-01"
    assert "inputs" in data
    assert "outputs" in data
    assert "symbols" in data
    assert "horizons" in data
    assert "versions" in data
    assert "sha" in data
