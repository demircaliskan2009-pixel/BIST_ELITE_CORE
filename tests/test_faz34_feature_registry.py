"""FAZ34: Feature registry + compute; deterministic; missing data => fail-closed notes."""

from __future__ import annotations

import json
from pathlib import Path

from bist_core.services.features import (
    compute_features,
    feature_registry,
    write_features,
)
from bist_core.services.eod_pipeline import run_eod_pipeline


def test_faz34_registry_has_baseline_features() -> None:
    """Baseline features: returns_1d, vol_20d, mom_20d, volume_z are registered."""
    assert "returns_1d" in feature_registry
    assert "vol_20d" in feature_registry
    assert "mom_20d" in feature_registry
    assert "volume_z" in feature_registry


def test_faz34_compute_deterministic() -> None:
    """compute_features: same context => same outputs; sorted by symbol."""

    def ctx_provider(symbol: str, day: str) -> dict:
        if symbol == "A":
            closes = [(f"2099-06-{i:02d}", 100.0 + i) for i in range(1, 22)]
            return {"close_series": closes, "volume_series": [(d, 1000.0) for d, _ in closes]}
        return {"close_series": [], "volume_series": None}

    rows1, notes1 = compute_features(["A", "B"], "2099-06-21", ctx_provider)
    rows2, notes2 = compute_features(["B", "A"], "2099-06-21", ctx_provider)
    assert rows1 == rows2
    assert notes1 == notes2
    assert rows1[0]["symbol"] == "A"
    assert rows1[1]["symbol"] == "B"
    assert "returns_1d" in rows1[0]
    assert "mom_20d" in rows1[0]


def test_faz34_returns_1d_simple() -> None:
    """returns_1d: (close_today - close_yesterday) / close_yesterday."""

    def ctx(symbol: str, day: str) -> dict:
        return {"close_series": [("2099-07-01", 100.0), ("2099-07-02", 110.0)], "volume_series": None}

    rows, _ = compute_features(["X"], "2099-07-02", ctx)
    assert len(rows) == 1
    assert rows[0]["returns_1d"] == 0.1


def test_faz34_missing_data_fail_closed_notes() -> None:
    """Missing/insufficient data => notes contain missing_data; stage fail-closed."""

    def empty_ctx(symbol: str, day: str) -> dict:
        return {"close_series": [], "volume_series": None}

    rows, notes = compute_features(["Y"], "2099-08-01", empty_ctx)
    assert "missing_data" in notes
    assert len(rows) == 1
    assert rows[0]["symbol"] == "Y"
    assert "returns_1d" not in rows[0] or rows[0].get("returns_1d") is None


def test_faz34_write_features_jsonl(tmp_path: Path) -> None:
    """write_features writes outdir/features/<day>/features.jsonl."""
    rows = [
        {"symbol": "Z", "date": "2099-09-01", "returns_1d": 0.01},
    ]
    path = write_features(tmp_path, "2099-09-01", rows)
    assert path == tmp_path / "features" / "2099-09-01" / "features.jsonl"
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["symbol"] == "Z"
    assert json.loads(lines[0])["returns_1d"] == 0.01


def test_faz34_pipeline_feature_stage_and_fail_closed(tmp_path: Path) -> None:
    """Pipeline: writes features stage; missing history => feature stage notes fail-closed."""
    day_str = "2099-10-01"
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / day_str).mkdir(parents=True)
    (snapshot_root / day_str / "snapshot.csv").write_text(
        "symbol,close\nAAA,10.0\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "run"
    outdir.mkdir(parents=True)
    manifest, code = run_eod_pipeline(
        day_str,
        snapshot_root,
        outdir,
        strict=False,
        ignore_calendar=True,
    )
    assert code == 0
    stages = manifest.get("stages", {})
    feat = stages.get("features", {})
    assert "path" in feat
    assert (outdir / "features" / day_str / "features.jsonl").is_file()
    assert feat.get("total", 0) >= 1
    notes = feat.get("notes", [])
    assert "missing_data" in notes or feat.get("ok") is False
