"""FAZ106: Backtest manifest + artifact hashes for lineage/audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bist_core.services.backtest import run_backtest


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def test_faz106_backtest_manifest_exists_and_artifact_hashes_match(tmp_path: Path) -> None:
    """Run minimal backtest; assert manifest.json exists; recompute sha256 for each artifact and match."""
    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-07-01", "2099-07-02"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nA,10.0\nB,20.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-07-01",
        date_to="2099-07-02",
        outdir=outdir,
        strategy="equal_weight",
        top_n=10,
    )
    backtest_dir = outdir / "backtest"
    manifest_path = backtest_dir / "manifest.json"
    assert manifest_path.is_file(), "manifest.json must exist"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == 1
    assert "day" in manifest
    assert "symbols_count" in manifest
    assert "policy_hash" in manifest
    artifacts = manifest.get("artifacts") or {}
    for name, expected_sha in artifacts.items():
        p = backtest_dir / name
        assert p.is_file(), f"artifact {name} must exist"
        actual = _file_sha256(p)
        assert actual == expected_sha, f"artifact {name}: hash mismatch"
