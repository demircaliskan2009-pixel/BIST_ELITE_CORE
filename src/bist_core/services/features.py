"""FAZ34: Feature registry (name->callable) + baseline features; deterministic compute; fail-closed on missing data."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Registry: feature name -> callable(symbol, day, context) -> float | None
feature_registry: Dict[str, Callable[..., Optional[float]]] = {}

# Context: close_series = [(date_str, close), ...] sorted by date; volume_series = [(date_str, vol), ...] or None
Context = Dict[str, Any]


def register(name: str, fn: Callable[..., Optional[float]]) -> None:
    feature_registry[name] = fn


def _returns_1d(symbol: str, day: str, context: Context) -> Optional[float]:
    close_series = context.get("close_series") or []
    if len(close_series) < 2:
        return None
    c1 = close_series[-1][1]
    c0 = close_series[-2][1]
    if c0 is None or c0 == 0 or c1 is None:
        return None
    try:
        return (float(c1) - float(c0)) / float(c0)
    except (TypeError, ValueError):
        return None


def _vol_20d(symbol: str, day: str, context: Context) -> Optional[float]:
    close_series = context.get("close_series") or []
    if len(close_series) < 21:
        return None
    closes = [float(p[1]) for p in close_series[-21:] if p[1] is not None]
    if len(closes) < 21:
        return None
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] and closes[i - 1] != 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    if len(returns) < 20:
        return None
    n = len(returns)
    mean_r = sum(returns) / n
    var = sum((r - mean_r) ** 2 for r in returns) / n
    return var**0.5 if var >= 0 else None


def _mom_20d(symbol: str, day: str, context: Context) -> Optional[float]:
    close_series = context.get("close_series") or []
    if len(close_series) < 21:
        return None
    c_today = close_series[-1][1]
    c_20d = close_series[-21][1]
    if c_today is None or c_20d is None or c_20d == 0:
        return None
    try:
        return float(c_today) / float(c_20d) - 1.0
    except (TypeError, ValueError):
        return None


def _volume_z(symbol: str, day: str, context: Context) -> Optional[float]:
    volume_series = context.get("volume_series")
    if not volume_series or len(volume_series) < 21:
        return None
    vols = [float(v[1]) for v in volume_series[-21:] if v[1] is not None]
    if len(vols) < 21:
        return None
    n = len(vols)
    mean_v = sum(vols) / n
    var = sum((x - mean_v) ** 2 for x in vols) / n
    std = var**0.5 if var >= 0 else 0.0
    if std == 0:
        return None
    return (vols[-1] - mean_v) / std


def _register_baseline() -> None:
    register("returns_1d", _returns_1d)
    register("vol_20d", _vol_20d)
    register("mom_20d", _mom_20d)
    register("volume_z", _volume_z)


_register_baseline()


def load_history(
    snapshot_root: Path,
    symbol: str,
    day: str,
    lookback_days: int = 21,
) -> Context:
    """Load close_series and volume_series for symbol over [day - lookback_days, day] (inclusive)."""
    try:
        day_dt = datetime.fromisoformat(day)
    except (TypeError, ValueError):
        return {"close_series": [], "volume_series": None}
    close_series: List[Tuple[str, Optional[float]]] = []
    volume_series: List[Tuple[str, Optional[float]]] = []
    for d in range(lookback_days + 1):
        d_date = day_dt - timedelta(days=d)
        date_str = d_date.strftime("%Y-%m-%d")
        path = snapshot_root / date_str / "snapshot.csv"
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                if (row.get("symbol") or "").strip().upper() != symbol.strip().upper():
                    continue
                c = row.get("close")
                close_series.append((date_str, float(c) if c not in (None, "") else None))
                v = row.get("volume")
                volume_series.append((date_str, float(v) if v not in (None, "") else None))
                break
    close_series.sort(key=lambda x: x[0])
    if volume_series:
        volume_series.sort(key=lambda x: x[0])
    return {
        "close_series": close_series,
        "volume_series": volume_series if volume_series else None,
    }


def compute_features(
    symbols: List[str],
    day: str,
    context_provider: Callable[[str, str], Context],
    registry: Optional[Dict[str, Callable[..., Optional[float]]]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Compute all registered features per symbol. Returns (rows, notes).
    Each row: {symbol, date, <feature_name>: value, ...}. Deterministic order: sorted by symbol.
    On missing/insufficient data, feature value is omitted and notes get "missing_data" or "insufficient_history".
    """
    reg = registry if registry is not None else feature_registry
    notes: List[str] = []
    rows: List[Dict[str, Any]] = []
    for symbol in sorted(symbols):
        context = context_provider(symbol, day)
        row: Dict[str, Any] = {"symbol": symbol, "date": day}
        any_missing = False
        for name, fn in sorted(reg.items()):
            try:
                val = fn(symbol, day, context)
                if val is not None:
                    row[name] = round(val, 10)
                else:
                    any_missing = True
            except Exception:
                any_missing = True
        if any_missing:
            notes.append("missing_data")
        rows.append(row)
    return rows, list(dict.fromkeys(notes))


def write_features(outdir: Path, day: str, rows: List[Dict[str, Any]]) -> Path:
    """Write feature rows to outdir/features/<day>/features.jsonl. Returns path."""
    feat_dir = outdir / "features" / day
    feat_dir.mkdir(parents=True, exist_ok=True)
    path = feat_dir / "features.jsonl"
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
    tmp.replace(path)
    return path
