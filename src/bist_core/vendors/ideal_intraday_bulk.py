from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Optional

from bist_core.vendors.ideal_intraday import (
    file_record_count,
    infer_symbol_from_filename,
    iter_file_records,
    record_is_plausible,
)


def export_intraday_tail_dataset(
    *,
    chart_root: str | Path,
    out_dir: str | Path,
    periods: Iterable[str] = ("60", "05", "01"),
    tail: int = 200,
    symbols: Optional[Iterable[str]] = None,
) -> dict:
    root = Path(chart_root)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    symbol_filter = None
    if symbols is not None:
        symbol_filter = {str(s).upper() for s in symbols if str(s).strip()}

    manifest: dict = {
        "chart_root": str(root),
        "out_dir": str(out),
        "tail": int(tail),
        "periods": {},
    }

    for period in periods:
        period = str(period).upper()
        pdir = root / period
        csv_path = out / f"intraday_{period}_tail{tail}.csv"

        meta = {
            "period": period,
            "source_dir": str(pdir),
            "csv_path": str(csv_path),
            "files_seen": 0,
            "files_selected": 0,
            "invalid_size_files": [],
            "rows_written": 0,
            "symbols_written": 0,
            "symbols": {},
        }

        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "symbol",
                    "period",
                    "record_index",
                    "ts_code_raw",
                    "ts_iso",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover_tl",
                    "reserved_u32",
                    "source_file",
                ]
            )

            files = sorted(pdir.glob("IMKBH'*.*")) if pdir.exists() else []
            meta["files_seen"] = len(files)

            for fp in files:
                sym = infer_symbol_from_filename(fp)
                if symbol_filter is not None and sym not in symbol_filter:
                    continue

                meta["files_selected"] += 1

                try:
                    total_records = file_record_count(fp)
                except Exception:
                    meta["invalid_size_files"].append(fp.name)
                    continue

                rows = list(iter_file_records(fp, tail=tail))
                plausible = all(record_is_plausible(r) for r in rows) if rows else False

                for r in rows:
                    d = asdict(r)
                    writer.writerow(
                        [
                            d["symbol"],
                            d["period"],
                            d["record_index"],
                            d["ts_code_raw"],
                            d["ts_iso"],
                            d["open"],
                            d["high"],
                            d["low"],
                            d["close"],
                            d["volume"],
                            d["turnover_tl"],
                            d["reserved_u32"],
                            d["source_file"],
                        ]
                    )

                if rows:
                    meta["symbols_written"] += 1
                    meta["rows_written"] += len(rows)
                    last = rows[-1]
                    meta["symbols"][sym] = {
                        "source_file": str(fp),
                        "total_records": total_records,
                        "tail_rows": len(rows),
                        "tail_all_plausible": plausible,
                        "tail_last": {
                            "record_index": last.record_index,
                            "ts_code_raw": last.ts_code_raw,
                            "ts_iso": last.ts_iso,
                            "open": last.open,
                            "high": last.high,
                            "low": last.low,
                            "close": last.close,
                            "volume": last.volume,
                            "turnover_tl": last.turnover_tl,
                        },
                    }

        manifest["periods"][period] = meta

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
