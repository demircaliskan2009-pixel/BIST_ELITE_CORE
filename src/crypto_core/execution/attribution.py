"""Attribution decomposition primitives — performance measurement foundation.

Decomposes realized trade performance into constituent components:
forecast alpha, fees, funding, slippage, markout, venue contribution,
execution-mode contribution, and regime/event tags.

Design rules:
  - All models are frozen dataclasses (deterministic, hashable, auditable).
  - Total attributed components must reconcile with actual PnL.
  - If decomposition does not sum to total within tolerance, flag as
    ATTRIBUTION_DRIFT (fail-closed for accounting).
  - Missing components are explicitly None — never zero unless measured.
  - Aggregation helpers are deterministic (same input → same output).

PRD reference: §7 Execution Engine, Research Memory §10 Attribution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AttributionStatus(str, Enum):
    """Completeness state of an attribution record."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    DRIFT = "drift"  # decomposition doesn't sum to total
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Per-trade attribution record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeAttribution:
    """Immutable per-trade performance decomposition.

    All component values are in basis points relative to notional.
    Positive = benefit / profit contribution.
    Negative = cost / loss contribution.

    The algebraic identity that must hold:
      total_pnl_bps ≈ forecast_alpha_bps
                     + fees_bps
                     + funding_bps
                     + slippage_bps
                     + markout_bps
                     + venue_contribution_bps
                     + execution_mode_bps
                     + residual_bps

    residual_bps captures any unexplained component. If abs(residual_bps) >
    drift_tolerance_bps, status = DRIFT.
    """

    # --- Identity ---
    order_id: str
    symbol: str
    exchange: str
    intent: str  # "buy" or "sell"
    timestamp_ns: int
    status: AttributionStatus

    # --- Realized PnL (ground truth) ---
    total_pnl_bps: float | None = None

    # --- Decomposition components (all in bps) ---
    forecast_alpha_bps: float | None = None  # signal strength at decision time
    fees_bps: float | None = None  # exchange fees (negative = cost)
    funding_bps: float | None = None  # funding cost/benefit over hold
    slippage_bps: float | None = None  # decision-to-fill price gap
    markout_bps: float | None = None  # post-fill adverse selection
    venue_contribution_bps: float | None = None  # venue-specific quality vs avg
    execution_mode_bps: float | None = None  # maker/taker choice quality
    residual_bps: float | None = None  # unexplained component

    # --- Context tags ---
    regime_tag: str = "unknown"
    event_tag: str | None = None
    execution_mode: str = "unknown"  # "maker" / "taker" / "unknown"
    hold_duration_s: float | None = None

    # --- Audit ---
    evidence: dict[str, object] = field(default_factory=dict)


#: Default drift tolerance in bps. If residual exceeds this, flag DRIFT.
DRIFT_TOLERANCE_BPS: float = 0.01


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_trade_attribution(
    *,
    order_id: str,
    symbol: str,
    exchange: str,
    intent: str,
    timestamp_ns: int,
    total_pnl_bps: float | None = None,
    forecast_alpha_bps: float | None = None,
    fees_bps: float | None = None,
    funding_bps: float | None = None,
    slippage_bps: float | None = None,
    markout_bps: float | None = None,
    venue_contribution_bps: float | None = None,
    execution_mode_bps: float | None = None,
    regime_tag: str = "unknown",
    event_tag: str | None = None,
    execution_mode: str = "unknown",
    hold_duration_s: float | None = None,
    drift_tolerance_bps: float = DRIFT_TOLERANCE_BPS,
) -> TradeAttribution:
    """Build a trade attribution record with residual computation.

    Computes residual_bps as:
      total_pnl_bps - sum(all non-None components)

    If total_pnl_bps is None → status = UNAVAILABLE.
    If any component is None → status = PARTIAL (some decomposition missing).
    If abs(residual_bps) > drift_tolerance_bps → status = DRIFT.
    Otherwise → status = COMPLETE.
    """
    if total_pnl_bps is None:
        return TradeAttribution(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            intent=intent,
            timestamp_ns=timestamp_ns,
            status=AttributionStatus.UNAVAILABLE,
            total_pnl_bps=None,
            forecast_alpha_bps=forecast_alpha_bps,
            fees_bps=fees_bps,
            funding_bps=funding_bps,
            slippage_bps=slippage_bps,
            markout_bps=markout_bps,
            venue_contribution_bps=venue_contribution_bps,
            execution_mode_bps=execution_mode_bps,
            residual_bps=None,
            regime_tag=regime_tag,
            event_tag=event_tag,
            execution_mode=execution_mode,
            hold_duration_s=hold_duration_s,
            evidence={"builder": "build_trade_attribution", "computed_at_ns": time.time_ns()},
        )

    # Sum all non-None components
    components = [
        forecast_alpha_bps,
        fees_bps,
        funding_bps,
        slippage_bps,
        markout_bps,
        venue_contribution_bps,
        execution_mode_bps,
    ]
    non_none = [c for c in components if c is not None]
    any_missing = len(non_none) < len(components)
    component_sum = sum(non_none)
    residual = total_pnl_bps - component_sum

    # Determine status
    if any_missing:
        status = AttributionStatus.PARTIAL
    elif abs(residual) > drift_tolerance_bps:
        status = AttributionStatus.DRIFT
    else:
        status = AttributionStatus.COMPLETE

    return TradeAttribution(
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        intent=intent,
        timestamp_ns=timestamp_ns,
        status=status,
        total_pnl_bps=total_pnl_bps,
        forecast_alpha_bps=forecast_alpha_bps,
        fees_bps=fees_bps,
        funding_bps=funding_bps,
        slippage_bps=slippage_bps,
        markout_bps=markout_bps,
        venue_contribution_bps=venue_contribution_bps,
        execution_mode_bps=execution_mode_bps,
        residual_bps=round(residual, 6),
        regime_tag=regime_tag,
        event_tag=event_tag,
        execution_mode=execution_mode,
        hold_duration_s=hold_duration_s,
        evidence={
            "builder": "build_trade_attribution",
            "component_sum": round(component_sum, 6),
            "residual": round(residual, 6),
            "drift_tolerance_bps": drift_tolerance_bps,
            "components_provided": len(non_none),
            "components_total": len(components),
            "computed_at_ns": time.time_ns(),
        },
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributionAggregation:
    """Aggregated attribution statistics over a group of trades.

    All averages are simple arithmetic mean of non-None values.
    """

    group_key: str  # e.g. "binance", "BTCUSDT", "stress", "maker"
    record_count: int
    avg_total_pnl_bps: float | None
    avg_forecast_alpha_bps: float | None
    avg_fees_bps: float | None
    avg_funding_bps: float | None
    avg_slippage_bps: float | None
    avg_markout_bps: float | None
    avg_venue_contribution_bps: float | None
    avg_execution_mode_bps: float | None
    avg_residual_bps: float | None
    complete_count: int = 0
    partial_count: int = 0
    drift_count: int = 0
    unavailable_count: int = 0


def aggregate_attributions(
    records: list[TradeAttribution],
    group_key: str,
) -> AttributionAggregation:
    """Aggregate a list of TradeAttribution records into summary statistics.

    Returns AttributionAggregation. Empty input → all averages None.
    """
    n = len(records)
    if n == 0:
        return AttributionAggregation(
            group_key=group_key,
            record_count=0,
            avg_total_pnl_bps=None,
            avg_forecast_alpha_bps=None,
            avg_fees_bps=None,
            avg_funding_bps=None,
            avg_slippage_bps=None,
            avg_markout_bps=None,
            avg_venue_contribution_bps=None,
            avg_execution_mode_bps=None,
            avg_residual_bps=None,
        )

    def _avg(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        return sum(valid) / len(valid) if valid else None

    status_counts = dict.fromkeys(AttributionStatus, 0)
    for r in records:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    return AttributionAggregation(
        group_key=group_key,
        record_count=n,
        avg_total_pnl_bps=_avg([r.total_pnl_bps for r in records]),
        avg_forecast_alpha_bps=_avg([r.forecast_alpha_bps for r in records]),
        avg_fees_bps=_avg([r.fees_bps for r in records]),
        avg_funding_bps=_avg([r.funding_bps for r in records]),
        avg_slippage_bps=_avg([r.slippage_bps for r in records]),
        avg_markout_bps=_avg([r.markout_bps for r in records]),
        avg_venue_contribution_bps=_avg([r.venue_contribution_bps for r in records]),
        avg_execution_mode_bps=_avg([r.execution_mode_bps for r in records]),
        avg_residual_bps=_avg([r.residual_bps for r in records]),
        complete_count=status_counts.get(AttributionStatus.COMPLETE, 0),
        partial_count=status_counts.get(AttributionStatus.PARTIAL, 0),
        drift_count=status_counts.get(AttributionStatus.DRIFT, 0),
        unavailable_count=status_counts.get(AttributionStatus.UNAVAILABLE, 0),
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def attribution_to_dict(record: TradeAttribution) -> dict:
    """Serialize a TradeAttribution to a plain dict for persistence."""
    return {
        "order_id": record.order_id,
        "symbol": record.symbol,
        "exchange": record.exchange,
        "intent": record.intent,
        "timestamp_ns": record.timestamp_ns,
        "status": record.status.value,
        "total_pnl_bps": record.total_pnl_bps,
        "forecast_alpha_bps": record.forecast_alpha_bps,
        "fees_bps": record.fees_bps,
        "funding_bps": record.funding_bps,
        "slippage_bps": record.slippage_bps,
        "markout_bps": record.markout_bps,
        "venue_contribution_bps": record.venue_contribution_bps,
        "execution_mode_bps": record.execution_mode_bps,
        "residual_bps": record.residual_bps,
        "regime_tag": record.regime_tag,
        "event_tag": record.event_tag,
        "execution_mode": record.execution_mode,
        "hold_duration_s": record.hold_duration_s,
    }


def attribution_from_dict(d: dict) -> TradeAttribution:
    """Deserialize a TradeAttribution from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        return TradeAttribution(
            order_id=str(d["order_id"]),
            symbol=str(d["symbol"]),
            exchange=str(d["exchange"]),
            intent=str(d["intent"]),
            timestamp_ns=int(d["timestamp_ns"]),
            status=AttributionStatus(d["status"]),
            total_pnl_bps=d.get("total_pnl_bps"),
            forecast_alpha_bps=d.get("forecast_alpha_bps"),
            fees_bps=d.get("fees_bps"),
            funding_bps=d.get("funding_bps"),
            slippage_bps=d.get("slippage_bps"),
            markout_bps=d.get("markout_bps"),
            venue_contribution_bps=d.get("venue_contribution_bps"),
            execution_mode_bps=d.get("execution_mode_bps"),
            residual_bps=d.get("residual_bps"),
            regime_tag=d.get("regime_tag", "unknown"),
            event_tag=d.get("event_tag"),
            execution_mode=d.get("execution_mode", "unknown"),
            hold_duration_s=d.get("hold_duration_s"),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed attribution dict: {exc}") from exc
