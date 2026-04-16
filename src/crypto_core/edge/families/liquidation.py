"""Liquidation Signal edge family (Family C) — liquidation-feed driven v1.

This phase stops relying on trade flow alone. The family now consumes real
LiquidationEvent inputs when available and fails closed when the liquidation
feed is absent from the runtime path.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.models.events import LiquidationEvent, TradeEvent, TradeSide
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection

_NS_PER_MINUTE: int = 60 * 1_000_000_000


@dataclass
class LiquidationConfig:
    """Configuration for the liquidation-feed evaluator.

    Legacy trade-proxy fields are retained for backward-compatible
    construction, but the phase-6C runtime path only treats liquidation events
    as tradable evidence.
    """

    min_events: int = 3
    min_total_liquidation_qty: float = 5.0
    imbalance_threshold: float = 0.60
    building_acceleration_threshold: float = 1.5
    active_acceleration_threshold: float = 3.0
    exhausting_ratio_threshold: float = 0.30
    complete_ratio_threshold: float = 0.10
    bucket_ns: int = _NS_PER_MINUTE
    max_buckets: int = 8
    window: int = 20
    baseline_window: int = 100
    price_threshold: float = 0.005
    vol_spike_threshold: float = 2.0
    min_trades: int = 21


class LiquidationSignalEdge:
    """Liquidation-family evaluator using real liquidation events."""

    def __init__(self, config: LiquidationConfig | None = None) -> None:
        self._cfg = config or LiquidationConfig()

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
        liquidation_events: list[LiquidationEvent] | tuple[LiquidationEvent, ...] | None = None,
    ) -> EdgeSignal:
        family = EdgeFamily.LIQUIDATION_SIGNAL
        cfg = self._cfg

        if liquidation_events is None:
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                "liquidation_feed_unavailable",
                timestamp_ns,
                {
                    "status": "unavailable",
                    "missing_inputs": ["liquidation_events"],
                },
            )

        events = sorted(liquidation_events, key=lambda event: event.timestamp_ns)
        if not events:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=0.0,
                evidence={
                    "status": "neutral",
                    "cascade_state": "NORMAL",
                    "liquidation_event_count": 0,
                    "total_liquidation_qty": 0.0,
                },
                timestamp_ns=timestamp_ns,
                is_valid=True,
                block_reason=None,
            )

        long_liq_qty = sum(event.qty for event in events if event.side == TradeSide.BUY)
        short_liq_qty = sum(event.qty for event in events if event.side == TradeSide.SELL)
        total_liq_qty = long_liq_qty + short_liq_qty
        imbalance = 0.0 if total_liq_qty <= 0.0 else (long_liq_qty - short_liq_qty) / total_liq_qty
        bucket_totals = _bucket_quantities(events, timestamp_ns, cfg.bucket_ns, cfg.max_buckets)
        peak_bucket_qty = max(bucket_totals) if bucket_totals else 0.0
        recent_bucket_qty = bucket_totals[-1] if bucket_totals else total_liq_qty
        baseline_buckets = bucket_totals[:-1]
        baseline_mean = (sum(baseline_buckets) / len(baseline_buckets)) if baseline_buckets else 0.0
        acceleration_ratio = (
            (recent_bucket_qty / baseline_mean)
            if baseline_mean > 0.0
            else (float("inf") if recent_bucket_qty > 0.0 else 0.0)
        )
        last_three = bucket_totals[-3:] if len(bucket_totals) >= 3 else []

        evidence: dict[str, object] = {
            "status": "active",
            "liquidation_event_count": len(events),
            "total_liquidation_qty": total_liq_qty,
            "long_liquidation_qty": long_liq_qty,
            "short_liquidation_qty": short_liq_qty,
            "liquidation_imbalance": imbalance,
            "bucket_totals": bucket_totals,
            "recent_bucket_qty": recent_bucket_qty,
            "peak_bucket_qty": peak_bucket_qty,
            "acceleration_ratio": acceleration_ratio,
        }

        if len(events) < cfg.min_events or total_liq_qty < cfg.min_total_liquidation_qty:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=0.0,
                evidence={
                    **evidence,
                    "status": "neutral",
                    "cascade_state": "NORMAL",
                    "reason": "insufficient_liquidation_pressure",
                },
                timestamp_ns=timestamp_ns,
                is_valid=True,
                block_reason=None,
            )

        cascade_state = "NORMAL"
        if acceleration_ratio >= cfg.active_acceleration_threshold:
            cascade_state = "ACTIVE_CASCADE"
        elif acceleration_ratio >= cfg.building_acceleration_threshold:
            cascade_state = "BUILDING"
        elif (
            peak_bucket_qty > 0.0
            and len(last_three) == 3
            and all(bucket_qty <= cfg.complete_ratio_threshold * peak_bucket_qty for bucket_qty in last_three)
        ):
            cascade_state = "CASCADE_COMPLETE"
        elif peak_bucket_qty > 0.0 and recent_bucket_qty <= cfg.exhausting_ratio_threshold * peak_bucket_qty:
            cascade_state = "EXHAUSTING"

        evidence["cascade_state"] = cascade_state

        if cascade_state == "ACTIVE_CASCADE":
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                "liquidation_cascade_active",
                timestamp_ns,
                {**evidence, "status": "blocked"},
            )
        if cascade_state == "BUILDING":
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                "liquidation_cascade_building",
                timestamp_ns,
                {**evidence, "status": "blocked"},
            )
        if cascade_state != "CASCADE_COMPLETE" or abs(imbalance) < cfg.imbalance_threshold:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=0.0,
                evidence={
                    **evidence,
                    "status": "neutral",
                    "dominant_side_ready": abs(imbalance) >= cfg.imbalance_threshold,
                },
                timestamp_ns=timestamp_ns,
                is_valid=True,
                block_reason=None,
            )

        direction = SignalDirection.BUY if imbalance > 0 else SignalDirection.SELL
        confidence = min(1.0, abs(imbalance) * min(1.0, peak_bucket_qty / cfg.min_total_liquidation_qty))

        return EdgeSignal(
            family=family,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            confidence=confidence,
            score=imbalance,
            evidence=evidence,
            timestamp_ns=timestamp_ns,
            is_valid=True,
            block_reason=None,
        )


def _bucket_quantities(
    events: list[LiquidationEvent],
    current_ns: int,
    bucket_ns: int,
    max_buckets: int,
) -> list[float]:
    if bucket_ns <= 0 or max_buckets <= 0:
        return []
    buckets = [0.0 for _ in range(max_buckets)]
    window_start = current_ns - bucket_ns * max_buckets
    for event in events:
        if event.timestamp_ns < window_start or event.timestamp_ns > current_ns:
            continue
        idx = int((event.timestamp_ns - window_start) // bucket_ns)
        idx = max(0, min(max_buckets - 1, idx))
        buckets[idx] += float(event.qty)
    return buckets
