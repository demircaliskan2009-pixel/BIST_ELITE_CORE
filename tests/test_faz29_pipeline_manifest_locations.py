"""FAZ29: Assert pipeline manifest is written to all three deterministic locations."""

from __future__ import annotations

import json
from pathlib import Path

from bist_core.services.eod_pipeline import _write_pipeline_manifest


def test_write_pipeline_manifest_writes_all_three_locations(tmp_path: Path) -> None:
    """_write_pipeline_manifest writes root, day-scoped, and legacy paths (no CLI, no network)."""
    day = "2099-01-01"
    manifest = {"schema_version": 1, "day": day, "outdir": str(tmp_path)}
    _write_pipeline_manifest(tmp_path, day, manifest)

    root_file = tmp_path / "pipeline_manifest.json"
    day_file = tmp_path / day / "pipeline_manifest.json"
    legacy_file = tmp_path / "_pipeline_manifest.json"

    assert root_file.exists(), "out/pipeline_manifest.json missing"
    assert day_file.exists(), "out/<day>/pipeline_manifest.json missing"
    assert legacy_file.exists(), "out/_pipeline_manifest.json missing"

    for p in (root_file, day_file, legacy_file):
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["day"] == day
        assert data["schema_version"] == 1
