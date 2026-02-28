"""FAZ74: UTC timestamps use timezone-aware datetime.now(timezone.utc); no utcnow(); format ISO8601 with milliseconds + 'Z'."""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path


# ISO8601 with milliseconds + Z: 2025-01-23T12:34:56.789Z
UTC_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_utc_timestamp_format() -> None:
    """Timestamp format is ISO8601 with milliseconds + 'Z'."""
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    assert UTC_TS_PATTERN.match(ts), f"Expected format YYYY-MM-DDTHH:MM:SS.mmmZ, got {ts!r}"


def test_utc_timestamp_no_deprecation_warning() -> None:
    """Generating UTC timestamp must not emit DeprecationWarning (no utcnow())."""
    from datetime import datetime, timezone

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", DeprecationWarning)
        _ = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    deprecations = [x for x in w if x.category is DeprecationWarning]
    assert len(deprecations) == 0, f"Unexpected DeprecationWarning(s): {deprecations}"


def test_pipeline_manifest_timestamps_format_and_no_deprecation(tmp_path: Path) -> None:
    """run_eod_pipeline writes manifest with started_at_utc/finished_at_utc in correct format; no DeprecationWarning."""
    from bist_core.services.eod_pipeline import run_eod_pipeline

    day = "2025-01-15"
    snapshot_root = tmp_path / "snapshot"
    outdir = tmp_path / "out"
    snapshot_root.mkdir(parents=True)
    outdir.mkdir(parents=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", DeprecationWarning)
        manifest, _ = run_eod_pipeline(
            day,
            snapshot_root,
            outdir,
            strict=False,
            emit_orders=False,
            ignore_calendar=True,
        )
    deprecations = [x for x in w if x.category is DeprecationWarning]
    assert len(deprecations) == 0, f"DeprecationWarning during pipeline: {deprecations}"
    assert "started_at_utc" in manifest
    assert "finished_at_utc" in manifest
    started = manifest["started_at_utc"]
    finished = manifest["finished_at_utc"]
    assert UTC_TS_PATTERN.match(started), f"started_at_utc wrong format: {started!r}"
    assert UTC_TS_PATTERN.match(finished), f"finished_at_utc wrong format: {finished!r}"


def test_written_manifest_has_utc_timestamps_format(tmp_path: Path) -> None:
    """Written pipeline_manifest.json contains started_at_utc/finished_at_utc in ISO8601.msZ format."""
    from bist_core.services.eod_pipeline import run_eod_pipeline

    day = "2025-01-16"
    snapshot_root = tmp_path / "snap"
    outdir = tmp_path / "out"
    snapshot_root.mkdir(parents=True)
    outdir.mkdir(parents=True)
    run_eod_pipeline(day, snapshot_root, outdir, strict=False, emit_orders=False, ignore_calendar=True)
    manifest_path = outdir / day / "pipeline_manifest.json"
    if not manifest_path.is_file():
        manifest_path = outdir / "pipeline_manifest.json"
    assert manifest_path.is_file(), "No pipeline_manifest.json written"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("started_at_utc", "finished_at_utc"):
        assert key in data
        assert UTC_TS_PATTERN.match(data[key]), f"{key} wrong format: {data[key]!r}"
