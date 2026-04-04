from __future__ import annotations

import struct
from pathlib import Path

import pytest

from bist_core.vendors.ideal_intraday import (
    REC_SIZE,
    decode_record_bytes,
    file_record_count,
    infer_period_from_filename,
    infer_symbol_from_filename,
    iter_file_records,
    record_is_plausible,
)


def _pack_rec(ts_code: int, o: float, h: float, l: float, c: float, v: float, t: float, r: int = 0) -> bytes:
    return struct.pack("<I6fI", ts_code, o, h, l, c, v, t, r)


def test_ideal_intraday_infer_filename_parts() -> None:
    p = Path(r"C:\iDeal\ChartData\IMKBH\05\IMKBH'ASELS.05")
    assert infer_symbol_from_filename(p) == "ASELS"
    assert infer_period_from_filename(p) == "05"


def test_ideal_intraday_decode_record_bytes() -> None:
    raw = _pack_rec(20017085, 10.0, 11.0, 9.5, 10.5, 12345.0, 130000.0, 7)
    rec = decode_record_bytes(
        raw,
        symbol="ASELS",
        period="05",
        record_index=3,
        source_file="x",
    )
    assert rec.symbol == "ASELS"
    assert rec.period == "05"
    assert rec.record_index == 3
    assert rec.ts_code_raw == 20017085
    assert rec.open == pytest.approx(10.0)
    assert rec.high == pytest.approx(11.0)
    assert rec.low == pytest.approx(9.5)
    assert rec.close == pytest.approx(10.5)
    assert rec.volume == pytest.approx(12345.0)
    assert rec.turnover_tl == pytest.approx(130000.0)
    assert rec.reserved_u32 == 7
    assert record_is_plausible(rec) is True


def test_ideal_intraday_iter_tail(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKFIS.01"
    raw = b"".join(
        [
            _pack_rec(1, 1.0, 1.2, 0.9, 1.1, 10.0, 11.0),
            _pack_rec(2, 2.0, 2.2, 1.9, 2.1, 20.0, 42.0),
            _pack_rec(3, 3.0, 3.2, 2.9, 3.1, 30.0, 93.0),
        ]
    )
    p.write_bytes(raw)
    assert len(raw) == 3 * REC_SIZE
    assert file_record_count(p) == 3

    rows = list(iter_file_records(p, tail=2))
    assert len(rows) == 2
    assert rows[0].record_index == 1
    assert rows[1].record_index == 2
    assert rows[0].symbol == "AKFIS"
    assert rows[0].period == "01"
    assert rows[1].close == pytest.approx(3.1)
