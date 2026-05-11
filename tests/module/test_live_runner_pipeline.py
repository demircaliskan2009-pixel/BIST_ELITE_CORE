"""Controlled live_runner pipeline: max_cycles, stages, qualifying action (mocked feed)."""

from __future__ import annotations

import io
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


def test_live_runner_stops_after_max_cycles_and_verifies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BIST_LIVE_REQUIRE_FULL_PROOF", raising=False)
    monkeypatch.setenv("BIST_LIVE_VALIDATION_MODE", "true")
    monkeypatch.setenv("BIST_ADAPTIVE_MODE", "0")
    monkeypatch.setenv("BIST_IDEAL_DATA_PATH", str(tmp_path))
    r = LiveRunner(poll_seconds=0.0, symbols=["ASELS"])
    monkeypatch.setattr(r.feed, "read_new", lambda s: _dummy_bars(s))
    buf = io.StringIO()
    with redirect_stdout(buf):
        r.run(max_cycles=2)
    out = buf.getvalue()
    assert "STOPPED_AFTER_MAX_CYCLES" in out
    assert "SIMULATION_SUMMARY" in out
    assert "incomplete_cycles" not in out
    assert "'stage': 'feed'" in out or '"stage": "feed"' in out
    assert "'stage': 'hardening'" in out or '"stage": "hardening"' in out
    assert "'stage': 'decision'" in out or '"stage": "decision"' in out
    assert "data_check" in out
    assert "price_variation" in out
    assert "DATA_STATUS" in out
    assert "MARKET_REALISM" in out and "RISK_METRICS" in out


def test_live_runner_raises_when_no_actions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BIST_LIVE_REQUIRE_FULL_PROOF", raising=False)
    monkeypatch.delenv("BIST_LIVE_VALIDATION_MODE", raising=False)
    monkeypatch.setenv("BIST_ADAPTIVE_MODE", "0")
    monkeypatch.setenv("BIST_IDEAL_DATA_PATH", str(tmp_path))
    monkeypatch.setattr(
        "bist_core.live.live_runner._pipeline_saw_qualifying_action",
        lambda _d: False,
    )
    r = LiveRunner(poll_seconds=0.0, symbols=["ASELS"])
    monkeypatch.setattr(r.feed, "read_new", lambda s: _dummy_bars(s))

    def _no_decision(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(r.decision, "evaluate_symbol", _no_decision)
    with pytest.raises(Exception, match="NO_ACTIONS_PRODUCED"):
        r.run(max_cycles=100)


def test_live_runner_requires_bist_ideal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BIST_IDEAL_DATA_PATH", raising=False)
    monkeypatch.delenv("IDEAL_DATA_PATH", raising=False)
    with pytest.raises(RuntimeError, match="BIST_IDEAL_DATA_PATH"):
        LiveRunner(poll_seconds=0.0, symbols=["ASELS"])
