"""
FAZ48: Deterministic portfolio ledger (fills -> positions/cash/PnL) + fees/slippage.
Supports buy/sell fills with fee_bps + slippage_bps. Metrics: realized_pnl, unrealized_pnl, equity, turnover.
Deterministic: apply fills in stable order; round to 6 decimals.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _round6(x: float) -> float:
    return round(x, 6)


def _effective_notional(notional: float, side: str, slippage_bps: float) -> float:
    """Notional after slippage: buy pays more, sell receives less."""
    if side.upper() == "BUY":
        return _round6(notional * (1.0 + slippage_bps / 10000.0))
    return _round6(notional * (1.0 - slippage_bps / 10000.0))


def _fee(notional_eff: float, fee_bps: float) -> float:
    return _round6(abs(notional_eff) * (fee_bps / 10000.0))


class PortfolioLedger:
    """
    Ledger: apply fills with fee_bps and slippage_bps; track positions, cash, realized/unrealized PnL, turnover.
    Deterministic: process fills in given order; round to 6 decimals.
    """

    def __init__(
        self,
        initial_cash: float = 0.0,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
    ) -> None:
        self._cash = _round6(float(initial_cash))
        self._fee_bps = float(fee_bps)
        self._slippage_bps = float(slippage_bps)
        self._positions: Dict[str, Dict[str, float]] = {}  # symbol -> {qty, cost_basis}
        self._realized_pnl = 0.0
        self._turnover = 0.0
        self._fills_applied: List[Dict[str, Any]] = []

    def apply_fill(self, fill: Dict[str, Any]) -> None:
        """
        Apply one fill: update positions, cash, realized_pnl, turnover.
        fill: symbol, side (BUY/SELL), signed_qty or qty, price, notional, day (optional).
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

        notional_eff = _effective_notional(notional, side, self._slippage_bps)
        fee = _fee(notional_eff, self._fee_bps)
        self._turnover = _round6(self._turnover + abs(notional_eff))

        pos = self._positions.setdefault(sym, {"qty": 0.0, "cost_basis": 0.0})

        if side == "BUY":
            self._cash = _round6(self._cash - notional_eff - fee)
            pos["qty"] = _round6(pos["qty"] + signed_qty)
            pos["cost_basis"] = _round6(pos["cost_basis"] + notional_eff + fee)
        else:
            qty_total = pos["qty"]
            if qty_total <= 0:
                return
            cost_total = pos["cost_basis"]
            qty_sold = abs(signed_qty)
            if qty_sold > qty_total:
                qty_sold = qty_total
            cost_of_sold = _round6(cost_total * (qty_sold / qty_total)) if qty_total else 0.0
            self._cash = _round6(self._cash + notional_eff - fee)
            self._realized_pnl = _round6(self._realized_pnl + (notional_eff - fee) - cost_of_sold)
            pos["qty"] = _round6(pos["qty"] - qty_sold)
            pos["cost_basis"] = _round6(pos["cost_basis"] - cost_of_sold)
        self._fills_applied.append(dict(fill))

    def apply_fills(self, fills: List[Dict[str, Any]], sort_key: Optional[tuple] = None) -> None:
        """Apply fills in order. If sort_key is (day, symbol), sort for determinism."""
        if sort_key:
            fills = sorted(fills, key=lambda f: (f.get(sort_key[0], ""), f.get(sort_key[1], "")))
        for f in fills:
            self.apply_fill(f)

    def cash(self) -> float:
        return self._cash

    def positions(self) -> List[Dict[str, Any]]:
        """List of {symbol, qty, cost_basis} for non-zero positions (sorted by symbol)."""
        out = []
        for sym in sorted(self._positions.keys()):
            p = self._positions[sym]
            if p["qty"] != 0:
                out.append({
                    "symbol": sym,
                    "qty": p["qty"],
                    "cost_basis": p["cost_basis"],
                })
        return out

    def position_map(self) -> Dict[str, float]:
        """Symbol -> qty (for backtest compatibility)."""
        return {p["symbol"]: p["qty"] for p in self.positions()}

    def realized_pnl(self) -> float:
        return _round6(self._realized_pnl)

    def unrealized_pnl(self, mark_prices: Dict[str, float]) -> float:
        """Sum (mark_price - avg_cost) * qty for each position."""
        total = 0.0
        for p in self.positions():
            sym = p["symbol"]
            qty = p["qty"]
            cost_basis = p["cost_basis"]
            avg_cost = (cost_basis / qty) if qty else 0.0
            mark = mark_prices.get(sym, avg_cost)
            total += (mark - avg_cost) * qty
        return _round6(total)

    def equity(self, mark_prices: Optional[Dict[str, float]] = None) -> float:
        """Cash + sum(qty * mark_price). If mark_prices None, use cost_basis (no mark)."""
        total = self._cash
        for p in self.positions():
            sym = p["symbol"]
            qty = p["qty"]
            if mark_prices and sym in mark_prices:
                total += qty * mark_prices[sym]
            else:
                total += p["cost_basis"]
        return _round6(total)

    def turnover(self) -> float:
        return self._turnover
