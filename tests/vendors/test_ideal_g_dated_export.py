from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from struct import Struct

from bist_core.vendors.ideal_g_dated_export import (
    combine_dated_g32_exports,
    export_dated_g32_csv,
    infer_anchor_date_from_g_file,
)

REC = Struct("<I7f")


def _pack_bar(date_code, o, h, l, c, v, t, r=0.0):
    return REC.pack(date_code, float(o), float(h), float(l), float(c), float(v), float(t), float(r))


def _write_canonical_csv(path: Path, symbol: str, source_file: str, raw_codes: list[int]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        w.writeheader()
        for i, raw_code in enumerate(raw_codes):
            w.writerow(
                {
                    "symbol": symbol,
                    "source_file": source_file,
                    "row_index": i,
                    "raw_date_code": raw_code,
                    "open": 10 + i,
                    "high": 11 + i,
                    "low": 9 + i,
                    "close": 10.5 + i,
                    "volume": 100 + i,
                    "turnover": 1000 + i,
                    "reserved": 0,
                }
            )


def test_infer_anchor_date_from_g_file_uses_previous_weekday_on_weekend(tmp_path: Path) -> None:
    g = tmp_path / "IMKBH'ASELS.G"
    g.write_bytes(_pack_bar(1, 1, 1, 1, 1, 1, 1))

    ts = datetime(2026, 3, 14, 12, 0, 0).timestamp()  # Saturday
    os.utime(g, (ts, ts))

    assert infer_anchor_date_from_g_file(g).isoformat() == "2026-03-13"


def test_export_dated_g32_csv_maps_raw_codes_to_iso_dates(tmp_path: Path) -> None:
    canonical = tmp_path / "IMKBH_ASELS.csv"
    out = tmp_path / "dated.csv"
    gdir = tmp_path / "g"
    gdir.mkdir()

    g = gdir / "IMKBH'ASELS.G"
    g.write_bytes(_pack_bar(1, 1, 1, 1, 1, 1, 1))

    _write_canonical_csv(
        canonical,
        symbol="ASELS",
        source_file="IMKBH'ASELS.G",
        raw_codes=[778054, 778057, 778058, 778059, 778060, 778061],
    )

    meta = export_dated_g32_csv(
        canonical,
        out,
        source_g_dir=gdir,
        anchor_date="2026-03-13",
    )

    assert meta["last_date"] == "2026-03-13"
    txt = out.read_text(encoding="utf-8")
    assert "ASELS,2026-03-06,IMKBH'ASELS.G,0,778054" in txt
    assert "ASELS,2026-03-09,IMKBH'ASELS.G,1,778057" in txt
    assert "ASELS,2026-03-13,IMKBH'ASELS.G,5,778061" in txt


def test_combine_dated_g32_exports_writes_combined_csv_and_summary(tmp_path: Path) -> None:
    src_dir = tmp_path / "canonical"
    out_dir = tmp_path / "dated_out"
    gdir = tmp_path / "g"
    src_dir.mkdir()
    gdir.mkdir()

    (gdir / "IMKBH'ASELS.G").write_bytes(_pack_bar(1, 1, 1, 1, 1, 1, 1))
    (gdir / "IMKBH'AKBNK.G").write_bytes(_pack_bar(1, 1, 1, 1, 1, 1, 1))

    _write_canonical_csv(src_dir / "IMKBH_ASELS.csv", "ASELS", "IMKBH'ASELS.G", [778060, 778061])
    _write_canonical_csv(src_dir / "IMKBH_AKBNK.csv", "AKBNK", "IMKBH'AKBNK.G", [778060, 778061])

    summary = combine_dated_g32_exports(
        src_dir,
        out_dir,
        source_g_dir=gdir,
        anchor_date="2026-03-13",
    )

    assert summary["file_count_seen"] == 2
    assert (out_dir / "combined_ohlcv.csv").exists()
    assert (out_dir / "summary.json").exists()

    combined = (out_dir / "combined_ohlcv.csv").read_text(encoding="utf-8")
    assert "ASELS,2026-03-12" in combined
    assert "AKBNK,2026-03-13" in combined

def test_export_dated_g32_csv_skips_weekends_when_mapping_raw_codes(tmp_path: Path) -> None:
    canonical = tmp_path / "IMKBH_ASELS.csv"
    out = tmp_path / "dated_weekdays.csv"
    gdir = tmp_path / "g"
    gdir.mkdir()

    g = gdir / "IMKBH'ASELS.G"
    g.write_bytes(_pack_bar(1, 1, 1, 1, 1, 1, 1))

    _write_canonical_csv(
        canonical,
        symbol="ASELS",
        source_file="IMKBH'ASELS.G",
        raw_codes=[778054, 778057, 778058, 778059, 778060, 778061],
    )

    export_dated_g32_csv(
        canonical,
        out,
        source_g_dir=gdir,
        anchor_date="2026-03-13",
    )

    txt = out.read_text(encoding="utf-8")
    assert "ASELS,2026-03-06,IMKBH'ASELS.G,0,778054" in txt
    assert "ASELS,2026-03-09,IMKBH'ASELS.G,1,778057" in txt
    assert "ASELS,2026-03-10,IMKBH'ASELS.G,2,778058" in txt
    assert "ASELS,2026-03-11,IMKBH'ASELS.G,3,778059" in txt
    assert "ASELS,2026-03-12,IMKBH'ASELS.G,4,778060" in txt
    assert "ASELS,2026-03-13,IMKBH'ASELS.G,5,778061" in txt
    assert "2026-03-07" not in txt
    assert "2026-03-08" not in txt

def test_export_dated_g32_csv_drops_weekend_rows_after_calendar_mapping(tmp_path: Path) -> None:
    canonical = tmp_path / "IMKBH_TEST.csv"
    out = tmp_path / "dated_drop_weekend.csv"
    gdir = tmp_path / "g"
    gdir.mkdir()

    g = gdir / "IMKBH'TEST.G"
    g.write_bytes(_pack_bar(1, 1, 1, 1, 1, 1, 1))

    _write_canonical_csv(
        canonical,
        symbol="TEST",
        source_file="IMKBH'TEST.G",
        raw_codes=[101, 102, 103],
    )

    meta = export_dated_g32_csv(
        canonical,
        out,
        source_g_dir=gdir,
        anchor_date="2026-03-09",
    )

    assert meta["anchor_date"] == "2026-03-09"
    assert meta["exported_rows"] == 1
    assert meta["dropped_weekend_rows"] == 2

    txt = out.read_text(encoding="utf-8")
    assert "TEST,2026-03-09,IMKBH'TEST.G,2,103" in txt
    assert "2026-03-07" not in txt
    assert "2026-03-08" not in txt
