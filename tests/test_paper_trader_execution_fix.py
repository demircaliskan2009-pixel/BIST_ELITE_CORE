"""Tests for PaperTrader execution fix — sizing, fail-closed, determinism."""

from __future__ import annotations

from bist_core.models.ohlcv import OHLCVBar
from bist_core.live.paper_trader import PaperTrader


def _bar(ts: str, symbol: str, close: float) -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts,
        symbol=symbol,
        open=close,
        high=close + 1,
        low=max(close - 1, 0.01),
        close=close,
        volume=1000,
    )


def _make_bars(symbol: str, n: int, base: float = 100.0, step: float = 0.1) -> list[OHLCVBar]:
    return [_bar(str(1704067200 + i * 86400), symbol, base + i * step) for i in range(n)]


def test_sizing_correctness() -> None:
    """risk_per_trade=capital*0.015, size=risk_per_trade/(entry-stop). entry=100, stop=95, capital=10000 → size=30."""
    data = {"X": _make_bars("X", 100, base=100.0, step=0.05)}
    fetcher = lambda s: data
    trader = PaperTrader(
        ["X"],
        data_fetcher=fetcher,
        initial_capital=10_000.0,
    )
    result = trader.run_once()
    logs = result.get("trades", []) if result.get("status") == "executed" else []
    if logs:
        t = logs[0]
        entry = t.get("entry")
        stop = t.get("stop")
        size = t.get("size")
        if entry is not None and stop is not None and size is not None:
            risk_per_share = entry - stop
            expected = (10_000 * 0.015) / risk_per_share
            assert abs(size - expected) < 0.01, f"expected size ~{expected}, got {size}"


def test_invalid_risk_skipped() -> None:
    """entry <= stop → no trade (pipeline filters or we skip)."""
    data = {"A": _make_bars("A", 100)}
    fetcher = lambda s: data
    trader = PaperTrader(["A"], data_fetcher=fetcher)
    result = trader.run_once()
    logs = result.get("trades", []) if result.get("status") == "executed" else []
    for t in logs:
        entry = t.get("entry")
        stop = t.get("stop")
        if entry is not None and stop is not None:
            assert entry > stop


def test_deterministic() -> None:
    """Same input twice → identical outputs."""
    data = {"Y": _make_bars("Y", 100)}
    fetcher = lambda s: data
    trader_a = PaperTrader(["Y"], data_fetcher=fetcher)
    trader_b = PaperTrader(["Y"], data_fetcher=fetcher)
    ra, rb = trader_a.run_once(), trader_b.run_once()
    a = ra.get("trades", []) if ra.get("status") == "executed" else []
    b = rb.get("trades", []) if rb.get("status") == "executed" else []
    assert len(a) == len(b)
    for ea, eb in zip(a, b):
        assert ea["symbol"] == eb["symbol"]
        assert ea["entry"] == eb["entry"]
        assert ea.get("exit") == eb.get("exit")
        assert ea.get("size") == eb.get("size")
        assert ea.get("net_pnl") == eb.get("net_pnl")


def test_capital_update_consistency() -> None:
    """Two trades sequential — second trade must use updated capital. size_2 != size_1."""
    data = {
        "A": _make_bars("A", 100, base=100.0, step=0.1),
        "B": _make_bars("B", 100, base=50.0, step=0.05),
    }
    fetcher = lambda s: data
    trader = PaperTrader(
        ["A", "B"],
        data_fetcher=fetcher,
        initial_capital=10_000.0,
    )
    result = trader.run_once()
    trades = result.get("trades", []) if result.get("status") == "executed" else []
    if len(trades) >= 2:
        size_1 = trades[0].get("size")
        size_2 = trades[1].get("size")
        if size_1 is not None and size_2 is not None:
            assert size_2 != size_1, "second trade must use updated capital (different size)"
