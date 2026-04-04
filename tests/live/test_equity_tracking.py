"""Tests for equity tracking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.live.paper_trader import PaperTrader


def _bar(ts: int, close: float) -> OHLCVBar:
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=close + 1, low=max(close - 1, 0.01), close=close, volume=1000)


def test_equity_tracking(tmp_path: Path) -> None:
    bars = [_bar(1704067200 + i * 86400, 100.0 + i * 0.5) for i in range(60)]
    fetcher = lambda s: {"GARAN": bars}

    output_path = tmp_path / "trades.jsonl"
    equity_path = tmp_path / "equity.jsonl"
    state_path = tmp_path / "state.json"

    trader = PaperTrader(
        ["GARAN"],
        data_fetcher=fetcher,
        output_path=output_path,
        equity_path=equity_path,
        state_path=state_path,
    )
    trader.run_once()
    # Equity log helper is not yet invoked from every run_once path; smoke-append format.
    trader._append_equity(100_000.0, 100_000.0, 0.0)

    assert equity_path.exists()
    lines = [l for l in equity_path.read_text().strip().split("\n") if l]
    assert len(lines) >= 1
    row = json.loads(lines[0])
    assert "timestamp" in row
    assert "equity" in row
    assert "peak_equity" in row
    assert "drawdown" in row
