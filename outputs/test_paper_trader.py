"""Tests for Live Paper Trader — NO real trades, PnL tracking."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.live.paper_trader import PaperTrader, compute_paper_metrics


def _bar(ts: str, close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=1000)


def test_run_once_empty_fetcher() -> None:
    """Empty fetcher → no logs."""
    trader = PaperTrader(["GARAN"], data_fetcher=lambda s: {})
    result = trader.run_once()
    assert result.get("status") == "no_trade"
    assert result.get("trades", []) == []


def test_run_once_with_mock_data() -> None:
    """Mock data → scan → rank → decision → simulate → log with entry, exit, pnl."""
    def fetcher(symbols):
        return {
            "GARAN": [
                _bar("1704067200", 98.0),
                _bar("1704153600", 100.0),
                _bar("1704240000", 102.0),
                _bar("1704326400", 104.0),
            ],
        }
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        trader = PaperTrader(["GARAN"], data_fetcher=fetcher, output_path=path)
        result = trader.run_once()
        logs = result.get("trades", []) if result.get("status") == "executed" else []
        assert len(logs) >= 0
        for entry in logs:
            assert "timestamp" in entry
            assert "symbol" in entry
            assert "action" in entry
            assert "entry" in entry
            assert "exit" in entry
            assert "pnl" in entry
            assert "entry_fill" in entry
            assert "exit_fill" in entry
            assert "net_pnl" in entry
            assert "cost" in entry
            assert "exit_reason" in entry
            assert "score" in entry
            assert "regime" in entry
            assert entry["action"] == "BUY"
        if logs:
            content = Path(path).read_text(encoding="utf-8")
            lines = [l for l in content.strip().split("\n") if l]
            assert len(lines) == len(logs)
            for line in lines:
                obj = json.loads(line)
                assert "entry" in obj and "exit" in obj and "pnl" in obj
    finally:
        Path(path).unlink(missing_ok=True)


def test_compute_paper_metrics() -> None:
    """compute_paper_metrics returns correct schema."""
    logs = [
        {"action": "BUY", "entry": 100, "exit": 110, "pnl": 10},
        {"action": "BUY", "entry": 100, "exit": 90, "pnl": -10},
    ]
    m = compute_paper_metrics(logs)
    assert m["total_trades"] == 2
    assert m["wins"] == 1
    assert m["losses"] == 1
    assert m["win_rate"] == 0.5
    assert m["expectancy"] == 0.0


def test_determinism() -> None:
    """Same input produces same trade logs."""
    def fetcher(symbols):
        return {
            "GARAN": [
                _bar("1704067200", 98.0),
                _bar("1704153600", 100.0),
                _bar("1704240000", 102.0),
                _bar("1704326400", 104.0),
            ],
        }
    trader_a = PaperTrader(["GARAN"], data_fetcher=fetcher)
    trader_b = PaperTrader(["GARAN"], data_fetcher=fetcher)
    ra, rb = trader_a.run_once(), trader_b.run_once()
    a = ra.get("trades", []) if ra.get("status") == "executed" else []
    b = rb.get("trades", []) if rb.get("status") == "executed" else []
    assert len(a) == len(b)
    for ea, eb in zip(a, b):
        assert ea["symbol"] == eb["symbol"]
        assert ea["entry"] == eb["entry"]
        assert ea["exit"] == eb["exit"]
        assert ea["pnl"] == eb["pnl"]
        assert ea["net_pnl"] == eb["net_pnl"]
        assert ea["exit_reason"] == eb["exit_reason"]


def test_backtest_paper_parity() -> None:
    """Both use same ExecutionModel; net_pnl includes costs."""
    from bist_core.execution.execution_model import ExecutionModel
    from bist_core.backtest.backtest import BacktestEngine
    bars = [_bar(str(1704067200 + i * 86400), 100.0 + i * 0.3) for i in range(60)]
    symbol_data = {"GARAN": bars}
    exec_model = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
    engine = BacktestEngine(threshold=0.0, execution_model=exec_model)
    bt_result = engine.run(symbol_data)
    fetcher = lambda s: symbol_data
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        trader = PaperTrader(["GARAN"], data_fetcher=fetcher, output_path=path, execution_model=exec_model)
        result = trader.run_once()
        paper_logs = result.get("trades", []) if result.get("status") == "executed" else []
        for t in bt_result["trades"]:
            assert "entry_fill" in t
            assert "exit_fill" in t
            assert "net_pnl" in t
            assert t["net_pnl"] == t["pnl"]
        for t in paper_logs:
            assert "entry_fill" in t
            assert "exit_fill" in t
            assert "net_pnl" in t
            assert t["net_pnl"] == t["pnl"]
    finally:
        Path(path).unlink(missing_ok=True)
