"""
FAZ45: Data-driven BIST RulesPack (tick size + price bands) with provenance.
Test uses tmp rulespack folder and asserts validate_tick / validate_band decisions.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from bist_core.risk.rulespack import (
    load_rulespack,
    validate_tick,
    validate_band,
    validate_price_tick,
    validate_price_band,
    tick_for_price,
    band_pct_for_market,
)


def test_faz45_validate_tick_decisions() -> None:
    """validate_tick(price, tick): on-tick valid, off-tick invalid."""
    assert validate_tick(10.00, 0.01) is True
    assert validate_tick(10.02, 0.02) is True
    assert validate_tick(100.05, 0.05) is True
    assert validate_tick(10.001, 0.01) is False
    assert validate_tick(10.03, 0.02) is False
    assert validate_tick(1.0, 0) is False
    assert validate_tick(1.0, -0.01) is False


def test_faz45_validate_band_decisions() -> None:
    """validate_band(ref_price, price, band_pct): inside band valid, outside invalid."""
    ref = 100.0
    assert validate_band(ref, 100.0, 10.0) is True
    assert validate_band(ref, 110.0, 10.0) is True
    assert validate_band(ref, 90.0, 10.0) is True
    assert validate_band(ref, 111.0, 10.0) is False
    assert validate_band(ref, 89.0, 10.0) is False
    assert validate_band(0, 10.0, 10.0) is False
    assert validate_band(100.0, 90.0, -1.0) is False


def test_faz45_rulespack_tmp_folder_decisions(tmp_path: Path) -> None:
    """Load rulespack from tmp folder; assert tick lookup and band decisions."""
    # tick_sizes: 0-9.99 -> 0.01, 10-99.99 -> 0.02
    (tmp_path / "tick_sizes.csv").write_text(
        "min_price,max_price,tick\n0,9.99,0.01\n10,99.99,0.02\n", encoding="utf-8"
    )
    # price_bands: default 10%, market X -> 5%
    (tmp_path / "price_bands.csv").write_text(
        "band_pct,market\n10,\n5,X\n", encoding="utf-8"
    )
    pack, prov = load_rulespack(tmp_path)
    assert "dir" in prov
    assert prov["tick_sizes"]["rows"] == 2
    assert prov["price_bands"]["rows"] == 2

    assert tick_for_price(pack, 5.0) == 0.01
    assert tick_for_price(pack, 50.0) == 0.02
    assert tick_for_price(pack, 1000.0) is None

    assert validate_price_tick(pack, 5.00) == (True, 0.01)
    assert validate_price_tick(pack, 5.001) == (False, 0.01)
    assert validate_price_tick(pack, 50.02) == (True, 0.02)
    assert validate_price_tick(pack, 50.03) == (False, 0.02)
    assert validate_price_tick(pack, 1000.0) == (False, None)

    assert band_pct_for_market(pack, None) == 10.0
    assert band_pct_for_market(pack, "X") == 5.0
    assert validate_price_band(pack, 100.0, 105.0, None) == (True, 10.0)
    assert validate_price_band(pack, 100.0, 112.0, None) == (False, 10.0)
    assert validate_price_band(pack, 100.0, 103.0, "X") == (True, 5.0)
    assert validate_price_band(pack, 100.0, 106.0, "X") == (False, 5.0)


def test_faz45_rulespack_provenance_keys(tmp_path: Path) -> None:
    """Provenance includes dir and per-file source/rows."""
    (tmp_path / "tick_sizes.csv").write_text(
        "min_price,max_price,tick\n0,100,0.01\n", encoding="utf-8"
    )
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    pack, prov = load_rulespack(tmp_path)
    assert prov["dir"] == str(tmp_path)
    assert "tick_sizes" in prov and prov["tick_sizes"]["source"] == "tick_sizes.csv"
    assert "price_bands" in prov and prov["price_bands"]["source"] == "price_bands.csv"
    assert pack["provenance"] == prov


def test_faz45_gate_rulespack_decisions(tmp_path: Path) -> None:
    """RiskGateEngine with rulespack: pass when tick/band valid, block when violated."""
    from bist_core.risk.gates import RiskGateEngine

    (tmp_path / "tick_sizes.csv").write_text(
        "min_price,max_price,tick\n0,99.99,0.01\n100,999.99,0.05\n", encoding="utf-8"
    )
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    pack, _ = load_rulespack(tmp_path)
    gate = RiskGateEngine()
    stages = {"snapshot": {"errors": 0}, "advice": {"errors": 0}}

    # valid tick (105.00 on 0.05) and within band (ref 100, price 105)
    allowed, notes = gate.evaluate(
        {"day": "2024-01-01", "actions": [{"symbol": "A", "price": 105.0, "ref_price": 100.0}]},
        stages=stages,
        rulespack=pack,
    )
    assert allowed is True

    # invalid tick (10.001)
    allowed, notes = gate.evaluate(
        {"day": "2024-01-01", "actions": [{"symbol": "A", "price": 10.001}]},
        stages=stages,
        rulespack=pack,
    )
    assert allowed is False
    assert any("tick" in n for n in notes)

    # valid tick but band violation (ref 100, price 115 > 110)
    allowed, notes = gate.evaluate(
        {"day": "2024-01-01", "actions": [{"symbol": "A", "price": 100.0, "ref_price": 100.0}]},
        stages=stages,
        rulespack=pack,
    )
    assert allowed is True
    allowed, notes = gate.evaluate(
        {"day": "2024-01-01", "actions": [{"symbol": "A", "price": 115.0, "ref_price": 100.0}]},
        stages=stages,
        rulespack=pack,
    )
    assert allowed is False
    assert any("band" in n for n in notes)
