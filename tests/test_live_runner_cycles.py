"""Hard cycle cap and validation emission for live_runner.run()."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from bist_core.models.ohlcv import OHLCVBar

from bist_core.live.live_runner import LiveRunner


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


def test_live_runner_stops_after_env_max_cycles_emits_simulation_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BIST_LIVE_REQUIRE_FULL_PROOF", raising=False)
    monkeypatch.setenv("BIST_LIVE_VALIDATION_MODE", "true")
    monkeypatch.setenv("BIST_LIVE_MAX_CYCLES", "5")
    monkeypatch.setenv("BIST_ADAPTIVE_MODE", "0")
    monkeypatch.setenv("BIST_IDEAL_DATA_PATH", str(tmp_path))
    r = LiveRunner(poll_seconds=0.0, symbols=["ASELS"])
    monkeypatch.setattr(r.feed, "read_new", lambda s: _dummy_bars(s))
    buf = io.StringIO()
    with redirect_stdout(buf):
        r.run()
    out = buf.getvalue()
    assert "STOPPED_AFTER_MAX_CYCLES" in out
    assert "SIMULATION_SUMMARY" in out
    found = None
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "SIMULATION_SUMMARY" in obj:
            found = obj["SIMULATION_SUMMARY"]
            break
    assert found is not None
    assert found.get("total_cycles") == 5
