"""Transaction Cost Analysis (TCA) models — execution measurement closure.

Per-order TCA records capturing decision-price-to-fill-price shortfall,
expected vs realized slippage, maker/taker classification, partial fill
accounting, signed markout curves, venue-specific aggregation, and
stress-regime segmentation.

Design rules:
  - All models are frozen dataclasses (deterministic, hashable, auditable).
  - Missing data is explicitly None — never zero, never estimated.
  - Fail-closed: if required price data is unavailable, computation returns
    an explicit unavailable state rather than a fabricated result.
  - Markout horizons are configurable but default to 1s, 5s, 30s, 300s.
  - All basis-point values are signed (positive = cost, negative = benefit
    for shortfall; positive = favorable, negative = adverse for markout).

PRD reference: §7 Execution Engine, Research Memory §2 TCA Requirements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FillRole(str, Enum):
    """Whether the fill was passive (maker) or aggressive (taker)."""

    MAKER = "maker"
    TAKER = "taker"
    UNKNOWN = "unknown"


class TCAStatus(str, Enum):
    """Completeness state of a TCA record.

    COMPLETE:   All required fields populated, markout horizons filled.
    PARTIAL:    Core shortfall computed, some markout horizons pending.
    PENDING:    Fill recorded, awaiting subsequent mid-price for markout.
    UNAVAILABLE: Required reference price missing — cannot compute TCA.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"


class RegimeTag(str, Enum):
    """Regime classification at fill time for TCA segmentation."""

    NORMAL = "normal"
    HIGH_VOL = "high_vol"
    LOW_LIQ = "low_liq"
    STRESS = "stress"
    EVENT = "event"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Markout observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarkoutObservation:
    """Single markout measurement at a specific horizon after fill.

    mid_price_at_horizon: mid-price observed at fill_time + horizon_seconds.
    markout_bps: signed price change in bps from fill perspective.
      For a BUY:  markout_bps = (mid_at_horizon - fill_price) / fill_price × 10000
      For a SELL: markout_bps = (fill_price - mid_at_horizon) / fill_price × 10000
      Positive = favorable (price moved in fill direction).
      Negative = adverse selection (price moved against fill direction).
    """

    horizon_seconds: int
    mid_price_at_horizon: float | None  # None = not yet observed
    markout_bps: float | None  # None = cannot compute

    @property
    def is_available(self) -> bool:
        return self.mid_price_at_horizon is not None and self.markout_bps is not None


#: Default markout horizons in seconds.
DEFAULT_MARKOUT_HORIZONS: tuple[int, ...] = (1, 5, 30, 300)


# ---------------------------------------------------------------------------
# Per-order TCA record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TCARecord:
    """Immutable per-order transaction cost analysis record.

    Core shortfall:
      decision_price: mid-price at signal generation time.
      arrival_price:  mid-price when order reaches venue / is submitted.
      execution_price: actual (or simulated) fill price.
      implementation_shortfall_bps: (exec - decision) / decision × 10000 (signed).
      arrival_shortfall_bps: (exec - arrival) / arrival × 10000 (signed).
        For BUY: positive = overpaid. For SELL: sign is flipped internally.

    Slippage decomposition:
      expected_slippage_bps: pre-trade model estimate.
      realized_slippage_bps: actual cost from mid at fill time.
      slippage_surprise_bps: realized - expected.
      spread_cost_bps: half-spread component.
      impact_cost_bps: market impact component.

    Cost components:
      fee_cost_bps: exchange fee (maker/taker) in bps.
      funding_cost_bps: pro-rated funding cost over expected hold period.

    Fill quality:
      fill_ratio: filled_quantity / requested_quantity [0, 1].
      filled_quantity: base-currency amount actually filled.
      requested_quantity: base-currency amount originally requested.
      fill_role: maker / taker / unknown.

    Markout curve:
      markouts: tuple of MarkoutObservation at configured horizons.

    Context:
      order_id: execution engine order_id.
      symbol: trading pair.
      exchange: venue identifier.
      intent: BUY or SELL.
      regime_tag: regime at fill time.
      event_tag: event active at fill time (None if no event).
      timestamp_ns: fill timestamp.
      status: completeness state of this record.
    """

    # --- Identity ---
    order_id: str
    symbol: str
    exchange: str
    intent: str  # "buy" or "sell"
    timestamp_ns: int
    status: TCAStatus

    # --- Core shortfall (None if reference prices unavailable) ---
    decision_price: float | None = None
    arrival_price: float | None = None
    execution_price: float | None = None
    implementation_shortfall_bps: float | None = None
    arrival_shortfall_bps: float | None = None

    # --- Slippage decomposition ---
    expected_slippage_bps: float | None = None
    realized_slippage_bps: float | None = None
    slippage_surprise_bps: float | None = None
    spread_cost_bps: float | None = None
    impact_cost_bps: float | None = None

    # --- Fee / funding ---
    fee_cost_bps: float | None = None
    funding_cost_bps: float | None = None

    # --- Fill quality ---
    fill_ratio: float | None = None
    filled_quantity: float | None = None
    requested_quantity: float | None = None
    fill_role: FillRole = FillRole.UNKNOWN

    # --- Markout curve ---
    markouts: tuple[MarkoutObservation, ...] = ()

    # --- Context ---
    regime_tag: RegimeTag = RegimeTag.UNKNOWN
    event_tag: str | None = None

    # --- Audit ---
    evidence: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TCA computation helpers
# ---------------------------------------------------------------------------


def compute_shortfall_bps(
    reference_price: float | None,
    execution_price: float | None,
    is_buy: bool,
) -> float | None:
    """Compute signed shortfall in bps.

    For BUY: positive = overpaid (exec > ref).
    For SELL: positive = undersold (exec < ref).

    Returns None if either price is None or reference is non-positive.
    """
    if reference_price is None or execution_price is None:
        return None
    if reference_price <= 0.0:
        return None
    raw_bps = (execution_price - reference_price) / reference_price * 10_000.0
    return raw_bps if is_buy else -raw_bps


def compute_markout_bps(
    fill_price: float,
    mid_price_at_horizon: float | None,
    is_buy: bool,
) -> float | None:
    """Compute signed markout in bps.

    Positive = favorable (price moved in fill direction after fill).
    Negative = adverse selection.

    Returns None if mid_price_at_horizon is None or fill_price non-positive.
    """
    if mid_price_at_horizon is None or fill_price <= 0.0:
        return None
    raw_bps = (mid_price_at_horizon - fill_price) / fill_price * 10_000.0
    return raw_bps if is_buy else -raw_bps


def build_tca_record(
    *,
    order_id: str,
    symbol: str,
    exchange: str,
    intent: str,
    timestamp_ns: int,
    decision_price: float | None = None,
    arrival_price: float | None = None,
    execution_price: float | None = None,
    expected_slippage_bps: float | None = None,
    spread_cost_bps: float | None = None,
    impact_cost_bps: float | None = None,
    fee_cost_bps: float | None = None,
    funding_cost_bps: float | None = None,
    filled_quantity: float | None = None,
    requested_quantity: float | None = None,
    fill_role: FillRole = FillRole.UNKNOWN,
    markout_mids: dict[int, float | None] | None = None,
    regime_tag: RegimeTag = RegimeTag.UNKNOWN,
    event_tag: str | None = None,
) -> TCARecord:
    """Build a TCA record with deterministic computation of all derived fields.

    This is the primary factory function. It computes shortfall, slippage
    surprise, fill ratio, and markout curve from raw inputs.

    Args:
        markout_mids: dict mapping horizon_seconds → mid_price_at_horizon.
            None values mean that horizon has not been observed yet.

    Returns:
        TCARecord with all computable fields populated.
        Fields that cannot be computed are explicitly None.
    """
    is_buy = intent == "buy"

    # --- Shortfall ---
    impl_shortfall = compute_shortfall_bps(decision_price, execution_price, is_buy)
    arr_shortfall = compute_shortfall_bps(arrival_price, execution_price, is_buy)

    # --- Realized slippage (from mid at fill time = arrival_price) ---
    realized_slippage = arr_shortfall  # arrival shortfall IS the realized slippage

    # --- Slippage surprise ---
    slippage_surprise: float | None = None
    if realized_slippage is not None and expected_slippage_bps is not None:
        slippage_surprise = realized_slippage - expected_slippage_bps

    # --- Fill ratio ---
    fill_ratio: float | None = None
    if filled_quantity is not None and requested_quantity is not None and requested_quantity > 0.0:
        fill_ratio = min(filled_quantity / requested_quantity, 1.0)

    # --- Markout curve ---
    markouts: list[MarkoutObservation] = []
    if markout_mids is not None and execution_price is not None:
        for horizon in sorted(markout_mids):
            mid_at_h = markout_mids[horizon]
            m_bps = compute_markout_bps(execution_price, mid_at_h, is_buy)
            markouts.append(
                MarkoutObservation(
                    horizon_seconds=horizon,
                    mid_price_at_horizon=mid_at_h,
                    markout_bps=m_bps,
                )
            )

    # --- Status ---
    if execution_price is None or decision_price is None:
        status = TCAStatus.UNAVAILABLE
    elif not markouts or all(not m.is_available for m in markouts):
        status = TCAStatus.PENDING
    elif all(m.is_available for m in markouts):
        status = TCAStatus.COMPLETE
    else:
        status = TCAStatus.PARTIAL

    evidence: dict[str, object] = {
        "builder": "build_tca_record",
        "computed_at_ns": time.time_ns(),
    }

    return TCARecord(
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        intent=intent,
        timestamp_ns=timestamp_ns,
        status=status,
        decision_price=decision_price,
        arrival_price=arrival_price,
        execution_price=execution_price,
        implementation_shortfall_bps=impl_shortfall,
        arrival_shortfall_bps=arr_shortfall,
        expected_slippage_bps=expected_slippage_bps,
        realized_slippage_bps=realized_slippage,
        slippage_surprise_bps=slippage_surprise,
        spread_cost_bps=spread_cost_bps,
        impact_cost_bps=impact_cost_bps,
        fee_cost_bps=fee_cost_bps,
        funding_cost_bps=funding_cost_bps,
        fill_ratio=fill_ratio,
        filled_quantity=filled_quantity,
        requested_quantity=requested_quantity,
        fill_role=fill_role,
        markouts=tuple(markouts),
        regime_tag=regime_tag,
        event_tag=event_tag,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# TCA aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TCAAggregation:
    """Aggregated TCA statistics over a set of records.

    Used for venue-level, symbol-level, or regime-level reporting.
    All averages are fill-ratio-weighted where fill_ratio is available.
    """

    group_key: str  # e.g. "binance", "BTCUSDT", "stress"
    record_count: int
    avg_implementation_shortfall_bps: float | None
    avg_arrival_shortfall_bps: float | None
    avg_realized_slippage_bps: float | None
    avg_slippage_surprise_bps: float | None
    avg_spread_cost_bps: float | None
    avg_impact_cost_bps: float | None
    avg_fee_cost_bps: float | None
    avg_fill_ratio: float | None
    maker_count: int
    taker_count: int
    # Markout averages by horizon
    avg_markout_by_horizon: dict[int, float | None] = field(default_factory=dict)
    complete_count: int = 0
    partial_count: int = 0
    pending_count: int = 0
    unavailable_count: int = 0


def aggregate_tca_records(
    records: list[TCARecord],
    group_key: str,
) -> TCAAggregation:
    """Aggregate a list of TCA records into summary statistics.

    Simple arithmetic mean for each metric. Records with None values for a
    given metric are excluded from that metric's average.

    Returns TCAAggregation. If records is empty, all averages are None.
    """
    n = len(records)
    if n == 0:
        return TCAAggregation(
            group_key=group_key,
            record_count=0,
            avg_implementation_shortfall_bps=None,
            avg_arrival_shortfall_bps=None,
            avg_realized_slippage_bps=None,
            avg_slippage_surprise_bps=None,
            avg_spread_cost_bps=None,
            avg_impact_cost_bps=None,
            avg_fee_cost_bps=None,
            avg_fill_ratio=None,
            maker_count=0,
            taker_count=0,
        )

    def _avg(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        return sum(valid) / len(valid) if valid else None

    # Markout aggregation
    horizon_values: dict[int, list[float]] = {}
    for r in records:
        for m in r.markouts:
            if m.markout_bps is not None:
                horizon_values.setdefault(m.horizon_seconds, []).append(m.markout_bps)

    avg_markout: dict[int, float | None] = {}
    for h, vals in sorted(horizon_values.items()):
        avg_markout[h] = sum(vals) / len(vals) if vals else None

    # Status counts
    status_counts = dict.fromkeys(TCAStatus, 0)
    for r in records:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    return TCAAggregation(
        group_key=group_key,
        record_count=n,
        avg_implementation_shortfall_bps=_avg([r.implementation_shortfall_bps for r in records]),
        avg_arrival_shortfall_bps=_avg([r.arrival_shortfall_bps for r in records]),
        avg_realized_slippage_bps=_avg([r.realized_slippage_bps for r in records]),
        avg_slippage_surprise_bps=_avg([r.slippage_surprise_bps for r in records]),
        avg_spread_cost_bps=_avg([r.spread_cost_bps for r in records]),
        avg_impact_cost_bps=_avg([r.impact_cost_bps for r in records]),
        avg_fee_cost_bps=_avg([r.fee_cost_bps for r in records]),
        avg_fill_ratio=_avg([r.fill_ratio for r in records]),
        maker_count=sum(1 for r in records if r.fill_role == FillRole.MAKER),
        taker_count=sum(1 for r in records if r.fill_role == FillRole.TAKER),
        avg_markout_by_horizon=avg_markout,
        complete_count=status_counts.get(TCAStatus.COMPLETE, 0),
        partial_count=status_counts.get(TCAStatus.PARTIAL, 0),
        pending_count=status_counts.get(TCAStatus.PENDING, 0),
        unavailable_count=status_counts.get(TCAStatus.UNAVAILABLE, 0),
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def tca_record_to_dict(record: TCARecord) -> dict:
    """Serialize a TCARecord to a plain dict for JSONL persistence."""
    markout_list = []
    for m in record.markouts:
        markout_list.append(
            {
                "horizon_seconds": m.horizon_seconds,
                "mid_price_at_horizon": m.mid_price_at_horizon,
                "markout_bps": m.markout_bps,
            }
        )

    return {
        "order_id": record.order_id,
        "symbol": record.symbol,
        "exchange": record.exchange,
        "intent": record.intent,
        "timestamp_ns": record.timestamp_ns,
        "status": record.status.value,
        "decision_price": record.decision_price,
        "arrival_price": record.arrival_price,
        "execution_price": record.execution_price,
        "implementation_shortfall_bps": record.implementation_shortfall_bps,
        "arrival_shortfall_bps": record.arrival_shortfall_bps,
        "expected_slippage_bps": record.expected_slippage_bps,
        "realized_slippage_bps": record.realized_slippage_bps,
        "slippage_surprise_bps": record.slippage_surprise_bps,
        "spread_cost_bps": record.spread_cost_bps,
        "impact_cost_bps": record.impact_cost_bps,
        "fee_cost_bps": record.fee_cost_bps,
        "funding_cost_bps": record.funding_cost_bps,
        "fill_ratio": record.fill_ratio,
        "filled_quantity": record.filled_quantity,
        "requested_quantity": record.requested_quantity,
        "fill_role": record.fill_role.value,
        "markouts": markout_list,
        "regime_tag": record.regime_tag.value,
        "event_tag": record.event_tag,
    }


def tca_record_from_dict(d: dict) -> TCARecord:
    """Deserialize a TCARecord from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        markouts = tuple(
            MarkoutObservation(
                horizon_seconds=int(m["horizon_seconds"]),
                mid_price_at_horizon=m.get("mid_price_at_horizon"),
                markout_bps=m.get("markout_bps"),
            )
            for m in d.get("markouts", [])
        )
        return TCARecord(
            order_id=str(d["order_id"]),
            symbol=str(d["symbol"]),
            exchange=str(d["exchange"]),
            intent=str(d["intent"]),
            timestamp_ns=int(d["timestamp_ns"]),
            status=TCAStatus(d["status"]),
            decision_price=d.get("decision_price"),
            arrival_price=d.get("arrival_price"),
            execution_price=d.get("execution_price"),
            implementation_shortfall_bps=d.get("implementation_shortfall_bps"),
            arrival_shortfall_bps=d.get("arrival_shortfall_bps"),
            expected_slippage_bps=d.get("expected_slippage_bps"),
            realized_slippage_bps=d.get("realized_slippage_bps"),
            slippage_surprise_bps=d.get("slippage_surprise_bps"),
            spread_cost_bps=d.get("spread_cost_bps"),
            impact_cost_bps=d.get("impact_cost_bps"),
            fee_cost_bps=d.get("fee_cost_bps"),
            funding_cost_bps=d.get("funding_cost_bps"),
            fill_ratio=d.get("fill_ratio"),
            filled_quantity=d.get("filled_quantity"),
            requested_quantity=d.get("requested_quantity"),
            fill_role=FillRole(d.get("fill_role", "unknown")),
            markouts=markouts,
            regime_tag=RegimeTag(d.get("regime_tag", "unknown")),
            event_tag=d.get("event_tag"),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed TCA record dict: {exc}") from exc
