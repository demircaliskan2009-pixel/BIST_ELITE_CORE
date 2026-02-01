"""FAZ81: Idempotency — running live execute twice for same day/outdir must not change any artifacts (byte-identical)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _valid_core_config() -> dict:
    return {
        "timezone": "Europe/Istanbul",
        "default_spread_bps_max": 80,
        "default_adv_tl_min": 30000000,
        "default_auction_ratio_max": 0.15,
        "default_price_band_pct": 20.0,
        "risk_per_trade": 0.015,
    }


def _bist_fixture_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bist"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99,0.01\n", encoding="utf-8")
    (d / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (d / "restrictions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "restrictions.json").write_text("{}", encoding="utf-8")
    return d


def _file_hashes_under(root: Path) -> dict[str, str]:
    """Return dict of relative path -> sha256 hex for every file under root."""
    out = {}
    root = root.resolve()
    for f in root.rglob("*"):
        if f.is_file():
            rel = f.relative_to(root)
            out[str(rel).replace("\\", "/")] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def test_faz81_live_execute_twice_byte_identical_artifacts(tmp_path: Path) -> None:
    """Run CLI eod execute --live --broker paper twice; all artifacts must be byte-identical (same file hashes)."""
    day = "2099-02-01"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "core.json").write_text(json.dumps(_valid_core_config()), encoding="utf-8")
    env["BIST_CORE_CONFIG"] = str(tmp_path / "core.json")
    _bist_fixture_dir(tmp_path)
    env["BIST_RULESPACK_DIR"] = str(tmp_path / "bist")
    env["BIST_RESTRICTIONS_FILE"] = str(tmp_path / "restrictions.json")

    (tmp_path / day).mkdir(parents=True, exist_ok=True)
    orders_path = tmp_path / "orders" / day / "orders_intent.json"
    orders_path.parent.mkdir(parents=True, exist_ok=True)
    orders_path.write_text(
        json.dumps({"day": day, "actions": [{"symbol": "X", "side": "BUY", "weight": 1.0}]}),
        encoding="utf-8",
    )
    (tmp_path / day / "pipeline_manifest.json").write_text(
        json.dumps({"schema_version": 2, "day": day, "stages": {}, "orders_intent_path": str(orders_path)}),
        encoding="utf-8",
    )
    (tmp_path / "dossier" / day).mkdir(parents=True, exist_ok=True)
    (tmp_path / "dossier" / day / "dossier.json").write_text(
        json.dumps({"schema_version": 1, "day": day, "evidence": {"advice_path": "", "orders_intent_path": str(orders_path)}}),
        encoding="utf-8",
    )

    cmd = [
        sys.executable, "-m", "bist_core.cli", "eod", "execute",
        "--day", day, "--outdir", str(tmp_path), "--live", "--broker", "paper",
    ]

    r1 = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
    assert r1.returncode == 0, (r1.stdout, r1.stderr)

    hashes_after_first = _file_hashes_under(tmp_path)
    assert len(hashes_after_first) >= 1, "first run must produce at least one file"

    r2 = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
    assert r2.returncode == 0, (r2.stdout, r2.stderr)

    hashes_after_second = _file_hashes_under(tmp_path)
    for rel_path, h1 in hashes_after_first.items():
        assert rel_path in hashes_after_second, f"file {rel_path} missing after second run"
        assert hashes_after_second[rel_path] == h1, (
            f"file {rel_path} changed after second run (not byte-identical)"
        )
    assert len(hashes_after_second) == len(hashes_after_first), (
        "second run must not add or remove files (idempotent)"
    )
