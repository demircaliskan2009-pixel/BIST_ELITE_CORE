"""FAZ38/FAZ39: Walk-forward backtest harness — snapshot + strategy + paper broker; metrics + equity curve; walk-forward splits + gates."""
from __future__ import annotations

import csv
import json
from datetime import date as Date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.audit.ledger import write_fills_jsonl, write_positions_jsonl
from bist_core.brokers import PaperBroker
from bist_core.services import snapshot_integrity
from bist_core.portfolio.accounting import Ledger as PortfolioLedger
from bist_core.orders.strategies import resolve_strategy


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


def _sha256_file(file_path: Path) -> str:
    """SHA256 of file contents (binary read)."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _leakage_guard(date_from: Date, date_to: Date, as_of: Date | None) -> str | None:
    """FAZ393: Fail-closed leakage guard. Returns error message if date > as_of, else None."""
    if as_of is None:
        return None
    if date_from > as_of:
        return f"LEAKAGE: date_from {date_from.isoformat()} > as_of {as_of.isoformat()}"
    if date_to > as_of:
        return f"LEAKAGE: date_to {date_to.isoformat()} > as_of {as_of.isoformat()}"
    return None


def run_backtest(
    snapshot_root: Path | str,
    date_from: str,
    date_to: str,
    outdir: Path | str,
    strategy: str = "equal_weight",
    top_n: int = 10,
    initial_equity: float = 1.0,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    as_of: str | Date | None = None,
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
    as_of_date: Date | None = None
    if as_of is not None:
        as_of_date = Date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    leak = _leakage_guard(start, end, as_of_date)
    if leak:
        return {
            "error": "leakage_guard",
            "leakage_message": leak,
            "date_from": date_from,
            "date_to": date_to,
            "as_of": as_of_date.isoformat() if as_of_date else None,
            "num_days": 0,
            "equity_curve_path": "",
            "metrics_path": "",
            "manifest_path": "",
        }
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
            "manifest_path": "",
        }

    params = {"top_n": top_n}
    ledger = PortfolioLedger(
        initial_cash=float(initial_equity),
        fee_bps=float(fee_bps),
        slippage_bps=float(slippage_bps),
    )
    equity_curve: List[Dict[str, str | float]] = []  # day, equity
    total_fills = 0
    all_symbols: set[str] = set()
    all_fills: List[Dict[str, Any]] = []

    for day in days:
        symbols, close_map = _load_snapshot_for_day(root, day)
        all_symbols.update(symbols)
        if not symbols:
            equity_curve.append({"day": day, "equity": round(ledger.equity(), 6)})
            continue
        advice_records = _build_synthetic_advice(symbols)
        orders_intent = strategy_impl.build_intent(
            day=day,
            universe=symbols,
            advice_records=advice_records,
            params=params,
        )
        equity_before = ledger.equity(close_map)
        broker = PaperBroker(snapshot_root=root, day=day, portfolio_value=max(equity_before, 1e-9))
        fills = broker.place_orders(orders_intent)
        total_fills += len(fills)
        all_fills.extend(fills)
        ledger.apply_fills(fills, sort_key=("day", "symbol"))
        write_fills_jsonl(out_path, day, fills)
        write_positions_jsonl(out_path, day, ledger.positions())
        equity = ledger.equity(close_map)
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
        "realized_pnl": round(ledger.realized_pnl(), 6),
        "turnover": round(ledger.turnover(), 6),
    }
    equity_path = backtest_dir / "equity_curve.csv"
    equity_json_path = backtest_dir / "equity_curve.json"
    metrics_path = backtest_dir / "metrics.json"
    fills_path = backtest_dir / "fills.jsonl"
    with equity_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["day", "equity"])
        w.writeheader()
        w.writerows(equity_curve)
    with equity_json_path.open("w", encoding="utf-8") as f:
        json.dump(equity_curve, f, ensure_ascii=False, indent=2)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    with fills_path.open("w", encoding="utf-8") as f:
        for row in all_fills:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    evidence_manifest = {
        "schema_version": 1,
        "kind": "backtest",
        "date_from": date_from,
        "date_to": date_to,
        "strategy": strategy,
        "top_n": top_n,
        "initial_equity": initial_equity,
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "outputs": {
            "metrics": {
                "path": "metrics.json",
                "sha256": snapshot_integrity.compute_sha256(metrics_path),
                "bytes": metrics_path.stat().st_size,
            },
            "equity_curve": {
                "path": "equity_curve.csv",
                "sha256": snapshot_integrity.compute_sha256(equity_path),
                "bytes": equity_path.stat().st_size,
            },
        },
    }
    manifest_path = backtest_dir / "manifest.json"
    snapshot_integrity.atomic_write_json(manifest_path, evidence_manifest)

    metrics["equity_curve_path"] = str(equity_path)
    metrics["metrics_path"] = str(metrics_path)
    metrics["manifest_path"] = str(manifest_path.resolve())
    return metrics


def _walk_forward_windows(date_from: Date, date_to: Date, window_days: int, step_days: int) -> List[tuple[Date, Date]]:
    """Deterministic window splits: [(start, end), ...] with start + (window_days-1) <= end, step by step_days."""
    if date_from > date_to or window_days < 1 or step_days < 1:
        return []
    windows: List[tuple[Date, Date]] = []
    start = date_from
    while start <= date_to:
        end = start + timedelta(days=window_days - 1)
        if end > date_to:
            break
        windows.append((start, end))
        start = start + timedelta(days=step_days)
    return windows


def walk_forward(run_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Walk-forward backtest: deterministic window splits, per-window metrics + aggregate, gates.
    run_config: snapshot_root, date_from, date_to, outdir, strategy, top_n, window (days), step (days),
                min_trades (gate: total_fills >= min_trades), max_dd (gate: worst max_drawdown <= max_dd), strict.
    Writes artifacts under outdir/backtest/walk_forward/ (manifest + aggregate_metrics + windows/<from>_<to>/).
    If gate fails and strict: returns exit_code=2 but still writes all artifacts.
    """
    root = Path(run_config["snapshot_root"])
    out_path = Path(run_config["outdir"])
    backtest_dir = out_path / "backtest"
    wf_dir = backtest_dir / "walk_forward"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "windows").mkdir(parents=True, exist_ok=True)

    date_from = Date.fromisoformat(str(run_config["date_from"]))
    date_to = Date.fromisoformat(str(run_config["date_to"]))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    window_days = int(run_config.get("window") or 0)
    step_days = int(run_config.get("step") or 1)
    min_trades = run_config.get("min_trades")  # None = no gate
    max_dd = run_config.get("max_dd")  # None = no gate
    strict = bool(run_config.get("strict", False))
    strategy = str(run_config.get("strategy") or "equal_weight")
    top_n = int(run_config.get("top_n") or 10)

    windows = _walk_forward_windows(date_from, date_to, window_days, step_days)
    per_window: List[Dict[str, Any]] = []
    for w_start, w_end in windows:
        w_from = w_start.isoformat()
        w_to = w_end.isoformat()
        window_key = f"{w_from}_{w_to}"
        window_outdir = wf_dir / "windows" / window_key
        window_outdir.mkdir(parents=True, exist_ok=True)
        m = run_backtest(
            snapshot_root=root,
            date_from=w_from,
            date_to=w_to,
            outdir=window_outdir,
            strategy=strategy,
            top_n=top_n,
            as_of=run_config.get("as_of"),
        )
        if m.get("error"):
            per_window.append({"date_from": w_from, "date_to": w_to, "error": m["error"], "total_fills": 0, "max_drawdown": 0.0})
        else:
            per_window.append({
                "date_from": w_from,
                "date_to": w_to,
                "metrics_path": m.get("metrics_path", ""),
                "equity_curve_path": m.get("equity_curve_path", ""),
                "num_days": m.get("num_days", 0),
                "total_fills": m.get("total_fills", 0),
                "total_return": m.get("total_return", 0.0),
                "max_drawdown": m.get("max_drawdown", 0.0),
                "final_equity": m.get("final_equity", 0.0),
            })

    total_fills = sum(w.get("total_fills", 0) for w in per_window)
    worst_max_dd = max((w.get("max_drawdown", 0.0) for w in per_window), default=0.0)
    returns = [w.get("total_return", 0.0) for w in per_window if w.get("error") is None]
    mean_return = sum(returns) / len(returns) if returns else 0.0

    gate_min_trades_ok = min_trades is None or total_fills >= min_trades
    gate_max_dd_ok = max_dd is None or worst_max_dd <= float(max_dd)
    gates_passed = gate_min_trades_ok and gate_max_dd_ok

    aggregate = {
        "schema_version": 1,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "window_days": window_days,
        "step_days": step_days,
        "num_windows": len(per_window),
        "total_fills": total_fills,
        "worst_max_drawdown": round(worst_max_dd, 6),
        "mean_return": round(mean_return, 6),
        "min_trades_gate": min_trades,
        "max_dd_gate": max_dd,
        "gates_passed": gates_passed,
    }
    manifest = {
        "schema_version": 1,
        "walk_forward": True,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "window_days": window_days,
        "step_days": step_days,
        "num_windows": len(per_window),
        "windows": per_window,
        "aggregate": aggregate,
        "gates_passed": gates_passed,
        "manifest_path": "",
        "aggregate_metrics_path": "",
    }

    aggregate_path = wf_dir / "aggregate_metrics.json"
    manifest_path = wf_dir / "manifest.json"
    manifest_legacy1 = backtest_dir / "_walk_forward_manifest.json"
    manifest_legacy2 = wf_dir / "_manifest.json"
    snapshot_integrity.atomic_write_json(aggregate_path, aggregate)
    manifest["aggregate_metrics_path"] = str(aggregate_path)
    manifest["manifest_path"] = str(manifest_path)
    snapshot_integrity.atomic_write_json(manifest_path, manifest)
    snapshot_integrity.atomic_write_json(manifest_legacy1, manifest)
    snapshot_integrity.atomic_write_json(manifest_legacy2, manifest)

    exit_code = 2 if (strict and not gates_passed) else 0
    return {
        "gates_passed": gates_passed,
        "exit_code": exit_code,
        "aggregate": aggregate,
        "manifest_path": str(manifest_path),
        "aggregate_metrics_path": str(aggregate_path),
        "num_windows": len(per_window),
        "windows": per_window,
    }
