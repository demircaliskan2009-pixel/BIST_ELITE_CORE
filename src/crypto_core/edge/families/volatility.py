"""Volatility Transition edge family (Family C).

Detects regime transitions from low to high volatility (or vice versa)
by comparing short-window realised volatility to a longer-window baseline.

Signal logic:
  vol_ratio = short_vol / long_vol
  vol_ratio > expansion_threshold → BUY/SELL based on momentum direction
  vol_ratio < contraction_threshold → NEUTRAL (regime compression = no signal)

PRD reference: §1.3 Family C — Volatility Regime.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from crypto_core.data.models.events import TradeEvent
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection

logger = logging.getLogger(__name__)

DEFAULT_SHORT_WINDOW: int = 20
DEFAULT_LONG_WINDOW: int = 100
DEFAULT_EXPANSION_THRESHOLD: float = 1.5  # short_vol > 1.5 * long_vol
DEFAULT_CONTRACTION_THRESHOLD: float = 0.5  # short_vol < 0.5 * long_vol
DEFAULT_MIN_TRADES: int = 21  # need at least long_window + 1


@dataclass
class VolatilityConfig:
    short_window: int = DEFAULT_SHORT_WINDOW
    long_window: int = DEFAULT_LONG_WINDOW
    expansion_threshold: float = DEFAULT_EXPANSION_THRESHOLD
    contraction_threshold: float = DEFAULT_CONTRACTION_THRESHOLD
    min_trades: int = DEFAULT_MIN_TRADES


def _realised_vol(prices: list[float]) -> float:
    """Log-return standard deviation over prices list."""
    if len(prices) < 2:
        return 0.0
    returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)


class VolatilityTransitionEdge:
    """Stateless volatility regime transition detector."""

    def __init__(self, config: VolatilityConfig | None = None) -> None:
        self._cfg = config or VolatilityConfig()

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
    ) -> EdgeSignal:
        cfg = self._cfg
        family = EdgeFamily.VOLATILITY_TRANSITION

        if len(trades) < cfg.min_trades:
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                f"insufficient_trades:{len(trades)}<{cfg.min_trades}",
                timestamp_ns,
                {"trade_count": len(trades)},
            )

        prices = [t.price for t in trades]
        recent = prices[-cfg.short_window :]
        baseline = prices[-cfg.long_window :]

        short_vol = _realised_vol(recent)
        long_vol = _realised_vol(baseline)

        evidence: dict[str, object] = {
            "short_vol": short_vol,
            "long_vol": long_vol,
            "short_window": cfg.short_window,
            "long_window": cfg.long_window,
            "trade_count": len(trades),
        }

        if long_vol < 1e-12:
            # Dead-flat baseline — no expansion possible → NEUTRAL (not an error)
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=0.0,
                evidence={**evidence, "vol_ratio": 0.0},
                timestamp_ns=timestamp_ns,
                is_valid=True,
                block_reason=None,
            )

        vol_ratio = short_vol / long_vol
        evidence["vol_ratio"] = vol_ratio

        if vol_ratio > cfg.expansion_threshold:
            # Expanding volatility → directional signal based on recent price trend
            recent_return = (prices[-1] / prices[-cfg.short_window]) - 1.0 if prices[-cfg.short_window] > 0 else 0.0
            direction = SignalDirection.BUY if recent_return > 0 else SignalDirection.SELL
            confidence = min(1.0, (vol_ratio - cfg.expansion_threshold) / cfg.expansion_threshold)
            evidence["recent_return"] = recent_return
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        score = vol_ratio - 1.0

        return EdgeSignal(
            family=family,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            confidence=confidence,
            score=score,
            evidence=evidence,
            timestamp_ns=timestamp_ns,
            is_valid=True,
            block_reason=None,
        )
