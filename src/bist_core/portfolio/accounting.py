"""
FAZ55: Deterministic portfolio accounting core.
Apply fills -> positions/cash; compute realized/unrealized PnL; fee+slippage model (configurable, deterministic).
Rounding: 6 decimals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def round6(x: float) -> float:
    """Deterministic round to 6 decimals."""
    return round(float(x), 6)


def effective_notional(notional: float, side: str, slippage_bps: float) -> float:
    """Notional after slippage: buy pays more, sell receives less."""
    n = float(notional)
    bps = float(slippage_bps) / 10000.0
    if str(side).upper() == "BUY":
        return round6(n * (1.0 + bps))
    return round6(n * (1.0 - bps))


def fee_amount(notional_eff: float, fee_bps: float) -> float:
    """Fee from effective notional (fee_bps in basis points)."""
    return round6(abs(float(notional_eff)) * (float(fee_bps) / 10000.0))


def create_initial_state(initial_cash: float = 0.0) -> Dict[str, Any]:
    """State: cash, positions {sym: {qty, cost_basis}}, realized_pnl, turnover."""
    return {
        "cash": round6(float(initial_cash)),
        "positions": {},
        "realized_pnl": 0.0,
        "turnover": 0.0,
    }


def apply_fill(
    state: Dict[str, Any],
    fill: Dict[str, Any],
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> None:
    """
    Apply one fill to state (mutates). Deterministic.
    fill: symbol, side (BUY/SELL), signed_qty or qty, price, notional (optional).
    """
    sym = (fill.get("symbol") or "").strip()
    if not sym:
        return
    side = str(fill.get("side", "BUY")).upper()
    signed_qty = fill.get("signed_qty")
    if signed_qty is None:
        qty = fill.get("qty", 0.0)
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            return
        signed_qty = -qty if side == "SELL" else qty
    try:
        signed_qty = float(signed_qty)
    except (TypeError, ValueError):
        return
    notional = fill.get("notional")
    if notional is None:
        price = fill.get("price")
        if price is not None:
            notional = abs(signed_qty) * float(price)
        else:
            return
    try:
        notional = float(notional)
    except (TypeError, ValueError):
        return
    if signed_qty == 0:
        return

    notional_eff = effective_notional(notional, side, slippage_bps)
    fee = fee_amount(notional_eff, fee_bps)
    state["turnover"] = round6(state["turnover"] + abs(notional_eff))
    positions = state["positions"]
    pos = positions.setdefault(sym, {"qty": 0.0, "cost_basis": 0.0})

    if side == "BUY":
        state["cash"] = round6(state["cash"] - notional_eff - fee)
        pos["qty"] = round6(pos["qty"] + signed_qty)
        pos["cost_basis"] = round6(pos["cost_basis"] + notional_eff + fee)
    else:
        qty_total = pos["qty"]
        if qty_total <= 0:
            return
        cost_total = pos["cost_basis"]
        qty_sold = min(abs(signed_qty), qty_total)
        cost_of_sold = round6(cost_total * (qty_sold / qty_total)) if qty_total else 0.0
        state["cash"] = round6(state["cash"] + notional_eff - fee)
        state["realized_pnl"] = round6(state["realized_pnl"] + (notional_eff - fee) - cost_of_sold)
        pos["qty"] = round6(pos["qty"] - qty_sold)
        pos["cost_basis"] = round6(pos["cost_basis"] - cost_of_sold)


def apply_fills(
    state: Dict[str, Any],
    fills: List[Dict[str, Any]],
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    sort_key: Optional[tuple] = None,
) -> None:
    """Apply fills in order. If sort_key e.g. ('day','symbol'), sort for determinism."""
    if sort_key:
        fills = sorted(fills, key=lambda f: (f.get(sort_key[0], ""), f.get(sort_key[1], "")))
    for f in fills:
        apply_fill(state, f, fee_bps=fee_bps, slippage_bps=slippage_bps)


def compute_unrealized_pnl(state: Dict[str, Any], mark_prices: Dict[str, float]) -> float:
    """Sum (mark_price - avg_cost) * qty for each position. Deterministic."""
    total = 0.0
    for sym in sorted(state["positions"].keys()):
        p = state["positions"][sym]
        qty = p["qty"]
        if qty == 0:
            continue
        avg_cost = p["cost_basis"] / qty
        mark = mark_prices.get(sym, avg_cost)
        total += (float(mark) - avg_cost) * qty
    return round6(total)


def equity(
    state: Dict[str, Any],
    mark_prices: Optional[Dict[str, float]] = None,
) -> float:
    """Cash + sum(qty * mark_price). If mark_prices None, use cost_basis."""
    total = state["cash"]
    for sym in sorted(state["positions"].keys()):
        p = state["positions"][sym]
        qty = p["qty"]
        if mark_prices and sym in mark_prices:
            total += qty * float(mark_prices[sym])
        else:
            total += p["cost_basis"]
    return round6(total)


class Ledger:
    """
    Stateful wrapper over accounting state. Same API as services.portfolio_ledger.PortfolioLedger
    for minimal backtest integration. Deterministic: fee_bps + slippage_bps configurable; round 6 decimals.
    """

    def __init__(
        self,
        initial_cash: float = 0.0,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
    ) -> None:
        self._state = create_initial_state(initial_cash)
        self._fee_bps = float(fee_bps)
        self._slippage_bps = float(slippage_bps)

    def apply_fill(self, fill: Dict[str, Any]) -> None:
        apply_fill(self._state, fill, fee_bps=self._fee_bps, slippage_bps=self._slippage_bps)

    def apply_fills(
        self,
        fills: List[Dict[str, Any]],
        sort_key: Optional[tuple] = None,
    ) -> None:
        apply_fills(
            self._state,
            fills,
            fee_bps=self._fee_bps,
            slippage_bps=self._slippage_bps,
            sort_key=sort_key,
        )

    def cash(self) -> float:
        return self._state["cash"]

    def positions(self) -> List[Dict[str, Any]]:
        """List of {symbol, qty, cost_basis} for non-zero positions (sorted by symbol)."""
        out = []
        for sym in sorted(self._state["positions"].keys()):
            p = self._state["positions"][sym]
            if p["qty"] != 0:
                out.append({"symbol": sym, "qty": p["qty"], "cost_basis": p["cost_basis"]})
        return out

    def realized_pnl(self) -> float:
        return round6(self._state["realized_pnl"])

    def unrealized_pnl(self, mark_prices: Dict[str, float]) -> float:
        return compute_unrealized_pnl(self._state, mark_prices)

    def equity(self, mark_prices: Optional[Dict[str, float]] = None) -> float:
        return equity(self._state, mark_prices)

    def turnover(self) -> float:
        return self._state["turnover"]
