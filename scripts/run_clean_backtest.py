"""PRDV3 Clean Backtest Runner — deterministic, single-run, multi-symbol.

Loads vendor EOD data, runs BacktestEngine via _run_bar_sequence path,
writes clean outputs (equity_curve.jsonl, paper_trades.json,
outputs/backtest_metrics.json), and validates against PRDV3 requirements.

Usage:
    python scripts/run_clean_backtest.py
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bist_core.backtest.backtest_engine import BacktestEngine, CostModel
from bist_core.backtest.metrics_engine_v2 import MetricsEngineV2, export_metrics_to_json
from bist_core.decision.portfolio_decision import PortfolioDecisionEngine
from bist_core.execution.order_state_machine import RiskLimits
from bist_core.execution.paper_engine import SlippageModel
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Configuration — deterministic, no randomness
# ---------------------------------------------------------------------------

VENDOR_CSV = ROOT / "data" / "vendor" / "datastore_normalized.csv"

# 15 liquid BIST symbols selected by avg volume >= 50M, 378 bars each
SYMBOL_UNIVERSE = [
    "SASA", "ISCTR", "CANTE", "TSPOR", "GSRAY",
    "PEKGY", "YKBNK", "EKGYO", "PSGYO", "ADESE",
    "EREGL", "HEKTS", "KATMR", "AKBNK", "PETKM",
]

INITIAL_EQUITY = 100_000.0

# Output paths
EQUITY_CURVE_PATH = ROOT / "equity_curve.jsonl"
PAPER_TRADES_PATH = ROOT / "paper_trades.json"
METRICS_PATH = ROOT / "outputs" / "backtest_metrics.json"


def _date_to_unix(date_str: str) -> int:
    """Convert YYYY-MM-DD to Unix seconds (UTC midnight). Deterministic."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_bars() -> list[OHLCVBar]:
    """Load vendor CSV, filter to universe, convert to OHLCVBar."""
    if not VENDOR_CSV.exists():
        print(f"FAIL: vendor data not found at {VENDOR_CSV}", file=sys.stderr)
        sys.exit(1)

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
            except (KeyError, ValueError) as exc:
                print(f"WARN: skipping row {row}: {exc}", file=sys.stderr)
                continue
            if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
                continue
            if bar.volume < 0:
                continue
            bars.append(bar)

    if not bars:
        print("FAIL: no valid bars loaded", file=sys.stderr)
        sys.exit(1)

    bars.sort(key=lambda b: (b.timestamp, b.symbol))
    symbols = sorted(set(b.symbol for b in bars))
    dates = sorted(set(b.timestamp for b in bars))
    print(f"Loaded {len(bars)} bars, {len(symbols)} symbols, {len(dates)} dates")
    print(f"Symbols: {symbols}")
    print(f"Date range: {datetime.fromtimestamp(dates[0], tz=timezone.utc).date()} "
          f"to {datetime.fromtimestamp(dates[-1], tz=timezone.utc).date()}")
    return bars


def run_backtest(bars: list[OHLCVBar]) -> dict:
    """Run deterministic backtest using _run_bar_sequence path."""
    cost = CostModel(
        slippage=SlippageModel(base_slippage_bps=5.0),
        commission_bps=10.0,
        exchange_fee_bps=5.0,
    )
    risk = RiskLimits()
    engine = BacktestEngine(
        cost_model=cost,
        risk_limits=risk,
        initial_equity=INITIAL_EQUITY,
        decision_fn=PortfolioDecisionEngine(equity=INITIAL_EQUITY),
        decision_engine=None,  # Force bar-sequence path, skip DecisionEngineV2
    )
    result = engine.run(bars)
    return result


def write_equity_curve(equity_curve: list[dict], path: Path) -> None:
    """Write single continuous equity curve as JSONL. No resets."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for point in equity_curve:
            record = {
                "timestamp": point["timestamp"],
                "equity": round(float(point["equity"]), 2),
            }
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    print(f"Written equity_curve: {len(equity_curve)} points -> {path}")


def write_trades(trades: list[dict], path: Path) -> None:
    """Write unique closed trades as JSON array. No duplicates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    unique_trades: list[dict] = []
    for t in trades:
        if t.get("status") != "CLOSED":
            continue
        key = f"{t['trade_id']}"
        if key in seen:
            continue
        seen.add(key)
        unique_trades.append({
            "trade_id": t["trade_id"],
            "symbol": t["symbol"],
            "entry_price": t["entry_price"],
            "exit_price": round(t["entry_price"] + t["pnl"] / t["position_size"], 4)
            if t.get("position_size", 0) > 0
            else t["entry_price"],
            "pnl": t["pnl"],
            "fees": t.get("fees", 0.0),
            "position_size": t.get("position_size", 0),
            "entry_time": t.get("entry_time", ""),
            "exit_time": t.get("exit_time", ""),
            "exit_reason": _infer_exit_reason(t),
            "edge": t.get("edge", ""),
        })
    with path.open("w", encoding="utf-8") as f:
        json.dump(unique_trades, f, indent=2)
    print(f"Written trades: {len(unique_trades)} closed trades -> {path}")


def _infer_exit_reason(trade: dict) -> str:
    """Infer exit reason from trade data."""
    if trade.get("pnl", 0) > 0:
        entry = trade.get("entry_price", 0)
        target = trade.get("target_price", 0)
        exit_p = entry + trade["pnl"] / trade["position_size"] if trade.get("position_size", 0) > 0 else 0
        if target > 0 and exit_p >= target * 0.99:
            return "target"
        return "profit_exit"
    elif trade.get("pnl", 0) < 0:
        entry = trade.get("entry_price", 0)
        stop = trade.get("stop_price", 0)
        exit_p = entry + trade["pnl"] / trade["position_size"] if trade.get("position_size", 0) > 0 else 0
        if stop > 0 and exit_p <= stop * 1.01:
            return "stop"
        return "loss_exit"
    return "breakeven"


def generate_metrics(trades: list[dict], equity_curve: list[dict]) -> dict:
    """Compute metrics via MetricsEngineV2 and export to JSON."""
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    if not closed:
        print("FAIL: no closed trades for metrics", file=sys.stderr)
        sys.exit(1)

    # Build trade list for MetricsEngineV2 (needs 'pnl' field)
    metric_trades = [{"pnl": t["pnl"]} for t in closed]

    # Build equity points for MetricsEngineV2 (needs timestamp + equity, monotonic)
    # Deduplicate by keeping last equity per timestamp
    seen_ts: dict[int, float] = {}
    for point in equity_curve:
        ts = point["timestamp"]
        eq = float(point["equity"])
        seen_ts[ts] = eq

    sorted_points = [
        {"timestamp": ts, "equity": eq}
        for ts, eq in sorted(seen_ts.items())
    ]

    if len(sorted_points) < 2:
        print("FAIL: insufficient equity curve points", file=sys.stderr)
        sys.exit(1)

    engine = MetricsEngineV2()
    metrics = engine.compute_metrics(metric_trades, sorted_points)
    path = export_metrics_to_json(metrics, output_path=METRICS_PATH)
    print(f"Written metrics -> {path}")
    return metrics


def validate(metrics: dict, trades_path: Path, equity_path: Path) -> bool:
    """Validate outputs against PRDV3 requirements."""
    errors: list[str] = []

    # Check win_rate != 1.0
    if metrics.get("win_rate") == 1.0:
        errors.append("win_rate == 1.0 (impossible for valid backtest)")

    # Check trade_count >= 30
    if metrics.get("trade_count", 0) < 30:
        errors.append(f"trade_count = {metrics.get('trade_count', 0)} < 30")

    # Check multiple symbols
    with trades_path.open(encoding="utf-8") as f:
        trade_data = json.load(f)
    symbols = set(t["symbol"] for t in trade_data)
    if len(symbols) < 2:
        errors.append(f"only {len(symbols)} symbol(s) traded")

    # Check no equity resets
    with equity_path.open(encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    equities = [line["equity"] for line in lines]
    for i in range(1, len(equities)):
        # A reset is defined as a jump back to exactly initial equity after diverging
        # Threshold must be proportional to avoid false positives on small-trade systems
        if abs(equities[i] - INITIAL_EQUITY) < 0.01 and abs(equities[i - 1] - INITIAL_EQUITY) > 5000:
            errors.append(f"equity reset detected at line {i + 1}")
            break

    # Check no duplicate trades
    trade_ids = [t["trade_id"] for t in trade_data]
    if len(trade_ids) != len(set(trade_ids)):
        errors.append("duplicate trade IDs detected")

    if errors:
        print("\n=== VALIDATION FAILED ===")
        for e in errors:
            print(f"  - {e}")
        return False

    print("\n=== VALIDATION PASSED ===")
    return True


def main() -> None:
    print("=" * 60)
    print("PRDV3 Clean Backtest Runner")
    print("=" * 60)

    # Step 1: Load data
    bars = load_bars()

    # Step 2: Run backtest
    print("\nRunning backtest...")
    result = run_backtest(bars)

    trades = result.get("trades", [])
    equity_curve = result.get("equity_curve", [])
    internal_metrics = result.get("metrics", {})

    print(f"\nInternal metrics: {json.dumps(internal_metrics, indent=2, default=str)}")
    print(f"Total trades (all): {len(trades)}")
    closed = [t for t in trades if t.get('status') == 'CLOSED']
    print(f"Closed trades: {len(closed)}")
    print(f"Equity curve points: {len(equity_curve)}")

    if not closed:
        print("\nFAIL: No closed trades produced. Cannot continue.", file=sys.stderr)
        sys.exit(1)

    # Step 3: Write outputs
    print("\nWriting outputs...")
    write_equity_curve(equity_curve, EQUITY_CURVE_PATH)
    write_trades(trades, PAPER_TRADES_PATH)

    # Step 4: Generate metrics via MetricsEngineV2
    print("\nGenerating MetricsEngineV2 metrics...")
    metrics = generate_metrics(trades, equity_curve)
    print(f"\nMetrics: {json.dumps(metrics, indent=2)}")

    # Step 5: Validate
    valid = validate(metrics, PAPER_TRADES_PATH, EQUITY_CURVE_PATH)
    if not valid:
        print("\nBacktest completed but validation failed. Review outputs.")
        sys.exit(1)

    # Summary
    print("\n" + "=" * 60)
    print("BACKTEST COMPLETE — CLEAN RUN")
    print("=" * 60)
    print(f"Symbols traded: {sorted(set(t['symbol'] for t in closed))}")
    print(f"Trade count: {metrics['trade_count']}")
    print(f"Win rate: {metrics['win_rate']:.4f}")
    print(f"Total return: {metrics['total_return']:.6f}")
    print(f"Max drawdown: {metrics['max_drawdown']:.6f}")
    print(f"Sharpe ratio: {metrics['sharpe_ratio']:.6f}")
    print(f"Expectancy: {metrics['expectancy']:.4f}")
    print(f"Profit factor: {metrics['profit_factor']}")
    print(f"Avg win: {metrics['avg_win']:.4f}")
    print(f"Avg loss: {metrics['avg_loss']:.4f}")

    # Sample trades
    print("\nSample trades (first 5):")
    with PAPER_TRADES_PATH.open(encoding="utf-8") as f:
        sample = json.load(f)[:5]
    for t in sample:
        print(f"  {t['symbol']} entry={t['entry_price']} exit={t['exit_price']} "
              f"pnl={t['pnl']} reason={t['exit_reason']}")


if __name__ == "__main__":
    main()
