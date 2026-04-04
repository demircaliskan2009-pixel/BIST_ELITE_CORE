"""CLI: live paper runner (local iDeal files only)."""

from __future__ import annotations

import argparse
import os

from bist_core.live.live_runner import LiveRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Live paper trading (iDeal tail read)")
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated symbols, e.g. ASELS,THYAO",
    )
    parser.add_argument(
        "--data-path",
        default=os.environ.get("BIST_IDEAL_DATA_PATH")
        or os.environ.get("IDEAL_DATA_PATH")
        or r"C:\iDeal\ChartData\IMKBH\01",
        help="Directory containing IMKBH'<SYM>.01 files",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Sleep between full symbol scans",
    )
    parser.add_argument(
        "--state-path",
        default=None,
        help="Optional JSON path to persist positions / equity / dedup offsets",
    )
    parser.add_argument(
        "--offsets-path",
        default=None,
        help="Optional JSON path to persist per-symbol file read offsets",
    )
    parser.add_argument(
        "--max-total-positions",
        type=int,
        default=30,
        help="Max open legs across all symbols",
    )
    parser.add_argument(
        "--daily-loss-limit",
        type=float,
        default=-0.2,
        help="Block new entries when daily_pnl <= this (fractional)",
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    runner = LiveRunner(
        symbols=symbols,
        data_path=str(args.data_path),
        poll_seconds=float(args.poll_seconds),
        state_path=args.state_path,
        offsets_path=args.offsets_path,
        max_total_positions=int(args.max_total_positions),
        daily_loss_limit=float(args.daily_loss_limit),
    )
    runner.run()


if __name__ == "__main__":
    main()
