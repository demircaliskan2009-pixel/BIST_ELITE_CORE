"""Live paper modules — deterministic, no network."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

from bist_core.live.data_feed import IdealDataFeed
from bist_core.live.execution_runtime import PaperExecution
from bist_core.live.health import get_health
from bist_core.live.state_store import LiveState


def _encode_bar_32(ts: int, close_tl: float, vol: float = 1000.0) -> bytes:
    """Locked ``<iffffffi``; ``close_tl`` is on-disk float (TL-scale, normalized with ÷divisor)."""
    c_raw = float(close_tl)
    return struct.pack(
        "<iffffffi",
        int(ts),
        c_raw - 0.5,
        c_raw + 0.5,
        c_raw - 1.0,
        c_raw,
        float(vol),
        0.0,
        int(0),
    )


def test_ideal_data_feed_full_snapshot_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each read_new reloads full file; strict increasing ts required per record."""
    monkeypatch.setenv("BIST_IDEAL_PARSE_STRICT", "0")
    monkeypatch.setenv("BIST_IDEAL_MARKET_SEAL", "0")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        p = base / "IMKBH'X.01"
        p.write_bytes(_encode_bar_32(1, 256.93) + _encode_bar_32(2, 256.93))

        feed = IdealDataFeed(str(base))
        first = feed.read_new("X")
        assert len(first) == 2
        assert first[0].close == pytest.approx(256.93)

        second = feed.read_new("X")
        assert len(second) == 2
        assert second[-1].close == pytest.approx(first[-1].close)

        with open(p, "ab") as wf:
            wf.write(_encode_bar_32(3, 100.0))
        third = feed.read_new("X")
        assert len(third) == 3
        assert third[-1].close == pytest.approx(100.0)


def test_paper_execution_enter_exit() -> None:
    st = LiveState()
    px = PaperExecution(st)
    px.execute("ASELS", "enter", 100.0, edge_score=0.65)
    assert len(st.positions["ASELS"]) == 1
    px.execute("ASELS", "exit", 110.0)
    assert st.positions["ASELS"] == []
    assert st.equity > 1.0


def test_get_health() -> None:
    st = LiveState()
    st.equity = 1.1
    h = get_health(st)
    assert h["equity"] == 1.1
    assert h["daily_pnl"] == 0.0
    assert "errors" in h
    assert "open_positions" in h


def test_live_state_save_load_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "st.json"
        st = LiveState()
        st.equity = 1.2
        st.last_bar_id["X"] = "0|100.0"
        st.save(p)
        st2 = LiveState.load(p)
        assert st2.equity == 1.2
        assert st2.last_bar_id["X"] == "0|100.0"


def test_feed_snapshot_has_no_offsets_roundtrip() -> None:
    """Full snapshot feed does not persist byte offsets; save/load are no-ops."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        p = base / "off.json"
        f = IdealDataFeed(str(base))
        f.save_offsets(p)
        g = IdealDataFeed(str(base))
        g.load_offsets(p)
        assert f.to_jsonable() == {}
        assert g.to_jsonable() == {}


def test_duplicate_enter_skipped_after_first_leg() -> None:
    st = LiveState()
    px = PaperExecution(st)
    r1 = px.execute(
        "A",
        "enter",
        10.0,
        volatility=0.02,
        volume_proxy=50_000.0,
        size_fraction=0.2,
        edge_score=0.65,
    )
    assert r1 is not None
    r2 = px.execute(
        "A",
        "enter",
        10.0,
        volatility=0.02,
        volume_proxy=50_000.0,
        size_fraction=0.2,
        edge_score=0.65,
    )
    assert r2 is None
    assert len(st.positions["A"]) == 1
