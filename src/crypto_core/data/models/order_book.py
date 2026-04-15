"""L2 order book state model.

OrderBook is the ONLY mutable data container in the data layer.
All mutations go through OrderBookManager — never directly.

State boundary:
- Owned by: OrderBookManager
- Readable by: edge engine, validator (via snapshot copy)
- Written by: OrderBookManager.apply_snapshot() / apply_delta()

Determinism: same sequence of events → identical book state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class OrderBook:
    """Mutable L2 order book state.

    bids: price → qty (buy side, descending price order meaningless in dict)
    asks: price → qty (sell side, ascending price order meaningless in dict)
    qty == 0 entries are deleted immediately on application.

    last_update_id: the u-field from the last applied delta (or snapshot).
    last_update_ts_ns: timestamp_ns of the last applied event.
    snapshot_ts_ns: timestamp_ns when the snapshot was taken (REST or WS).
    """

    symbol: str
    exchange: str
    bids: Dict[float, float] = field(default_factory=dict)
    asks: Dict[float, float] = field(default_factory=dict)
    last_update_id: int = 0
    last_update_ts_ns: int = 0
    snapshot_ts_ns: int = 0

    def best_bid(self) -> Optional[float]:
        """Returns the highest bid price, or None if book is empty."""
        return max(self.bids.keys()) if self.bids else None

    def best_ask(self) -> Optional[float]:
        """Returns the lowest ask price, or None if book is empty."""
        return min(self.asks.keys()) if self.asks else None

    def mid_price(self) -> Optional[float]:
        """Returns (best_bid + best_ask) / 2, or None if either side empty."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2.0

    def spread(self) -> Optional[float]:
        """Returns best_ask - best_bid, or None if either side empty."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    def is_crossed(self) -> bool:
        """Returns True if best_bid >= best_ask (invalid state)."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return False
        return bb >= ba

    def is_empty(self) -> bool:
        """Returns True if either side of the book has no entries."""
        return not self.bids or not self.asks

    def bid_depth(self, n_levels: int) -> Dict[float, float]:
        """Returns top-n bid levels sorted by descending price."""
        sorted_prices = sorted(self.bids.keys(), reverse=True)[:n_levels]
        return {p: self.bids[p] for p in sorted_prices}

    def ask_depth(self, n_levels: int) -> Dict[float, float]:
        """Returns top-n ask levels sorted by ascending price."""
        sorted_prices = sorted(self.asks.keys())[:n_levels]
        return {p: self.asks[p] for p in sorted_prices}
