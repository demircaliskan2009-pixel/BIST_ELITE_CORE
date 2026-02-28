"""
FAZ46: Pre-execution order validation gate using RulesPack (tick/band/lot/notional), fail-closed.
Test: tmp rulespack, order with off-tick price => blocked.
"""

from __future__ import annotations

from pathlib import Path


from bist_core.risk.gates import gate_order_rules
from bist_core.risk.rulespack import load_rulespack


def test_faz46_off_tick_price_blocked(tmp_path: Path) -> None:
    """Create tmp rulespack; order with off-tick price => blocked (errors include tick_violation)."""
    (tmp_path / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99.99,0.01\n", encoding="utf-8")
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    pack, _ = load_rulespack(tmp_path)

    order = {"symbol": "A", "price": 10.001, "ref_price": 10.0}
    result = gate_order_rules(order, pack, ref_price=10.0)
    assert result["ok"] is False
    assert "tick_violation" in result["errors"]
    assert result["errors"] == sorted(result["errors"])


def test_faz46_on_tick_price_passes(tmp_path: Path) -> None:
    """On-tick price and within band => ok."""
    (tmp_path / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99.99,0.01\n", encoding="utf-8")
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n10,\n", encoding="utf-8")
    pack, _ = load_rulespack(tmp_path)

    order = {"symbol": "A", "price": 10.0, "ref_price": 10.0}
    result = gate_order_rules(order, pack, ref_price=10.0)
    assert result["ok"] is True
    assert result["errors"] == []


def test_faz46_deterministic_errors_sorted(tmp_path: Path) -> None:
    """Errors list is sorted for deterministic output."""
    (tmp_path / "tick_sizes.csv").write_text("min_price,max_price,tick\n0,99.99,0.01\n", encoding="utf-8")
    (tmp_path / "price_bands.csv").write_text("band_pct,market\n1,\n", encoding="utf-8")
    pack, _ = load_rulespack(tmp_path)
    pack["max_notional"] = 100.0

    order = {"symbol": "A", "price": 10.001, "ref_price": 10.0, "quantity": 20}
    result = gate_order_rules(order, pack, ref_price=10.0)
    assert result["ok"] is False
    assert result["errors"] == sorted(result["errors"])
    assert "tick_violation" in result["errors"]
