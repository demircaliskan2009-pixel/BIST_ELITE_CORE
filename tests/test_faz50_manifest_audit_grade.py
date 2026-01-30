"""
FAZ50: Audit-grade pipeline manifest (schema v2).
Test: run twice with same fixtures; compare manifests after removing run_id/timestamps => equal.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _strip_volatile(manifest: dict) -> dict:
    """Remove run_id, timestamps, runtime_ms for deterministic comparison."""
    out = dict(manifest)
    out.pop("run_id", None)
    out.pop("started_at_utc", None)
    out.pop("finished_at_utc", None)
    out.pop("runtime_ms", None)
    return out


def _normalize_paths(obj: object, outdir: str, placeholder: str = "<outdir>") -> object:
    """Recursively replace outdir path with placeholder for comparison."""
    if isinstance(obj, dict):
        return {k: _normalize_paths(v, outdir, placeholder) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_paths(v, outdir, placeholder) for v in obj]
    if isinstance(obj, str) and outdir in obj:
        return obj.replace(outdir, placeholder)
    return obj


def test_faz50_run_twice_manifests_equal_after_strip(tmp_path: Path) -> None:
    """Run pipeline twice with same fixtures; strip run_id/timestamps; manifests must be equal."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    day = "2099-01-15"
    snapshot_root = tmp_path / "snap"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text(
        "symbol,close\nAAA,10.0\nBBB,20.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)
    outdir1 = tmp_path / "out1"
    outdir2 = tmp_path / "out2"
    for outdir in (outdir1, outdir2):
        result = subprocess.run(
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
                "--ignore-calendar",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(repo_root),
        )
        assert result.returncode == 0, (result.stdout, result.stderr)

    # Load manifests (any of the three locations)
    def load_manifest(outdir: Path) -> dict:
        for p in (
            outdir / "pipeline_manifest.json",
            outdir / day / "pipeline_manifest.json",
            outdir / "_pipeline_manifest.json",
        ):
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"no manifest under {outdir}")

    m1 = load_manifest(outdir1)
    m2 = load_manifest(outdir2)
    assert m1.get("schema_version") == 2
    assert m2.get("schema_version") == 2
    assert m1.get("run_id") != m2.get("run_id")
    s1 = _strip_volatile(m1)
    s2 = _strip_volatile(m2)
    # Normalize outdir paths so out1 vs out2 compare equal
    s1 = _normalize_paths(s1, str(outdir1))
    s2 = _normalize_paths(s2, str(outdir2))
    assert s1 == s2, f"manifests differ after strip: {json.dumps({'s1_keys': list(s1.keys()), 's2_keys': list(s2.keys())}, indent=2)}"


def test_faz50_manifest_has_run_id_and_timestamps(tmp_path: Path) -> None:
    """Manifest schema v2 includes run_id, started_at_utc, finished_at_utc."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    day = "2099-01-16"
    snapshot_root = tmp_path / "snap"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text("symbol,close\nX,1.0\n", encoding="utf-8")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)
    outdir = tmp_path / "out"
    result = subprocess.run(
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
            "--ignore-calendar",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(repo_root),
    )
    assert result.returncode == 0
    manifest_path = outdir / "pipeline_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert "run_id" in manifest and len(manifest["run_id"]) > 0
    assert "started_at_utc" in manifest and "T" in manifest["started_at_utc"]
    assert "finished_at_utc" in manifest and "T" in manifest["finished_at_utc"]
    stages = manifest.get("stages", {})
    for name, stage in stages.items():
        assert "provenance" in stage
        assert "inputs" in stage["provenance"]
        assert "inputs_hash" in stage["provenance"]
