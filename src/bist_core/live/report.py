"""Daily report engine — per-day metrics, per-symbol, per-regime."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bist_core.live.paper_trader import compute_paper_metrics


def _load_trades(path: Path, date_str: str) -> list[dict]:
    trades: list[dict] = []
    if not path.exists():
        return trades
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if not line:
            continue
        try:
            obj = json.loads(line)
            ts = obj.get("timestamp", "")
            if isinstance(ts, str) and ts.startswith(date_str):
                trades.append(obj)
        except json.JSONDecodeError:
            continue
    return trades


def _build_daily_report(
    trades: list[dict],
    date_str: str,
) -> dict[str, Any]:
    pnl = sum(float(t.get("net_pnl", t.get("pnl", 0))) for t in trades if t.get("action") == "BUY")
    metrics = compute_paper_metrics(trades)
    per_symbol: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    per_regime: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    for t in trades:
        if t.get("action") != "BUY" or ("pnl" not in t and "net_pnl" not in t):
            continue
        sym = t.get("symbol", "?")
        regime = str(t.get("regime", "unknown"))
        p = float(t.get("net_pnl", t.get("pnl", 0)))
        per_symbol[sym]["trades"] += 1
        per_symbol[sym]["pnl"] += p
        if p > 0:
            per_symbol[sym]["wins"] += 1
        else:
            per_symbol[sym]["losses"] += 1
        per_regime[regime]["trades"] += 1
        per_regime[regime]["pnl"] += p
        if p > 0:
            per_regime[regime]["wins"] += 1
        else:
            per_regime[regime]["losses"] += 1
    return {
        "date": date_str,
        "total_trades": metrics["total_trades"],
        "wins": metrics["wins"],
        "losses": metrics["losses"],
        "win_rate": metrics["win_rate"],
        "expectancy": metrics["expectancy"],
        "pnl": round(pnl, 4),
        "max_drawdown": metrics["max_drawdown"],
        "per_symbol": dict(per_symbol),
        "per_regime": dict(per_regime),
    }


def generate_daily_report(
    date_str: str | None = None,
    trades_path: str | Path = "paper_trades.jsonl",
    output_dir: str | Path = ".",
) -> Path:
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = Path(trades_path)
    trades = _load_trades(p, date_str)
    report = _build_daily_report(trades, date_str)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"daily_report_{date_str}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


__all__ = ["generate_daily_report"]
