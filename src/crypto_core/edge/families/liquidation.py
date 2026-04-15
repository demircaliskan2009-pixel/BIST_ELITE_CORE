"""Liquidation Signal edge family (Family D).

Detects liquidation-driven price dislocations by monitoring for large,
rapid price moves accompanied by high volume — a proxy for forced
liquidation cascades in perpetual futures markets.

Signal logic (proxy — without a dedicated liquidation feed):
  price_move = abs(price[-1] - price[-window]) / price[-window]
  vol_spike  = current_window_volume / baseline_volume
  If price_move > price_threshold AND vol_spike > vol_threshold:
      signal BUY on up-move, SELL on down-move
  Confidence = min(1.0, price_move * vol_spike)

PRD reference: §1.4 Family D — Liquidation Intelligence.
Note: Full version consumes dedicated liquidation event feed (§4.5).
This v1 approximates from trade flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.data.models.events import TradeEvent
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection

logger = logging.getLogger(__name__)

DEFAULT_WINDOW: int = 20
DEFAULT_BASELINE_WINDOW: int = 100
DEFAULT_PRICE_THRESHOLD: float = 0.005  # 0.5% move
DEFAULT_VOL_SPIKE_THRESHOLD: float = 2.0  # 2× baseline volume
DEFAULT_MIN_TRADES: int = 21


@dataclass
class LiquidationConfig:
    window: int = DEFAULT_WINDOW
    baseline_window: int = DEFAULT_BASELINE_WINDOW
    price_threshold: float = DEFAULT_PRICE_THRESHOLD
    vol_spike_threshold: float = DEFAULT_VOL_SPIKE_THRESHOLD
    min_trades: int = DEFAULT_MIN_TRADES


class LiquidationSignalEdge:
    """Stateless liquidation-proxy signal detector."""

    def __init__(self, config: LiquidationConfig | None = None) -> None:
        self._cfg = config or LiquidationConfig()

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
    ) -> EdgeSignal:
        cfg = self._cfg
        family = EdgeFamily.LIQUIDATION_SIGNAL

        if len(trades) < cfg.min_trades:
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                f"insufficient_trades:{len(trades)}<{cfg.min_trades}",
                timestamp_ns,
                {"trade_count": len(trades)},
            )

        recent_trades = list(trades)[-cfg.window :]
        baseline_trades = list(trades)[-cfg.baseline_window :]

        prices = [t.price for t in recent_trades]
        price_start = prices[0] if prices else 0.0

        if price_start <= 0.0:
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                "zero_price",
                timestamp_ns,
                {"price_start": price_start},
            )

        price_end = prices[-1]
        price_move = (price_end - price_start) / price_start
        abs_move = abs(price_move)

        recent_vol = sum(t.qty for t in recent_trades)
        baseline_vol = sum(t.qty for t in baseline_trades) / max(1, len(baseline_trades) // cfg.window)

        vol_spike = recent_vol / baseline_vol if baseline_vol > 0 else 0.0

        evidence: dict[str, object] = {
            "price_start": price_start,
            "price_end": price_end,
            "price_move_pct": price_move * 100,
            "abs_move": abs_move,
            "vol_spike": vol_spike,
            "recent_vol": recent_vol,
            "baseline_vol": baseline_vol,
            "trade_count": len(trades),
        }

        if abs_move < cfg.price_threshold or vol_spike < cfg.vol_spike_threshold:
            return EdgeSignal(
                family=family,
                symbol=symbol,
                exchange=exchange,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                score=0.0,
                evidence=evidence,
                timestamp_ns=timestamp_ns,
                is_valid=True,
                block_reason=None,
            )

        direction = SignalDirection.BUY if price_move > 0 else SignalDirection.SELL
        confidence = min(1.0, abs_move * vol_spike)

        return EdgeSignal(
            family=family,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            confidence=confidence,
            score=price_move * vol_spike,
            evidence=evidence,
            timestamp_ns=timestamp_ns,
            is_valid=True,
            block_reason=None,
        )
