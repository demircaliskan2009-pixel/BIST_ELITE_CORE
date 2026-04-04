"""Paper trading metrics — deterministic, in-memory."""

from __future__ import annotations

from typing import Any


class PaperTracker:
    def __init__(self) -> None:
        self.trades: list[dict[str, Any]] = []
        self.equity: float = 100_000.0

    def record(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        size: float,
        reason: str,
        *,
        pnl: float | None = None,
    ) -> None:
        """Append one closed trade. If ``pnl`` is given, use it (realized $); else ``(exit-entry)*size``."""
        if entry_price <= 0 or exit_price <= 0 or size <= 0:
            return
        if pnl is not None:
            pnl_v = float(pnl)
        else:
            pnl_v = (exit_price - entry_price) * size
        self.equity += pnl_v
        self.trades.append(
            {
                "symbol": str(symbol),
                "entry": float(entry_price),
                "exit": float(exit_price),
                "size": float(size),
                "pnl": float(pnl_v),
                "equity": float(self.equity),
                "reason": str(reason),
            }
        )

    def stats(self) -> dict[str, Any]:
        wins = sum(1 for t in self.trades if float(t["pnl"]) > 0)
        total = len(self.trades)
        return {
            "total_trades": total,
            "winrate": (wins / total) if total else 0.0,
            "equity": float(self.equity),
        }


__all__ = ["PaperTracker"]
