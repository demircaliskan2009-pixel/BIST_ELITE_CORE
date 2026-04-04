from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from bist_core.vendors.ideal_g32 import parse_g32_file


def _symbol_from_path(path: str | Path) -> str:
    name = Path(path).name
    if "'" in name:
        rhs = name.split("'", 1)[1]
        return rhs.rsplit(".", 1)[0]
    return Path(path).stem


def export_g32_valid_rows_to_csv(
    src_path: str | Path,
    out_csv: str | Path,
    *,
    max_anomaly_ratio: float = 0.10,
    min_valid_rows: int = 200,
) -> dict[str, Any]:
    parsed = parse_g32_file(src_path, strict=False)

    record_count = int(parsed["record_count"])
    valid_count = int(parsed["valid_count"])
    anomaly_count = int(parsed["anomaly_count"])
    anomaly_ratio = (anomaly_count / record_count) if record_count else 0.0

    if valid_count < min_valid_rows:
        raise ValueError(
            f"Too few valid rows for export: valid_count={valid_count} min_valid_rows={min_valid_rows}"
        )

    if anomaly_ratio > max_anomaly_ratio:
        raise ValueError(
            f"Anomaly ratio too high for export: ratio={anomaly_ratio:.6f} limit={max_anomaly_ratio:.6f}"
        )

    src = Path(src_path)
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "symbol",
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

    rows = parsed["rows"]
    symbol = _symbol_from_path(src)

    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for idx, row in enumerate(rows):
            w.writerow(
                {
                    "symbol": symbol,
                    "source_file": src.name,
                    "row_index": idx,
                    "raw_date_code": row["raw_date_code"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                    "turnover": row["turnover"],
                    "reserved": row["reserved"],
                }
            )

    return {
        "symbol": symbol,
        "source_file": src.name,
        "out_csv": str(out),
        "record_count": record_count,
        "valid_count": valid_count,
        "anomaly_count": anomaly_count,
        "anomaly_ratio": round(anomaly_ratio, 6),
        "exported_rows": len(rows),
        "max_anomaly_ratio": max_anomaly_ratio,
        "min_valid_rows": min_valid_rows,
    }
