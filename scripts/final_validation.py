"""Final validation — Phase 7: full A/B backtest with complete metrics."""

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


def maxdd(trades, eq):
    peak = eq
    dd = 0
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return abs(dd) / peak * 100 if peak > 0 else 0


def main():
    bars = load_bars()
    idx = build_event_index()
    cost = CostModel(
        slippage=SlippageModel(base_slippage_bps=5.0),
        commission_bps=10.0,
        exchange_fee_bps=5.0,
    )

    # Baseline (no events)
    eng_b = PortfolioDecisionEngine(equity=EQUITY, event_filter_enabled=False)
    bt_b = BacktestEngine(
        cost_model=cost, risk_limits=RiskLimits(),
        initial_equity=EQUITY, decision_fn=eng_b, decision_engine=None,
    )
    rb = bt_b.run(bars)

    # Event-filtered
    eng_e = PortfolioDecisionEngine(equity=EQUITY, event_filter_enabled=True)
    eng_e.load_event_index(idx)
    bt_e = BacktestEngine(
        cost_model=cost, risk_limits=RiskLimits(),
        initial_equity=EQUITY, decision_fn=eng_e, decision_engine=None,
    )
    re = bt_e.run(bars)

    # Closed trades
    tb = [t for t in rb["trades"] if t["status"] == "CLOSED"]
    te = [t for t in re["trades"] if t["status"] == "CLOSED"]
    pnl_b = sum(t["pnl"] for t in tb)
    pnl_e = sum(t["pnl"] for t in te)
    ret_b = pnl_b / EQUITY * 100
    ret_e = pnl_e / EQUITY * 100

    dd_b = maxdd(tb, EQUITY)
    dd_e = maxdd(te, EQUITY)

    # Profit factor
    wins_b = sum(t["pnl"] for t in tb if t["pnl"] > 0)
    loss_b = abs(sum(t["pnl"] for t in tb if t["pnl"] < 0))
    wins_e = sum(t["pnl"] for t in te if t["pnl"] > 0)
    loss_e = abs(sum(t["pnl"] for t in te if t["pnl"] < 0))
    pf_b = wins_b / loss_b if loss_b > 0 else 0
    pf_e = wins_e / loss_e if loss_e > 0 else 0

    # Event breakdown
    evt = [t for t in te if t.get("edge", "").startswith("event_")]
    tech = [t for t in te if not t.get("edge", "").startswith("event_")]
    evpnl = sum(t["pnl"] for t in evt)
    techpnl = sum(t["pnl"] for t in tech)

    # Tracker desync
    actual_open_b = sum(1 for t in rb["trades"] if t["status"] != "CLOSED")
    tracker_b = eng_b._tracker.total_open()
    actual_open_e = sum(1 for t in re["trades"] if t["status"] != "CLOSED")
    tracker_e = eng_e._tracker.total_open()

    # Rejected bars
    rej_b = rb["metrics"].get("rejected_bars", 0)
    rej_e = re["metrics"].get("rejected_bars", 0)

    # Auditability check
    has_source = all("source" in t for t in re["trades"])
    has_event_kind = all("event_kind" in t for t in re["trades"])
    has_event_mult = all("event_multiplier" in t for t in re["trades"])

    # Ret/DD ratio
    retdd_b = ret_b / dd_b if dd_b > 0 else 0
    retdd_e = ret_e / dd_e if dd_e > 0 else 0

    print("=" * 60)
    print("FINAL VALIDATION — BIST ELITE CORE PRDV3")
    print("=" * 60)
    print(f"Baseline:  {len(tb)} trades, {ret_b:.2f}% ret, PF={pf_b:.2f}, MaxDD={dd_b:.2f}%, rej_bars={rej_b}")
    print(f"Filtered:  {len(te)} trades ({len(evt)} event + {len(tech)} tech), {ret_e:.2f}% ret, PF={pf_e:.2f}, MaxDD={dd_e:.2f}%, rej_bars={rej_e}")
    print(f"Event PnL: {evpnl:.2f}, Tech PnL: {techpnl:.2f}")
    print(f"Ret/DD:    {retdd_b:.2f} -> {retdd_e:.2f}")
    print(f"Desync:    baseline={tracker_b - actual_open_b}, filtered={tracker_e - actual_open_e}")
    print(f"Audit:     source={has_source}, event_kind={has_event_kind}, event_multiplier={has_event_mult}")
    print(f"Config:    frozen=True, market=bist, entry_kinds={{partnership}}")
    print("=" * 60)

    # Assertions
    assert tracker_b - actual_open_b == 0, "Baseline desync!"
    assert tracker_e - actual_open_e == 0, "Filtered desync!"
    assert has_source, "Missing source field"
    assert has_event_kind, "Missing event_kind field"
    assert has_event_mult, "Missing event_multiplier field"
    assert len(te) > len(tb), "Event filter should generate more trades"
    assert pf_e >= pf_b, "Event filter PF regression"
    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
