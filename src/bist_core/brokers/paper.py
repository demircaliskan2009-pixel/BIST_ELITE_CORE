"""Paper broker: fills at close price from snapshot (deterministic)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

from bist_core.brokers.base import Broker


def _load_close_map(snapshot_root: Path, day: str) -> Dict[str, float]:
    """Load symbol -> close from snapshot_root/<day>/snapshot.csv. Deterministic order by symbol."""
    path = snapshot_root / day / "snapshot.csv"
    if not path.is_file():
        alt = snapshot_root / (day + ".csv")
        path = alt if alt.is_file() else path
    if not path.is_file():
        return {}
    out: Dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            c = row.get("close")
            if c is None or c == "":
                continue
            try:
                out[sym] = float(c)
            except (TypeError, ValueError):
                continue
    return dict(sorted(out.items()))


class PaperBroker:
    """Broker that fills all orders at snapshot close price (deterministic)."""

    def __init__(
        self,
        snapshot_root: Path | str,
        day: str,
        portfolio_value: float = 1.0,
    ) -> None:
        self._snapshot_root = Path(snapshot_root)
        self._day = day
        self._portfolio_value = float(portfolio_value)
        self._close_map: Dict[str, float] | None = None
        self._fills: List[Dict[str, Any]] = []
        self._positions: Dict[str, Dict[str, Any]] = {}  # symbol -> {qty, notional, avg_price}

    def _ensure_close_map(self) -> Dict[str, float]:
        if self._close_map is None:
            self._close_map = _load_close_map(self._snapshot_root, self._day)
        return self._close_map

    def place_orders(self, orders_intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fill orders at close price from snapshot. Same intent + snapshot => same fills (deterministic)."""
        actions = orders_intent.get("actions") or []
        if not isinstance(actions, list):
            return []
        day = str(orders_intent.get("day") or self._day)
        close_map = self._ensure_close_map()
        # Process in deterministic order (by symbol)
        sorted_actions = sorted(
            [a for a in actions if isinstance(a, dict) and a.get("symbol")],
            key=lambda a: str(a.get("symbol", "")),
        )
        new_fills: List[Dict[str, Any]] = []
        for idx, action in enumerate(sorted_actions):
            symbol = str(action.get("symbol", "")).strip()
            side = str(action.get("side", "BUY")).upper()
            weight = action.get("weight")
            if symbol not in close_map or weight is None:
                continue
            try:
                w = float(weight)
            except (TypeError, ValueError):
                continue
            if w <= 0:
                continue
            price = close_map[symbol]
            if price <= 0:
                continue
            notional = round(w * self._portfolio_value, 6)
            qty = round(notional / price, 6)
            if side == "SELL":
                qty = -qty
            order_id = str(idx)
            fill = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "qty": abs(qty),
                "signed_qty": qty,
                "price": round(price, 6),
                "notional": round(notional, 6),
                "day": day,
            }
            new_fills.append(fill)
            # Update positions
            pos = self._positions.setdefault(symbol, {"qty": 0.0, "notional": 0.0, "avg_price": 0.0})
            old_qty = pos["qty"]
            old_notional = pos["notional"]
            pos["qty"] = round(old_qty + qty, 6)
            pos["notional"] = round(old_notional + (notional if side == "BUY" else -notional), 6)
            pos["avg_price"] = round(price, 6) if pos["qty"] != 0 else 0.0
            if pos["qty"] != 0:
                pos["avg_price"] = round(pos["notional"] / pos["qty"], 6)
        self._fills.extend(new_fills)
        return new_fills

    def cancel(self, order_id: Any = None) -> bool:
        """Paper broker fills immediately; no pending orders. No-op."""
        return False

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return current positions (symbol, qty, notional, avg_price) for non-zero qty."""
        result = []
        for symbol in sorted(self._positions.keys()):
            pos = self._positions[symbol]
            if pos["qty"] == 0:
                continue
            result.append({
                "symbol": symbol,
                "qty": pos["qty"],
                "notional": pos["notional"],
                "avg_price": pos["avg_price"],
            })
        return result
