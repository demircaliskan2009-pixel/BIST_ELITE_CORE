"""iDeal .01 — locked 32-byte ``<iffffffi`` layout; dynamic OHLC scale."""

from __future__ import annotations

import io
import struct
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from bist_core.live.data_feed import IdealDataFeed, parse_ideal_01_bytes, select_dynamic_scale


@pytest.fixture(autouse=True)
def _ideal_feed_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_IDEAL_MARKET_SEAL", "0")
    yield


def pack_bar(
    ts: int,
    o: float,
    h: float,
    l: float,
    c_raw: float,
    v: float,
    val: float = 0.0,
    pad: int = 0,
) -> bytes:
    """Raw file floats (TL-scale); feed normalizes with ÷divisor."""
    return struct.pack(
        "<iffffffi",
        int(ts),
        float(o),
        float(h),
        float(l),
        float(c_raw),
        float(v),
        float(val),
        int(pad),
    )


def test_select_dynamic_scale_matches_synthetic_series() -> None:
    # Raw closes as stored (e.g. ~330 TL); divisor 1 → normalized median in BIST band.
    raw = [330.0 + float(i) * 0.5 for i in range(30)]
    divisor, matched = select_dynamic_scale(raw)
    assert matched is True
    assert divisor == 1.0


def test_parse_ideal_01_bytes_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_IDEAL_PARSE_STRICT", "0")
    # On-disk close 105.0 → ÷1 → 105 TL
    b = pack_bar(1, 100.0, 110.0, 90.0, 105.0, 1000.0)
    bars = parse_ideal_01_bytes(b, "X")
    assert len(bars) == 1
    assert bars[0].symbol == "X"
    assert bars[0].timestamp == 1
    assert bars[0].close == pytest.approx(105.0)
    assert bars[0].open == pytest.approx(100.0)
    assert bars[0].volume == pytest.approx(1000.0)
    assert bars[0].is_dummy is False


def test_ideal_feed_full_snapshot_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_IDEAL_PARSE_STRICT", "0")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        p = base / "IMKBH'X.01"
        p.write_bytes(
            pack_bar(1, 100.0, 101.0, 99.0, 100.5, 1.0)
            + pack_bar(2, 100.0, 101.0, 99.0, 100.6, 2.0)
        )

        feed = IdealDataFeed(str(base))
        first = feed.read_new("X")
        assert len(first) == 2
        assert first[0].close == pytest.approx(100.5)

        second = feed.read_new("X")
        assert len(second) == 2

        p.write_bytes(p.read_bytes() + pack_bar(3, 102.0, 103.0, 101.0, 102.5, 3.0))
        third = feed.read_new("X")
        assert len(third) == 3
        assert third[-1].close == pytest.approx(102.5)


def test_many_bars_production_gate() -> None:
    buf = bytearray()
    for i in range(60):
        c_raw = 100.0 + float(i) * 0.1
        buf.extend(
            pack_bar(
                1000 + i,
                c_raw - 0.1,
                c_raw + 0.1,
                c_raw - 0.2,
                c_raw,
                float(1000 + i),
            )
        )
    bars = parse_ideal_01_bytes(bytes(buf), "Y")
    assert len(bars) == 60
    closes = [x.close for x in bars[-10:]]
    assert len({round(x, 4) for x in closes}) >= 5


def test_production_parse_at_least_50_bars_unique() -> None:
    buf = bytearray()
    for i in range(120):
        c_raw = 120.0 + float(i) * 0.2
        buf.extend(
            pack_bar(
                1000 + i,
                c_raw - 0.1,
                c_raw + 0.1,
                c_raw - 0.2,
                c_raw,
                float(i),
            )
        )
    bars = parse_ideal_01_bytes(bytes(buf), "Z")
    assert len(bars) == 120
    sample = bars[-20:]
    closes = [b.close for b in sample]
    assert len(bars) >= 50
    assert len({round(x, 6) for x in closes}) > 10


def test_ideal_feed_read_new_prints_final_locked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BIST_IDEAL_PARSE_STRICT", raising=False)
    monkeypatch.setenv("BIST_IDEAL_MARKET_SEAL", "1")
    buf = bytearray()
    for i in range(120):
        c_raw = 150.0 + float(i) * 0.1
        buf.extend(
            pack_bar(
                1000 + i,
                c_raw - 0.1,
                c_raw + 0.1,
                c_raw - 0.2,
                c_raw,
                float(i),
            )
        )
    p = tmp_path / "IMKBH'X.01"
    p.write_bytes(bytes(buf))

    feed = IdealDataFeed(str(tmp_path))
    out = io.StringIO()
    with redirect_stdout(out):
        feed.read_new("X")
    s = out.getvalue()
    assert "DATA_PROOF" in s
    assert "NORMALIZED_SAMPLE" in s
    assert "FINAL_SAMPLE" in s
    assert "per_bar_lt10_x100" in s


def test_parse_rejects_close_out_of_band(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_IDEAL_PARSE_STRICT", "0")
    # Per-bar: raw < 10 → ×100; 0.08 → 8.0 still outside (10, 10000)
    b = pack_bar(1, 0.08, 0.09, 0.07, 0.08, 1.0)
    bars = parse_ideal_01_bytes(b, "X")
    assert len(bars) == 0


def test_read_new_raises_parse_failed_when_under_50_bars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BIST_IDEAL_PARSE_STRICT", "1")
    buf = bytearray()
    for i in range(40):
        c_raw = 120.0 + float(i) * 0.1
        buf.extend(
            pack_bar(
                1000 + i,
                c_raw - 0.1,
                c_raw + 0.1,
                c_raw - 0.2,
                c_raw,
                float(i),
            )
        )
    p = tmp_path / "IMKBH'X.01"
    p.write_bytes(bytes(buf))
    feed = IdealDataFeed(str(tmp_path))
    with pytest.raises(Exception, match="PARSE_FAILED"):
        feed.read_new("X")


def test_ideal_feed_rejects_path_with_data_segment(tmp_path: Path) -> None:
    bad = tmp_path / "nested" / "data" / "IMKBH"
    bad.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="FORBIDDEN_IDEAL_PATH"):
        IdealDataFeed(str(bad))


def test_ideal_01_parser_real_file() -> None:
    """Requires BIST_IDEAL_DATA_PATH pointing to iDeal ChartData with IMKBH'ASELS.01."""
    import os

    base = os.environ.get("BIST_IDEAL_DATA_PATH") or os.environ.get("IDEAL_DATA_PATH") or ""
    if not base.strip():
        pytest.skip("BIST_IDEAL_DATA_PATH not set")
    p = Path(base) / "IMKBH'ASELS.01"
    if not p.exists():
        pytest.skip(f"Real file not found: {p}")
    feed = IdealDataFeed(str(base))
    bars = feed.read_new("ASELS", "01")
    assert len(bars) > 100
    assert bars[-1].close > 0
    closes = [float(b.close) for b in bars]
    unique_prices = len({round(x, 6) for x in closes})
    assert unique_prices >= 5
