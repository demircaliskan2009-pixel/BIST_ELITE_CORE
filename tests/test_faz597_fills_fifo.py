"""FAZ597: Fills import + FIFO realized PnL. Offline, deterministic."""
from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo / "src"))

from bist_core.execution.fills_schema import read_fills_csv
from bist_core.execution.fifo import run_fifo
from bist_core.execution.reporting import compute_summary_totals


def test_fills_schema_read_fifo_basic(tmp_path: Path) -> None:
    """Read fixture, validate FIFO: 10@100 + 5@110, sell 12@120 -> realized 220, remaining 3@110."""
    fixture = _repo / "tests" / "fixtures" / "fills_fifo_basic.csv"
    assert fixture.is_file(), f"fixture missing: {fixture}"

    fills = read_fills_csv(fixture)
    assert len(fills) == 3
    assert fills[0].symbol == "AAA" and fills[0].side == "BUY" and fills[0].qty == 10
    assert fills[1].symbol == "AAA" and fills[1].side == "BUY" and fills[1].qty == 5
    assert fills[2].symbol == "AAA" and fills[2].side == "SELL" and fills[2].qty == 12

    realized_trades, lots_by_symbol = run_fifo(fills)
    realized_pnl = sum(t.pnl_try for t in realized_trades)
    assert realized_pnl == Decimal("220"), f"expected 220, got {realized_pnl}"

    assert "AAA" in lots_by_symbol
    lots_aaa = lots_by_symbol["AAA"]
    total_qty = sum(l.qty_remaining for l in lots_aaa)
    assert total_qty == 3, f"expected remaining 3, got {total_qty}"
    total_cost = sum(Decimal(l.qty_remaining) * l.price for l in lots_aaa)
    avg_cost = total_cost / total_qty
    assert avg_cost == Decimal("110"), f"expected avg_cost 110, got {avg_cost}"


def test_import_fills_cli(tmp_path: Path) -> None:
    """Run import_fills module; assert execution_summary.json has realized_pnl_try=220."""
    fixture = _repo / "tests" / "fixtures" / "fills_fifo_basic.csv"
    out_root = tmp_path / "execution"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.execution.import_fills",
            "--day",
            "2026-02-14",
            "--fills",
            str(fixture),
            "--out-root",
            str(out_root),
        ],
        cwd=str(_repo),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(_repo / "src")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"

    out_dir = out_root / "2026-02-14"
    summary_path = out_dir / "execution_summary.json"
    assert summary_path.is_file()
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    totals = data["totals"]
    assert Decimal(totals["realized_pnl_try"]) == Decimal("220")
    assert totals["n_fills"] == 3

    positions_path = out_dir / "positions.csv"
    assert positions_path.is_file()
    lines = positions_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2  # header + AAA
    assert "AAA" in lines[1]
    parts = lines[1].split(",")
    assert parts[1] == "3"  # qty
    assert Decimal(parts[2]) == Decimal("110")  # avg_cost
