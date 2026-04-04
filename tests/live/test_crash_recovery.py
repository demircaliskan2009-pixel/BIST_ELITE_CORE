"""Tests for crash recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.live.paper_trader import PaperTrader
from bist_core.live.state import load_state


def test_crash_recovery(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime_state.json"
    output_path = tmp_path / "trades.jsonl"
    equity_path = tmp_path / "equity.jsonl"

    def failing_fetcher(symbols):
        return {}

    trader = PaperTrader(
        ["X"],
        data_fetcher=failing_fetcher,
        output_path=output_path,
        equity_path=equity_path,
        state_path=state_path,
    )
    result = trader.run_once()
    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert isinstance(result.get("results"), list)
    assert len(result["results"]) == 0
    s = load_state(state_path)
    assert "equity" in s
    assert "last_run_ts" in s
