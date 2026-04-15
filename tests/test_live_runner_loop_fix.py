"""Main-loop termination: cycle_count and break target the single outer while True."""

from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from bist_core.live.live_runner import LiveRunner
from bist_core.models.ohlcv import OHLCVBar

pytestmark = pytest.mark.slow


def _dummy_bars(sym: str) -> list[OHLCVBar]:
    return [
        OHLCVBar(
            timestamp=1000 + i,
            symbol=sym,
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=1000.0,
            is_dummy=True,
        )
        for i in range(60)
    ]


def test_main_loop_exits_after_max_cycles_with_cycle_debug_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BIST_LIVE_REQUIRE_FULL_PROOF", raising=False)
    monkeypatch.setenv("BIST_LIVE_VALIDATION_MODE", "true")
    monkeypatch.setenv("BIST_LIVE_MAX_CYCLES", "3")
    monkeypatch.setenv("BIST_ADAPTIVE_MODE", "0")
    monkeypatch.setenv("BIST_IDEAL_DATA_PATH", str(tmp_path))
    r = LiveRunner(poll_seconds=0.0, symbols=["ASELS"])
    monkeypatch.setattr(r.feed, "read_new", lambda s: _dummy_bars(s))
    buf = io.StringIO()
    with redirect_stdout(buf):
        r.run()
    out = buf.getvalue()
    cycle_lines = re.findall(r"\{['\"]cycle['\"]:\s*(\d+)", out)
    assert cycle_lines == ["1", "2", "3"], cycle_lines
    assert "STOPPED_AFTER_MAX_CYCLES" in out
    assert "'status'" in out or '"status"' in out
