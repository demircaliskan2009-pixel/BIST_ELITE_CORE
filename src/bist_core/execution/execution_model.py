"""Deterministic execution model — slippage, spread, commission."""

from __future__ import annotations


def apply_execution_cost(price: float, side: str) -> float:
    """Single cost source: 0.3% (0.2% slippage + 0.1% spread)."""
    if not isinstance(price, (int, float)):
        return price
    cost = 0.003
    return price * (1.0 + cost if side == "buy" else 1.0 - cost if side == "sell" else 1.0)


class ExecutionModel:
    def __init__(
        self,
        slippage_bps: float = 5.0,
        spread_bps: float = 10.0,
        commission_bps: float = 2.0,
    ) -> None:
        self._slippage_bps = float(slippage_bps)
        self._spread_bps = float(spread_bps)
        self._commission_bps = float(commission_bps)

    def apply_execution(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
        size: float,
    ) -> dict:
        if size <= 0 or entry_price <= 0 or exit_price <= 0:
            raise ValueError("Invalid execution inputs")
        entry_fill = entry_price * (1.0 + (self._spread_bps + self._slippage_bps) / 10000.0)
        exit_fill = exit_price * (1.0 - (self._spread_bps + self._slippage_bps) / 10000.0)
        gross_pnl = (exit_fill - entry_fill) * size
        cost = (entry_fill * size + exit_fill * size) * self._commission_bps / 10000.0
        net_pnl = gross_pnl - cost
        return {
            "entry_fill": round(entry_fill, 6),
            "exit_fill": round(exit_fill, 6),
            "gross_pnl": round(gross_pnl, 6),
            "net_pnl": round(net_pnl, 6),
            "cost": round(cost, 6),
        }


def apply_to_trade(trade: dict, model: ExecutionModel) -> dict:
    try:
        ex = model.apply_execution("BUY", trade["entry"], trade["exit"], trade["size"])
    except (ValueError, KeyError, TypeError):
        print("EXEC REJECT", flush=True)
        return None

    trade["entry_fill"] = ex["entry_fill"]
    trade["exit_fill"] = ex["exit_fill"]
    trade["gross_pnl"] = ex["gross_pnl"]
    trade["net_pnl"] = ex["net_pnl"]
    trade["cost"] = ex["cost"]
    trade["pnl"] = ex["net_pnl"]

    return trade


__all__ = ["ExecutionModel", "apply_to_trade", "apply_execution_cost"]
