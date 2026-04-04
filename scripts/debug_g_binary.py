"""
Deep inspect iDeal .G binary structure (no decoding assumptions).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any


TARGET_FILE = Path(r"C:\iDeal\ChartData\IMKBH\G\IMKBH'THYAO.G")
RECORD_SIZES = [16, 20, 24, 28, 32, 40, 48]


def _hex_preview(data: bytes, n: int = 128) -> dict[str, str]:
    head = data[:n].hex(" ")
    tail = data[-n:].hex(" ") if len(data) >= n else data.hex(" ")
    return {"first_128_hex": head, "last_128_hex": tail}


def _unpack_first_record(rec: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if len(rec) >= 4:
        out["int32_le_0"] = struct.unpack("<i", rec[0:4])[0]
        out["uint32_le_0"] = struct.unpack("<I", rec[0:4])[0]
        out["float32_le_0"] = struct.unpack("<f", rec[0:4])[0]
    if len(rec) >= 8:
        out["int64_le_0"] = struct.unpack("<q", rec[0:8])[0]
        out["uint64_le_0"] = struct.unpack("<Q", rec[0:8])[0]
        out["float64_le_0"] = struct.unpack("<d", rec[0:8])[0]
    out["float32_seq"] = [
        struct.unpack("<f", rec[i : i + 4])[0]
        for i in range(0, len(rec) - (len(rec) % 4), 4)
    ]
    out["float64_seq"] = [
        struct.unpack("<d", rec[i : i + 8])[0]
        for i in range(0, len(rec) - (len(rec) % 8), 8)
    ]
    return out


def _ohlc_consistency_score(data: bytes, size: int) -> dict[str, Any]:
    total_records = len(data) // size
    if total_records == 0:
        return {"size": size, "records": 0, "consistent": 0, "ratio": 0.0}

    max_scan = min(total_records, 2000)
    consistent = 0
    checked = 0
    samples: list[dict[str, float]] = []

    for r in range(max_scan):
        rec = data[r * size : (r + 1) * size]
        if len(rec) < 20:
            continue
        try:
            o = struct.unpack("<f", rec[4:8])[0]
            h = struct.unpack("<f", rec[8:12])[0]
            l = struct.unpack("<f", rec[12:16])[0]
            c = struct.unpack("<f", rec[16:20])[0]
        except struct.error:
            continue
        checked += 1
        if (
            all(x == x and abs(x) < 1e9 for x in (o, h, l, c))
            and h >= l
            and l <= o <= h
            and l <= c <= h
        ):
            consistent += 1
            if len(samples) < 3:
                samples.append({"o": o, "h": h, "l": l, "c": c})
    ratio = (consistent / checked) if checked > 0 else 0.0
    return {
        "size": size,
        "records": total_records,
        "checked": checked,
        "consistent": consistent,
        "ratio": ratio,
        "sample_ohlc": samples,
    }


def main() -> int:
    path = TARGET_FILE
    if not path.is_file():
        print(json.dumps({"error": "FILE_NOT_FOUND", "path": str(path)}, ensure_ascii=False))
        return 2

    data = path.read_bytes()
    print(
        json.dumps(
            {
                "file": str(path),
                "total_bytes": len(data),
                **_hex_preview(data, 128),
            },
            ensure_ascii=False,
        )
    )

    layout_reports: list[dict[str, Any]] = []
    for size in RECORD_SIZES:
        total_records = len(data) // size
        first = data[:size] if len(data) >= size else b""
        unpacked = _unpack_first_record(first) if first else {}
        ohlc_eval = _ohlc_consistency_score(data, size)
        report = {
            "size": size,
            "total_records": total_records,
            "first_record_interpretations": unpacked,
            "ohlc_candidate_eval": ohlc_eval,
        }
        layout_reports.append(report)
        print(json.dumps({"record_size_analysis": report}, ensure_ascii=False))

    ranked = sorted(
        layout_reports,
        key=lambda x: (
            float(x["ohlc_candidate_eval"]["ratio"]),
            int(x["ohlc_candidate_eval"]["consistent"]),
            int(x["total_records"]),
        ),
        reverse=True,
    )
    top5 = [
        {
            "size": x["size"],
            "ratio": x["ohlc_candidate_eval"]["ratio"],
            "consistent": x["ohlc_candidate_eval"]["consistent"],
            "checked": x["ohlc_candidate_eval"]["checked"],
            "total_records": x["total_records"],
            "sample_ohlc": x["ohlc_candidate_eval"]["sample_ohlc"],
        }
        for x in ranked[:5]
    ]
    print(json.dumps({"top_5_consistent_layouts": top5}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
