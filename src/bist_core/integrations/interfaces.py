"""Integration interfaces (data vendor + broker). Kept minimal; no side effects on import."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Protocol

Side = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]
TimeInForce = Literal["DAY", "IOC", "FOK"]

@dataclass(frozen=True)
class Order:
    symbol: str
    side: Side
    qty: int
    order_type: OrderType = "LIMIT"
    limit_price: Optional[float] = None
    tif: TimeInForce = "DAY"
    client_order_id: Optional[str] = None
    meta: Dict[str, Any] = None

@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    broker_order_id: Optional[str] = None
    reason: Optional[str] = None
    raw: Dict[str, Any] = None

class BrokerAdapter(Protocol):
    """Fail-closed: implementations MUST raise on ambiguity or return accepted=False with reason."""
    def place_order(self, order: Order) -> OrderResult: ...
    def cancel_order(self, broker_order_id: str) -> bool: ...
    def positions(self) -> List[Dict[str, Any]]: ...
    def cash(self) -> Dict[str, Any]: ...

class DataVendorAdapter(Protocol):
    """Market data vendor adapter (EOD/Intraday/L2 later)."""
    def health(self) -> Dict[str, Any]: ...
