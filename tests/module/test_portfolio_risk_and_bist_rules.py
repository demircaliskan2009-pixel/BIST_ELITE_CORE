"""PortfolioRiskEngine + BISTRules — deterministic gates."""

from __future__ import annotations

from bist_core.models.ohlcv import OHLCVBar
from bist_core.risk.bist_rules import BISTRules
from bist_core.risk.portfolio_risk_engine import PortfolioRiskEngine


def test_portfolio_exposure_never_exceeds_limits() -> None:
    eng = PortfolioRiskEngine()
    ok, _ = eng.validate(
        [{"symbol": "A", "weight": 0.2}, {"symbol": "B", "weight": 0.2}],
        equity=100_000.0,
        peak_equity=100_000.0,
    )
    assert ok is True
    bad, r = eng.validate(
        [{"symbol": "A", "weight": 0.30}],
        equity=100_000.0,
        peak_equity=100_000.0,
    )
    assert bad is False
    assert r == "max_symbol_exposure_breached"


def test_drawdown_triggers_block() -> None:
    eng = PortfolioRiskEngine()
    ok, _ = eng.validate([{"symbol": "A", "weight": 0.1}], equity=84.0, peak_equity=100.0)
    assert ok is False
    _, reason = eng.validate([{"symbol": "A", "weight": 0.1}], equity=84.0, peak_equity=100.0)
    assert reason == "max_drawdown_breached"


def test_bist_illiquid_filtered() -> None:
    r = BISTRules()
    bars = [
        OHLCVBar(
            timestamp=i,
            symbol="X",
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.0,
            volume=100.0,
        )
        for i in range(5)
    ]
    assert r.is_liquid(bars) is False


def test_bist_price_and_band() -> None:
    r = BISTRules()
    assert r.is_price_valid(1.0) is True
    assert r.is_price_valid(0.5) is False
    assert r.is_trade_allowed(10.0, 10.0) is True
    assert r.is_trade_allowed(20.0, 10.0) is False
