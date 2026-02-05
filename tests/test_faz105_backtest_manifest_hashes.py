"""FAZ105: Backtest evidence manifest — manifest.json with outputs (path, sha256, bytes)."""
from __future__ import annotations

import json
from pathlib import Path

from bist_core.services import snapshot_integrity
from bist_core.services.backtest import run_backtest


def test_faz105_backtest_evidence_manifest_exists_sha256_and_bytes_match(tmp_path: Path) -> None:
    """Tiny 2-day backtest; assert manifest.json exists; recompute sha256 via snapshot_integrity and assert equals + bytes match."""
    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-08-01", "2099-08-02"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nX,1.0\nY,2.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-08-01",
        date_to="2099-08-02",
        outdir=outdir,
        strategy="equal_weight",
        top_n=10,
    )
    backtest_dir = outdir / "backtest"
    manifest_path = backtest_dir / "manifest.json"
    assert manifest_path.is_file(), "manifest.json must exist"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == 1
    assert manifest.get("kind") == "backtest"
    outputs = manifest.get("outputs") or {}
    assert "metrics" in outputs
    assert "equity_curve" in outputs
    for name, out in [("metrics", outputs["metrics"]), ("equity_curve", outputs["equity_curve"])]:
        p = backtest_dir / out["path"]
        assert p.is_file(), f"{name} file must exist"
        assert snapshot_integrity.compute_sha256(p) == out["sha256"], f"{name}: sha256 mismatch"
        assert p.stat().st_size == out["bytes"], f"{name}: bytes mismatch"
