from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def _coerce_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def infer_anchor_date_from_g_file(g_file: str | Path) -> date:
    p = Path(g_file)
    if not p.exists():
        raise FileNotFoundError(f"G file not found for anchor inference: {p}")

    d = datetime.fromtimestamp(p.stat().st_mtime).date()
    while d.weekday() >= 5:  # Sat/Sun -> previous Friday
        d -= timedelta(days=1)
    return d




def _shift_weekdays(anchor: date, delta_days: int) -> date:
    """
    delta_days kadar GERİ giderken sadece hafta içi günleri say.
    delta_days=0 -> anchor
    """
    if delta_days < 0:
        raise ValueError(f"delta_days must be >= 0, got {delta_days}")

    d = anchor
    remaining = delta_days
    while remaining > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            remaining -= 1
    return d


def _read_csv_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    with p.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"Empty canonical csv: {p}")
    return rows


def export_dated_g32_csv(
    src_csv: str | Path,
    out_csv: str | Path,
    *,
    source_g_dir: str | Path,
    anchor_date: str | date | None = None,
) -> dict[str, Any]:
    src_csv = Path(src_csv)
    out_csv = Path(out_csv)
    source_g_dir = Path(source_g_dir)

    rows = _read_csv_rows(src_csv)
    first = rows[0]

    source_file = str(first.get("source_file") or "").strip()
    symbol = str(first.get("symbol") or "").strip()
    if not source_file:
        raise ValueError(f"Missing source_file in canonical csv: {src_csv}")

    g_file = source_g_dir / source_file
    anchor = _coerce_date(anchor_date)
    if anchor is None:
        anchor = infer_anchor_date_from_g_file(g_file)

    latest_raw = max(int(r["raw_date_code"]) for r in rows)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "date",
        "source_file",
        "row_index",
        "raw_date_code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "reserved",
    ]

    first_date = None
    last_date = None
    dropped_weekend_rows = 0
    exported_rows = 0

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        for r in rows:
            raw_code = int(r["raw_date_code"])
            mapped_date = anchor - timedelta(days=(latest_raw - raw_code))
            if mapped_date.weekday() >= 5:
                dropped_weekend_rows += 1
                continue
            iso_date = mapped_date.isoformat()
            if first_date is None or iso_date < first_date:
                first_date = iso_date
            if last_date is None or iso_date > last_date:
                last_date = iso_date

            w.writerow(
                {
                    "symbol": r["symbol"],
                    "date": iso_date,
                    "source_file": r["source_file"],
                    "row_index": r["row_index"],
                    "raw_date_code": r["raw_date_code"],
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume": r["volume"],
                    "turnover": r["turnover"],
                    "reserved": r["reserved"],
                }
            )
            exported_rows += 1

    return {
        "symbol": symbol,
        "source_file": source_file,
        "src_csv": str(src_csv),
        "out_csv": str(out_csv),
        "anchor_date": anchor.isoformat(),
        "latest_raw_date_code": latest_raw,
        "first_date": first_date,
        "last_date": last_date,
        "exported_rows": exported_rows,
        "dropped_weekend_rows": dropped_weekend_rows,
    }


def combine_dated_g32_exports(
    src_dir: str | Path,
    out_dir: str | Path,
    *,
    source_g_dir: str | Path,
    glob_pattern: str = "*.csv",
    limit: int | None = None,
    anchor_date: str | date | None = None,
) -> dict[str, Any]:
    src_dir = Path(src_dir)
    out_dir = Path(out_dir)
    source_g_dir = Path(source_g_dir)

    if not src_dir.exists():
        raise FileNotFoundError(f"Canonical source folder not found: {src_dir}")

    files = sorted(src_dir.glob(glob_pattern))
    if limit is not None:
        files = files[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    per_symbol_dir = out_dir / "per_symbol"
    per_symbol_dir.mkdir(parents=True, exist_ok=True)

    combined_csv = out_dir / "combined_ohlcv.csv"
    manifest: list[dict[str, Any]] = []

    combined_fieldnames = [
        "symbol",
        "date",
        "source_file",
        "row_index",
        "raw_date_code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "reserved",
    ]

    with combined_csv.open("w", encoding="utf-8", newline="") as fout:
        w = csv.DictWriter(fout, fieldnames=combined_fieldnames)
        w.writeheader()

        for src_csv in files:
            out_csv = per_symbol_dir / src_csv.name
            meta = export_dated_g32_csv(
                src_csv,
                out_csv,
                source_g_dir=source_g_dir,
                anchor_date=anchor_date,
            )
            manifest.append(meta)

            with out_csv.open("r", encoding="utf-8", newline="") as fin:
                for row in csv.DictReader(fin):
                    w.writerow(row)

    summary = {
        "src_dir": str(src_dir),
        "source_g_dir": str(source_g_dir),
        "out_dir": str(out_dir),
        "combined_csv": str(combined_csv),
        "file_count_seen": len(files),
        "manifest": manifest,
    }

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return summary
