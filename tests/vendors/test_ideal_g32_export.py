from pathlib import Path
from struct import Struct

import pytest

from bist_core.vendors.ideal_g32_export import export_g32_valid_rows_to_csv

REC = Struct("<I7f")


def _pack_bar(date_code, o, h, l, c, v, t, r=0.0):
    return REC.pack(date_code, float(o), float(h), float(l), float(c), float(v), float(t), float(r))


def test_export_g32_valid_rows_to_csv_writes_canonical_csv(tmp_path: Path) -> None:
    src = tmp_path / "IMKBH'ASELS.G"
    out = tmp_path / "asels.csv"

    src.write_bytes(
        b"".join(
            [
                _pack_bar(101, 10, 11, 9, 10.5, 100, 1000),
                _pack_bar(102, 11, 12, 10, 11.5, 110, 1100),
                _pack_bar(103, 12, 13, 11, 12.5, 120, 1200),
            ]
        )
    )

    meta = export_g32_valid_rows_to_csv(src, out, max_anomaly_ratio=0.10, min_valid_rows=2)

    assert meta["symbol"] == "ASELS"
    assert meta["exported_rows"] == 3
    assert out.exists()

    txt = out.read_text(encoding="utf-8")
    assert "symbol,source_file,row_index,raw_date_code,open,high,low,close,volume,turnover,reserved" in txt
    assert "ASELS,IMKBH'ASELS.G,0,101" in txt


def test_export_g32_valid_rows_to_csv_fails_when_anomaly_ratio_too_high(tmp_path: Path) -> None:
    src = tmp_path / "IMKBH'BAD.G"
    out = tmp_path / "bad.csv"

    src.write_bytes(
        b"".join(
            [
                _pack_bar(101, 10, 11, 9, 10.5, 100, 1000),
                _pack_bar(102, 1, 2, 5, 1.5, 100, 1000),   # anomaly
                _pack_bar(103, 12, 13, 11, 12.5, 120, 1200),
            ]
        )
    )

    with pytest.raises(ValueError, match="Anomaly ratio too high"):
        export_g32_valid_rows_to_csv(src, out, max_anomaly_ratio=0.20, min_valid_rows=2)


def test_export_g32_valid_rows_to_csv_fails_when_valid_rows_too_few(tmp_path: Path) -> None:
    src = tmp_path / "IMKBH'SHORT.G"
    out = tmp_path / "short.csv"

    src.write_bytes(
        b"".join(
            [
                _pack_bar(101, 10, 11, 9, 10.5, 100, 1000),
            ]
        )
    )

    with pytest.raises(ValueError, match="Too few valid rows"):
        export_g32_valid_rows_to_csv(src, out, max_anomaly_ratio=0.10, min_valid_rows=2)
