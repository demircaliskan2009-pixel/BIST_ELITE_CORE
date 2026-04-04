from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from bist_core.vendors.ideal_intraday_bulk import export_intraday_tail_dataset


def _pack_u32_floats(ts, o, h, l, c, v, t, r=0) -> bytes:
    import struct
    return struct.pack("<I6fI", ts, o, h, l, c, v, t, r)


def _write_file(p: Path, recs: list[bytes]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"".join(recs))


def test_export_intraday_tail_dataset(tmp_path: Path) -> None:
    root = tmp_path / "IMKBH"

    _write_file(
        root / "60" / "IMKBH'ASELS.60",
        [
            _pack_u32_floats(1, 10, 11, 9, 10.5, 100, 1050),
            _pack_u32_floats(2, 11, 12, 10, 11.5, 200, 2300),
            _pack_u32_floats(3, 12, 13, 11, 12.5, 300, 3750),
        ],
    )
    _write_file(
        root / "60" / "IMKBH'AKFIS.60",
        [
            _pack_u32_floats(4, 20, 21, 19, 20.5, 400, 8200),
        ],
    )
    _write_file(
        root / "05" / "IMKBH'ASELS.05",
        [
            _pack_u32_floats(10, 1, 1, 1, 1, 10, 10),
            _pack_u32_floats(11, 2, 2, 2, 2, 20, 40),
        ],
    )

    out = tmp_path / "out"
    manifest = export_intraday_tail_dataset(chart_root=root, out_dir=out, periods=("60", "05"), tail=2)

    assert set(manifest["periods"].keys()) == {"60", "05"}
    assert manifest["periods"]["60"]["files_seen"] == 2
    assert manifest["periods"]["60"]["symbols_written"] == 2
    assert manifest["periods"]["05"]["symbols_written"] == 1

    csv60 = out / "intraday_60_tail2.csv"
    assert csv60.exists()

    rows60 = list(csv.DictReader(csv60.open("r", encoding="utf-8")))
    assert len(rows60) == 3
    cnt = Counter(r["symbol"] for r in rows60)
    assert cnt["ASELS"] == 2
    assert cnt["AKFIS"] == 1

    csv05 = out / "intraday_05_tail2.csv"
    rows05 = list(csv.DictReader(csv05.open("r", encoding="utf-8")))
    assert len(rows05) == 2
    assert manifest["periods"]["05"]["symbols"]["ASELS"]["tail_last"]["close"] == 2.0
