from pathlib import Path
from struct import Struct

import pytest

from bist_core.vendors.ideal_g32 import parse_g32_file, tail_g32_file, audit_g32_file

REC = Struct("<I7f")


def _pack_bar(date_code, o, h, l, c, v, t, r=0.0):
    return REC.pack(date_code, float(o), float(h), float(l), float(c), float(v), float(t), float(r))


def test_parse_g32_file_reads_ohlcv_records(tmp_path: Path) -> None:
    p = tmp_path / "sample.G"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(778058, 319.25, 336.00, 319.25, 334.25, 29364718, 9669047296),
                _pack_bar(778059, 334.50, 335.75, 326.50, 335.75, 18257244, 6062096384),
            ]
        )
    )

    got = parse_g32_file(p)

    assert got["record_count"] == 2
    assert got["valid_count"] == 2
    assert got["anomaly_count"] == 0
    assert got["rows"][0]["raw_date_code"] == 778058
    assert got["rows"][0]["close"] == 334.25


def test_parse_g32_file_strict_raises_on_implausible_record(tmp_path: Path) -> None:
    p = tmp_path / "bad.G"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(1, 10, 12, 9, 11, 100, 1000),
                _pack_bar(2, 1, 2, 5, 1.5, 100, 1000),  # low > open/close -> implausible
            ]
        )
    )

    with pytest.raises(ValueError):
        parse_g32_file(p, strict=True)


def test_parse_g32_file_tolerant_keeps_valid_rows_and_reports_anomalies(tmp_path: Path) -> None:
    p = tmp_path / "mixed.G"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(1, 10, 12, 9, 11, 100, 1000),
                _pack_bar(2, 1, 2, 5, 1.5, 100, 1000),  # anomaly
                _pack_bar(3, 20, 21, 19, 20.5, 120, 1500),
            ]
        )
    )

    got = parse_g32_file(p, strict=False)

    assert got["record_count"] == 3
    assert got["valid_count"] == 2
    assert got["anomaly_count"] == 1
    assert got["anomalies"][0]["offset"] == 32
    assert got["rows"][-1]["raw_date_code"] == 3


def test_tail_and_audit_g32_file(tmp_path: Path) -> None:
    p = tmp_path / "tail.G"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(1, 10, 11, 9, 10.5, 100, 1000),
                _pack_bar(2, 11, 12, 10, 11.5, 110, 1100),
                _pack_bar(3, 12, 13, 11, 12.5, 120, 1200),
            ]
        )
    )

    tail = tail_g32_file(p, n=2, strict=False)
    audit = audit_g32_file(p, tail_n=2)

    assert [x["raw_date_code"] for x in tail] == [2, 3]
    assert audit["anomaly_count"] == 0
    assert len(audit["tail_rows"]) == 2
