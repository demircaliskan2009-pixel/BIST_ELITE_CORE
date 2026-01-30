"""
FAZ48: Deterministic portfolio ledger (fills -> positions/cash/PnL) + fees/slippage.
Test with fixed prices/fills verifying exact outputs.
"""
from __future__ import annotations

import pytest

from bist_core.services.portfolio_ledger import PortfolioLedger


def test_faz48_ledger_buy_sell_no_fees_exact() -> None:
    """Fixed fills: buy then sell at same price; no fee/slippage => exact cash/equity/realized_pnl."""
    ledger = PortfolioLedger(initial_cash=1000.0, fee_bps=0.0, slippage_bps=0.0)
    # Buy 10 @ 50 = 500
    ledger.apply_fill({
        "symbol": "A",
        "side": "BUY",
        "signed_qty": 10.0,
        "price": 50.0,
        "notional": 500.0,
        "day": "2024-01-01",
    })
    assert ledger.cash() == 500.0
    assert ledger.equity({"A": 50.0}) == 1000.0
    assert ledger.realized_pnl() == 0.0
    assert ledger.unrealized_pnl({"A": 50.0}) == 0.0
    assert ledger.turnover() == 500.0
    # Sell 10 @ 50 = 500
    ledger.apply_fill({
        "symbol": "A",
        "side": "SELL",
        "signed_qty": -10.0,
        "price": 50.0,
        "notional": 500.0,
        "day": "2024-01-02",
    })
    assert ledger.cash() == 1000.0
    assert ledger.equity({}) == 1000.0
    assert ledger.realized_pnl() == 0.0
    assert ledger.turnover() == 1000.0
    assert len(ledger.positions()) == 0


def test_faz48_ledger_fee_bps_exact() -> None:
    """fee_bps=10 (0.1%): buy 500 => fee 0.5; cash drops by 500.5."""
    ledger = PortfolioLedger(initial_cash=1000.0, fee_bps=10.0, slippage_bps=0.0)
    ledger.apply_fill({
        "symbol": "B",
        "side": "BUY",
        "signed_qty": 10.0,
        "price": 50.0,
        "notional": 500.0,
        "day": "2024-01-01",
    })
    # notional_eff = 500, fee = 500 * 10/10000 = 0.5, cash = 1000 - 500 - 0.5 = 499.5
    assert ledger.cash() == 499.5
    assert ledger.turnover() == 500.0
    # Sell: notional_eff = 500, fee = 0.5, cash += 500 - 0.5 = 499.5; cost_basis 500.5, realized = 499.5 - 500.5 = -1.0
    ledger.apply_fill({
        "symbol": "B",
        "side": "SELL",
        "signed_qty": -10.0,
        "price": 50.0,
        "notional": 500.0,
        "day": "2024-01-02",
    })
    assert ledger.cash() == 999.0  # 499.5 + 499.5
    assert ledger.realized_pnl() == -1.0  # two fees 0.5+0.5


def test_faz48_ledger_slippage_bps_exact() -> None:
    """slippage_bps=20 (0.2%): buy pays 1.002 * notional; sell receives 0.998 * notional."""
    ledger = PortfolioLedger(initial_cash=1000.0, fee_bps=0.0, slippage_bps=20.0)
    ledger.apply_fill({
        "symbol": "C",
        "side": "BUY",
        "signed_qty": 10.0,
        "price": 50.0,
        "notional": 500.0,
        "day": "2024-01-01",
    })
    # notional_eff = 500 * 1.002 = 501.0, cash = 1000 - 501 = 499.0
    assert ledger.cash() == 499.0
    assert ledger.turnover() == 501.0
    ledger.apply_fill({
        "symbol": "C",
        "side": "SELL",
        "signed_qty": -10.0,
        "price": 50.0,
        "notional": 500.0,
        "day": "2024-01-02",
    })
    # notional_eff = 500 * 0.998 = 499.0, cash += 499 => 499 + 499 = 998; cost_basis 501, realized = 499 - 501 = -2
    assert ledger.cash() == 998.0
    assert ledger.realized_pnl() == -2.0


def test_faz48_ledger_unrealized_pnl_exact() -> None:
    """Buy 10 @ 50; mark 60 => unrealized = 10 * (60 - 50) = 100."""
    ledger = PortfolioLedger(initial_cash=1000.0, fee_bps=0.0, slippage_bps=0.0)
    ledger.apply_fill({
        "symbol": "D",
        "side": "BUY",
        "signed_qty": 10.0,
        "price": 50.0,
        "notional": 500.0,
        "day": "2024-01-01",
    })
    assert ledger.unrealized_pnl({"D": 60.0}) == 100.0
    assert ledger.equity({"D": 60.0}) == 1100.0  # 500 cash + 10*60


def test_faz48_ledger_equity_turnover_exact() -> None:
    """Multiple fills; assert equity and turnover exact."""
    ledger = PortfolioLedger(initial_cash=2000.0, fee_bps=0.0, slippage_bps=0.0)
    ledger.apply_fill({"symbol": "X", "side": "BUY", "signed_qty": 5.0, "notional": 100.0, "day": "2024-01-01"})
    ledger.apply_fill({"symbol": "Y", "side": "BUY", "signed_qty": 10.0, "notional": 200.0, "day": "2024-01-01"})
    assert ledger.cash() == 1700.0
    assert ledger.turnover() == 300.0
    assert ledger.equity({"X": 20.0, "Y": 20.0}) == 1700.0 + 100.0 + 200.0  # 2000
    assert ledger.realized_pnl() == 0.0
