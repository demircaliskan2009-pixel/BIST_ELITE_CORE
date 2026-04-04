"""Tests for Live Paper Trader — NO real trades, PnL tracking."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.live.paper_trader import PaperTrader, compute_paper_metrics


class _PermissiveBistRules:
    """Tests focus on decision path; BIST microstructure gates are bypassed."""

    def is_price_valid(self, price: float) -> bool:
        return True

    def is_liquid(self, bars) -> bool:
        return True

    def is_trade_allowed(self, price: float, prev_close: float) -> bool:
        return True


def _bar(ts: int, close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(
        timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=1_500_000
    )


def test_run_once_empty_fetcher() -> None:
    """No valid prices → empty results."""
    trader = PaperTrader(["GARAN"], data_fetcher=lambda s: {})
    result = trader.run_once()
    assert result.get("status") == "ok"
    assert isinstance(result.get("results"), list)


def test_run_once_with_mock_data() -> None:
    """Mock price + decision_engine → live loop → results."""
    import bist_core.live.paper_trader as pt_mod
    orig = pt_mod.get_current_price
    pt_mod.get_current_price = lambda s: 100.0 if s == "GARAN" else None
    try:
        class DE:
            def evaluate_symbol(self, ctx):
                return {"action": "enter", "reason": "test"}
        trader = PaperTrader(["GARAN"], bist_rules=_PermissiveBistRules())
        trader.decision_engine = DE()
        result = trader.run_once()
        assert result.get("status") == "ok"
        results = result.get("results", [])
        assert len(results) >= 1
        r = results[0]
        assert r.get("symbol") == "GARAN"
        assert r.get("price") == 100.0
        assert r.get("action") == "enter"
        assert "position" in r
        assert "pnl" in r
    finally:
        pt_mod.get_current_price = orig


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
    """Same price + decision produces same results."""
    import bist_core.live.paper_trader as pt_mod
    orig = pt_mod.get_current_price
    pt_mod.get_current_price = lambda s: 100.0 if s == "GARAN" else None
    try:
        class DE:
            def evaluate_symbol(self, ctx):
                return {"action": "enter", "reason": "test"}
        trader_a = PaperTrader(["GARAN"], bist_rules=_PermissiveBistRules())
        trader_a.decision_engine = DE()
        trader_b = PaperTrader(["GARAN"], bist_rules=_PermissiveBistRules())
        trader_b.decision_engine = DE()
        ra, rb = trader_a.run_once(), trader_b.run_once()
        a = ra.get("results", [])
        b = rb.get("results", [])
        assert len(a) == len(b)
        for ea, eb in zip(a, b):
            assert ea["symbol"] == eb["symbol"]
            assert ea["price"] == eb["price"]
            assert ea["pnl"] == eb["pnl"]
    finally:
        pt_mod.get_current_price = orig


def test_decision_engine_execution() -> None:
    """Decision-engine path: evaluate_symbol(context) → enter/hold/exit."""
    import bist_core.live.paper_trader as pt_mod
    orig = pt_mod.get_current_price
    pt_mod.get_current_price = lambda s: 10.0 if s == "GARAN" else None
    try:
        class DE:
            def evaluate_symbol(self, ctx):
                # High confidence so live ExecutionEngine try_fill can pass without artificial floors.
                return {"action": "enter", "reason": "test", "confidence": 1.0}
        pt = PaperTrader(["GARAN"], bist_rules=_PermissiveBistRules())
        # (high-low)*close proxy must exceed PaperTrader floor; range% must stay ≤10%.
        liq_bars = [
            OHLCVBar(
                timestamp=1704067200 + i * 86400,
                symbol="X",
                open=100_000.0,
                high=100_020.0,
                low=99_985.0,
                close=100_000.0,
                volume=1_500_000,
            )
            for i in range(60)
        ]
        pt._replay_feed = {"GARAN": {"current_price": 10.0, "bars": liq_bars}}
        pt.decision_engine = DE()
        res = pt.run_once()
        assert res["status"] == "ok"
        results = res.get("results", [])
        assert len(results) >= 1
        r = next((x for x in results if x.get("symbol") == "GARAN"), None)
        assert r is not None
        assert r["price"] == 10.0
        assert r["action"] == "enter"
        assert r["position"] is True
    finally:
        pt_mod.get_current_price = orig


def test_decision_engine_minimal_bars_no_lookback_lock() -> None:
    """Decision-engine with hold action; position tracked."""
    import bist_core.live.paper_trader as pt_mod
    orig = pt_mod.get_current_price
    pt_mod.get_current_price = lambda s: 10.5 if s == "GARAN" else None
    try:
        class DE:
            def evaluate_symbol(self, ctx):
                return {"action": "hold", "reason": "minimal"}
        pt = PaperTrader(["GARAN"], bist_rules=_PermissiveBistRules())
        pt.decision_engine = DE()
        pt._positions["GARAN"] = {"entry_price": 10.0, "size": 1.0, "ts": 0}
        res = pt.run_once()
        assert isinstance(res, dict)
        assert res["status"] == "ok"
        results = res.get("results", [])
        r = next((x for x in results if x.get("symbol") == "GARAN"), None)
        assert r is not None
        assert r["action"] == "hold"
        assert r["position"] is True
    finally:
        pt_mod.get_current_price = orig


def test_backtest_paper_parity() -> None:
    """Backtest engine produces valid trades; paper trader uses live price loop."""
    from bist_core.execution.execution_model import ExecutionModel
    from bist_core.backtest.backtest import BacktestEngine
    bars = [_bar(1704067200 + i * 86400, 100.0 + i * 0.3) for i in range(60)]
    symbol_data = {"GARAN": bars}
    exec_model = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
    engine = BacktestEngine(threshold=0.0, execution_model=exec_model)
    bt_result = engine.run(symbol_data)
    for t in bt_result["trades"]:
        assert t.get("action") == "exit"
        assert "entry" in t
        assert "exit" in t
        assert "pnl" in t
    import bist_core.live.paper_trader as pt_mod
    orig = pt_mod.get_current_price
    pt_mod.get_current_price = lambda s: 100.0 if s == "GARAN" else None
    try:
        class DE:
            def evaluate_symbol(self, ctx):
                return {"action": "enter", "reason": "parity"}
        trader = PaperTrader(["GARAN"], execution_model=exec_model, bist_rules=_PermissiveBistRules())
        trader.decision_engine = DE()
        result = trader.run_once()
        assert result.get("status") == "ok"
        results = result.get("results", [])
        for r in results:
            assert "symbol" in r
            assert "price" in r
            assert "pnl" in r
    finally:
        pt_mod.get_current_price = orig
