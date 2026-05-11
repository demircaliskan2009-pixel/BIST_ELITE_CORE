"""Deterministic outer-cycle termination: STOPPED_AFTER_MAX_CYCLES + bounded bar work."""

from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from bist_core.live.live_runner import LiveRunner
from bist_core.models.ohlcv import OHLCVBar

pytestmark = pytest.mark.slow


def _bars_for_term(sym: str) -> list[OHLCVBar]:
    """60 bars, varying closes so unique_prices > 1 (not static)."""
    return [
        OHLCVBar(
            timestamp=10_000 + i,
            symbol=sym,
            open=100.0 + i * 0.01,
            high=101.0 + i * 0.01,
            low=99.0 + i * 0.01,
            close=100.0 + i * 0.02,
            volume=1000.0 + float(i),
            is_dummy=False,
        )
        for i in range(60)
    ]


def test_live_runner_deterministic_stop_after_max_cycles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BIST_LIVE_REQUIRE_FULL_PROOF", raising=False)
    monkeypatch.setenv("BIST_LIVE_VALIDATION_MODE", "true")
    monkeypatch.setenv("BIST_ADAPTIVE_MODE", "0")
    monkeypatch.setenv("BIST_IDEAL_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("BIST_LIVE_BARS_PER_SYMBOL_PER_CYCLE", "1")
    r = LiveRunner(poll_seconds=0.0, symbols=["ASELS"])
    monkeypatch.setattr(r.feed, "read_new", lambda s: _bars_for_term(s))
    buf = io.StringIO()
    with redirect_stdout(buf):
        r.run(max_cycles=5)
    out = buf.getvalue()
    assert "STOPPED_AFTER_MAX_CYCLES" in out
    assert re.search(r"['\"]cycles['\"]\s*:\s*5", out)
    assert re.search(r"['\"]status['\"]\s*:\s*['\"]STOPPED_AFTER_MAX_CYCLES['\"]", out)
    assert "SIMULATION_SUMMARY" in out
    assert "SYSTEM_STATUS_REPORT" in out
