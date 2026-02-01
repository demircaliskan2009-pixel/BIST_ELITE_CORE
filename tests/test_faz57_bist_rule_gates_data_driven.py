"""
FAZ57: Data-driven BIST risk gates (no hardcoded rule numbers).
Preflight requires tick_sizes, price_bands, vbts/restrictions when live; fail-closed when missing.
Tests: tmp fixtures; fail-closed when missing; allowed when fixtures present.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.risk.bist_rules import preflight_for_live
from bist_core.risk.gates import preflight_bist_rules_for_live


def test_faz57_preflight_fail_closed_when_tick_bands_missing(tmp_path: Path) -> None:
    """When rulespack dir empty or missing tick_sizes/price_bands -> preflight not ok, errors include bist_rules_tick_bands_missing."""
    # No tick_sizes, no price_bands
    ok, err = preflight_for_live(rulespack_dir=tmp_path, restrictions_path=tmp_path / "restrictions.json")
    assert ok is False
    assert "bist_rules_tick_bands_missing" in err

    (tmp_path / "restrictions.json").write_text('{"blocked_symbols": [], "short_sale_ban": false}', encoding="utf-8")
    ok2, err2 = preflight_for_live(rulespack_dir=tmp_path, restrictions_path=tmp_path / "restrictions.json")
    assert ok2 is False
    assert "bist_rules_tick_bands_missing" in err2


def test_faz57_preflight_fail_closed_when_vbts_missing(tmp_path: Path) -> None:
    """When restrictions file missing -> preflight not ok, errors include bist_rules_vbts_missing."""
    (tmp_path / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99.99,0.01\n", encoding="utf-8")
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    ok, err = preflight_for_live(rulespack_dir=tmp_path, restrictions_path=None)
    assert ok is False
    assert "bist_rules_vbts_missing" in err

    ok2, err2 = preflight_for_live(rulespack_dir=tmp_path, restrictions_path=tmp_path / "nonexistent.json")
    assert ok2 is False
    assert "bist_rules_vbts_missing" in err2


def test_faz57_preflight_allowed_when_fixtures_present(tmp_path: Path) -> None:
    """When rulespack has tick_sizes + price_bands and restrictions file exists -> preflight ok."""
    (tmp_path / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99.99,0.01\n", encoding="utf-8")
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (tmp_path / "restrictions.json").write_text('{"blocked_symbols": [], "short_sale_ban": false}', encoding="utf-8")
    ok, err = preflight_for_live(rulespack_dir=tmp_path, restrictions_path=tmp_path / "restrictions.json")
    assert ok is True
    assert err == []


def test_faz57_gates_preflight_wrapper(tmp_path: Path) -> None:
    """preflight_bist_rules_for_live in gates mirrors preflight_for_live."""
    (tmp_path / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99.99,0.01\n", encoding="utf-8")
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    (tmp_path / "restrictions.json").write_text('{"blocked_symbols": []}', encoding="utf-8")
    ok, err = preflight_bist_rules_for_live(rulespack_dir=tmp_path, restrictions_path=tmp_path / "restrictions.json")
    assert ok is True
    assert err == []

    ok2, err2 = preflight_bist_rules_for_live(rulespack_dir=tmp_path, restrictions_path=None)
    assert ok2 is False
    assert "bist_rules_vbts_missing" in err2


def test_faz57_execute_live_fail_closed_when_bist_rules_missing(tmp_path: Path) -> None:
    """eod execute --live with missing BIST rule data (no rulespack/restrictions) -> exit 2, blocked."""
    repo_root = Path(__file__).resolve().parents[1]
    outdir = tmp_path / "out"
    outdir.mkdir()
    day = "2099-01-01"
    (outdir / day).mkdir()
    (outdir / day / "pipeline_manifest.json").write_text(
        '{"schema_version":2,"day":"2099-01-01","stages":{},"orders_intent_path":"' + str(outdir / "orders" / day / "orders_intent.json").replace("\\", "/") + '"}',
        encoding="utf-8",
    )
    (outdir / "orders" / day).mkdir(parents=True)
    (outdir / "orders" / day / "orders_intent.json").write_text(
        '{"day":"2099-01-01","actions":[]}',
        encoding="utf-8",
    )
    empty_rules = tmp_path / "empty_rules"
    empty_rules.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_RULESPACK_DIR"] = str(empty_rules)
    env.pop("BIST_RESTRICTIONS_FILE", None)
    cmd = [
        sys.executable, "-m", "bist_core.cli", "eod", "execute",
        "--day", day, "--outdir", str(outdir), "--live", "--broker", "paper",
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert r.returncode == 2
    err = (r.stderr or "").lower()
    assert ("blocked" in err) or ("bist_rules_missing" in err)
    assert "bist_rules" in (r.stderr or r.stdout or "")
