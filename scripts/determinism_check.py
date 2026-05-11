"""Determinism check — run backtest 3x, assert identical metrics."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

from bist_core.backtest.backtest_engine import BacktestEngine, CostModel
from bist_core.decision.portfolio_decision import PortfolioDecisionEngine
from bist_core.execution.order_state_machine import RiskLimits
from bist_core.execution.paper_engine import SlippageModel
from bist_core.models.ohlcv import OHLCVBar

VENDOR = "data/vendor/datastore_normalized.csv"
EVENTS = "data/events"
SYMS = [
    "SASA", "ISCTR", "CANTE", "TSPOR", "GSRAY",
    "PEKGY", "YKBNK", "EKGYO", "PSGYO", "ADESE",
    "EREGL", "HEKTS", "KATMR", "AKBNK", "PETKM",
]
EQUITY = 100_000.0
RUNS = 3


def _ts(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def load_bars():
    bars = []
    with open(VENDOR, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = r["symbol"].upper().strip()
            if s not in SYMS:
                continue
            try:
                b = OHLCVBar(
                    timestamp=_ts(r["date"]),
                    symbol=s,
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["volume"]),
                )
            except Exception:
                continue
            if b.open <= 0 or b.high <= 0 or b.low <= 0 or b.close <= 0:
                continue
            bars.append(b)
    bars.sort(key=lambda b: (b.timestamp, b.symbol))
    return bars


def build_event_index():
    idx = {}
    for fn in sorted(os.listdir(EVENTS)):
        if not fn.endswith(".jsonl"):
            continue
        with open(os.path.join(EVENTS, fn), "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                ev = json.loads(ln)
                t = ev.get("ts", "")
                ds = t[:10] if t else fn.replace(".jsonl", "")
                sym = ev.get("symbol", "")
                kind = ev.get("kind", "unknown")
                k = (ds, sym)
                if k not in idx:
                    idx[k] = []
                idx[k].append(kind)
    return idx


def run_once(bars, idx):
    cost = CostModel(
        slippage=SlippageModel(base_slippage_bps=5.0),
        commission_bps=10.0,
        exchange_fee_bps=5.0,
    )
    eng = PortfolioDecisionEngine(equity=EQUITY, event_filter_enabled=True)
    eng.load_event_index(idx)
    bt = BacktestEngine(
        cost_model=cost,
        risk_limits=RiskLimits(),
        initial_equity=EQUITY,
        decision_fn=eng,
        decision_engine=None,
    )
    result = bt.run(bars)
    closed = [t for t in result["trades"] if t["status"] == "CLOSED"]
    pnl = sum(t["pnl"] for t in closed)
    return {
        "trade_count": len(closed),
        "total_pnl": round(pnl, 4),
        "trade_ids": [t["trade_id"] for t in closed],
        "pnls": [round(t["pnl"], 4) for t in closed],
        "symbols": [t["symbol"] for t in closed],
        "edges": [t["edge"] for t in closed],
    }


def main():
    bars = load_bars()
    idx = build_event_index()

    results = []
    for i in range(RUNS):
        r = run_once(bars, idx)
        results.append(r)
        print(f"Run {i+1}: {r['trade_count']} trades, PnL={r['total_pnl']}")

    # Compare all runs to run 0
    ref = results[0]
    all_match = True
    for i in range(1, RUNS):
        r = results[i]
        if r["trade_count"] != ref["trade_count"]:
            print(f"FAIL: Run {i+1} trade_count={r['trade_count']} != {ref['trade_count']}")
            all_match = False
        if r["total_pnl"] != ref["total_pnl"]:
            print(f"FAIL: Run {i+1} total_pnl={r['total_pnl']} != {ref['total_pnl']}")
            all_match = False
        if r["trade_ids"] != ref["trade_ids"]:
            print(f"FAIL: Run {i+1} trade_ids differ")
            all_match = False
        if r["pnls"] != ref["pnls"]:
            print(f"FAIL: Run {i+1} per-trade PnLs differ")
            all_match = False
        if r["symbols"] != ref["symbols"]:
            print(f"FAIL: Run {i+1} symbols differ")
            all_match = False
        if r["edges"] != ref["edges"]:
            print(f"FAIL: Run {i+1} edges differ")
            all_match = False

    if all_match:
        print(f"\nDETERMINISM CHECK: PASS — {RUNS} runs identical")
        print(f"  trades={ref['trade_count']}, pnl={ref['total_pnl']}")
    else:
        print(f"\nDETERMINISM CHECK: FAIL")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
