from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List


@dataclass
class Trade:
    symbol: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    timestamp: datetime


class PerformanceTracker:
    def __init__(self) -> None:
        self.open_positions: Dict[str, dict] = {}
        self.closed_trades: List[Trade] = []

    def on_entry(
        self,
        symbol: str,
        price: float,
        size: float,
        ts: datetime,
        *,
        side: str = "long",
    ):
        if symbol in self.open_positions:
            return
        _sd = str(side).strip().lower()
        if _sd != "short":
            _sd = "long"
        self.open_positions[symbol] = {
            "price": price,
            "size": size,
            "ts": ts,
            "side": _sd,
        }

    def on_exit(self, symbol: str, price: float, ts: datetime):
        pos = self.open_positions.pop(symbol, None)
        if not pos:
            return

        entry_price = pos["price"]
        size = pos["size"]
        is_short = str(pos.get("side", "long")).strip().lower() == "short"

        if is_short:
            pnl = (entry_price - price) / entry_price
        else:
            pnl = (price - entry_price) / entry_price

        self.closed_trades.append(
            Trade(
                symbol=symbol,
                entry_price=entry_price,
                exit_price=price,
                size=size,
                pnl=pnl,
                timestamp=ts,
            )
        )

    def compute_metrics(self):
        trades = self.closed_trades
        if not trades:
            return {
                "trades": 0,
                "winrate": 0,
                "expectancy": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "total_pnl": 0,
            }

        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [t.pnl for t in trades if t.pnl <= 0]

        winrate = len(wins) / len(trades)

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        expectancy = (winrate * avg_win) + ((1 - winrate) * avg_loss)

        total_pnl = sum(t.pnl for t in trades)

        return {
            "trades": len(trades),
            "winrate": round(winrate, 4),
            "expectancy": round(expectancy, 5),
            "avg_win": round(avg_win, 5),
            "avg_loss": round(avg_loss, 5),
            "total_pnl": round(total_pnl, 5),
        }
