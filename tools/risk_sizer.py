#!/usr/bin/env python3
"""FAZ585: Risk budget sizer (ATR-based) for manual stage-1. Offline, deterministic."""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from pathlib import Path

HORIZONS = (1, 3, 5, 20)
PLAN_FIELDS = (
    "day", "horizon_days", "rank", "symbol", "capital_try", "risk_pct", "risk_try",
    "atr", "stop_atr_mult", "stop_distance", "qty", "tp_r_mult", "tp_distance", "notes",
)

DEFAULTS = {
    "BIST_CAPITAL_TRY": 30000.0,
    "BIST_RISK_PCT": 0.02,
    "BIST_ATR_N": 14,
    "BIST_STOP_ATR_MULT": 2.0,
    "BIST_TP_R_MULT": 2.0,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_config() -> tuple[dict, str | None]:
    """Load config from env. Returns (config_dict, error). Invalid => error set."""
    cfg = {}
    for key, default in DEFAULTS.items():
        val = os.environ.get(key)
        if val is None or val.strip() == "":
            cfg[key] = default
            continue
        try:
            if "PCT" in key:
                cfg[key] = float(val)
            elif "N" in key:
                cfg[key] = int(val)
            else:
                cfg[key] = float(val)
        except (TypeError, ValueError):
            return {}, f"invalid_env:{key}={val!r}"

    if cfg["BIST_CAPITAL_TRY"] <= 0:
        return {}, "invalid_env:BIST_CAPITAL_TRY<=0"
    if cfg["BIST_RISK_PCT"] <= 0 or cfg["BIST_RISK_PCT"] >= 1:
        return {}, "invalid_env:BIST_RISK_PCT_not_in_0_1"
    if cfg["BIST_ATR_N"] < 2:
        return {}, "invalid_env:BIST_ATR_N<2"
    if cfg["BIST_STOP_ATR_MULT"] <= 0:
        return {}, "invalid_env:BIST_STOP_ATR_MULT<=0"
    if cfg["BIST_TP_R_MULT"] <= 0:
        return {}, "invalid_env:BIST_TP_R_MULT<=0"

    return cfg, None


def _list_snapshot_days(snapshot_root: Path) -> list[str]:
    """List available days with snapshot.csv. Sorted ascending."""
    if not snapshot_root.is_dir():
        return []
    days = []
    for sub in sorted(snapshot_root.iterdir()):
        if sub.is_dir() and (sub / "snapshot.csv").is_file():
            name = sub.name
            if len(name) == 10 and name[4] == "-" and name[7] == "-":
                try:
                    int(name[:4])
                    int(name[5:7])
                    int(name[8:10])
                    days.append(name)
                except ValueError:
                    pass
    return sorted(days)


def _load_ohlc_bars(
    snapshot_root: Path,
    day: str,
    symbol: str,
    n_days: int,
) -> list[tuple[str, float, float, float, float]]:
    """Load (date, open, high, low, close) for symbol over last n_days ending at day. Oldest first."""
    days = _list_snapshot_days(snapshot_root)
    candidates = [d for d in days if d <= day]
    if not candidates or day not in candidates:
        return []
    window = candidates[-n_days:]

    bars: list[tuple[str, float, float, float, float]] = []
    for d in window:
        p = snapshot_root / d / "snapshot.csv"
        if not p.is_file():
            p = snapshot_root / (d + ".csv")
        if not p.is_file():
            return []
        try:
            with p.open(newline="", encoding="utf-8", errors="replace") as f:
                for row in csv.DictReader(f):
                    sym = (row.get("symbol") or "").strip().upper()
                    if sym != symbol.strip().upper():
                        continue
                    c = row.get("close")
                    if c is None or c == "":
                        return []
                    try:
                        close = float(c)
                    except (TypeError, ValueError):
                        return []
                    if not (close > 0 and close < 1e12):
                        return []
                    o = row.get("open")
                    h = row.get("high")
                    l_ = row.get("low")
                    open_ = close
                    high = close
                    low = close
                    if o not in (None, ""):
                        try:
                            open_ = float(o)
                        except (TypeError, ValueError):
                            pass
                    if h not in (None, ""):
                        try:
                            high = float(h)
                        except (TypeError, ValueError):
                            pass
                    if l_ not in (None, ""):
                        try:
                            low = float(l_)
                        except (TypeError, ValueError):
                            pass
                    bars.append((d, open_, high, low, close))
                    break
            if not bars or bars[-1][0] != d:
                return []
        except (OSError, csv.Error):
            return []
    return bars


def _compute_atr(bars: list[tuple[str, float, float, float, float]], n: int) -> float | None:
    """Compute ATR(N) = mean of last N true ranges. Returns None if insufficient bars."""
    if len(bars) < n:
        return None
    tr_list: list[float] = []
    for i, (_, o, h, l, c) in enumerate(bars):
        if i == 0:
            tr = h - l
        else:
            prev_c = bars[i - 1][4]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    atr = sum(tr_list[-n:]) / n
    return atr


def _load_topn(reports_dir: Path, horizon: int) -> list[dict] | None:
    """Load topn_h{H}.csv. Returns rows or None if missing."""
    for ext in ("csv", "json"):
        p = reports_dir / f"topn_h{horizon}.{ext}"
        if not p.is_file():
            continue
        try:
            if ext == "csv":
                with p.open(newline="", encoding="utf-8") as f:
                    return list(csv.DictReader(f))
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("rows") or []
        except (json.JSONDecodeError, OSError, csv.Error):
            pass
    return None


def _run_sizer(
    day: str,
    horizon: int,
    top_n: int,
    reports_root: Path,
    snapshot_root: Path,
    cfg: dict,
) -> list[dict] | None:
    """Build risk plan rows. Returns None if topn missing."""
    reports_dir = reports_root / day
    topn_rows = _load_topn(reports_dir, horizon)
    if topn_rows is None:
        return None

    atr_n = int(cfg["BIST_ATR_N"])
    capital = float(cfg["BIST_CAPITAL_TRY"])
    risk_pct = float(cfg["BIST_RISK_PCT"])
    stop_mult = float(cfg["BIST_STOP_ATR_MULT"])
    tp_mult = float(cfg["BIST_TP_R_MULT"])
    risk_try = capital * risk_pct

    rows: list[dict] = []
    for rank, row in enumerate(topn_rows[:top_n], 1):
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue

        bars = _load_ohlc_bars(snapshot_root, day, symbol, atr_n + 1)
        if len(bars) < atr_n + 1:
            rows.append({
                "day": day,
                "horizon_days": horizon,
                "rank": rank,
                "symbol": symbol,
                "capital_try": capital,
                "risk_pct": risk_pct,
                "risk_try": risk_try,
                "atr": None,
                "stop_atr_mult": stop_mult,
                "stop_distance": None,
                "qty": 0,
                "tp_r_mult": tp_mult,
                "tp_distance": None,
                "notes": "InsufficientHistory",
            })
            continue

        atr = _compute_atr(bars, atr_n)
        if atr is None or atr <= 0:
            rows.append({
                "day": day,
                "horizon_days": horizon,
                "rank": rank,
                "symbol": symbol,
                "capital_try": capital,
                "risk_pct": risk_pct,
                "risk_try": risk_try,
                "atr": round(atr or 0, 6) if atr is not None else None,
                "stop_atr_mult": stop_mult,
                "stop_distance": None,
                "qty": 0,
                "tp_r_mult": tp_mult,
                "tp_distance": None,
                "notes": "InsufficientHistory" if atr is None else "ATRZero",
            })
            continue

        stop_distance = atr * stop_mult
        qty_float = risk_try / stop_distance
        qty = int(math.floor(qty_float))
        if qty < 1:
            qty = 0
            notes = "TooSmall"
        else:
            notes = ""

        close = bars[-1][4]
        tp_distance = stop_distance * tp_mult

        rows.append({
            "day": day,
            "horizon_days": horizon,
            "rank": rank,
            "symbol": symbol,
            "capital_try": capital,
            "risk_pct": risk_pct,
            "risk_try": round(risk_try, 2),
            "atr": round(atr, 6),
            "stop_atr_mult": stop_mult,
            "stop_distance": round(stop_distance, 6),
            "qty": qty,
            "tp_r_mult": tp_mult,
            "tp_distance": round(tp_distance, 6),
            "notes": notes,
        })

    return rows


def _write_outputs(reports_dir: Path, horizon: int, day: str, rows: list[dict]) -> None:
    """Write risk_plan_h{H}.json, .csv, .txt."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    h = horizon

    report = {
        "schema_version": 1,
        "day": day,
        "horizon_days": horizon,
        "rows": rows,
    }

    json_path = reports_dir / f"risk_plan_h{h}.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    csv_path = reports_dir / f"risk_plan_h{h}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PLAN_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r[c]) for c in PLAN_FIELDS})

    txt_lines = [
        f"risk_plan {day} H{h}",
        f"rows={len(rows)}",
        "",
    ]
    for r in rows:
        txt_lines.append(
            f"{r['symbol']} rank={r['rank']} qty={r['qty']} atr={r.get('atr','')} "
            f"stop_dist={r.get('stop_distance','')} notes={r.get('notes','')}"
        )
    txt_path = reports_dir / f"risk_plan_h{h}.txt"
    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ585: Risk budget sizer (ATR-based)")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--horizon", type=int, required=True, choices=HORIZONS)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--reports-root", default="data/log/reports")
    p.add_argument("--snapshot-root", default=None)
    args = p.parse_args()

    cfg, cfg_err = _load_config()
    if cfg_err:
        print(cfg_err, file=sys.stderr)
        return 1

    repo = _repo_root()
    reports_root = Path(args.reports_root)
    if not reports_root.is_absolute():
        reports_root = (repo / reports_root).resolve()

    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.is_absolute():
        snapshot_root = (repo / snapshot_root).resolve()

    reports_dir = reports_root / args.day
    rows = _run_sizer(
        day=args.day,
        horizon=args.horizon,
        top_n=args.top,
        reports_root=reports_root,
        snapshot_root=snapshot_root,
        cfg=cfg,
    )

    if rows is None:
        print(f"topn_h{args.horizon} not found", file=sys.stderr)
        return 2

    try:
        _write_outputs(reports_dir, args.horizon, args.day, rows)
        print(f"risk_plan_h{args.horizon} -> {reports_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
