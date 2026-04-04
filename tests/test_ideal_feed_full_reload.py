"""IdealDataFeed full-file snapshot (no incremental offsets)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from bist_core.live.data_feed import IdealDataFeed
from bist_core.live.live_runner import LiveRunner


def _pack(
    ts: int,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float,
    extra: float = 0.0,
    flag: int = 0,
) -> bytes:
    return struct.pack("<iffffffi", ts, o, h, l, c, v, extra, flag)


def test_full_reload_returns_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_IDEAL_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("BIST_IDEAL_MARKET_SEAL", "0")
    buf = bytearray()
    for i in range(55):
        ts = 1_000_000_000 + i * 60
        c = 300.0 + i * 0.1
        buf.extend(_pack(ts, c - 0.1, c + 0.1, c - 0.2, c, 1000.0 + i))
    (tmp_path / "IMKBH'ASELS.01").write_bytes(bytes(buf))

    r = LiveRunner(poll_seconds=0.0, symbols=["ASELS"])
    bars = r.feed.read_new("ASELS")

    assert bars is not None
    assert len(bars) > 50
