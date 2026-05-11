"""Market regime typed models — Phase 5E.

Provides evidence-aware regime snapshot consumed by:
  - NoTradeGuard (MarketRegimeInput producer for NT-M01–NT-M04)
  - orchestrator telemetry
  - future edge activation matrix (Phase 5F+)

Design invariants:
  - All fields that cannot be computed are explicitly None, never fabricated.
  - Enums used instead of magic strings.
  - All dataclasses are frozen (immutable, hashable, deterministic).
  - No hidden mutable state — all mutable tracking lives in the tracker engine.

PRD reference: §1.21 NT-M family, §1.29 SHS.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LiquidityLevel(str, Enum):
    """Categorical liquidity state derived from a continuous liquidity score.

    Thresholds match the NoTradeConfig defaults:
      CRISIS   → score < 0.15   (NT-M01 blocking zone)
      DEGRADED → 0.15 <= score < 0.50  (watch zone)
      HEALTHY  → score >= 0.50

    These boundaries are intentionally distinct from the guard thresholds
    so the tracker can detect level transitions even when the guard does not
    fire.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRISIS = "crisis"


class RegimeEvidenceQuality(str, Enum):
    """Quality of the evidence backing a regime snapshot.

    FULL        — bid_depth_usd + ask_depth_usd + spread all present.
    PARTIAL     — some optional evidence fields present (depth OR spread).
    MINIMAL     — only level-count proxy available (v1 pipeline default).
    UNAVAILABLE — no computable inputs; all fields will be None.
    """

    FULL = "full"
    PARTIAL = "partial"
    MINIMAL = "minimal"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LiquiditySignal:
    """Point-in-time order book liquidity evidence.

    Mandatory fields (always required):
      bid_level_count    — number of bid levels currently in the book.
      ask_level_count    — number of ask levels currently in the book.
      recent_trade_count — trades observed in the current pipeline window.
      timestamp_ns       — when this observation was taken (ns since epoch).

    Optional richer evidence (unavailable in v1 pipeline — set by external
    depth provider once integrated):
      bid_depth_usd      — total bid-side depth in USD at top N levels.
      ask_depth_usd      — total ask-side depth in USD at top N levels.
      bid_ask_spread_bps — best bid/ask spread in basis points.

    All count fields must be >= 0.  All USD/BPS fields must be >= 0 when
    present.  The regime tracker validates this and raises ValueError on
    violation (fail-closed).
    """

    bid_level_count: int
    ask_level_count: int
    recent_trade_count: int
    timestamp_ns: int

    # Optional richer evidence (v2+ pipeline):
    bid_depth_usd: float | None = None
    ask_depth_usd: float | None = None
    bid_ask_spread_bps: float | None = None


@dataclass(frozen=True)
class RegimeSignalInput:
    """All external inputs to the regime tracker for a single evaluation.

    snapshot_ns: wall-clock for this update (ns since epoch).

    liquidity: order-book evidence. None = no book data available.

    leverage_proxy: externally supplied leverage proxy [0, +inf).
      Used to populate NT-M02 (oi_mc_ratio equivalent).
      None = unavailable.  Do NOT fabricate from internal signals.
      Suitable source: externally supplied open-interest / market-cap ratio.

    correlation_score: externally supplied mean pairwise portfolio correlation
      [-1, 1].  Used to populate NT-M04.
      None = unavailable.  Do NOT fabricate from internal signals.

    Both leverage_proxy and correlation_score remain None in v1 and must be
    explicitly set to None — the guard documents them as skipped.
    """

    snapshot_ns: int
    liquidity: LiquiditySignal | None = None
    leverage_proxy: float | None = None
    correlation_score: float | None = None


@dataclass(frozen=True)
class RegimeSnapshot:
    """Immutable output of one regime tracker evaluation.

    Fields mirror MarketRegimeInput so the orchestrator can map them
    directly to the guard without intermediate transformation.

    Fields that are None are explicitly unavailable — they were not
    fabricated, and the guard will document them as skipped checks.

    snapshot_ns        — matches RegimeSignalInput.snapshot_ns.
    evidence_quality   — summary of how many inputs were available.
    liquidity_score    — [0, 1] normalised; None = no book data.
    liquidity_crisis_sustained_ms — ms below crisis threshold; None = not in
                         crisis or duration unknown (only set when score
                         dropped below crisis level at a known time).
    oi_mc_ratio        — forwarded from leverage_proxy; None = unavailable.
    regime_transition_active — True if regime changed level >=
                         _INSTABILITY_CHANGES_THRESHOLD times in the last
                         _TRANSITION_WINDOW_NS; None = insufficient history
                         (fewer than 2 observations in the tracker).
    mean_pairwise_correlation — forwarded from correlation_score; None = unavailable.
    liquidity_level    — categorical level derived from liquidity_score;
                         None = score unavailable.
    crisis_first_seen_ns — ns when the current crisis episode started;
                         None = not currently in crisis.
    """

    snapshot_ns: int
    evidence_quality: RegimeEvidenceQuality

    # NT-M01
    liquidity_score: float | None
    liquidity_crisis_sustained_ms: float | None

    # NT-M02
    oi_mc_ratio: float | None

    # NT-M03
    regime_transition_active: bool | None

    # NT-M04
    mean_pairwise_correlation: float | None

    # Internal diagnostics (available for telemetry; not passed to guard directly)
    liquidity_level: LiquidityLevel | None
    crisis_first_seen_ns: int | None
