"""
Outcome evaluation for logged strategies.
Uses daily EODBar data from snapshot CSVs. Deterministic. Offline. Fail-closed.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional


OUTCOME_SCHEMA_VERSION = 1
DEFAULT_MAX_HOLD_DAYS = 30


def _parse_max_hold_days(env_val: Optional[str], default: int = DEFAULT_MAX_HOLD_DAYS) -> int:
    """Parse BIST_CORE_OUTCOME_MAX_HOLD_DAYS. Fail-closed: invalid => default."""
    if not env_val:
        return default
    try:
        n = int(env_val.strip())
        if 1 <= n <= 365:
            return n
    except (TypeError, ValueError):
        pass
    return default


@dataclass
class Bar:
    """Minimal bar for outcome simulation. high/low fallback to close when missing."""
    date_str: str
    close: float
    high: float
    low: float


def _load_bars_forward(
    snapshot_root: Path,
    symbol: str,
    from_day: str,
    max_days: int = 252,
) -> list[Bar]:
    """
    Load bars for symbol from from_day onward. Deterministic. Fail-closed: missing bar -> stop.
    """
    root = Path(snapshot_root)
    if not root.is_dir():
        return []

    days_found: list[str] = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        day_str = sub.name
        try:
            _ = date.fromisoformat(day_str)
        except ValueError:
            continue
        if (sub / "snapshot.csv").is_file():
            days_found.append(day_str)

    days_found.sort()
    candidates = [d for d in days_found if d >= from_day][:max_days]
    bars: list[Bar] = []

    for day_str in candidates:
        path = root / day_str / "snapshot.csv"
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sym = (row.get("symbol") or "").strip().upper()
                if sym != symbol.strip().upper():
                    continue
                c = row.get("close")
                if c is None or c == "":
                    continue
                try:
                    close = float(c)
                except (TypeError, ValueError):
                    continue
                if not (close > 0 and close < 1e12):
                    continue
                high = close
                low = close
                h = row.get("high")
                l = row.get("low")
                if h not in (None, ""):
                    try:
                        high = float(h)
                    except (TypeError, ValueError):
                        pass
                if l not in (None, ""):
                    try:
                        low = float(l)
                    except (TypeError, ValueError):
                        pass
                bars.append(Bar(date_str=day_str, close=close, high=high, low=low))
                break
        if not bars or bars[-1].date_str != day_str:
            # Symbol not in this day's snapshot
            continue

    return bars


def evaluate_strategy(
    log_entry: dict[str, Any],
    snapshot_root: Path,
    *,
    max_hold_days: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """
    Evaluate a logged strategy against actual price data.
    Returns outcome dict or None if no plan / HOLD / no-trade.

    Outcome: status (win|loss|HOLD), r_multiple, days_held, exit_price, exit_day.
    Deterministic: same bars => same outcome.
    Fail-closed: missing bar or invalid data => HOLD.
    """
    symbol = log_entry.get("symbol")
    day = log_entry.get("day")
    if not symbol or not day:
        return None

    strategy_detail = log_entry.get("strategy_detail") or {}
    plan = strategy_detail.get("plan")
    if not plan or not isinstance(plan, dict):
        return _hold_outcome(symbol, day, "no_plan")

    entry_val = plan.get("entry")
    stop_val = plan.get("stop")
    t1_val = plan.get("t1")
    if entry_val is None or stop_val is None or t1_val is None:
        return _hold_outcome(symbol, day, "incomplete_plan")

    try:
        entry = float(entry_val)
        stop = float(stop_val)
        t1 = float(t1_val)
    except (TypeError, ValueError):
        return _hold_outcome(symbol, day, "invalid_plan_values")

    if not (stop < entry < t1):
        return _hold_outcome(symbol, day, "invalid_plan_order")

    hold_days = max_hold_days if max_hold_days is not None else _parse_max_hold_days(
        os.environ.get("BIST_CORE_OUTCOME_MAX_HOLD_DAYS"), DEFAULT_MAX_HOLD_DAYS
    )
    bars = _load_bars_forward(snapshot_root, symbol, day, max_days=hold_days)
    if not bars:
        return _hold_outcome(symbol, day, "no_bars")

    # Entry fill: close of entry day (signal day)
    entry_fill = bars[0].close
    r_distance = entry_fill - stop
    if r_distance <= 0:
        return _hold_outcome(symbol, day, "zero_r_distance")

    # Simulate from bar 1 onward (first full day in trade after entry)
    for i, bar in enumerate(bars[1:], start=1):
        # Check stop first (conservative)
        if bar.low <= stop:
            exit_price = stop
            r_mult = -1.0
            return _build_outcome(
                symbol=symbol,
                day=day,
                status="loss",
                r_multiple=round(r_mult, 4),
                days_held=i,
                exit_price=round(exit_price, 6),
                exit_day=bar.date_str,
                reason="stop_hit",
            )
        if bar.high >= t1:
            exit_price = t1
            r_mult = (t1 - entry_fill) / r_distance
            return _build_outcome(
                symbol=symbol,
                day=day,
                status="win",
                r_multiple=round(r_mult, 4),
                days_held=i,
                exit_price=round(exit_price, 6),
                exit_day=bar.date_str,
                reason="target_hit",
            )

    # Timeout: exit at last bar's close
    last_bar = bars[-1]
    exit_price = last_bar.close
    r_mult = (exit_price - entry_fill) / r_distance
    status = "win" if r_mult > 0 else "loss" if r_mult < 0 else "timeout"
    return _build_outcome(
        symbol=symbol,
        day=day,
        status=status,
        r_multiple=round(r_mult, 4),
        days_held=len(bars) - 1,
        exit_price=round(exit_price, 6),
        exit_day=last_bar.date_str,
        reason="timeout",
    )


def _hold_outcome(symbol: str, day: str, reason: str) -> dict[str, Any]:
    return _build_outcome(
        symbol=symbol,
        day=day,
        status="HOLD",
        r_multiple=None,
        days_held=None,
        exit_price=None,
        exit_day=None,
        reason=reason,
    )


def _build_outcome(
    symbol: str,
    day: str,
    status: str,
    r_multiple: Optional[float],
    days_held: Optional[int],
    exit_price: Optional[float],
    exit_day: Optional[str],
    reason: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "symbol": symbol,
        "day": day,
        "status": status,
        "reason": reason,
    }
    if r_multiple is not None:
        out["r_multiple"] = r_multiple
    if days_held is not None:
        out["days_held"] = days_held
    if exit_price is not None:
        out["exit_price"] = exit_price
    if exit_day is not None:
        out["exit_day"] = exit_day
    return out


def _default_outcomes_path() -> Path:
    env_path = os.environ.get("BIST_CORE_STRATEGY_OUTCOMES")
    if env_path:
        return Path(env_path)
    from bist_core import config
    return config.REPO_ROOT / "data" / "log" / "strategy_outcomes.jsonl"


def evaluate_and_append_outcomes(
    strategies_path: Path,
    snapshot_root: Path,
    *,
    outcomes_path: Optional[Path] = None,
    max_hold_days: Optional[int] = None,
) -> int:
    """
    Read strategies.jsonl, evaluate each, append outcomes to strategy_outcomes.jsonl.
    Returns count of outcomes written. Fail-closed: raises on write error.
    """
    path = outcomes_path or _default_outcomes_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if not strategies_path.is_file():
        return 0

    lines = [ln.strip() for ln in strategies_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    count = 0
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        hold_days = max_hold_days if max_hold_days is not None else _parse_max_hold_days(
            os.environ.get("BIST_CORE_OUTCOME_MAX_HOLD_DAYS"), DEFAULT_MAX_HOLD_DAYS
        )
        outcome = evaluate_strategy(entry, snapshot_root, max_hold_days=hold_days)
        if outcome is None:
            continue
        out_line = json.dumps(outcome, ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(out_line)
            f.flush()
            os.fsync(f.fileno())
        count += 1
    return count
