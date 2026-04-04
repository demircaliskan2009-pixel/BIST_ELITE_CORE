"""
FAZ65: End-to-end golden path test.
Runs snapshot -> research -> advice -> orders -> execute(paper) for one day.
Asserts all deterministic artifacts exist and manifest schema v2 has full provenance + audit paths.
Fast, no external deps (stub research, tmp snapshot).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_daily_run_paper(day: str, outdir: Path, snapshot_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_dir)
    env["BIST_RESEARCH_SOURCE"] = "stub"
    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "daily",
        "run",
        "--day",
        day,
        "--outdir",
        str(outdir),
        "--paper",
    ]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


def _find_manifest(outdir: Path, day: str) -> Path:
    for p in (
        outdir / day / "pipeline_manifest.json",
        outdir / "pipeline_manifest.json",
        outdir / "_pipeline_manifest.json",
    ):
        if p.is_file():
            return p
    raise FileNotFoundError(f"pipeline_manifest.json not found under {outdir}")


def test_faz65_golden_path_artifacts_and_manifest_schema_v2(tmp_path: Path) -> None:
    """Full pipeline snapshot->research->advice->orders->execute(paper); assert artifacts + manifest v2 provenance/audit."""
    day = "2099-01-20"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / f"{day}.csv").write_text(
        "symbol,date,close\nAAA,2099-01-20,10\nBBB,2099-01-20,20\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"

    r = _run_daily_run_paper(day, outdir, snap_dir)
    # Pipeline must succeed; execute(paper) may return 0 or 2 (e.g. risk gate in minimal env)
    assert r.returncode in (0, 2), f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"

    # --- Manifest exists and schema v2 ---
    manifest_path = _find_manifest(outdir, day)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == 2
    assert "run_id" in manifest
    assert "started_at_utc" in manifest and manifest["started_at_utc"]
    assert "finished_at_utc" in manifest and manifest["finished_at_utc"]
    assert manifest.get("day") == day
    assert "provenance" in manifest
    prov = manifest["provenance"]
    assert "snapshot_hash" in prov or "cli_args" in prov
    assert "stages" in manifest

    # --- Per-stage provenance and audit paths ---
    stages = manifest["stages"]
    for stage_name in ("snapshot", "advice", "dossier", "orders"):
        assert stage_name in stages, f"stage {stage_name} missing"
        stage = stages[stage_name]
        assert "provenance" in stage
        if stage_name == "advice" and stage.get("path"):
            assert "advice" in (stage["path"] or "") or "advice_records" in (stage["path"] or "")
    if "research" in stages and stages["research"].get("path"):
        assert "research" in stages["research"]["path"]

    # --- Audit paths in manifest ---
    if manifest.get("orders_intent_path"):
        assert "orders" in manifest["orders_intent_path"] and "orders_intent" in manifest["orders_intent_path"]

    # --- Deterministic artifacts ---
    advice_path = outdir / "advice" / day / "advice_records.jsonl"
    assert advice_path.is_file(), f"advice_records.jsonl missing: {advice_path}"
    orders_path = outdir / "orders" / day / "orders_intent.json"
    assert orders_path.is_file(), f"orders_intent.json missing: {orders_path}"
    dossier_path = outdir / "dossier" / day / "dossier.json"
    assert dossier_path.is_file(), f"dossier.json missing: {dossier_path}"
    execution_result_path = outdir / day / "execution_result.json"
    assert execution_result_path.is_file(), f"execution_result.json missing: {execution_result_path}"

    # Research (stub): optional path from env
    research_entries = outdir / day / "research" / "entries.jsonl"
    if research_entries.is_file():
        lines = research_entries.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1

    # Manifest stage paths point to existing key artifacts
    assert stages.get("advice", {}).get("path")
    assert (
        Path(stages["advice"]["path"]).is_file() or (Path(stages["advice"]["path"]) / "advice_records.jsonl").is_file()
    )
    assert Path(stages["orders"]["path"]).is_file()
    assert stages.get("dossier", {}).get("path") or stages.get("dossier", {}).get("dossier_json_path")
    dossier_ref = stages["dossier"].get("dossier_json_path") or stages["dossier"].get("path")
    if dossier_ref and "dossier.json" in dossier_ref:
        assert Path(dossier_ref).is_file()
    elif dossier_ref:
        assert Path(dossier_ref).is_dir() or Path(dossier_ref).is_file()
