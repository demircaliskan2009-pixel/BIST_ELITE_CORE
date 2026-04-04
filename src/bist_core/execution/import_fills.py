"""FAZ597: Import fills CSV — validate, FIFO, write reports. Offline."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from bist_core.execution.fills_schema import read_fills_csv
from bist_core.execution.fifo import run_fifo
from bist_core.execution.reporting import (
    compute_summary_totals,
    write_execution_summary,
    write_fills_normalized,
    write_positions,
    write_realized_trades,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="FAZ597: Import fills, FIFO PnL, reports")
    parser.add_argument("--day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--fills", required=True, help="Path to fills CSV")
    parser.add_argument("--out-root", default="data/log/execution", help="Output root")
    args = parser.parse_args()

    fills_path = Path(args.fills)
    if not fills_path.is_file():
        print(f"fills file not found: {fills_path}", file=sys.stderr)
        return 2

    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        repo = Path(__file__).resolve().parents[3]  # src/bist_core/execution -> repo
        out_root = (repo / out_root).resolve()

    out_dir = out_root / args.day
    out_dir.mkdir(parents=True, exist_ok=True)

    fills_raw = out_dir / "fills_raw.csv"
    try:
        shutil.copy2(fills_path, fills_raw)
    except OSError:
        pass

    fills = read_fills_csv(fills_path)
    realized_trades, lots_by_symbol = run_fifo(fills)

    (
        buy_notional,
        sell_notional,
        fees,
        realized_pnl_try,
        remaining_exposure_cost_try,
    ) = compute_summary_totals(fills, realized_trades, lots_by_symbol)

    write_fills_normalized(fills, out_dir / "fills_normalized.csv")
    write_realized_trades(realized_trades, out_dir / "realized_trades.csv")
    write_positions(lots_by_symbol, out_dir / "positions.csv")
    write_execution_summary(
        n_fills=len(fills),
        buy_notional=buy_notional,
        sell_notional=sell_notional,
        fees=fees,
        realized_pnl_try=realized_pnl_try,
        remaining_exposure_cost_try=remaining_exposure_cost_try,
        out_path=out_dir / "execution_summary.json",
    )

    print(f"import_fills: day={args.day} out={out_dir}")
    print("  fills_normalized.csv")
    print("  realized_trades.csv")
    print("  positions.csv")
    print("  execution_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
