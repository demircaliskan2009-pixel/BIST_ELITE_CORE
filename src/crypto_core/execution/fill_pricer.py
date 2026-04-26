"""Deterministic paper fill pricer — Phase 6A execution realism.

Computes a realistic synthetic fill price from top-of-book data for
PAPER-mode execution.  No randomness.  All rejection paths are explicit.

Model overview (from mid-price perspective):
  half_spread_bps  = spread_bps / 2
  impact_bps       = size_impact_coefficient × participation_pct
                     (0.0 if side depth is unavailable)
  fill_cost_bps    = half_spread_bps + impact_bps

  BUY  fill_price  = mid × (1 + fill_cost_bps / 10_000)
  SELL fill_price  = mid × (1 - fill_cost_bps / 10_000)

Rejection gates (in order):
  1. BOOK_INVALID        — bid ≤ 0 or ask ≤ 0 or prices non-finite
  2. BOOK_CROSSED        — ask_price ≤ bid_price
  3. EXCESSIVE_SPREAD    — spread_bps > max_spread_bps
  4. INSUFFICIENT_LIQUIDITY — participation_pct > max_participation_pct
                              (only when side depth is available)
  5. EXCESSIVE_SLIPPAGE  — fill_cost_bps > max_slippage_bps

PRD reference: §7.1–§7.8 Execution Engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from crypto_core.execution.models import BookContext, OrderIntent, RejectionReason, SlippageResult


@dataclass(frozen=True)
class FillPricerConfig:
    """Configuration for the deterministic fill pricer.

    max_spread_bps:
        Reject if the full bid-ask spread exceeds this value.
        Default 200 bps (2%).  Wide spreads signal illiquid / unreliable book.

    max_slippage_bps:
        Reject if the total fill cost from mid (half-spread + impact) exceeds
        this value.  Default 100 bps (1%).

    max_participation_pct:
        Reject if requested size exceeds this percentage of visible side depth.
        Only enforced when depth data is available.  Default 10.0%.

    size_impact_coefficient:
        Slippage impact per percentage point of participation.
        impact_bps = size_impact_coefficient × participation_pct.
        Default 0.5 → at 10% participation: 5 bps impact.

    require_book_for_paper:
        If True, a None book context causes BOOK_UNAVAILABLE rejection.
        If False (default), None book context falls back to price_hint
        (dry-run-style fill with no slippage applied).
        Set True in production paper-trading environments.
    """

    max_spread_bps: float = 200.0
    max_slippage_bps: float = 100.0
    max_participation_pct: float = 10.0
    size_impact_coefficient: float = 0.5
    require_book_for_paper: bool = False


class FillPricer:
    """Stateless deterministic fill pricer for paper-mode execution.

    Usage::

        cfg = FillPricerConfig(max_spread_bps=150.0)
        pricer = FillPricer(cfg)
        result = pricer.price_fill(OrderIntent.BUY, size=0.1, book=book_ctx)
        if isinstance(result, RejectionReason):
            # fill rejected
        else:
            fill_price = result.fill_price

    Invariants:
      - No randomness.
      - Identical inputs → identical output.
      - Returns RejectionReason (not raises) for all invalid states.
    """

    def __init__(self, config: FillPricerConfig | None = None) -> None:
        self._cfg = config or FillPricerConfig()

    def price_fill(
        self,
        intent: OrderIntent,
        size: float,
        book: BookContext,
    ) -> SlippageResult | RejectionReason:
        """Derive a deterministic synthetic fill price.

        Args:
            intent: BUY or SELL.
            size:   requested fill size in base currency (> 0, already validated).
            book:   top-of-book context (must not be None — caller checks).

        Returns:
            SlippageResult if all gates pass.
            RejectionReason if any gate fails (fail-closed).
        """
        cfg = self._cfg

        # ── Gate 1: Book validity ───────────────────────────────────────
        if not _finite_positive(book.bid_price) or not _finite_positive(book.ask_price):
            return RejectionReason.BOOK_INVALID

        # ── Gate 2: Crossed book ────────────────────────────────────────
        if book.is_crossed:
            return RejectionReason.BOOK_CROSSED

        mid = book.mid_price
        spread_bps = book.spread_bps

        # ── Gate 3: Excessive spread ────────────────────────────────────
        if spread_bps > cfg.max_spread_bps:
            return RejectionReason.EXCESSIVE_SPREAD

        # ── Gate 4: Participation / liquidity ───────────────────────────
        side_depth = _side_depth(intent, book)
        participation_pct: float | None = None
        impact_bps = 0.0

        if side_depth is not None and side_depth > 0.0:
            participation_pct = size / side_depth * 100.0
            if participation_pct > cfg.max_participation_pct:
                return RejectionReason.INSUFFICIENT_LIQUIDITY
            impact_bps = cfg.size_impact_coefficient * participation_pct

        # ── Gate 5: Total fill cost ─────────────────────────────────────
        half_spread_bps = spread_bps / 2.0
        fill_cost_bps = half_spread_bps + impact_bps

        if fill_cost_bps > cfg.max_slippage_bps:
            return RejectionReason.EXCESSIVE_SLIPPAGE

        # ── Compute fill price ──────────────────────────────────────────
        if intent == OrderIntent.BUY:
            fill_price = mid * (1.0 + fill_cost_bps / 10_000.0)
        else:
            fill_price = mid * (1.0 - fill_cost_bps / 10_000.0)

        evidence: dict[str, object] = {
            "intent": str(intent),
            "size": size,
            "mid_price": round(mid, 8),
            "bid_price": round(book.bid_price, 8),
            "ask_price": round(book.ask_price, 8),
            "spread_bps": round(spread_bps, 4),
            "half_spread_bps": round(half_spread_bps, 4),
            "impact_bps": round(impact_bps, 4),
            "fill_cost_bps": round(fill_cost_bps, 4),
            "fill_price": round(fill_price, 8),
            "participation_pct": round(participation_pct, 4) if participation_pct is not None else None,
            "side_depth_available": side_depth is not None,
        }

        return SlippageResult(
            base_price=mid,
            spread_component_bps=half_spread_bps,
            slippage_component_bps=impact_bps,
            fill_price=fill_price,
            spread_bps=spread_bps,
            slippage_bps=fill_cost_bps,
            participation_pct=participation_pct,
            evidence=evidence,
        )


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _finite_positive(value: float) -> bool:
    """True iff value is a finite, strictly positive float."""
    return math.isfinite(value) and value > 0.0


def _side_depth(intent: OrderIntent, book: BookContext) -> float | None:
    """Return the relevant depth for the given intent.

    BUY consumes ask-side liquidity (we lift the offer).
    SELL consumes bid-side liquidity (we hit the bid).
    """
    if intent == OrderIntent.BUY:
        return book.ask_size
    return book.bid_size
