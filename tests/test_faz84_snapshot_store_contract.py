"""FAZ84: Snapshot store contract — put/get/sha256; pipeline manifest stage artifact {path, sha256}."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.storage.snapshots import get_snapshot, put_snapshot, snapshot_sha256


def test_faz84_put_get_roundtrip(tmp_path: Path) -> None:
    """put_snapshot then get_snapshot returns same bytes."""
    data = b"symbol,close\nX,10.0\n"
    art = put_snapshot(tmp_path, "day1/snapshot.csv", data)
    assert "path" in art
    assert "sha256" in art
    out = get_snapshot(tmp_path, "day1/snapshot.csv")
    assert out == data


def test_faz84_put_returns_artifact_path_sha256(tmp_path: Path) -> None:
    """put_snapshot returns artifact with path and sha256; sha256 matches snapshot_sha256."""
    data = b"x,y\n1,2\n"
    art = put_snapshot(tmp_path, "k.csv", data)
    assert art["path"]
    assert art["sha256"]
    assert len(art["sha256"]) == 64
    assert snapshot_sha256(tmp_path, "k.csv") == art["sha256"]


def test_faz84_get_missing_returns_none(tmp_path: Path) -> None:
    """get_snapshot for missing key returns None."""
    assert get_snapshot(tmp_path, "missing.csv") is None


def test_faz84_sha256_missing_returns_none(tmp_path: Path) -> None:
    """snapshot_sha256 for missing key returns None."""
    assert snapshot_sha256(tmp_path, "missing.csv") is None


def test_faz84_pipeline_manifest_snapshot_stage_has_artifact(tmp_path: Path) -> None:
    """EOD run with snapshot -> pipeline manifest snapshot stage has artifact {path, sha256}."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    snapshot_root = tmp_path / "snapshots"
    day_dir = snapshot_root / "2099-01-02"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nX,10.0\n", encoding="utf-8")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)
    outdir = tmp_path / "out"
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "run", "--day", "2099-01-02", "--outdir", str(outdir)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    manifest_path = outdir / "2099-01-02" / "pipeline_manifest.json"
    if not manifest_path.is_file():
        manifest_path = outdir / "pipeline_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snap_stage = manifest.get("stages", {}).get("snapshot", {})
    artifact = snap_stage.get("artifact")
    assert artifact is not None, "snapshot stage must have artifact"
    assert "path" in artifact
    assert "sha256" in artifact
    assert re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
