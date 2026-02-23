"""FAZ597: FIFO lot matching — realized PnL from fills. Offline, deterministic."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bist_core.execution.fills_schema import Fill


@dataclass
class Lot:
    symbol: str
    qty_remaining: int
    price: Decimal
    ts: str


@dataclass
class RealizedTrade:
    ts: str
    symbol: str
    qty: int
    buy_price: Decimal
    sell_price: Decimal
    pnl_try: Decimal


def apply_fill_fifo(
    lots_by_symbol: dict[str, list[Lot]],
    fill: "Fill",
) -> list[RealizedTrade]:
    """
    Apply one fill to lots. BUY: append lot. SELL: consume FIFO.
    Fail-closed if sell qty > available.
    Fees: subtract fee_try from that fill's realized pnl.
    """
    from bist_core.execution.fills_schema import Fill as FillType

    realized: list[RealizedTrade] = []
    sym = fill.symbol.upper()
    if sym not in lots_by_symbol:
        lots_by_symbol[sym] = []

    if fill.side == "BUY":
        lots_by_symbol[sym].append(
            Lot(symbol=sym, qty_remaining=fill.qty, price=fill.price, ts=fill.ts)
        )
        return realized

    # SELL
    remaining = fill.qty
    fill_pnl = Decimal("0")
    lots = lots_by_symbol[sym]
    consumed: list[tuple[Lot, int]] = []

    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.qty_remaining, remaining)
        if take <= 0:
            continue
        pnl_piece = (fill.price - lot.price) * Decimal(take)
        fill_pnl += pnl_piece
        realized.append(
            RealizedTrade(
                ts=fill.ts,
                symbol=sym,
                qty=take,
                buy_price=lot.price,
                sell_price=fill.price,
                pnl_try=pnl_piece,
            )
        )
        consumed.append((lot, take))
        remaining -= take

    if remaining > 0:
        raise ValueError(
            f"SELL {fill.qty} {sym} exceeds available lots (short by {remaining})"
        )

    for lot, take in consumed:
        lot.qty_remaining -= take
    lots_by_symbol[sym] = [l for l in lots if l.qty_remaining > 0]

    # Apply fee to this fill's realized pnl
    fee = getattr(fill, "fee_try", None) or Decimal("0")
    if fee > 0 and realized:
        adj = fee / len(realized)
        for r in realized:
            r.pnl_try -= adj

    return realized


def run_fifo(fills: list["Fill"]) -> tuple[list[RealizedTrade], dict[str, list[Lot]]]:
    """Run FIFO over all fills. Returns (realized_trades, lots_by_symbol)."""
    lots_by_symbol: dict[str, list[Lot]] = {}
    all_realized: list[RealizedTrade] = []
    for fill in fills:
        realized = apply_fill_fifo(lots_by_symbol, fill)
        all_realized.extend(realized)
    return all_realized, lots_by_symbol
