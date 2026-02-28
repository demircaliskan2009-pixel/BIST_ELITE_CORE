"""FAZ35: Strategy API + orders_intent — emit-orders writes file + manifest; policy blocks (fail-closed)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz35_emit_orders_writes_file_and_manifest_references(tmp_path: Path) -> None:
    """With --emit-orders, outdir/orders/<day>/orders_intent.json is written and pipeline_manifest references it."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "snapshots"
    day = "2099-03-15"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text("symbol,close\n", encoding="utf-8")
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
            "--emit-orders",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0

    orders_path = outdir / "orders" / day / "orders_intent.json"
    assert orders_path.is_file(), f"expected {orders_path}"
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == 1
    assert payload.get("day") == day
    assert payload.get("strategy", {}).get("name") == "equal_weight"
    assert isinstance(payload.get("actions"), list)

    for manifest_path in (
        outdir / "pipeline_manifest.json",
        outdir / day / "pipeline_manifest.json",
        outdir / "_pipeline_manifest.json",
    ):
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest.get("orders_intent_path") == str(orders_path)
            assert manifest["stages"]["orders"]["path"] == str(orders_path)
            break
    else:
        raise AssertionError("no pipeline_manifest found in any of the three locations")


def test_faz35_policy_blocks_orders_empty_blocked_by_policy(tmp_path: Path) -> None:
    """When policy disallows trading, orders_intent has actions=[] and notes include blocked_by_policy (fail-closed)."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "snapshots"
    day = "2099-03-16"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text("symbol,close\nAAA,1.0\n", encoding="utf-8")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": [
                    {
                        "id": "trading_disabled",
                        "type": "trading_disabled",
                        "enabled": True,
                        "action": "deny",
                        "reason": "trading_disabled",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

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
            "--emit-orders",
            "--policy-file",
            str(policy_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0

    orders_path = outdir / "orders" / day / "orders_intent.json"
    assert orders_path.is_file()
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    assert payload["actions"] == []
    assert "blocked_by_policy" in payload.get("notes", [])

    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    orders_stage = manifest["stages"]["orders"]
    assert orders_stage["ok"] == 0
    assert "blocked_by_policy" in orders_stage["notes"]
