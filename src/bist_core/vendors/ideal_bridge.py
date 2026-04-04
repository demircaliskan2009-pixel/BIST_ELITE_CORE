from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

from bist_core.vendors.ideal_intraday import infer_symbol_from_filename, iter_file_records

PERIODS = ("G", "60", "05", "01")
CURRENT_PRIORITY = ("01", "05", "60", "G")


def _find_symbol_file(root: Path, symbol: str, period: str) -> Path | None:
    p = root / period / f"IMKBH'{symbol}.{period}"
    return p if p.exists() else None


def _last_record(root: Path, symbol: str, period: str):
    fp = _find_symbol_file(root, symbol, period)
    if fp is None:
        return None
    rows = list(iter_file_records(fp, symbol=symbol, period=period, tail=1))
    return rows[-1] if rows else None


def discover_symbols(chart_root: str | Path, periods: Iterable[str] = PERIODS) -> list[str]:
    root = Path(chart_root)
    out: set[str] = set()
    for period in periods:
        d = root / str(period).upper()
        if not d.exists():
            continue
        for fp in d.glob("IMKBH'*.*"):
            out.add(infer_symbol_from_filename(fp))
    return sorted(out)


def build_symbol_bridge(chart_root: str | Path, symbol: str) -> dict:
    root = Path(chart_root)
    symbol = str(symbol).upper()

    recs: dict[str, object | None] = {}
    for period in PERIODS:
        recs[period] = _last_record(root, symbol, period)

    current_rec = None
    current_source = None
    for period in CURRENT_PRIORITY:
        rec = recs.get(period)
        if rec is not None:
            current_rec = rec
            current_source = period
            break

    g_rec = recs.get("G")
    current_close = float(current_rec.close) if current_rec is not None else None
    g_close = float(g_rec.close) if g_rec is not None else None

    delta_pct = None
    if current_close is not None and g_close not in (None, 0):
        delta_pct = ((current_close / g_close) - 1.0) * 100.0

    out = {
        "symbol": symbol,
        "has_g": g_rec is not None,
        "has_60": recs.get("60") is not None,
        "has_05": recs.get("05") is not None,
        "has_01": recs.get("01") is not None,
        "current_close_source": current_source,
        "current_close": current_close,
        "g_open": float(g_rec.open) if g_rec is not None else None,
        "g_high": float(g_rec.high) if g_rec is not None else None,
        "g_low": float(g_rec.low) if g_rec is not None else None,
        "g_close": g_close,
        "g_volume": float(g_rec.volume) if g_rec is not None else None,
        "g_turnover_tl": float(g_rec.turnover_tl) if g_rec is not None else None,
        "close_60": float(recs["60"].close) if recs.get("60") is not None else None,
        "close_05": float(recs["05"].close) if recs.get("05") is not None else None,
        "close_01": float(recs["01"].close) if recs.get("01") is not None else None,
        "ts_code_g": int(g_rec.ts_code_raw) if g_rec is not None else None,
        "ts_code_60": int(recs["60"].ts_code_raw) if recs.get("60") is not None else None,
        "ts_code_05": int(recs["05"].ts_code_raw) if recs.get("05") is not None else None,
        "ts_code_01": int(recs["01"].ts_code_raw) if recs.get("01") is not None else None,
        "delta_current_vs_g_close_pct": round(delta_pct, 6) if delta_pct is not None else None,
    }
    return out


def export_live_bridge_snapshot(
    *,
    chart_root: str | Path,
    out_dir: str | Path,
    symbols: Optional[Iterable[str]] = None,
) -> dict:
    root = Path(chart_root)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if symbols is None:
        symbol_list = discover_symbols(root)
    else:
        symbol_list = sorted({str(s).upper() for s in symbols if str(s).strip()})

    rows = [build_symbol_bridge(root, s) for s in symbol_list]
    rows = sorted(rows, key=lambda x: x["symbol"])

    csv_path = out / "bridge_snapshot.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "has_g",
                "has_60",
                "has_05",
                "has_01",
                "current_close_source",
                "current_close",
                "g_open",
                "g_high",
                "g_low",
                "g_close",
                "g_volume",
                "g_turnover_tl",
                "close_60",
                "close_05",
                "close_01",
                "ts_code_g",
                "ts_code_60",
                "ts_code_05",
                "ts_code_01",
                "delta_current_vs_g_close_pct",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    src_counter = Counter(r["current_close_source"] for r in rows if r["current_close_source"])
    manifest = {
        "chart_root": str(root),
        "out_dir": str(out),
        "symbols_total": len(rows),
        "symbols_with_g": sum(1 for r in rows if r["has_g"]),
        "symbols_with_60": sum(1 for r in rows if r["has_60"]),
        "symbols_with_05": sum(1 for r in rows if r["has_05"]),
        "symbols_with_01": sum(1 for r in rows if r["has_01"]),
        "symbols_with_current_close": sum(1 for r in rows if r["current_close"] is not None),
        "current_close_source_counts": dict(src_counter),
        "csv_path": str(csv_path),
    }

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
