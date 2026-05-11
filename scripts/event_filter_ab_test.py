"""A/B Test — Event Filter Impact on Backtest Performance.

Runs the clean backtest twice:
  A) BASELINE: no event filtering
  B) EVENT FILTER: evidence-based event policy (Phase 2 alpha study)

Compares: PF, total return, MaxDD, trade count.

Usage:
    python scripts/event_filter_ab_test.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bist_core.backtest.backtest_engine import BacktestEngine, CostModel
from bist_core.decision.portfolio_decision import PortfolioDecisionEngine
from bist_core.execution.order_state_machine import RiskLimits
from bist_core.execution.paper_engine import SlippageModel
from bist_core.models.ohlcv import OHLCVBar

VENDOR_CSV = ROOT / "data" / "vendor" / "datastore_normalized.csv"
EVENTS_DIR = ROOT / "data" / "events"

SYMBOL_UNIVERSE = [
    "SASA", "ISCTR", "CANTE", "TSPOR", "GSRAY",
    "PEKGY", "YKBNK", "EKGYO", "PSGYO", "ADESE",
    "EREGL", "HEKTS", "KATMR", "AKBNK", "PETKM",
]

INITIAL_EQUITY = 100_000.0


def _date_to_unix(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_bars() -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    with VENDOR_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row["symbol"].upper().strip()
            if symbol not in SYMBOL_UNIVERSE:
                continue
            try:
                bar = OHLCVBar(
                    timestamp=_date_to_unix(row["date"]),
                    symbol=symbol,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            except (KeyError, ValueError):
                continue
            if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
                continue
            if bar.volume < 0:
                continue
            bars.append(bar)
    bars.sort(key=lambda b: (b.timestamp, b.symbol))
    return bars


def build_event_index() -> dict[tuple[str, str], list[str]]:
    """Build (date, symbol) → [event_kind] index from JSONL files."""
    index: dict[tuple[str, str], list[str]] = {}
    if not EVENTS_DIR.is_dir():
        return index
    for fname in sorted(os.listdir(EVENTS_DIR)):
        if not fname.endswith(".jsonl"):
            continue
        fpath = EVENTS_DIR / fname
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                ts_str = ev.get("ts", "")
                date_str = ts_str[:10] if ts_str else fname.replace(".jsonl", "")
                symbol = ev.get("symbol", "")
                kind = ev.get("kind", "unknown")
                key = (date_str, symbol)
                if key not in index:
                    index[key] = []
                index[key].append(kind)
    return index


def compute_metrics(result: dict, label: str = "") -> dict:
    """Extract key metrics from backtest result."""
    trades = [t for t in result.get("trades", []) if t.get("status") == "CLOSED"]
    equity_curve = result.get("equity_curve", [])

    if not trades:
        return {
            "trade_count": 0,
            "total_return_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "avg_pnl": 0.0,
            "avg_position_size": 0.0,
            "min_position_size": 0,
            "max_position_size": 0,
            "median_position_size": 0,
            "event_trade_count": 0,
            "technical_trade_count": 0,
            "event_pnl": 0.0,
            "technical_pnl": 0.0,
        }

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # Equity curve drawdown
    peak = INITIAL_EQUITY
    max_dd = 0.0
    for point in equity_curve:
        eq = float(point.get("equity", INITIAL_EQUITY))
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    final_eq = float(equity_curve[-1]["equity"]) if equity_curve else INITIAL_EQUITY
    total_ret = ((final_eq - INITIAL_EQUITY) / INITIAL_EQUITY) * 100

    # Position size statistics
    sizes = [t["position_size"] for t in trades]
    sorted_sizes = sorted(sizes)
    median_size = sorted_sizes[len(sorted_sizes) // 2] if sorted_sizes else 0

    # Source breakdown (event entries have edge starting with "event_")
    event_trades = [t for t in trades if t.get("edge", "").startswith("event_")]
    tech_trades = [t for t in trades if not t.get("edge", "").startswith("event_")]
    event_pnl = sum(t["pnl"] for t in event_trades)
    tech_pnl = sum(t["pnl"] for t in tech_trades)

    return {
        "trade_count": len(trades),
        "total_return_pct": round(total_ret, 2),
        "profit_factor": round(pf, 4),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "avg_position_size": round(sum(sizes) / len(sizes), 1) if sizes else 0.0,
        "min_position_size": min(sizes) if sizes else 0,
        "max_position_size": max(sizes) if sizes else 0,
        "median_position_size": median_size,
        "event_trade_count": len(event_trades),
        "technical_trade_count": len(tech_trades),
        "event_pnl": round(event_pnl, 2),
        "technical_pnl": round(tech_pnl, 2),
    }


def run_backtest(event_filter: bool, event_index: dict | None = None) -> tuple[dict, list]:
    """Run backtest with or without event filter.

    Returns (backtest_result, event_log).
    """
    cost = CostModel(
        slippage=SlippageModel(base_slippage_bps=5.0),
        commission_bps=10.0,
        exchange_fee_bps=5.0,
    )
    risk = RiskLimits()
    decision = PortfolioDecisionEngine(equity=INITIAL_EQUITY, event_filter_enabled=event_filter)
    if event_filter and event_index:
        decision.load_event_index(event_index)

    engine = BacktestEngine(
        cost_model=cost,
        risk_limits=risk,
        initial_equity=INITIAL_EQUITY,
        decision_fn=decision,
        decision_engine=None,
    )
    result = engine.run(bars)
    return result, getattr(decision, "_event_log", [])


def main():
    global bars
    print("Loading price data...", file=sys.stderr)
    bars = load_bars()
    symbols = sorted(set(b.symbol for b in bars))
    dates = sorted(set(b.timestamp for b in bars))
    print(f"  {len(bars)} bars, {len(symbols)} symbols, {len(dates)} dates", file=sys.stderr)

    print("Building event index...", file=sys.stderr)
    event_index = build_event_index()
    # Count events for universe symbols
    universe_events = sum(
        len(kinds)
        for (d, s), kinds in event_index.items()
        if s in SYMBOL_UNIVERSE
    )
    print(f"  {len(event_index)} date-symbol pairs, {universe_events} events for universe", file=sys.stderr)

    # --- Run A: BASELINE (no event filter) ---
    print("\n=== RUN A: BASELINE (no event filter) ===", file=sys.stderr)
    result_a, log_a = run_backtest(event_filter=False)
    metrics_a = compute_metrics(result_a)

    # --- Run B: EVENT FILTER ---
    print("\n=== RUN B: WITH EVENT FILTER ===", file=sys.stderr)
    result_b, log_b = run_backtest(event_filter=True, event_index=event_index)
    metrics_b = compute_metrics(result_b)

    # --- Comparison ---
    report = {
        "baseline": metrics_a,
        "event_filter": metrics_b,
        "delta": {
            "trade_count": metrics_b["trade_count"] - metrics_a["trade_count"],
            "total_return_pct": round(metrics_b["total_return_pct"] - metrics_a["total_return_pct"], 2),
            "profit_factor": round(metrics_b["profit_factor"] - metrics_a["profit_factor"], 4),
            "max_drawdown_pct": round(metrics_b["max_drawdown_pct"] - metrics_a["max_drawdown_pct"], 2),
            "win_rate_pct": round(metrics_b["win_rate_pct"] - metrics_a["win_rate_pct"], 2),
            "avg_position_size": round(metrics_b["avg_position_size"] - metrics_a["avg_position_size"], 1),
        },
    }

    # Event interaction summary
    event_entries = [e for e in log_b if e.get("source") == "event"]
    event_interactions = [e for e in log_b if e.get("event_multiplier", 1.0) != 1.0]
    boosted = [e for e in log_b if e.get("event_multiplier", 1.0) > 1.0]
    penalized = [e for e in log_b if e.get("event_multiplier", 1.0) < 1.0 and e.get("source") != "event"]
    report["event_interactions"] = {
        "total_decisions": len(log_b),
        "event_entries": len(event_entries),
        "size_modified": len(event_interactions),
        "boosted": len(boosted),
        "penalized": len(penalized),
        "details": log_b[:20],  # first 20 for inspection
    }

    # Determine verdict
    pf_improved = metrics_b["profit_factor"] > metrics_a["profit_factor"]
    dd_improved = metrics_b["max_drawdown_pct"] < metrics_a["max_drawdown_pct"]
    ret_improved = metrics_b["total_return_pct"] > metrics_a["total_return_pct"]
    ret_dd_ratio_a = (
        metrics_a["total_return_pct"] / metrics_a["max_drawdown_pct"]
        if metrics_a["max_drawdown_pct"] > 0
        else 0.0
    )
    ret_dd_ratio_b = (
        metrics_b["total_return_pct"] / metrics_b["max_drawdown_pct"]
        if metrics_b["max_drawdown_pct"] > 0
        else 0.0
    )
    risk_adj_improved = ret_dd_ratio_b > ret_dd_ratio_a

    if ret_improved:
        verdict = "PASS — return increased"
    elif dd_improved:
        verdict = "PASS — drawdown decreased"
    elif risk_adj_improved:
        verdict = "PASS — risk-adjusted return improved"
    elif pf_improved:
        verdict = "PASS — PF improved"
    elif len(event_interactions) == 0:
        verdict = "FAIL — NO EVENT INTERACTION (events not hitting trades)"
    else:
        verdict = "FAIL — event filter worsens performance"

    report["verdict"] = verdict
    report["risk_adjusted"] = {
        "baseline_ret_dd": round(ret_dd_ratio_a, 4),
        "filtered_ret_dd": round(ret_dd_ratio_b, 4),
    }

    # Print comparison table
    print("\n" + "=" * 90)
    print(f"{'METRIC':<30} {'BASELINE':>15} {'EVENT FILTER':>15} {'DELTA':>15}")
    print("=" * 90)
    display_keys = [
        "trade_count", "event_trade_count", "technical_trade_count",
        "total_return_pct", "profit_factor",
        "max_drawdown_pct", "win_rate_pct", "avg_pnl",
        "event_pnl", "technical_pnl",
        "avg_position_size", "min_position_size", "max_position_size",
        "median_position_size",
    ]
    for key in display_keys:
        a_val = metrics_a[key]
        b_val = metrics_b[key]
        delta = b_val - a_val
        sign = "+" if delta > 0 else ""
        print(f"{key:<30} {a_val:>15} {b_val:>15} {sign}{delta:>14.4f}")
    print("-" * 90)
    print(f"{'ret/dd_ratio':<30} {ret_dd_ratio_a:>15.4f} {ret_dd_ratio_b:>15.4f} {'+'if ret_dd_ratio_b > ret_dd_ratio_a else ''}{ret_dd_ratio_b - ret_dd_ratio_a:>14.4f}")
    print("=" * 90)

    # Event interaction summary
    print(f"\nEVENT INTERACTIONS:")
    print(f"  Total decisions logged:   {len(log_b)}")
    print(f"  Event-driven entries:     {len(event_entries)}")
    print(f"  Size-modified by events:  {len(event_interactions)}")
    print(f"  Boosted (size increased): {len(boosted)}")
    print(f"  Penalized (size reduced): {len(penalized)}")
    if event_entries:
        print(f"\n  Event entry details:")
        for e in event_entries[:15]:
            print(f"    {e['symbol']} | {e['event_kind']} | ×{e['event_multiplier']} | base={e['base_size']} → final={e['final_size']} | {e['reason']}")
    if penalized:
        print(f"\n  Penalized trade details:")
        for e in penalized[:10]:
            print(f"    {e['symbol']} | {e['event_kind']} | ×{e['event_multiplier']} | base={e['base_size']} → final={e['final_size']}")

    print(f"\nVERDICT: {verdict}")

    # Save report
    out_path = ROOT / "tmp" / "event_filter_ab_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {out_path}")

    # JSON output
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
