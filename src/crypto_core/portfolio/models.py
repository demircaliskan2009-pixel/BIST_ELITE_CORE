"""Portfolio and position typed models.

PRD reference: §1.21 NT-R rules, §1.26 Margin, §1.28 Kelly.

Design rules:
  - All models are frozen dataclasses.
  - Unavailable upstream fields are typed as ``float | None``; None = "upstream
    data not yet available — not treated as safe".
  - No magic numbers. No silent defaults that imply correctness.
  - These models are consumed by: NoTradeGuard (RiskGuardInput), RiskEngine
    (PortfolioRiskSnapshot), and telemetry emitter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Position side
# ---------------------------------------------------------------------------


class PositionSide(str):
    """Direction of an open position."""

    pass


PositionSide.LONG = PositionSide("long")
PositionSide.SHORT = PositionSide("short")
PositionSide.FLAT = PositionSide("flat")  # no open position on this symbol


# ---------------------------------------------------------------------------
# Single position model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Position:
    """Immutable snapshot of one open position on one symbol.

    Unavailable fields use ``None`` — never fabricated.

    Fields:
      symbol          — trading symbol (e.g. "BTCUSDT")
      exchange        — exchange identifier ("binance" | "bybit")
      side            — LONG | SHORT | FLAT
      quantity        — base-currency size (always positive; direction = side)
      avg_entry_price — volume-weighted average entry price in USD
      mark_price      — current mark price in USD (updated on each tick)
      leverage        — leverage used for this position [1, 3]
      unrealized_pnl  — mark-to-market PnL in USD (signed)
      realized_pnl    — closed-position PnL accumulated this day in USD (signed)
      notional_usd    — quantity × mark_price in USD (always positive)
      position_risk_pct  — notional_usd / nav × 100 (%); None if nav unavailable
      liquidation_price  — exchange-supplied liq price in USD; None if unavailable
      dtl_pct            — |mark − liq| / mark × 100; None if liq unavailable
      snapshot_ns        — timestamp this snapshot was produced (ns)
    """

    symbol: str
    exchange: str
    side: PositionSide
    quantity: float  # base-currency size, ≥ 0
    avg_entry_price: float  # USD
    mark_price: float  # USD
    leverage: float  # [1.0, 3.0]
    unrealized_pnl: float  # USD, signed
    realized_pnl: float  # USD accumulated today, signed
    notional_usd: float  # USD, always ≥ 0
    snapshot_ns: int  # wall-clock in ns

    # Optional fields — None = upstream data not available
    position_risk_pct: float | None = None  # % of NAV
    liquidation_price: float | None = None  # USD from exchange
    dtl_pct: float | None = None  # % distance-to-liquidation

    @property
    def is_open(self) -> bool:
        """True when the position has non-zero quantity."""
        return self.side != PositionSide.FLAT and self.quantity > 0.0


# ---------------------------------------------------------------------------
# Portfolio snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Portfolio-level state at a point in time.

    Produced by PositionTracker on demand.  Suitable for:
      - NoTradeGuard RiskGuardInput construction
      - RiskEngine PortfolioRiskSnapshot construction
      - Telemetry emission

    All optional fields represent data that requires upstream components not
    yet implemented.  They must not be silently defaulted to safe values —
    callers that receive None must propagate None.

    Fields:
      nav_usd                  — net asset value (equity) in USD
      cash_usd                 — unallocated cash balance in USD
      total_notional_usd       — sum of all position notionals in USD
      gross_exposure_pct       — total_notional_usd / nav × 100 (%)
      net_exposure_pct         — net directional exposure / nav × 100 (%)
      open_risk_pct            — sum of position_risk_pct across open positions;
                                 None if any position lacks risk_pct
      daily_realized_pnl_usd   — sum of today's realized PnL across all positions
      daily_realized_pnl_pct   — daily_realized_pnl_usd / nav × 100 (signed %)
      total_unrealized_pnl_usd — sum of unrealized PnL across all positions
      concentration_max_pct    — largest single position as % of NAV
      active_position_count    — number of positions with quantity > 0
      max_leverage_in_use      — highest leverage of any open position
      margin_used_pct          — used_margin / available_margin × 100 (%);
                                 None if exchange margin data unavailable
      dtl_available_count      — number of positions that have a valid dtl_pct
      snapshot_ns              — wall-clock in ns when snapshot was produced
      positions                — tuple of all open Position objects
    """

    nav_usd: float  # USD
    cash_usd: float  # USD
    total_notional_usd: float  # USD
    gross_exposure_pct: float  # %
    net_exposure_pct: float  # %
    daily_realized_pnl_usd: float  # USD, signed
    daily_realized_pnl_pct: float  # %, signed
    total_unrealized_pnl_usd: float  # USD, signed
    concentration_max_pct: float  # %
    active_position_count: int
    max_leverage_in_use: float
    snapshot_ns: int

    # Optional fields — None = upstream not available
    open_risk_pct: float | None  # %
    margin_used_pct: float | None  # %

    # Audit / trace
    dtl_available_count: int = 0
    positions: tuple[Position, ...] = field(default_factory=tuple)
