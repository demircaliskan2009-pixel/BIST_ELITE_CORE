from __future__ import annotations

from typing import Any

RISK_PER_TRADE = 0.015
DAILY_LOSS_LIMIT_PCT = 0.05
MAX_POSITIONS = 10
MIN_RPS = 0.01
MAX_POSITION_VALUE_PCT = 0.75
MIN_SIZE = 1


class PortfolioState:
    """Persistent portfolio state. Single source of truth for capital, positions, PnL.
    PRDV2 compliant. No external dependencies. Fail-closed.
    """

    def __init__(self, capital: float) -> None:
        if capital <= 0:
            raise ValueError(f"initial capital must be > 0, got {capital}")
        self._capital: float = float(capital)
        self.open_positions: dict[str, dict[str, Any]] = {}
        self.daily_realized_pnl: float = 0.0
        self.daily_loss_used: float = 0.0
        self.trade_history: list[dict[str, Any]] = []

    @property
    def capital(self) -> float:
        return self._capital

    @capital.setter
    def capital(self, value: float) -> None:
        if value < 0:
            raise ValueError(f"capital cannot be negative: {value}")
        self._capital = float(value)

    def daily_loss_limit(self) -> float:
        return self._capital * DAILY_LOSS_LIMIT_PCT

    def can_trade(self) -> tuple[bool, str]:
        if self._capital <= 0:
            return False, "no_capital"
        if self.daily_loss_used >= self.daily_loss_limit():
            return False, "daily_loss_limit_reached"
        if len(self.open_positions) >= MAX_POSITIONS:
            return False, "max_positions_reached"
        return True, "ok"

    def size_trade(self, entry: float, stop: float) -> tuple[float, str]:
        if not entry or entry <= 0:
            return 0.0, "invalid_entry"
        if not stop or stop <= 0 or stop >= entry:
            return 0.0, "invalid_stop"
        rps = entry - stop
        if rps < MIN_RPS:
            return 0.0, "rps_too_small"
        remaining = self.daily_loss_limit() - self.daily_loss_used
        risk_amount = min(self._capital * RISK_PER_TRADE, remaining)
        if risk_amount <= 0:
            return 0.0, "no_risk_budget"
        size = risk_amount / rps
        max_by_value = (self._capital * MAX_POSITION_VALUE_PCT) / entry
        size = min(size, max_by_value)
        size = float(int(size))
        if size < MIN_SIZE:
            return 0.0, "size_too_small"
        return size, "ok"

    def open_position(self, symbol: str, entry: float, size: float,
                      stop: float, target: float) -> None:
        if not symbol or entry <= 0 or size < MIN_SIZE:
            return
        self.open_positions[symbol] = {
            "symbol": symbol,
            "entry": entry,
            "size": size,
            "stop": stop,
            "target": target,
        }

    def close_position(self, symbol: str, net_pnl: float) -> None:
        self.open_positions.pop(symbol, None)
        self._capital += float(net_pnl)
        if net_pnl < 0:
            self.daily_loss_used += abs(float(net_pnl))
        self.daily_realized_pnl += float(net_pnl)

    def record_trade(self, trade: dict[str, Any]) -> None:
        if isinstance(trade, dict):
            self.trade_history.append(trade)

    def reset_daily(self) -> None:
        self.daily_realized_pnl = 0.0
        self.daily_loss_used = 0.0
