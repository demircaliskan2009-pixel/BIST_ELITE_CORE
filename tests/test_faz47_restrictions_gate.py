"""
FAZ47: Restriction-state gate (VBTS/halts/circuit) data-driven + fail-closed.
Test: blocked_symbols=["AAA"] blocks order for AAA.
"""

from __future__ import annotations

import json
from pathlib import Path


from bist_core.risk.gates import gate_restrictions
from bist_core.risk.restrictions import load_restrictions


def test_faz47_blocked_symbols_aaa_blocks_order(tmp_path: Path) -> None:
    """blocked_symbols=["AAA"] blocks order for AAA."""
    restrictions_file = tmp_path / "restrictions.json"
    restrictions_file.write_text(
        json.dumps({"blocked_symbols": ["AAA"], "short_sale_ban": False}),
        encoding="utf-8",
    )
    state, prov = load_restrictions(restrictions_file)
    assert "AAA" in (s.upper() for s in state["blocked_symbols"])

    orders_intent = {
        "day": "2024-01-01",
        "actions": [{"symbol": "AAA", "price": 10.0, "quantity": 100}],
    }
    result = gate_restrictions(orders_intent, state)
    assert result["ok"] is False
    assert "symbol_blocked" in result["errors"]
    assert result["errors"] == sorted(result["errors"])


def test_faz47_non_blocked_symbol_passes(tmp_path: Path) -> None:
    """Order for symbol not in blocked_symbols passes."""
    restrictions_file = tmp_path / "restrictions.json"
    restrictions_file.write_text(
        json.dumps({"blocked_symbols": ["AAA"], "short_sale_ban": False}),
        encoding="utf-8",
    )
    state, _ = load_restrictions(restrictions_file)
    orders_intent = {
        "day": "2024-01-01",
        "actions": [{"symbol": "BBB", "price": 10.0, "quantity": 100}],
    }
    result = gate_restrictions(orders_intent, state)
    assert result["ok"] is True
    assert result["errors"] == []


def test_faz47_short_sale_ban_blocks_short(tmp_path: Path) -> None:
    """short_sale_ban active blocks short sell (quantity < 0)."""
    restrictions_file = tmp_path / "restrictions.json"
    restrictions_file.write_text(
        json.dumps({"blocked_symbols": [], "short_sale_ban": True}),
        encoding="utf-8",
    )
    state, _ = load_restrictions(restrictions_file)
    orders_intent = {
        "day": "2024-01-01",
        "actions": [{"symbol": "CCC", "side": "short", "quantity": -100}],
    }
    result = gate_restrictions(orders_intent, state)
    assert result["ok"] is False
    assert "short_sale_blocked" in result["errors"]


def test_faz47_provenance_includes_file_and_sha256(tmp_path: Path) -> None:
    """load_restrictions returns provenance with file and sha256."""
    restrictions_file = tmp_path / "restrictions.json"
    restrictions_file.write_text(
        json.dumps({"blocked_symbols": []}),
        encoding="utf-8",
    )
    state, prov = load_restrictions(restrictions_file)
    assert "file" in prov
    assert prov["file"] == str(restrictions_file)
    assert "sha256" in prov
    assert isinstance(prov["sha256"], str)
