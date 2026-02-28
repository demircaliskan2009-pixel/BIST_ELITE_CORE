"""FAZ597: Execution reports â€” fills_normalized, realized_trades, positions, summary."""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from bist_core.execution.fifo import Lot, RealizedTrade
from bist_core.execution.fills_schema import Fill


def write_fills_normalized(fills: list[Fill], out_path: Path) -> None:
    """Write fills_normalized.csv."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "symbol", "side", "qty", "price", "fee_try"])
        for fill in fills:
            w.writerow([fill.ts, fill.symbol, fill.side, fill.qty, str(fill.price), str(fill.fee_try)])


def write_realized_trades(trades: list[RealizedTrade], out_path: Path) -> None:
    """Write realized_trades.csv (one row per matched piece)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "symbol", "qty", "buy_price", "sell_price", "pnl_try"])
        for t in trades:
            w.writerow([t.ts, t.symbol, t.qty, str(t.buy_price), str(t.sell_price), str(t.pnl_try)])


def write_positions(lots_by_symbol: dict[str, list[Lot]], out_path: Path) -> None:
    """Write positions.csv: symbol, qty, avg_cost per symbol."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, int, Decimal]] = []
    for sym, lots in sorted(lots_by_symbol.items()):
        total_qty = sum(lot.qty_remaining for lot in lots)
        if total_qty <= 0:
            continue
        total_cost = sum(Decimal(lot.qty_remaining) * lot.price for lot in lots)
        avg_cost = total_cost / total_qty
        rows.append((sym, total_qty, avg_cost))

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "qty", "avg_cost"])
        for sym, qty, avg in rows:
            w.writerow([sym, qty, str(avg)])


def write_execution_summary(
    n_fills: int,
    buy_notional: Decimal,
    sell_notional: Decimal,
    fees: Decimal,
    realized_pnl_try: Decimal,
    remaining_exposure_cost_try: Decimal,
    out_path: Path,
) -> None:
    """Write execution_summary.json."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "totals": {
            "n_fills": n_fills,
            "buy_notional": str(buy_notional),
            "sell_notional": str(sell_notional),
            "fees": str(fees),
            "realized_pnl_try": str(realized_pnl_try),
            "remaining_exposure_cost_try": str(remaining_exposure_cost_try),
        }
    }
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def compute_summary_totals(
    fills: list[Fill],
    realized_trades: list[RealizedTrade],
    lots_by_symbol: dict[str, list[Lot]],
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Return (buy_notional, sell_notional, fees, realized_pnl_try, remaining_exposure_cost_try)."""
    buy_notional = Decimal("0")
    sell_notional = Decimal("0")
    fees = Decimal("0")
    for f in fills:
        if f.side == "BUY":
            buy_notional += f.price * f.qty
        else:
            sell_notional += f.price * f.qty
        fees += f.fee_try

    realized_pnl_try = sum(t.pnl_try for t in realized_trades)
    remaining_cost = Decimal("0")
    for lots in lots_by_symbol.values():
        for lot in lots:
            remaining_cost += lot.price * lot.qty_remaining

    return buy_notional, sell_notional, fees, realized_pnl_try, remaining_cost
