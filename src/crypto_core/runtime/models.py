"""Runtime bridge typed models — Phase 7F.

All session-lifecycle and trigger models for the continuous
feed→session runtime bridge.

Determinism: frozen models are immutable (one per trigger event).
Mutable state is explicit in SymbolRuntimeState (updated in place).

PRD reference: §2 System Orchestration, §4.1-§4.5 Data Layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crypto_core.data.models.events import MarkPriceEvent
    from crypto_core.session.models import PaperSessionStatus


# ---------------------------------------------------------------------------
# Trigger policy and reason enums
# ---------------------------------------------------------------------------


class TriggerPolicy(str, Enum):
    """Session cycle trigger policy.

    MARK_PRICE:  trigger on every MarkPriceEvent (~3-5 s cadence on Binance).
    KLINE_CLOSE: trigger on every closed KlineEvent (bar-close driven).
    TRADE_BATCH: trigger after accumulating trade_batch_size trade events.
    TOP_OF_BOOK: trigger on every top-of-book price change.
    """

    MARK_PRICE = "mark_price"
    KLINE_CLOSE = "kline_close"
    TRADE_BATCH = "trade_batch"
    TOP_OF_BOOK = "top_of_book"


class TriggerReason(str, Enum):
    """Why a session cycle was triggered or suppressed."""

    MARK_PRICE = "mark_price"
    KLINE_CLOSE = "kline_close"
    TRADE_BATCH = "trade_batch"
    TOP_OF_BOOK = "top_of_book"
    DEDUP_SUPPRESSED = "dedup_suppressed"
    RECOVERY_BLOCKED = "recovery_blocked"
    SESSION_BLOCKED = "session_blocked"
    ASSEMBLER_INCOMPLETE = "assembler_incomplete"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeBridgeConfig:
    """Configuration for the feed-to-session runtime bridge.

    trigger_policy:            when to trigger a session cycle.
    trade_batch_size:          trade count threshold for TRADE_BATCH policy.
    max_trades_per_cycle:      max TradeEvents forwarded per cycle.
    max_liquidations_per_cycle: max LiquidationEvents forwarded per cycle.
    """

    trigger_policy: TriggerPolicy = TriggerPolicy.MARK_PRICE
    trade_batch_size: int = 10
    max_trades_per_cycle: int = 50
    max_liquidations_per_cycle: int = 20


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleTrigger:
    """Immutable audit record of one trigger event (fired or suppressed).

    One record is created for every potential trigger decision.
    suppressed=True means no session cycle was fired.
    """

    symbol: str
    exchange: str
    trigger_ts_ns: int  # timestamp of the triggering event
    reason: TriggerReason
    cycle_number: int  # session cycle number (0 when suppressed)
    suppressed: bool  # True = no cycle was fired
    suppression_reason: str | None  # set when suppressed=True


# ---------------------------------------------------------------------------
# Per-symbol mutable runtime state
# ---------------------------------------------------------------------------


@dataclass
class SymbolRuntimeState:
    """Mutable per-symbol runtime market state.

    Updated on every incoming event. Not frozen — written in place for
    efficiency. One instance exists per (symbol, exchange) pair.
    """

    symbol: str
    exchange: str

    # Order-book state (best bid / ask extracted from book manager)
    book_bid_price: float = 0.0
    book_ask_price: float = 0.0
    book_bid_size: float | None = None
    book_ask_size: float | None = None
    book_bid_count: int = 0
    book_ask_count: int = 0
    book_has_snapshot: bool = False
    book_last_update_ns: int = 0

    # Latest mark price event (None = stream not yet wired)
    mark_price_event: MarkPriceEvent | None = None
    last_mark_price_ts_ns: int = 0

    # Trade + liquidation accumulators (drained after each cycle)
    pending_trades: list = field(default_factory=list)
    pending_liquidations: list = field(default_factory=list)

    # Feed state strings (mirrored from FeedState)
    feed_connection_state: str = "disconnected"
    feed_recovery_state: str = "idle"

    # Trigger dedup: (symbol, exchange, reason) → last trigger_ts_ns
    last_trigger_ts_ns: dict = field(default_factory=dict)

    # Trade batch counter for TRADE_BATCH policy (reset on cycle)
    trade_batch_count: int = 0

    # Last known top-of-book for TOP_OF_BOOK dedup
    last_top_bid: float = 0.0
    last_top_ask: float = 0.0

    # Whether the liquidation feed was ever wired for this symbol.
    # False → liquidation_events is None in MarketDataInput (feed not present).
    # True  → liquidation_events is a tuple (possibly empty).
    liquidation_feed_wired: bool = False


# ---------------------------------------------------------------------------
# Operator-facing runtime status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeStatus:
    """Operator-facing runtime bridge + session status snapshot.

    Frozen — runner creates a new instance on every status() call.
    """

    session_status: PaperSessionStatus
    total_event_count: int
    total_trigger_count: int
    total_suppressed_count: int
    per_symbol_ready: dict  # symbol -> bool (feed live and READY)
    per_symbol_last_trigger_ns: dict  # symbol -> last trigger_ts_ns (int)
    recovery_in_progress: bool  # True if any registered feed is not READY
    blocked_reason: str | None  # non-None if session is not RUNNING
