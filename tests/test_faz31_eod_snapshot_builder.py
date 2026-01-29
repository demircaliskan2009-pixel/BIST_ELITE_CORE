"""FAZ31: EOD snapshot builder — build_eod_snapshot writes snapshot.csv + _snapshot_hash.json; pipeline uses builder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.services import snapshot_integrity


def test_faz31_builder_writes_snapshot_and_hash(tmp_path: Path) -> None:
    """build_eod_snapshot(day, src_dir, outdir) writes <outdir>/<day>/snapshot.csv and _snapshot_hash.json."""
    day = "2025-01-15"
    src_dir = tmp_path / "src"
    out_dir = tmp_path / "out"
    src_dir.mkdir(parents=True)
    (src_dir / day).mkdir(parents=True, exist_ok=True)
    snapshot_csv = src_dir / day / "snapshot.csv"
    snapshot_csv.write_text("symbol,close\nX,1.0\nY,2.0\n", encoding="utf-8")

    result = snapshot_integrity.build_eod_snapshot(day, src_dir, out_dir)

    out_day = out_dir / day
    out_csv = out_day / "snapshot.csv"
    out_hash = out_day / "_snapshot_hash.json"
    assert out_csv.is_file()
    assert out_csv.read_text(encoding="utf-8") == "symbol,close\nX,1.0\nY,2.0\n"
    assert out_hash.is_file()
    payload = json.loads(out_hash.read_text(encoding="utf-8"))
    assert payload["day"] == day
    assert payload["sha256"] == snapshot_integrity.compute_sha256(out_csv)
    assert result["sha256"] == payload["sha256"]


def test_faz31_builder_stable_hash(tmp_path: Path) -> None:
    """Same content produces same sha256 (deterministic)."""
    day = "2025-01-16"
    content = "symbol,close\nA,1\nB,2\n"
    src = tmp_path / "s1"
    out = tmp_path / "o1"
    src.mkdir()
    (src / day).mkdir()
    (src / day / "snapshot.csv").write_text(content, encoding="utf-8")

    r1 = snapshot_integrity.build_eod_snapshot(day, src, out)
    r2 = snapshot_integrity.build_snapshot_hash_manifest(out / day / "snapshot.csv")
    assert r1["sha256"] == r2["sha256"]


def test_faz31_builder_uses_alt_day_csv(tmp_path: Path) -> None:
    """Source can be snapshot_src_dir/<day>.csv (flat file)."""
    day = "2025-01-17"
    src_dir = tmp_path / "flat"
    src_dir.mkdir()
    alt_csv = src_dir / (day + ".csv")
    alt_csv.write_text("symbol,close\nZ,3.0\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    snapshot_integrity.build_eod_snapshot(day, src_dir, out_dir)

    out_csv = out_dir / day / "snapshot.csv"
    out_hash = out_dir / day / "_snapshot_hash.json"
    assert out_csv.is_file()
    assert out_csv.read_text(encoding="utf-8") == "symbol,close\nZ,3.0\n"
    assert out_hash.is_file()
    assert json.loads(out_hash.read_text())["day"] == day


def test_faz31_builder_raises_when_missing(tmp_path: Path) -> None:
    """build_eod_snapshot raises FileNotFoundError when no source exists."""
    day = "2025-01-18"
    src_dir = tmp_path / "empty"
    src_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with pytest.raises(FileNotFoundError) as exc_info:
        snapshot_integrity.build_eod_snapshot(day, src_dir, out_dir)
    assert "snapshot source" in str(exc_info.value).lower() or day in str(exc_info.value)


def test_faz31_pipeline_uses_builder_tmp_snapshots(tmp_path: Path) -> None:
    """Pipeline uses builder: snapshot in tmp dir, run pipeline with tmp snapshot root."""
    from bist_core.services.eod_pipeline import run_eod_pipeline

    day_str = "2099-06-01"
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / day_str).mkdir(parents=True, exist_ok=True)
    (snapshot_root / day_str / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "run"
    outdir.mkdir(parents=True, exist_ok=True)

    manifest, exit_code = run_eod_pipeline(
        day_str,
        snapshot_root,
        outdir,
        strict=False,
    )

    assert exit_code == 0
    day_dir = snapshot_root / day_str
    assert (day_dir / "snapshot.csv").is_file()
    hash_path = day_dir / "_snapshot_hash.json"
    assert hash_path.is_file()
    payload = json.loads(hash_path.read_text(encoding="utf-8"))
    assert payload.get("sha256")
    assert payload.get("day") == day_str
    assert manifest.get("provenance", {}).get("snapshot_hash", {}).get("value") == payload["sha256"]
