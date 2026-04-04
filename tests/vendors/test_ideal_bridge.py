from __future__ import annotations

import struct
from pathlib import Path

import pytest

from bist_core.vendors.ideal_bridge import build_symbol_bridge, export_live_bridge_snapshot


def _pack_rec(ts_code: int, o: float, h: float, l: float, c: float, v: float, t: float, r: int = 0) -> bytes:
    return struct.pack("<I6fI", ts_code, o, h, l, c, v, t, r)


def _write_file(p: Path, recs: list[bytes]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"".join(recs))


def test_build_symbol_bridge_prefers_01_then_05_then_60_then_g(tmp_path: Path) -> None:
    root = tmp_path / "IMKBH"

    _write_file(root / "G" / "IMKBH'ASELS.G", [_pack_rec(100, 10, 11, 9, 10, 1000, 10000)])
    _write_file(root / "60" / "IMKBH'ASELS.60", [_pack_rec(200, 10, 11, 9, 11, 100, 1100)])
    _write_file(root / "05" / "IMKBH'ASELS.05", [_pack_rec(300, 10, 11, 9, 12, 100, 1200)])
    _write_file(root / "01" / "IMKBH'ASELS.01", [_pack_rec(400, 10, 11, 9, 13, 100, 1300)])

    row = build_symbol_bridge(root, "ASELS")
    assert row["current_close_source"] == "01"
    assert row["current_close"] == pytest.approx(13.0)
    assert row["g_close"] == pytest.approx(10.0)
    assert row["delta_current_vs_g_close_pct"] == pytest.approx(30.0)


def test_build_symbol_bridge_falls_back_to_g(tmp_path: Path) -> None:
    root = tmp_path / "IMKBH"
    _write_file(root / "G" / "IMKBH'AKFIS.G", [_pack_rec(100, 20, 21, 19, 20.5, 500, 10250)])

    row = build_symbol_bridge(root, "AKFIS")
    assert row["current_close_source"] == "G"
    assert row["current_close"] == pytest.approx(20.5)
    assert row["close_01"] is None


def test_export_live_bridge_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "IMKBH"

    _write_file(root / "G" / "IMKBH'ASELS.G", [_pack_rec(100, 10, 11, 9, 10, 1000, 10000)])
    _write_file(root / "01" / "IMKBH'ASELS.01", [_pack_rec(400, 10, 11, 9, 13, 100, 1300)])
    _write_file(root / "G" / "IMKBH'AKFIS.G", [_pack_rec(100, 20, 21, 19, 20.5, 500, 10250)])

    out = tmp_path / "out"
    manifest = export_live_bridge_snapshot(chart_root=root, out_dir=out)

    assert manifest["symbols_total"] == 2
    assert manifest["symbols_with_current_close"] == 2
    assert manifest["current_close_source_counts"]["01"] == 1
    assert manifest["current_close_source_counts"]["G"] == 1

    csv_path = out / "bridge_snapshot.csv"
    txt = csv_path.read_text(encoding="utf-8")
    assert "ASELS" in txt
    assert "AKFIS" in txt
