"""Edge Engine — coordinates edge family evaluation with guard and state integration.

Integrates:
  - NoTradeGuard (mandatory gate)
  - SystemStateEngine current state
  - Registered edge families

PRD reference: §1.1–§1.13.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.data.models.events import TradeEvent
from crypto_core.edge.families.order_flow import OFIConfig, OrderFlowImbalanceEdge
from crypto_core.edge.models import EdgeFamily, EdgeSignal
from crypto_core.guard.models import NoTradeDecision
from crypto_core.state.models import SystemState, is_at_least

logger = logging.getLogger(__name__)


@dataclass
class EdgeEngineConfig:
    """Edge engine configuration."""

    ofi: OFIConfig = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.ofi is None:
            self.ofi = OFIConfig()


class EdgeEngine:
    """Evaluates configured edge families for one market data snapshot.

    Guard integration:
      - NoTradeDecision.allowed=False → all signals blocked (invalid).
      - SystemState >= DEFENSIVE → all signals blocked.

    Telemetry integration:
      - Caller is responsible for wrapping calls in telemetry timing.

    Phase 3A scope: ORDER_FLOW_IMBALANCE only.

    Usage::

        engine = EdgeEngine()
        signals = engine.evaluate(trades, symbol, exchange, no_trade, state, ts_ns)
    """

    def __init__(self, config: EdgeEngineConfig | None = None) -> None:
        cfg = config or EdgeEngineConfig()
        self._ofi_edge = OrderFlowImbalanceEdge(cfg.ofi)
        self._families: list[EdgeFamily] = [EdgeFamily.ORDER_FLOW_IMBALANCE]

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        no_trade: NoTradeDecision,
        system_state: SystemState,
        timestamp_ns: int,
    ) -> list[EdgeSignal]:
        """Evaluate all registered edge families.

        Returns one EdgeSignal per family.
        On guard/state block: returns invalid signals for all families.
        """
        # Gate 1: no-trade guard
        if not no_trade.allowed:
            return [
                EdgeSignal.invalid(
                    fam,
                    symbol,
                    exchange,
                    f"no_trade_blocked:{no_trade.reason}",
                    timestamp_ns,
                )
                for fam in self._families
            ]

        # Gate 2: system state >= DEFENSIVE
        if is_at_least(system_state, SystemState.DEFENSIVE):
            return [
                EdgeSignal.invalid(
                    fam,
                    symbol,
                    exchange,
                    f"system_state_blocked:{system_state}",
                    timestamp_ns,
                )
                for fam in self._families
            ]

        # Evaluate each family
        signals: list[EdgeSignal] = []
        for fam in self._families:
            sig = self._evaluate_family(fam, trades, symbol, exchange, timestamp_ns)
            signals.append(sig)

        return signals

    def _evaluate_family(
        self,
        family: EdgeFamily,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
    ) -> EdgeSignal:
        try:
            if family == EdgeFamily.ORDER_FLOW_IMBALANCE:
                return self._ofi_edge.evaluate(trades, symbol, exchange, timestamp_ns)
        except Exception as exc:
            logger.exception("Edge family %s raised — fail-closed", family)
            return EdgeSignal.invalid(
                family, symbol, exchange, f"exception:{exc}", timestamp_ns
            )
        # Unknown family
        return EdgeSignal.invalid(
            family, symbol, exchange, "unknown_family", timestamp_ns
        )
