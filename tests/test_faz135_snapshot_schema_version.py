"""FAZ135: Snapshot metadata includes schema_version."""

from __future__ import annotations

import json
from pathlib import Path

from bist_core.services import snapshot_integrity


def test_faz135_snapshot_hash_manifest_has_schema_version(tmp_path: Path) -> None:
    """_snapshot_hash.json must include schema_version."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir()
    csv_path = day_dir / "snapshot.csv"
    csv_path.write_text("symbol,close\nX,1.0\n", encoding="utf-8")

    manifest = snapshot_integrity.build_snapshot_hash_manifest(csv_path)
    assert "schema_version" in manifest
    assert manifest["schema_version"] == 1


def test_faz135_build_eod_snapshot_writes_schema_version(tmp_path: Path) -> None:
    """build_eod_snapshot produces _snapshot_hash.json with schema_version."""
    day = "2025-01-16"
    src = tmp_path / "src"
    out = tmp_path / "out"
    (src / day).mkdir(parents=True)
    (src / day / "snapshot.csv").write_text("symbol,close\nA,10\n", encoding="utf-8")

    snapshot_integrity.build_eod_snapshot(day, src, out)
    hash_path = out / day / "_snapshot_hash.json"
    payload = json.loads(hash_path.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == 1
