"""Funding Rate edge family (Family B) — PRDV4 safety-hardened paper signal.

Directional funding trades now require explicit safety context.
If the runtime cannot supply the required safety inputs, the family fails closed
for directional trades instead of silently allowing them.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.models.events import MarkPriceEvent, TradeEvent
from crypto_core.edge.activation import RegimeState
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection

_DEFAULT_RATE_THRESHOLD: float = 0.0005
_TREND_STRENGTH_BLOCK: float = 1.5
_RETURN_4H_BLOCK: float = 0.02


@dataclass
class FundingConfig:
    """Configuration for the funding-rate evaluator."""

    rate_threshold: float = _DEFAULT_RATE_THRESHOLD


@dataclass(frozen=True)
class FundingSafetyContext:
    """Runtime safety inputs required for directional funding trades."""

    regime_state: str | None = None
    regime_trending_recently: bool | None = None
    recent_return_4h: float | None = None
    trend_strength: float | None = None


class FundingRateEdge:
    """Deterministic funding-rate evaluator with explicit safety gates."""

    def __init__(self, config: FundingConfig | None = None) -> None:
        self._cfg = config or FundingConfig()

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
        mark_price_event: MarkPriceEvent | None = None,
        safety_context: FundingSafetyContext | None = None,
    ) -> EdgeSignal:
        family = EdgeFamily.FUNDING_RATE
        cfg = self._cfg

        if mark_price_event is None:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=0.0,
                evidence={
                    "status": "unavailable",
                    "reason": "mark_price_event_not_provided",
                    "missing_inputs": ["mark_price_event"],
                },
                timestamp_ns=timestamp_ns,
                is_valid=False,
                block_reason="funding_feed_unavailable",
            )

        rate = mark_price_event.funding_rate
        abs_rate = abs(rate)
        evidence: dict[str, object] = {
            "status": "active",
            "funding_rate": rate,
            "rate_threshold": cfg.rate_threshold,
            "mark_price": mark_price_event.mark_price,
            "index_price": mark_price_event.index_price,
            "next_funding_time_ns": mark_price_event.next_funding_time_ns,
            "safety_context_available": safety_context is not None,
        }

        if abs_rate < cfg.rate_threshold:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=rate,
                evidence={**evidence, "status": "neutral"},
                timestamp_ns=timestamp_ns,
                is_valid=True,
                block_reason=None,
            )

        direction = SignalDirection.SELL if rate > 0 else SignalDirection.BUY
        confidence = min(1.0, (abs_rate - cfg.rate_threshold) / (cfg.rate_threshold * 9))

        blocked = self._validate_safety(direction, safety_context, rate)
        if blocked is not None:
            reason, extra = blocked
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=rate,
                evidence={**evidence, "status": "blocked", **extra},
                timestamp_ns=timestamp_ns,
                is_valid=False,
                block_reason=reason,
            )

        assert safety_context is not None  # guarded by _validate_safety
        return EdgeSignal(
            family=family,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            confidence=confidence,
            score=rate,
            evidence={
                **evidence,
                "regime_state": safety_context.regime_state,
                "regime_trending_recently": safety_context.regime_trending_recently,
                "recent_return_4h": safety_context.recent_return_4h,
                "trend_strength": safety_context.trend_strength,
            },
            timestamp_ns=timestamp_ns,
            is_valid=True,
            block_reason=None,
        )

    @staticmethod
    def _validate_safety(
        direction: SignalDirection,
        safety_context: FundingSafetyContext | None,
        rate: float,
    ) -> tuple[str, dict[str, object]] | None:
        if safety_context is None:
            return "funding_safety_context_unavailable", {"missing_inputs": ["funding_safety_context"]}

        if safety_context.regime_state is None:
            return "funding_regime_state_unavailable", {"missing_inputs": ["regime_state"]}
        if safety_context.regime_state not in (RegimeState.RANGE, RegimeState.HIGH_VOL):
            return (
                f"funding_regime_blocked:{safety_context.regime_state}",
                {"regime_state": safety_context.regime_state},
            )

        if safety_context.regime_trending_recently is None:
            return (
                "funding_transition_context_unavailable",
                {"missing_inputs": ["regime_trending_recently"]},
            )
        if safety_context.regime_trending_recently:
            return "funding_transition_cooldown", {"regime_trending_recently": True}

        if safety_context.recent_return_4h is None:
            return "funding_return_4h_unavailable", {"missing_inputs": ["recent_return_4h"]}
        if safety_context.trend_strength is None:
            return "funding_trend_strength_unavailable", {"missing_inputs": ["trend_strength"]}

        trend_strength = float(safety_context.trend_strength)
        if rate > 0 and trend_strength > _TREND_STRENGTH_BLOCK:
            return "funding_strong_uptrend_blocked", {"trend_strength": trend_strength}
        if rate < 0 and trend_strength < -_TREND_STRENGTH_BLOCK:
            return "funding_strong_downtrend_blocked", {"trend_strength": trend_strength}

        recent_return_4h = float(safety_context.recent_return_4h)
        if direction == SignalDirection.SELL and recent_return_4h > _RETURN_4H_BLOCK:
            return "funding_price_runaway_up", {"recent_return_4h": recent_return_4h}
        if direction == SignalDirection.BUY and recent_return_4h < -_RETURN_4H_BLOCK:
            return "funding_price_runaway_down", {"recent_return_4h": recent_return_4h}

        return None
