"""PaperExecution + MarketRealismMetrics aggregates."""

from __future__ import annotations

from bist_core.live.execution_runtime import PaperExecution
from bist_core.live.state_store import LiveState


def test_realism_metrics_on_miss_and_fill() -> None:
    st = LiveState()
    st.equity = 1.0
    pe = PaperExecution(st)
    # Below liquidity floor → process_fill misses; forced buy fill still stores position.
    r = pe.execute(
        "A",
        "enter",
        100.0,
        volatility=0.02,
        volume_proxy=10.0,
        edge_score=0.65,
    )
    assert r is not None
    assert r.get("ok") is True
    assert pe.realism_metrics.missed_trades == 0
    r2 = pe.execute(
        "B",
        "enter",
        100.0,
        volatility=0.02,
        volume_proxy=50_000.0,
        edge_score=0.65,
    )
    assert r2 is not None
    s = pe.realism_metrics.summary()
    assert "fill_attempts" in s
    assert int(s["fill_attempts"]) >= 2
    assert int(s["fills_ok"]) + int(s["missed_trades"]) == int(s["fill_attempts"])
    assert "fill_success_rate" in s
    assert "avg_slippage_fraction" in s
    assert "missed_trades" in s


def test_enter_clamps_size_to_max_symbol_fraction() -> None:
    """size_fraction=1.0 with max_symbol_fraction=0.30 must not reject before paper fill (PRDV3 risk cap)."""
    st = LiveState()
    st.equity = 100_000.0
    pe = PaperExecution(st)
    pe.configure_risk(
        max_total_positions=5,
        max_symbol_fraction=0.30,
        daily_loss_limit=-1.0,
    )
    r = pe.execute(
        "ASELS",
        "enter",
        350.0,
        volatility=0.02,
        volume_proxy=50_000.0,
        size_fraction=1.0,
        edge_score=0.65,
    )
    assert r is not None
    assert r.get("ok") is True
