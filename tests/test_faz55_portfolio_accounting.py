"""FAZ55: Deterministic portfolio accounting (fills -> positions/cash, realized/unrealized PnL, fee+slippage)."""

from __future__ import annotations

from bist_core.portfolio.accounting import (
    Ledger,
    create_initial_state,
    apply_fills,
    round6,
    effective_notional,
    fee_amount,
)


def test_round6_deterministic() -> None:
    """Rounding to 6 decimals is deterministic."""
    assert round6(1.23456789) == 1.234568
    assert round6(0.0) == 0.0
    assert round6(1.1111115) == 1.111112


def test_effective_notional_and_fee() -> None:
    """Slippage: buy pays more, sell receives less. Fee from effective notional."""
    assert effective_notional(100.0, "BUY", 10.0) == round6(100.0 * 1.001)
    assert effective_notional(100.0, "SELL", 10.0) == round6(100.0 * 0.999)
    assert fee_amount(100.0, 5.0) == round6(100.0 * 0.0005)


def test_apply_fill_buy_then_sell_deterministic() -> None:
    """Same fills + params => same state (determinism)."""
    fills = [
        {"symbol": "A", "side": "BUY", "qty": 10, "price": 10.0},
        {"symbol": "A", "side": "SELL", "qty": 5, "price": 12.0},
    ]
    state1 = create_initial_state(1000.0)
    state2 = create_initial_state(1000.0)
    apply_fills(state1, fills, fee_bps=0.0, slippage_bps=0.0)
    apply_fills(state2, fills, fee_bps=0.0, slippage_bps=0.0)
    assert state1["cash"] == state2["cash"]
    assert state1["realized_pnl"] == state2["realized_pnl"]
    assert state1["positions"] == state2["positions"]


def test_ledger_realized_pnl_and_rounding() -> None:
    """Ledger: buy then sell; realized PnL and positions rounded to 6 decimals."""
    ledger = Ledger(initial_cash=1000.0, fee_bps=0.0, slippage_bps=0.0)
    ledger.apply_fill({"symbol": "X", "side": "BUY", "qty": 10, "price": 10.0})
    ledger.apply_fill({"symbol": "X", "side": "SELL", "qty": 10, "price": 11.0})
    assert ledger.cash() == round6(1000.0 - 100.0 + 110.0)
    assert ledger.realized_pnl() == round6(10.0)
    assert ledger.positions() == []


def test_ledger_unrealized_pnl() -> None:
    """Unrealized PnL = sum (mark - avg_cost) * qty; deterministic."""
    ledger = Ledger(initial_cash=1000.0)
    ledger.apply_fill({"symbol": "Y", "side": "BUY", "qty": 20, "price": 5.0})
    mark_prices = {"Y": 6.0}
    u = ledger.unrealized_pnl(mark_prices)
    assert u == round6(20.0 * (6.0 - 5.0))


def test_ledger_equity_with_mark_prices() -> None:
    """Equity = cash + sum(qty * mark_price)."""
    ledger = Ledger(initial_cash=500.0)
    ledger.apply_fill({"symbol": "Z", "side": "BUY", "qty": 10, "price": 10.0})
    eq = ledger.equity({"Z": 12.0})
    assert eq == round6(500.0 - 100.0 + 10.0 * 12.0)


def test_fee_and_slippage_configurable() -> None:
    """Fee and slippage reduce cash / PnL deterministically."""
    ledger = Ledger(initial_cash=1000.0, fee_bps=10.0, slippage_bps=5.0)
    ledger.apply_fill({"symbol": "A", "side": "BUY", "qty": 10, "price": 10.0})
    notional_eff = effective_notional(100.0, "BUY", 5.0)
    fee = fee_amount(notional_eff, 10.0)
    expected_cash = round6(1000.0 - notional_eff - fee)
    assert ledger.cash() == expected_cash


def test_apply_fills_sort_key_deterministic() -> None:
    """apply_fills with sort_key yields stable order."""
    fills = [
        {"symbol": "B", "day": "2020-01-02", "side": "BUY", "qty": 1, "price": 1.0},
        {"symbol": "A", "day": "2020-01-01", "side": "BUY", "qty": 1, "price": 1.0},
    ]
    state = create_initial_state(100.0)
    apply_fills(state, fills, sort_key=("day", "symbol"))
    order_first = list(state["positions"].keys())
    state2 = create_initial_state(100.0)
    apply_fills(state2, fills, sort_key=("day", "symbol"))
    assert order_first == list(state2["positions"].keys())
    assert state["cash"] == state2["cash"]
