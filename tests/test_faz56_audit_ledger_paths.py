"""
FAZ56: Audit ledger — deterministic paths and minimal schema.
Verify outdir/ledger/<day>/orders.jsonl, fills.jsonl, positions.jsonl.
No new dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.audit.ledger import (
    write_fills_jsonl,
    write_orders_jsonl,
    write_positions_jsonl,
)


def test_faz56_ledger_deterministic_paths(tmp_path: Path) -> None:
    """Ledger files are written under outdir/ledger/<day>/ with fixed filenames."""
    day = "2024-01-15"
    write_orders_jsonl(tmp_path, day, [{"symbol": "A", "side": "BUY", "weight": 0.1}])
    write_fills_jsonl(tmp_path, day, [{"symbol": "A", "side": "BUY", "qty": 10.0, "price": 5.0}])
    write_positions_jsonl(tmp_path, day, [{"symbol": "A", "qty": 10.0, "cost_basis": 50.0}])

    base = tmp_path / "ledger" / day
    assert base.is_dir()
    orders_path = base / "orders.jsonl"
    fills_path = base / "fills.jsonl"
    positions_path = base / "positions.jsonl"
    assert orders_path.is_file()
    assert fills_path.is_file()
    assert positions_path.is_file()


def test_faz56_ledger_orders_minimal_schema(tmp_path: Path) -> None:
    """orders.jsonl: each line is JSON object; minimal schema includes symbol."""
    day = "2024-01-16"
    orders = [
        {"symbol": "X", "side": "BUY", "weight": 0.2},
        {"symbol": "Y", "side": "SELL", "weight": 0.1},
    ]
    path = write_orders_jsonl(tmp_path, day, orders)
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for i, line in enumerate(lines):
        obj = json.loads(line)
        assert "symbol" in obj
        assert obj["symbol"] == orders[i]["symbol"]


def test_faz56_ledger_fills_minimal_schema(tmp_path: Path) -> None:
    """fills.jsonl: each line is JSON; minimal schema includes symbol, side, qty/price or notional."""
    day = "2024-01-17"
    fills = [
        {"symbol": "A", "side": "BUY", "qty": 10.0, "price": 5.0, "notional": 50.0, "day": day},
        {"symbol": "B", "side": "SELL", "signed_qty": -5.0, "price": 20.0, "notional": 100.0},
    ]
    path = write_fills_jsonl(tmp_path, day, fills)
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for i, line in enumerate(lines):
        obj = json.loads(line)
        assert "symbol" in obj
        assert obj["symbol"] == fills[i]["symbol"]


def test_faz56_ledger_positions_minimal_schema(tmp_path: Path) -> None:
    """positions.jsonl: each line is JSON; minimal schema includes symbol, qty, cost_basis."""
    day = "2024-01-18"
    positions = [
        {"symbol": "A", "qty": 10.0, "cost_basis": 50.0},
        {"symbol": "B", "qty": -2.0, "cost_basis": 0.0},
    ]
    path = write_positions_jsonl(tmp_path, day, positions)
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for i, line in enumerate(lines):
        obj = json.loads(line)
        assert "symbol" in obj and "qty" in obj
        assert obj["symbol"] == positions[i]["symbol"]
        assert obj["qty"] == positions[i]["qty"]


def test_faz56_ledger_empty_lists_write_valid_jsonl(tmp_path: Path) -> None:
    """Empty lists produce valid empty JSONL files (zero lines)."""
    day = "2024-01-19"
    for writer, name in [
        (write_orders_jsonl, "orders.jsonl"),
        (write_fills_jsonl, "fills.jsonl"),
        (write_positions_jsonl, "positions.jsonl"),
    ]:
        path = writer(tmp_path, day, [])
        assert path.name == name
        assert path.read_text(encoding="utf-8") == ""


def test_faz56_backtest_writes_ledger_at_deterministic_paths(tmp_path: Path) -> None:
    """run_backtest writes ledger/<day>/fills.jsonl and positions.jsonl (deterministic)."""
    from bist_core.services.backtest import run_backtest

    snapshot_root = tmp_path / "snapshots"
    for day in ["2099-07-01", "2099-07-02"]:
        (snapshot_root / day).mkdir(parents=True)
        (snapshot_root / day / "snapshot.csv").write_text(
            "symbol,close\nA,10.0\nB,20.0\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    metrics = run_backtest(
        snapshot_root=snapshot_root,
        date_from="2099-07-01",
        date_to="2099-07-02",
        outdir=outdir,
        strategy="equal_weight",
        top_n=2,
    )
    assert metrics.get("error") is None
    for day in ["2099-07-01", "2099-07-02"]:
        ledger_dir = outdir / "ledger" / day
        fills_path = ledger_dir / "fills.jsonl"
        positions_path = ledger_dir / "positions.jsonl"
        assert fills_path.is_file(), f"expected {fills_path}"
        assert positions_path.is_file(), f"expected {positions_path}"
        for p in (fills_path, positions_path):
            for line in p.read_text(encoding="utf-8").strip().split("\n"):
                if line:
                    obj = json.loads(line)
                    assert "symbol" in obj
