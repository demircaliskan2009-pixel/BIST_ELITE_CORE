"""FAZ38: Walk-forward backtest harness — snapshot + strategy + paper broker; metrics + equity curve."""
from __future__ import annotations

import csv
import json
from datetime import date as Date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.brokers import PaperBroker
from bist_core.strategies import resolve_strategy


def _load_snapshot_for_day(snapshot_root: Path, day: str) -> tuple[List[str], Dict[str, float]]:
    """Load symbols and close map from snapshot_root/<day>/snapshot.csv. Deterministic (sorted by symbol)."""
    path = snapshot_root / day / "snapshot.csv"
    if not path.is_file():
        alt = snapshot_root / (day + ".csv")
        path = alt if alt.is_file() else path
    if not path.is_file():
        return [], {}
    symbols: List[str] = []
    close_map: Dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            c = row.get("close")
            if c is None or c == "":
                continue
            try:
                close_map[sym] = float(c)
                symbols.append(sym)
            except (TypeError, ValueError):
                continue
    symbols = sorted(set(symbols))
    close_map = dict(sorted(close_map.items()))
    return symbols, close_map


def _build_synthetic_advice(symbols: List[str]) -> List[Dict[str, Any]]:
    """Minimal advice for backtest: one BUY per symbol, score=1.0 (deterministic ranking by symbol)."""
    return [
        {"symbol": s, "decision_raw": "BUY", "score": 1.0}
        for s in symbols
    ]


def run_backtest(
    snapshot_root: Path | str,
    date_from: str,
    date_to: str,
    outdir: Path | str,
    strategy: str = "equal_weight",
    top_n: int = 10,
    initial_equity: float = 1.0,
) -> Dict[str, Any]:
    """
    Walk-forward backtest over [date_from, date_to]: snapshot -> strategy -> paper broker.
    Writes outdir/backtest/metrics.json and outdir/backtest/equity_curve.csv.
    Returns metrics dict.
    """
    root = Path(snapshot_root)
    out_path = Path(outdir)
    backtest_dir = out_path / "backtest"
    backtest_dir.mkdir(parents=True, exist_ok=True)

    start = Date.fromisoformat(date_from)
    end = Date.fromisoformat(date_to)
    if start > end:
        start, end = end, start
    days: List[str] = []
    d = start
    while d <= end:
        days.append(d.isoformat())
        d += timedelta(days=1)

    try:
        strategy_impl = resolve_strategy(strategy)
    except ValueError:
        return {
            "error": "strategy_not_found",
            "strategy": strategy,
            "num_days": 0,
            "equity_curve_path": "",
            "metrics_path": "",
        }

    params = {"top_n": top_n}
    cash = float(initial_equity)
    positions: Dict[str, float] = {}  # symbol -> signed qty
    equity_curve: List[Dict[str, str | float]] = []  # day, equity
    total_fills = 0

    for day in days:
        symbols, close_map = _load_snapshot_for_day(root, day)
        if not symbols:
            equity_curve.append({"day": day, "equity": round(cash, 6)})
            continue
        advice_records = _build_synthetic_advice(symbols)
        orders_intent = strategy_impl.build_intent(
            day=day,
            universe=symbols,
            advice_records=advice_records,
            params=params,
        )
        equity_before = cash + sum(
            positions.get(s, 0.0) * close_map.get(s, 0.0)
            for s in positions
        )
        broker = PaperBroker(snapshot_root=root, day=day, portfolio_value=max(equity_before, 1e-9))
        fills = broker.place_orders(orders_intent)
        total_fills += len(fills)
        for f in fills:
            sym = f.get("symbol", "")
            signed_qty = f.get("signed_qty", 0.0)
            notional = f.get("notional", 0.0)
            side = str(f.get("side", "")).upper()
            positions[sym] = positions.get(sym, 0.0) + signed_qty
            if side == "BUY":
                cash -= notional
            else:
                cash += notional
        equity = cash + sum(
            positions.get(s, 0.0) * close_map.get(s, 0.0)
            for s in positions
        )
        equity_curve.append({"day": day, "equity": round(equity, 6)})

    # Metrics
    equity_start = float(initial_equity)
    equity_end = equity_curve[-1]["equity"] if equity_curve else equity_start
    total_return = (equity_end - equity_start) / equity_start if equity_start else 0.0
    equities = [r["equity"] for r in equity_curve]
    peak = equity_start
    max_dd = 0.0
    for e in equities:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    metrics = {
        "schema_version": 1,
        "date_from": date_from,
        "date_to": date_to,
        "num_days": len(days),
        "strategy": strategy,
        "top_n": top_n,
        "initial_equity": equity_start,
        "final_equity": round(equity_end, 6),
        "total_return": round(total_return, 6),
        "max_drawdown": round(max_dd, 6),
        "total_fills": total_fills,
    }
    equity_path = backtest_dir / "equity_curve.csv"
    metrics_path = backtest_dir / "metrics.json"
    with equity_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["day", "equity"])
        w.writeheader()
        w.writerows(equity_curve)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    metrics["equity_curve_path"] = str(equity_path)
    metrics["metrics_path"] = str(metrics_path)
    return metrics
