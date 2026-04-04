"""Tests for iDeal fetcher — real .G files, no mock."""

from __future__ import annotations

from struct import Struct

import pytest

from bist_core.data.ideal_fetcher import ideal_fetcher, make_ideal_fetcher

REC = Struct("<I7f")


def _pack_bar(date_code: int, o: float, h: float, l: float, c: float, v: float, t: float = 0.0, r: float = 0.0) -> bytes:
    return REC.pack(date_code, o, h, l, c, v, t, r)


def test_ideal_fetcher_valid(tmp_path) -> None:
    from pathlib import Path
    base = Path(tmp_path)
    bars = [_pack_bar(778000 + i, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 1000.0) for i in range(60)]
    p = base / "IMKBH'GARAN.G"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"".join(bars))
    result = ideal_fetcher(["GARAN"], base_path=str(base))
    assert "GARAN" in result
    assert len(result["GARAN"]) >= 50


def test_ideal_fetcher_missing_symbol(tmp_path) -> None:
    from pathlib import Path
    base = Path(tmp_path)
    result = ideal_fetcher(["NONEXISTENT"], base_path=str(base))
    assert result == {}


def test_ideal_fetcher_skips_insufficient_bars(tmp_path) -> None:
    from pathlib import Path
    base = Path(tmp_path)
    bars = [_pack_bar(778000 + i, 100.0, 101.0, 99.0, 100.5, 1000.0) for i in range(10)]
    p = base / "IMKBH'SHORT.G"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"".join(bars))
    result = ideal_fetcher(["SHORT"], base_path=str(base))
    assert "SHORT" not in result


def test_determinism(tmp_path) -> None:
    from pathlib import Path
    base = Path(tmp_path)
    bars = [_pack_bar(778000 + i, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 1000.0) for i in range(60)]
    p = base / "IMKBH'GARAN.G"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"".join(bars))
    a = ideal_fetcher(["GARAN"], base_path=str(base))
    b = ideal_fetcher(["GARAN"], base_path=str(base))
    assert a == b
    assert len(a["GARAN"]) == len(b["GARAN"])


def test_make_ideal_fetcher(tmp_path) -> None:
    from pathlib import Path
    base = Path(tmp_path)
    bars = [_pack_bar(778000 + i, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 1000.0) for i in range(60)]
    p = base / "IMKBH'TEST.G"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"".join(bars))
    fetcher = make_ideal_fetcher(base_path=str(base))
    result = fetcher(["TEST"])
    assert "TEST" in result
    assert len(result["TEST"]) >= 50
