"""CLI control loop — paper trader + health snapshot (no live broker)."""

from __future__ import annotations

import argparse
import sys
import time

from bist_core.live.paper_trader import PaperTrader


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run PaperTrader control loop (deterministic paper path).")
    p.add_argument(
        "--symbols",
        nargs="+",
        default=["ASELS", "GARAN", "THYAO"],
        help="Universe symbols",
    )
    p.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of run_once iterations (0 = infinite; use e.g. 1 for smoke test)",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=5.0,
        help="Seconds between cycles",
    )
    args = p.parse_args(argv)

    trader = PaperTrader(list(args.symbols))
    interval = float(args.sleep) if args.sleep and args.sleep > 0 else 5.0
    n = 0
    while True:
        result = trader.run_once()
        print("RESULT:", result)
        print("HEALTH:", trader.get_system_health())
        n += 1
        if args.cycles > 0 and n >= int(args.cycles):
            break
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
