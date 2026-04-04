"""Performance metrics — win rate, expectancy, drawdown."""

from __future__ import annotations

from typing import Any


def compute_metrics(trades: list[dict]) -> dict[str, Any]:
    """Compute performance metrics from closed trades.

    trades: list of {"entry": float, "exit": float, "size": float, "pnl": float}
    or {"entry": float, "exit": float, "pnl": float} (size default 1)
    """
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "expectancy": 0.0,
            "max_drawdown": 0.0, "total_cost": 0.0, "net_expectancy": 0.0,
        }

    pnls: list[float] = []
    for t in trades:
        pnl = t.get("net_pnl") or t.get("pnl")
        if pnl is None:
            pnl = (float(t.get("exit_fill", t.get("exit", 0))) - float(t.get("entry_fill", t.get("entry", 0)))) * float(t.get("size", 1))
        pnls.append(float(pnl))

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]


    total_trades = len(pnls)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total_trades if total_trades > 0 else 0.0
    avg_win = sum(wins) / win_count if win_count > 0 else 0.0
    avg_loss = abs(sum(losses)) / loss_count if loss_count > 0 else 0.0
    expectancy = sum(pnls) / total_trades if total_trades > 0 else 0.0

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    total_cost = sum(float(t.get("cost", 0)) for t in trades)
    return {
        "total_trades": total_trades, "wins": win_count, "losses": loss_count,
        "win_rate": round(win_rate, 4), "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4), "expectancy": round(expectancy, 4),
        "max_drawdown": round(max_dd, 4), "total_cost": round(total_cost, 6),
        "net_expectancy": round(expectancy, 4),
    }


__all__ = ["compute_metrics"]
