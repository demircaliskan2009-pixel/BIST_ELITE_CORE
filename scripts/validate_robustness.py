"""PRDV3 Walk-Forward + Monte Carlo Validation — deterministic robustness testing.

Validates backtest results are not overfit by:
1. Walk-forward: train on window, test on next window, roll
2. Monte Carlo: trade-order shuffle, slippage increase, random loss injection
3. Multi-dimensional stability check

Usage:
    python scripts/validate_robustness.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bist_core.backtest.backtest_engine import BacktestEngine, CostModel
from bist_core.decision.portfolio_decision import PortfolioDecisionEngine
from bist_core.execution.order_state_machine import RiskLimits
from bist_core.execution.paper_engine import SlippageModel
from bist_core.models.ohlcv import OHLCVBar

VENDOR_CSV = ROOT / "data" / "vendor" / "datastore_normalized.csv"
INITIAL_EQUITY = 100_000.0

# Same universe as run_clean_backtest.py
SYMBOL_UNIVERSE = [
    "SASA", "ISCTR", "CANTE", "TSPOR", "GSRAY",
    "PEKGY", "YKBNK", "EKGYO", "PSGYO", "ADESE",
    "EREGL", "HEKTS", "KATMR", "AKBNK", "PETKM",
]


def _date_to_unix(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_all_bars() -> list[OHLCVBar]:
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


def run_backtest_on_bars(bars: list[OHLCVBar]) -> dict:
    cost = CostModel(
        slippage=SlippageModel(base_slippage_bps=5.0),
        commission_bps=10.0,
        exchange_fee_bps=5.0,
    )
    engine = BacktestEngine(
        cost_model=cost,
        risk_limits=RiskLimits(),
        initial_equity=INITIAL_EQUITY,
        decision_fn=PortfolioDecisionEngine(equity=INITIAL_EQUITY),
        decision_engine=None,
    )
    return engine.run(bars)


# ===================================================================
# 1. Walk-Forward Validation
# ===================================================================


def walk_forward(
    bars: list[OHLCVBar],
    train_days: int = 180,
    test_days: int = 60,
) -> list[dict]:
    """Roll train/test windows across data and run independent backtests."""
    timestamps = sorted(set(b.timestamp for b in bars))
    results = []

    i = 0
    window_id = 0
    while i + train_days + test_days <= len(timestamps):
        train_end_ts = timestamps[i + train_days - 1]
        test_start_ts = timestamps[i + train_days]
        test_end_idx = min(i + train_days + test_days - 1, len(timestamps) - 1)
        test_end_ts = timestamps[test_end_idx]

        # Split bars
        train_bars = [b for b in bars if b.timestamp <= train_end_ts
                      and b.timestamp >= timestamps[i]]
        test_bars = [b for b in bars if b.timestamp >= test_start_ts
                     and b.timestamp <= test_end_ts]

        if not train_bars or not test_bars:
            i += test_days
            continue

        # Run test window only (train window is for universe calibration context)
        # But we need ALL bars up to test end for proper warmup
        context_bars = [b for b in bars if b.timestamp <= test_end_ts
                        and b.timestamp >= timestamps[i]]

        result = run_backtest_on_bars(context_bars)
        metrics = result.get("metrics", {})

        # Extract test-period trades only
        all_trades = result.get("trades", [])
        test_trades = [
            t for t in all_trades
            if t.get("status") == "CLOSED"
            and isinstance(t.get("entry_time"), (int, float))
            and t["entry_time"] >= test_start_ts
        ]

        test_pnl = sum(t.get("pnl", 0) for t in test_trades)
        test_wins = sum(1 for t in test_trades if t.get("pnl", 0) > 0)
        test_losses = sum(1 for t in test_trades if t.get("pnl", 0) <= 0)
        test_gross_win = sum(t["pnl"] for t in test_trades if t["pnl"] > 0)
        test_gross_loss = abs(sum(t["pnl"] for t in test_trades if t["pnl"] <= 0))
        test_pf = test_gross_win / test_gross_loss if test_gross_loss > 0 else (
            float("inf") if test_gross_win > 0 else 0.0
        )

        ts_start = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).date()
        ts_end = datetime.fromtimestamp(test_end_ts, tz=timezone.utc).date()

        results.append({
            "window": window_id,
            "period": f"{ts_start} → {ts_end}",
            "test_trades": len(test_trades),
            "test_pnl": round(test_pnl, 2),
            "test_pf": round(test_pf, 4) if test_pf != float("inf") else 999.0,
            "test_wr": round(test_wins / len(test_trades), 4) if test_trades else 0.0,
        })

        window_id += 1
        i += test_days

    return results


# ===================================================================
# 2. Monte Carlo Simulation
# ===================================================================


def _deterministic_shuffle(trades: list[dict], seed: int) -> list[dict]:
    """Deterministic trade-order shuffle using hash-based sort."""
    def sort_key(t: dict) -> str:
        raw = f"{seed}:{t.get('trade_id', '')}:{t.get('pnl', 0)}"
        return hashlib.md5(raw.encode()).hexdigest()
    return sorted(trades, key=sort_key)


def monte_carlo(
    trades: list[dict],
    n_simulations: int = 1000,
    slippage_stress_bps: float = 10.0,
    random_loss_pct: float = 0.05,
) -> dict:
    """Monte Carlo simulation of trade outcomes.

    Simulations:
    1. Trade order shuffle (equity path sensitivity)
    2. Additional slippage stress (cost sensitivity)
    3. Random loss injection (robustness to adverse draws)

    All simulations are deterministic (hash-based, not random).
    """
    if not trades:
        return {"error": "no trades"}

    closed = [t for t in trades if t.get("pnl") is not None]
    if not closed:
        return {"error": "no closed trades"}

    equity_finals: list[float] = []
    max_drawdowns: list[float] = []
    profit_factors: list[float] = []

    for sim in range(n_simulations):
        # Shuffle trade order deterministically
        shuffled = _deterministic_shuffle(closed, sim)

        equity = INITIAL_EQUITY
        peak = equity
        max_dd = 0.0
        gross_win = 0.0
        gross_loss = 0.0

        for j, trade in enumerate(shuffled):
            pnl = trade["pnl"]

            # Additional slippage stress
            entry_price = trade.get("entry_price", 0)
            pos_size = trade.get("position_size", 0)
            if entry_price > 0 and pos_size > 0:
                stress_cost = entry_price * pos_size * slippage_stress_bps / 10_000.0
                pnl -= stress_cost

            # Random loss injection (deterministic via hash)
            inject_hash = int(hashlib.md5(
                f"{sim}:{j}:loss_inject".encode()
            ).hexdigest()[:8], 16)
            if (inject_hash % 100) < int(random_loss_pct * 100):
                # Convert this trade to a loss (adverse scenario)
                if pnl > 0:
                    pnl = -abs(pnl) * 0.5

            equity += pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            if pnl > 0:
                gross_win += pnl
            else:
                gross_loss += abs(pnl)

        equity_finals.append(equity)
        max_drawdowns.append(max_dd)
        pf = gross_win / gross_loss if gross_loss > 0 else 0.0
        profit_factors.append(pf)

    # Percentile analysis
    equity_finals.sort()
    max_drawdowns.sort()
    profit_factors.sort()

    def percentile(data: list[float], pct: float) -> float:
        idx = int(len(data) * pct / 100.0)
        idx = max(0, min(idx, len(data) - 1))
        return round(data[idx], 4)

    return {
        "simulations": n_simulations,
        "equity_final": {
            "p5": percentile(equity_finals, 5),
            "p25": percentile(equity_finals, 25),
            "p50": percentile(equity_finals, 50),
            "p75": percentile(equity_finals, 75),
            "p95": percentile(equity_finals, 95),
            "mean": round(sum(equity_finals) / len(equity_finals), 2),
        },
        "max_drawdown": {
            "p5": percentile(max_drawdowns, 5),
            "p50": percentile(max_drawdowns, 50),
            "p95": percentile(max_drawdowns, 95),
            "mean": round(sum(max_drawdowns) / len(max_drawdowns), 4),
        },
        "profit_factor": {
            "p5": percentile(profit_factors, 5),
            "p25": percentile(profit_factors, 25),
            "p50": percentile(profit_factors, 50),
            "p75": percentile(profit_factors, 75),
            "p95": percentile(profit_factors, 95),
            "mean": round(sum(profit_factors) / len(profit_factors), 4),
        },
        "ruin_probability": round(
            sum(1 for e in equity_finals if e < INITIAL_EQUITY * 0.85) / len(equity_finals),
            4,
        ),
        "profitable_pct": round(
            sum(1 for e in equity_finals if e > INITIAL_EQUITY) / len(equity_finals),
            4,
        ),
    }


# ===================================================================
# Main
# ===================================================================


def main() -> None:
    print("=" * 60)
    print("PRDV3 ROBUSTNESS VALIDATION")
    print("=" * 60)

    bars = load_all_bars()
    print(f"Loaded {len(bars)} bars")

    # --- Full backtest ---
    print("\n--- Full Backtest ---")
    result = run_backtest_on_bars(bars)
    metrics = result["metrics"]
    print(f"PF={metrics.get('profit_factor', 0):.4f}  "
          f"WR={metrics.get('win_rate', 0):.4f}  "
          f"Return={metrics.get('total_return', 0):.4f}  "
          f"DD={metrics.get('max_drawdown', 0):.4f}  "
          f"Trades={metrics.get('closed_trades', 0)}  "
          f"Rejected={metrics.get('rejected_orders', 0)}  "
          f"Partial={metrics.get('partial_fills', 0)}")

    # --- Walk-Forward ---
    # 378 trading days → use 120/60 to get more windows
    print("\n--- Walk-Forward Validation (120-train / 60-test) ---")
    wf_results = walk_forward(bars, train_days=120, test_days=60)
    for wf in wf_results:
        marker = "✓" if wf["test_pf"] > 1.0 else "✗"
        print(f"  [{marker}] Window {wf['window']}: {wf['period']}  "
              f"trades={wf['test_trades']:3d}  PF={wf['test_pf']:.3f}  "
              f"WR={wf['test_wr']:.0%}  PnL={wf['test_pnl']:,.0f}")

    positive_windows = sum(1 for wf in wf_results if wf["test_pf"] > 1.0)
    total_windows = len(wf_results)
    print(f"\n  Walk-forward score: {positive_windows}/{total_windows} profitable windows "
          f"({positive_windows/total_windows*100:.0f}%)" if total_windows > 0 else "")

    # --- Monte Carlo ---
    print("\n--- Monte Carlo (1000 sims, +10bps stress, 5% loss injection) ---")
    trades = result.get("trades", [])
    closed_trades = [t for t in trades if t.get("status") == "CLOSED"]
    mc = monte_carlo(closed_trades, n_simulations=1000)

    print(f"  Equity final: p5={mc['equity_final']['p5']:,.0f}  "
          f"p50={mc['equity_final']['p50']:,.0f}  "
          f"p95={mc['equity_final']['p95']:,.0f}")
    print(f"  Max drawdown: p50={mc['max_drawdown']['p50']:.2%}  "
          f"p95={mc['max_drawdown']['p95']:.2%}")
    print(f"  Profit factor: p5={mc['profit_factor']['p5']:.3f}  "
          f"p50={mc['profit_factor']['p50']:.3f}  "
          f"p95={mc['profit_factor']['p95']:.3f}")
    print(f"  Ruin probability (equity < 85K): {mc['ruin_probability']:.1%}")
    print(f"  Profitable simulations: {mc['profitable_pct']:.1%}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    issues = []
    if metrics.get("profit_factor", 0) < 1.1:
        issues.append(f"PF={metrics['profit_factor']:.3f} < 1.1 threshold")
    if metrics.get("max_drawdown", 0) > 0.10:
        issues.append(f"DD={metrics['max_drawdown']:.2%} > 10% threshold")
    if total_windows > 0 and positive_windows / total_windows < 0.5:
        issues.append(f"WF score {positive_windows}/{total_windows} < 50%")
    if mc.get("ruin_probability", 0) > 0.10:
        issues.append(f"Ruin prob {mc['ruin_probability']:.1%} > 10%")
    if mc.get("profitable_pct", 0) < 0.60:
        issues.append(f"Profitable sims {mc['profitable_pct']:.1%} < 60%")

    if issues:
        print("ISSUES:")
        for issue in issues:
            print(f"  ⚠ {issue}")
    else:
        print("  No critical issues detected.")

    # Write results
    out = ROOT / "outputs" / "robustness_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "metrics": metrics,
            "walk_forward": wf_results,
            "monte_carlo": mc,
            "issues": issues,
        }, f, indent=2, default=str)
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
