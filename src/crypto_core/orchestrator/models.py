"""Pipeline orchestrator typed models.

PRD reference: §2 System Orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from crypto_core.data.models.events import TradeEvent
from crypto_core.edge.models import EdgeSignal
from crypto_core.execution.models import ExecutionDecision
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.kill_switch import KillSwitchResult
from crypto_core.risk.models import RiskEvaluation
from crypto_core.state.models import StateSnapshot


@dataclass(frozen=True)
class MarketDataInput:
    """Single pipeline invocation input — validated market data snapshot.

    trades: ordered tuple of recent TradeEvent objects.
    book_last_update_ns: last order book update timestamp (ns).
    book_has_snapshot: whether a valid OB snapshot has been applied.
    book_bid_count / book_ask_count: current level counts.
    feed_connection_state / feed_recovery_state: feed lifecycle state strings.

    Phase 6A: top-of-book price/size fields for paper execution pricing.
    book_bid_price / book_ask_price: best bid/ask prices in USD (0.0 = absent).
    book_bid_size / book_ask_size: visible depth at best level (base currency).
    """

    symbol: str
    exchange: str
    timestamp_ns: int  # pipeline invocation wall-clock

    trades: tuple[TradeEvent, ...] = field(default_factory=tuple)
    book_last_update_ns: int = 0
    book_has_snapshot: bool = False
    book_bid_count: int = 0
    book_ask_count: int = 0
    feed_connection_state: str = "connected"
    feed_recovery_state: str = "ready"
    # Phase 6A: top-of-book for paper fill pricing (0.0 / None = absent)
    book_bid_price: float = 0.0
    book_ask_price: float = 0.0
    book_bid_size: float | None = None
    book_ask_size: float | None = None


@dataclass(frozen=True)
class PipelineResult:
    """Immutable result of one full pipeline evaluation cycle.

    block_stage: which stage blocked the pipeline, or None if fully approved.
    approved: True iff all stages passed and risk evaluation approved.
    ks_result: kill-switch evaluation result for this cycle (always present).

    Phase 6A:
    execution_decisions: one ExecutionDecision per approved risk evaluation;
                         empty tuple when pipeline is blocked before execution.
    """

    input_ts_ns: int
    output_ts_ns: int
    state_snapshot: StateSnapshot
    no_trade_decision: NoTradeDecision
    edge_signals: tuple[EdgeSignal, ...]  # one per registered family
    risk_evaluations: tuple[RiskEvaluation, ...]  # one per edge signal
    block_stage: str | None  # "state" | "guard" | "edge" | "risk" | None
    block_reason: str | None
    approved: bool  # True = at least one risk evaluation is APPROVED
    ks_result: KillSwitchResult | None = None  # None only in legacy / test paths
    execution_decisions: tuple[ExecutionDecision, ...] = field(default_factory=tuple)  # Phase 6A
