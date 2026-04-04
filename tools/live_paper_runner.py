#!/usr/bin/env python3
"""Live paper trading runner — BIST session-aware continuous loop.
Usage: IDEAL_CHART_DIR=C:/iDeal/ChartData/IMKBH python tools/live_paper_runner.py
"""
from __future__ import annotations
import os
import sys
import time
import json
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bist_core.live.paper_trader import PaperTrader

SYMBOLS = os.environ.get("BIST_SYMBOLS", "GARAN,AKBNK,THYAO,SISE,KCHOL,EREGL,BIMAS,ARCLK,TOASO,FROTO").split(",")
INITIAL_CAPITAL = float(os.environ.get("BIST_CAPITAL", "100000"))
INTERVAL_SEC = int(os.environ.get("BIST_INTERVAL", "60"))
SESSION_START = dt.time(10, 0)
SESSION_END = dt.time(18, 0)
LOG_PATH = Path(os.environ.get("BIST_LOG", "paper_trades.jsonl"))


def _in_session(now: dt.datetime) -> bool:
    if now.weekday() >= 5:
        return False
    return SESSION_START <= now.time() < SESSION_END


def _log(entry: dict) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        print(f"LOG ERROR: {e}", flush=True)


def _print(msg: str) -> None:
    print(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main() -> None:
    _print(f"LIVE PAPER TRADER STARTING — symbols={SYMBOLS} capital={INITIAL_CAPITAL}")
    pt = PaperTrader(symbols=SYMBOLS, initial_capital=INITIAL_CAPITAL)

    while True:
        start = time.time()
        now = dt.datetime.now()

        if not _in_session(now):
            _print(f"OUT OF SESSION ({now.strftime('%H:%M')} weekday={now.weekday()}) — sleeping {INTERVAL_SEC}s")
            time.sleep(INTERVAL_SEC)
            continue

        try:
            result = pt.run_once()
            status = result["status"]
            count = result["count"]
            trades = result["trades"]

            log_entry = {
                "ts": now.isoformat(),
                "status": status,
                "count": count,
                "reason": result.get("reason", ""),
                "trades": trades,
            }
            _log(log_entry)

            if status == "executed":
                _print(f"EXECUTED — {count} trade(s)")
                for t in trades:
                    _print(f"  TRADE: {t.get('symbol')} entry={t.get('entry')} net_pnl={t.get('net_pnl')}")
            else:
                _print(f"NO TRADE — {result.get('reason', 'unknown')}")

        except Exception as e:
            _print(f"CYCLE ERROR (fail-closed): {type(e).__name__}: {e}")

        elapsed = time.time() - start
        time.sleep(max(0, INTERVAL_SEC - elapsed))


if __name__ == "__main__":
    main()
