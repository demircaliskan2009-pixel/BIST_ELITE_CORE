"""Paper trading engine — Phase D execution adapter per PRD §10/§12.

Simulates order lifecycle, fills with slippage, trade journaling,
performance metrics and deterministic replay.  Pure stdlib, no network.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Sequence


# ---------------------------------------------------------------------------
# Order state machine
# ---------------------------------------------------------------------------

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


_VALID_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({
        OrderStatus.OPEN,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    }),
    OrderStatus.OPEN: frozenset({
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    }),
    OrderStatus.PARTIALLY_FILLED: frozenset({
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
    }),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


class OrderStateMachine:
    """Enforce valid order lifecycle transitions."""

    __slots__ = ("_status",)

    def __init__(self, initial: OrderStatus = OrderStatus.PENDING) -> None:
        self._status = initial

    @property
    def status(self) -> OrderStatus:
        return self._status

    def transition(self, target: OrderStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self._status, frozenset())
        if target not in allowed:
            raise ValueError(
                f"Invalid transition: {self._status.value} -> {target.value}"
            )
        self._status = target


# ---------------------------------------------------------------------------
# Order types
# ---------------------------------------------------------------------------

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


# ---------------------------------------------------------------------------
# Slippage model
# ---------------------------------------------------------------------------

@dataclass
class SlippageModel:
    base_slippage_bps: float = 5.0
    volatility_adjustment: float = 0.0
    liquidity_adjustment: float = 0.0

    def compute(self, price: float, side: OrderSide) -> float:
        total_bps = (
            self.base_slippage_bps
            + self.volatility_adjustment
            + self.liquidity_adjustment
        )
        slip_pct = total_bps / 10_000.0
        if side == OrderSide.BUY:
            return round(price * (1.0 + slip_pct), 4)
        return round(price * (1.0 - slip_pct), 4)


_DEFAULT_SLIPPAGE = SlippageModel()


# ---------------------------------------------------------------------------
# Trade model
# ---------------------------------------------------------------------------

@dataclass
class PaperTrade:
    trade_id: str
    symbol: str
    entry_price: float
    stop_price: float
    target_price: float
    position_size: int
    entry_time: str
    exit_time: Optional[str] = None
    status: str = "OPEN"
    pnl: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    edge: str = ""
    source: str = "technical"
    event_kind: str = ""
    event_multiplier: float = 1.0

    def close(self, exit_price: float, exit_time: str, fees: float = 0.0) -> None:
        self.exit_time = exit_time
        self.fees = fees
        self.pnl = round(
            (exit_price - self.entry_price) * self.position_size - fees,
            4,
        )
        self.status = "CLOSED"

    @property
    def r_multiple(self) -> Optional[float]:
        risk = self.entry_price - self.stop_price
        if risk <= 0 or self.status != "CLOSED":
            return None
        return round(self.pnl / (risk * self.position_size), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "position_size": self.position_size,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "status": self.status,
            "pnl": self.pnl,
            "fees": self.fees,
            "slippage": self.slippage,
            "r_multiple": self.r_multiple,
            "edge": self.edge,
            "source": self.source,
            "event_kind": self.event_kind,
            "event_multiplier": self.event_multiplier,
        }


# ---------------------------------------------------------------------------
# Trade journal
# ---------------------------------------------------------------------------

class PaperTradeJournal:
    """Stores all trades and computes aggregate metrics."""

    def __init__(self) -> None:
        self._trades: list[PaperTrade] = []

    @property
    def all_trades(self) -> list[PaperTrade]:
        return list(self._trades)

    @property
    def open_trades(self) -> list[PaperTrade]:
        return [t for t in self._trades if t.status == "OPEN"]

    @property
    def closed_trades(self) -> list[PaperTrade]:
        return [t for t in self._trades if t.status == "CLOSED"]

    def add(self, trade: PaperTrade) -> None:
        self._trades.append(trade)

    def performance_metrics(self) -> Dict[str, Any]:
        closed = self.closed_trades
        if not closed:
            return {
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
                "max_drawdown": 0.0,
                "avg_R_multiple": 0.0,
                "total_trades": 0,
                "open_count": len(self.open_trades),
                "closed_count": 0,
            }

        wins = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl <= 0]
        total_win = sum(t.pnl for t in wins)
        total_loss = abs(sum(t.pnl for t in losses))

        win_rate = round(len(wins) / len(closed), 4) if closed else 0.0
        profit_factor = round(total_win / total_loss, 4) if total_loss > 0 else float("inf") if total_win > 0 else 0.0
        expectancy = round(sum(t.pnl for t in closed) / len(closed), 4)

        r_multiples = [t.r_multiple for t in closed if t.r_multiple is not None]
        avg_r = round(sum(r_multiples) / len(r_multiples), 4) if r_multiples else 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in closed:
            cumulative += t.pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return {
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "max_drawdown": round(max_dd, 4),
            "avg_R_multiple": avg_r,
            "total_trades": len(self._trades),
            "open_count": len(self.open_trades),
            "closed_count": len(closed),
        }


# ---------------------------------------------------------------------------
# Paper execution engine
# ---------------------------------------------------------------------------

@dataclass
class _SimOrder:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_price: float
    quantity: int
    filled_quantity: int = 0
    fill_price: float = 0.0
    sm: OrderStateMachine = field(default_factory=OrderStateMachine)


class PaperExecutionEngine:
    """Simulates order fills, slippage, and trade lifecycle from advisor decision objects."""

    def __init__(
        self,
        slippage: SlippageModel | None = None,
        fee_bps: float = 10.0,
    ) -> None:
        self._slippage = slippage or _DEFAULT_SLIPPAGE
        self._fee_bps = fee_bps
        self._journal = PaperTradeJournal()
        self._orders: list[_SimOrder] = []
        self._order_counter = 0

    @property
    def journal(self) -> PaperTradeJournal:
        return self._journal

    # -- order creation ---------------------------------------------------

    def _gen_id(self) -> str:
        self._order_counter += 1
        return f"PE-{self._order_counter:06d}"

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        price: float,
        quantity: int,
    ) -> _SimOrder:
        order = _SimOrder(
            order_id=self._gen_id(),
            symbol=symbol.upper().strip(),
            side=side,
            order_type=order_type,
            requested_price=price,
            quantity=quantity,
        )
        order.sm.transition(OrderStatus.OPEN)
        self._orders.append(order)
        return order

    # -- fill simulation --------------------------------------------------

    def fill_order(
        self,
        order: _SimOrder,
        market_price: float,
        fill_quantity: int | None = None,
    ) -> bool:
        if order.sm.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        ):
            return False

        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and market_price > order.requested_price:
                return False
            if order.side == OrderSide.SELL and market_price < order.requested_price:
                return False

        fill_qty = fill_quantity if fill_quantity is not None else (order.quantity - order.filled_quantity)
        fill_qty = min(fill_qty, order.quantity - order.filled_quantity)
        if fill_qty <= 0:
            return False

        exec_price = self._slippage.compute(market_price, order.side)
        order.filled_quantity += fill_qty
        order.fill_price = exec_price

        if order.filled_quantity >= order.quantity:
            order.sm.transition(OrderStatus.FILLED)
        else:
            if order.sm.status == OrderStatus.OPEN:
                order.sm.transition(OrderStatus.PARTIALLY_FILLED)

        return True

    def cancel_order(self, order: _SimOrder) -> None:
        order.sm.transition(OrderStatus.CANCELLED)

    def expire_order(self, order: _SimOrder) -> None:
        order.sm.transition(OrderStatus.EXPIRED)

    # -- advisor integration ----------------------------------------------

    def execute_decision(
        self,
        symbol: str,
        entry: float,
        stop: float,
        target: float,
        position_size: int,
        market_price: float,
        entry_time: str,
        edge: str = "",
        source: str = "technical",
        event_kind: str = "",
        event_multiplier: float = 1.0,
    ) -> PaperTrade | None:
        if entry <= 0 or stop <= 0 or target <= 0 or position_size <= 0:
            return None

        order = self.submit_order(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=entry,
            quantity=position_size,
        )

        filled = self.fill_order(order, market_price)
        if not filled:
            self.cancel_order(order)
            return None

        slippage = round(abs(order.fill_price - entry) * position_size, 4)
        trade = PaperTrade(
            trade_id=order.order_id,
            symbol=symbol.upper().strip(),
            entry_price=order.fill_price,
            stop_price=stop,
            target_price=target,
            position_size=position_size,
            entry_time=entry_time,
            slippage=slippage,
            edge=edge,
            source=source,
            event_kind=event_kind,
            event_multiplier=event_multiplier,
        )
        self._journal.add(trade)
        return trade

    def simulate_exit(
        self,
        trade: PaperTrade,
        exit_price: float,
        exit_time: str,
    ) -> None:
        if trade.status != "OPEN":
            return

        order = self.submit_order(
            symbol=trade.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            price=exit_price,
            quantity=trade.position_size,
        )
        filled = self.fill_order(order, exit_price)
        if not filled:
            return

        notional = order.fill_price * trade.position_size
        fees = round(notional * self._fee_bps / 10_000.0, 4)
        trade.close(order.fill_price, exit_time, fees=fees)

    # -- deterministic replay --------------------------------------------

    def replay_trades(
        self,
        snapshot_data: Sequence[Dict[str, Any]],
    ) -> list[PaperTrade]:
        results: list[PaperTrade] = []
        for row in snapshot_data:
            symbol = str(row.get("symbol") or "").upper().strip()
            entry = _safe_float(row.get("entry"))
            stop = _safe_float(row.get("stop"))
            target = _safe_float(row.get("target"))
            position_size = _safe_int(row.get("position_size"))
            market_price = _safe_float(row.get("market_price") or row.get("current_close"))
            entry_time = str(row.get("entry_time") or row.get("day") or "")
            exit_price = _safe_float(row.get("exit_price"))
            exit_time = str(row.get("exit_time") or "")

            if not symbol or entry is None or stop is None or target is None:
                continue
            if position_size is None or position_size <= 0:
                continue
            if market_price is None or market_price <= 0:
                continue

            trade = self.execute_decision(
                symbol=symbol,
                entry=entry,
                stop=stop,
                target=target,
                position_size=position_size,
                market_price=market_price,
                entry_time=entry_time,
            )
            if trade is None:
                continue

            if exit_price is not None and exit_price > 0 and exit_time:
                self.simulate_exit(trade, exit_price, exit_time)

            results.append(trade)
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
