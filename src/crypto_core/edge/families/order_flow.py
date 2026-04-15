"""Order Flow Imbalance edge family (Family A).

OFI measures the net directional pressure from the trade stream:

    OFI = (buy_volume - sell_volume) / total_volume  ∈ [-1, 1]

Signal interpretation:
  OFI >  threshold  → BUY signal  (buy-side pressure dominant)
  OFI < -threshold  → SELL signal (sell-side pressure dominant)
  |OFI| <= threshold → NEUTRAL    (balanced flow)

Confidence = |OFI| (linear — stronger imbalance → stronger signal).

PRD reference: §1.3 Family A — Microstructure Depth / Order Flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.data.models.events import TradeEvent, TradeSide
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_OFI_WINDOW: int = 50  # rolling trade count
DEFAULT_OFI_THRESHOLD: float = 0.10  # |OFI| >= this to generate non-neutral signal
DEFAULT_MIN_TRADE_COUNT: int = 10  # minimum trades required for valid signal


@dataclass
class OFIConfig:
    """Tunable parameters for the OFI edge family."""

    window: int = DEFAULT_OFI_WINDOW
    threshold: float = DEFAULT_OFI_THRESHOLD
    min_trade_count: int = DEFAULT_MIN_TRADE_COUNT


# ---------------------------------------------------------------------------
# Core computation (pure function — no side effects)
# ---------------------------------------------------------------------------


def compute_ofi(
    trades: list[TradeEvent] | tuple[TradeEvent, ...],
    window: int = DEFAULT_OFI_WINDOW,
) -> tuple[float, dict[str, object]]:
    """Compute Order Flow Imbalance over the last *window* trades.

    Returns:
        (ofi, evidence_dict)

    ofi is in [-1, 1].  Returns (0.0, error_evidence) on degenerate input.
    Deterministic: same trade list → same output.
    """
    if not trades:
        return 0.0, {"error": "no_trades", "trade_count": 0}

    recent = list(trades[-window:]) if len(trades) > window else list(trades)
    buy_vol = sum(t.qty for t in recent if t.side == TradeSide.BUY)
    sell_vol = sum(t.qty for t in recent if t.side == TradeSide.SELL)
    total_vol = buy_vol + sell_vol

    if total_vol < 1e-12:
        return 0.0, {"error": "zero_volume", "trade_count": len(recent)}

    ofi = (buy_vol - sell_vol) / total_vol
    evidence: dict[str, object] = {
        "ofi": ofi,
        "buy_vol": buy_vol,
        "sell_vol": sell_vol,
        "total_vol": total_vol,
        "trade_count": len(recent),
        "window": window,
    }
    return ofi, evidence


# ---------------------------------------------------------------------------
# Edge evaluator
# ---------------------------------------------------------------------------


class OrderFlowImbalanceEdge:
    """Stateless evaluator for the OFI edge family.

    Stateless: all state is passed in via arguments.
    Fail-closed: missing or insufficient inputs → invalid signal.

    Usage::

        ofi_edge = OrderFlowImbalanceEdge(OFIConfig())
        signal = ofi_edge.evaluate(trades, symbol, exchange, timestamp_ns)
    """

    def __init__(self, config: OFIConfig | None = None) -> None:
        self._cfg = config or OFIConfig()

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
    ) -> EdgeSignal:
        """Evaluate OFI signal from recent trade stream.

        Fail-closed on:
          - empty trades
          - fewer than min_trade_count trades
          - zero total volume
        """
        cfg = self._cfg
        family = EdgeFamily.ORDER_FLOW_IMBALANCE

        if not trades:
            return EdgeSignal.invalid(family, symbol, exchange, "no_trades", timestamp_ns)

        trade_count = min(len(trades), cfg.window)
        if trade_count < cfg.min_trade_count:
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                f"insufficient_trades:{trade_count}<{cfg.min_trade_count}",
                timestamp_ns,
                {"trade_count": trade_count, "min_required": cfg.min_trade_count},
            )

        ofi, evidence = compute_ofi(trades, cfg.window)

        if "error" in evidence:
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                evidence["error"],
                timestamp_ns,
                evidence,  # type: ignore[arg-type]
            )

        # Determine direction
        if ofi > cfg.threshold:
            direction = SignalDirection.BUY
        elif ofi < -cfg.threshold:
            direction = SignalDirection.SELL
        else:
            direction = SignalDirection.NEUTRAL

        confidence = min(1.0, abs(ofi))

        return EdgeSignal(
            family=family,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            confidence=confidence,
            score=ofi,
            evidence=evidence,
            timestamp_ns=timestamp_ns,
            is_valid=True,
            block_reason=None,
        )
