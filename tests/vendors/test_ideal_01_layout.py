from pathlib import Path
from struct import Struct

from bist_core.vendors.ideal_01_layout import audit_ideal_01_file

REC = Struct("<I7f")


def _pack_bar(time_code, o, h, l, c, v, t, r=0.0):
    return REC.pack(time_code, float(o), float(h), float(l), float(c), float(v), float(t), float(r))


def test_audit_ideal_01_file_finds_best_header_and_tail_rows(tmp_path: Path) -> None:
    p = tmp_path / "sample.01"
    header = b"\xAA" * 32
    body = b"".join(
        [
            _pack_bar(1001, 10, 11, 9, 10.5, 100, 1000),
            _pack_bar(1002, 10.5, 12, 10, 11.5, 120, 1300),
            _pack_bar(1003, 11.5, 12.5, 11, 12.0, 140, 1500),
        ]
    )
    p.write_bytes(header + body)

    got = audit_ideal_01_file(p, tail_n=2)

    assert got["best"]["header_bytes"] == 32
    assert got["best"]["coverage_ratio"] == 0.75
    assert got["best"]["record_bytes"] == 32
    assert got["best"]["record_count"] == 3
    assert got["best"]["valid_count"] == 3
    assert got["best"]["anomaly_count"] == 0
    assert [x["raw_time_code"] for x in got["best"]["tail_rows"]] == [1002, 1003]


def test_audit_ideal_01_file_reports_anomalies(tmp_path: Path) -> None:
    p = tmp_path / "bad.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(2001, 10, 11, 9, 10.5, 100, 1000),
                _pack_bar(2002, 1, 2, 5, 1.5, 100, 1000),  # anomaly
                _pack_bar(2003, 12, 13, 11, 12.5, 120, 1200),
            ]
        )
    )

    got = audit_ideal_01_file(p, tail_n=3)

    assert got["best"]["header_bytes"] == 0
    assert got["best"]["record_count"] == 3
    assert got["best"]["valid_count"] == 2
    assert got["best"]["anomaly_count"] == 1
    assert got["best"]["coverage_ratio"] == 1.0
    assert got["best"]["first_anomalies"][0]["reason"] in ("high_below_low", "low_above_open_or_close")
