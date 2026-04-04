"""Portfolio tracker — capital and positions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .position import Position


class Portfolio:
    """Tracks capital and open positions. Deterministic calculations."""

    def __init__(self, capital: float) -> None:
        self._capital = float(capital)
        self._open_positions: list["Position"] = []

    def open_position(self, position: "Position") -> None:
        """Add position to portfolio. Capital reduced by entry * size."""
        self._open_positions.append(position)
        self._capital -= position.entry * position.size

    def close_position(self, position: "Position", exit_price: float) -> None:
        """Remove position and update capital. Capital += exit_price * size."""
        if position in self._open_positions:
            self._open_positions.remove(position)
        self._capital += exit_price * position.size

    def current_value(self) -> float:
        """Total value: capital + sum(entry * size) of open positions (cost basis)."""
        pos_value = sum(p.entry * p.size for p in self._open_positions)
        return self._capital + pos_value

    def equity(self, mark_prices: dict[str, float] | None = None) -> float:
        """Equity = capital + unrealized PnL. If mark_prices given, use for MTM; else cost basis."""
        if not mark_prices or not self._open_positions:
            return self.current_value()
        pos_value = sum(
            (mark_prices.get(p.symbol) or p.entry) * p.size for p in self._open_positions
        )
        return self._capital + pos_value

    @property
    def open_positions(self) -> list["Position"]:
        return list(self._open_positions)


__all__ = ["Portfolio"]
