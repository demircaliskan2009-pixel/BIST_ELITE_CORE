"""Execution Engine typed models.

PRD reference: §7 Execution Engine.
Phase 6A additions: BookContext, SlippageResult, paper fill pricing evidence on ExecutionDecision.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.risk.models import RiskEvaluation


class ExecutionMode(str):
    """Execution mode — controls whether real orders are placed."""

    pass


ExecutionMode.DRY_RUN = ExecutionMode("dry_run")  # No file writes, no state mutations
ExecutionMode.PAPER = ExecutionMode("paper")  # Logs paper fills, no exchange calls
# ExecutionMode.LIVE is NOT implemented yet — reserved for future adapter injection


class OrderIntent(str):
    """Requested trade direction."""

    pass


OrderIntent.BUY = OrderIntent("buy")
OrderIntent.SELL = OrderIntent("sell")


class RejectionReason(str):
    """Why an execution request was rejected."""

    pass


RejectionReason.INVALID_SYMBOL = RejectionReason("invalid_symbol")
RejectionReason.INCOMPLETE_PAYLOAD = RejectionReason("incomplete_payload")
RejectionReason.SYSTEM_STATE_DEFENSIVE = RejectionReason("system_state_defensive")
RejectionReason.RISK_NOT_APPROVED = RejectionReason("risk_not_approved")
RejectionReason.LIVE_NOT_ENABLED = RejectionReason("live_not_enabled")
RejectionReason.ZERO_SIZE = RejectionReason("zero_size")
RejectionReason.EXCEPTION_FAIL_CLOSED = RejectionReason("exception_fail_closed")
# Phase 6A: paper execution realism rejection reasons
RejectionReason.BOOK_UNAVAILABLE = RejectionReason("book_unavailable")
RejectionReason.BOOK_INVALID = RejectionReason("book_invalid")
RejectionReason.BOOK_CROSSED = RejectionReason("book_crossed")
RejectionReason.EXCESSIVE_SPREAD = RejectionReason("excessive_spread")
RejectionReason.EXCESSIVE_SLIPPAGE = RejectionReason("excessive_slippage")
RejectionReason.INSUFFICIENT_LIQUIDITY = RejectionReason("insufficient_liquidity")


@dataclass(frozen=True)
class BookContext:
    """Top-of-book snapshot for realistic paper fill pricing.

    bid_price: best bid in USD.  Must be > 0 for a valid book.
    ask_price: best ask in USD.  Must be > bid_price for a valid book.
    bid_size: visible base-currency depth at best bid; None = unavailable.
    ask_size: visible base-currency depth at best ask; None = unavailable.
    bid_level_count: number of price levels on the bid side.
    ask_level_count: number of price levels on the ask side.

    A book is valid iff bid_price > 0 and ask_price > bid_price.
    A book is crossed iff ask_price <= bid_price.

    Note: size fields are in base currency (e.g. BTC), same unit as
    ExecutionRequest.size, enabling direct participation-ratio calculation.
    """

    bid_price: float
    ask_price: float
    bid_size: float | None = None  # base-currency depth; None = unavailable
    ask_size: float | None = None  # base-currency depth; None = unavailable
    bid_level_count: int = 0
    ask_level_count: int = 0

    @property
    def mid_price(self) -> float:
        """Reference mid price."""
        return (self.bid_price + self.ask_price) / 2.0

    @property
    def spread(self) -> float:
        """Absolute bid-ask spread in USD."""
        return self.ask_price - self.bid_price

    @property
    def spread_bps(self) -> float:
        """Full bid-ask spread in basis points (10_000 = 100%)."""
        mid = self.mid_price
        if mid <= 0.0:
            return float("inf")
        return self.spread / mid * 10_000.0

    @property
    def is_valid(self) -> bool:
        """True iff book has positive prices and a positive spread."""
        return self.bid_price > 0.0 and self.ask_price > self.bid_price

    @property
    def is_crossed(self) -> bool:
        """True iff ask_price <= bid_price (crossed or locked book)."""
        return self.ask_price <= self.bid_price


@dataclass(frozen=True)
class SlippageResult:
    """Deterministic fill price derivation result for one paper execution.

    All cost components are expressed from the mid-price perspective.

    Fields:
      base_price             — reference mid price (USD)
      spread_component_bps   — half-spread cost applied to fill (bps, ≥ 0)
      slippage_component_bps — size-impact cost applied to fill (bps, ≥ 0)
      fill_price             — final synthetic fill price (USD)
      spread_bps             — full bid-ask spread width (bps)
      slippage_bps           — total fill cost from mid (half-spread + impact, bps)
      participation_pct      — size / side_depth × 100; None if depth unavailable
      evidence               — full audit dictionary
    """

    base_price: float
    spread_component_bps: float
    slippage_component_bps: float
    fill_price: float
    spread_bps: float
    slippage_bps: float
    participation_pct: float | None
    evidence: dict[str, object]


@dataclass(frozen=True)
class ExecutionRequest:
    """Input to the execution engine — built from a risk-approved payload.

    All fields are required unless noted. The engine rejects requests with
    missing or invalid data.

    book: optional top-of-book context for paper fill pricing.
          None → fill pricing falls back to price_hint (degraded paper mode).
          Provided but invalid → execution rejected fail-closed.
    """

    symbol: str
    exchange: str
    intent: OrderIntent
    size: float  # base currency quantity (positive)
    price_hint: float  # last known mid-price (for dry-run logging / fallback)
    risk_evaluation: RiskEvaluation
    timestamp_ns: int
    book: BookContext | None = None  # Phase 6A: top-of-book for paper fill pricing


@dataclass(frozen=True)
class ExecutionDecision:
    """Immutable result of one execution engine evaluation.

    order_id: generated UUID for dry-run / paper orders; None if rejected.
    mode: the mode under which this decision was made.

    Phase 6A paper fill evidence (populated when allowed=True and mode=PAPER
    with valid BookContext; None otherwise — never fabricated):
      ref_mid_price     — reference mid price used for fill pricing (USD)
      ref_bid_price     — reference best bid (USD)
      ref_ask_price     — reference best ask (USD)
      fill_price        — synthetic fill price (USD); None = not computed
      spread_bps        — full bid-ask spread in bps
      slippage_bps      — total fill cost from mid in bps
      participation_pct — size / side_depth × 100; None if depth unavailable
      fill_generated    — True when a SyntheticFill was created downstream
    """

    allowed: bool
    rejection_reason: RejectionReason | None  # None iff allowed=True
    mode: ExecutionMode
    order_id: str | None  # dry-run / paper generates a UUID; None if rejected
    evidence: dict[str, object]
    timestamp_ns: int
    # Phase 6A: paper fill pricing evidence (defaults for backward compat)
    ref_mid_price: float | None = None
    ref_bid_price: float | None = None
    ref_ask_price: float | None = None
    fill_price: float | None = None
    spread_bps: float | None = None
    slippage_bps: float | None = None
    participation_pct: float | None = None
    fill_generated: bool = False

    @property
    def rejected(self) -> bool:
        return not self.allowed
