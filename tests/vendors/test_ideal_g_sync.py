from pathlib import Path
from struct import Struct

from bist_core.vendors.ideal_g_sync import sync_ideal_g_folder_to_canonical

REC = Struct("<I7f")


def _pack_bar(date_code, o, h, l, c, v, t, r=0.0):
    return REC.pack(date_code, float(o), float(h), float(l), float(c), float(v), float(t), float(r))


def test_sync_ideal_g_folder_to_canonical_exports_and_rejects(tmp_path: Path) -> None:
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()

    good = src / "IMKBH'ASELS.G"
    bad = src / "IMKBH'ADEL.G"

    good.write_bytes(
        b"".join(
            [
                _pack_bar(101, 10, 11, 9, 10.5, 100, 1000),
                _pack_bar(102, 11, 12, 10, 11.5, 110, 1100),
                _pack_bar(103, 12, 13, 11, 12.5, 120, 1200),
            ]
        )
    )

    bad.write_bytes(
        b"".join(
            [
                _pack_bar(201, 10, 11, 9, 10.5, 100, 1000),
                _pack_bar(202, 1, 2, 5, 1.5, 100, 1000),   # anomaly
                _pack_bar(203, 12, 13, 11, 12.5, 120, 1200),
            ]
        )
    )

    got = sync_ideal_g_folder_to_canonical(
        src,
        out,
        max_anomaly_ratio=0.20,
        min_valid_rows=2,
    )

    assert got["file_count_seen"] == 2
    assert got["exported_count"] == 1
    assert got["rejected_count"] == 1

    rows = {x["source_file"]: x for x in got["results"]}
    assert rows["IMKBH'ASELS.G"]["status"] == "exported"
    assert rows["IMKBH'ADEL.G"]["status"] == "rejected"
    assert (out / "IMKBH_ASELS.csv").exists()


def test_sync_ideal_g_folder_to_canonical_respects_limit(tmp_path: Path) -> None:
    src = tmp_path / "src2"
    out = tmp_path / "out2"
    src.mkdir()

    for i in range(3):
        p = src / f"IMKBH'TEST{i}.G"
        p.write_bytes(
            b"".join(
                [
                    _pack_bar(101, 10, 11, 9, 10.5, 100, 1000),
                    _pack_bar(102, 11, 12, 10, 11.5, 110, 1100),
                ]
            )
        )

    got = sync_ideal_g_folder_to_canonical(
        src,
        out,
        max_anomaly_ratio=0.10,
        min_valid_rows=2,
        limit=2,
    )

    assert got["file_count_seen"] == 2
    assert got["exported_count"] == 2
