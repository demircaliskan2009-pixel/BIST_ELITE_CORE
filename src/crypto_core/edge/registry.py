"""Edge Family Registry — maps EdgeFamily tags to evaluator instances.

The registry is the single source of truth for which edge families are
active and their configurations.  It is consumed by EdgeEngine.

Design:
  - Registry is immutable after construction (no runtime hot-swap).
  - Each family has exactly one evaluator instance.
  - Unknown family lookups return None (not an error — guards handle absence).
  - Families E/F/G: registered with _UnsupportedEdge that always returns
    is_valid=False.  They exist in the registry so callers can discover them
    without accidentally activating them.

PRD reference: §1.6 Edge Health Score (EHS), §1.22 Edge Evolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from crypto_core.data.models.events import TradeEvent
from crypto_core.edge.families.funding import FundingConfig, FundingRateEdge
from crypto_core.edge.families.liquidation import LiquidationConfig, LiquidationSignalEdge
from crypto_core.edge.families.order_flow import OFIConfig, OrderFlowImbalanceEdge
from crypto_core.edge.families.volatility import VolatilityConfig, VolatilityTransitionEdge
from crypto_core.edge.models import EdgeFamily, EdgeSignal

_RUNTIME_FAMILIES: tuple[EdgeFamily, ...] = (
    EdgeFamily.ORDER_FLOW_IMBALANCE,
    EdgeFamily.FUNDING_RATE,
    EdgeFamily.VOLATILITY_TRANSITION,
    EdgeFamily.LIQUIDATION_SIGNAL,
)

_UNSUPPORTED_FAMILIES: tuple[EdgeFamily, ...] = (
    EdgeFamily.CROSS_EXCHANGE_SPREAD,
    EdgeFamily.LATENCY_ARBITRAGE,
    EdgeFamily.VOL_SURFACE_SKEW,
)


# ---------------------------------------------------------------------------
# Unsupported family stub
# ---------------------------------------------------------------------------


class _UnsupportedEdge:
    """Evaluator for families not yet implemented.

    Always returns is_valid=False with reason "family_not_implemented".
    Prevents silent activation of families E, F, G.
    """

    def __init__(self, family: EdgeFamily) -> None:
        self._family = family

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
    ) -> EdgeSignal:
        return EdgeSignal.invalid(
            self._family,
            symbol,
            exchange,
            "family_not_implemented",
            timestamp_ns,
            {"family_status": "not_implemented", "family": str(self._family)},
        )


# ---------------------------------------------------------------------------
# Registry configuration
# ---------------------------------------------------------------------------


@dataclass
class RegistryConfig:
    """Per-family configuration overrides."""

    ofi: OFIConfig = field(default_factory=OFIConfig)
    volatility: VolatilityConfig = field(default_factory=VolatilityConfig)
    liquidation: LiquidationConfig = field(default_factory=LiquidationConfig)
    funding: FundingConfig = field(default_factory=FundingConfig)


class EdgeFamilyRegistry:
    """Immutable registry of active edge evaluators.

    Usage::

        registry = EdgeFamilyRegistry(RegistryConfig())
        evaluator = registry.get(EdgeFamily.ORDER_FLOW_IMBALANCE)
        if evaluator:
            signal = evaluator.evaluate(trades, symbol, exchange, ts_ns)
    """

    def __init__(self, config: RegistryConfig | None = None) -> None:
        cfg = config or RegistryConfig()
        self._registry: dict[str, object] = {
            EdgeFamily.ORDER_FLOW_IMBALANCE: OrderFlowImbalanceEdge(cfg.ofi),
            EdgeFamily.FUNDING_RATE: FundingRateEdge(cfg.funding),
            EdgeFamily.VOLATILITY_TRANSITION: VolatilityTransitionEdge(cfg.volatility),
            EdgeFamily.LIQUIDATION_SIGNAL: LiquidationSignalEdge(cfg.liquidation),
            # Phase 6B contract stubs — not yet implemented.
            EdgeFamily.CROSS_EXCHANGE_SPREAD: _UnsupportedEdge(EdgeFamily.CROSS_EXCHANGE_SPREAD),
            EdgeFamily.LATENCY_ARBITRAGE: _UnsupportedEdge(EdgeFamily.LATENCY_ARBITRAGE),
            EdgeFamily.VOL_SURFACE_SKEW: _UnsupportedEdge(EdgeFamily.VOL_SURFACE_SKEW),
        }

    def get(self, family: str) -> object | None:
        """Return the evaluator for *family*, or None if not registered."""
        return self._registry.get(family)

    def families(self) -> list[str]:
        """All registered family tags."""
        return list(self._registry.keys())

    def runtime_families(self) -> tuple[EdgeFamily, ...]:
        """Implemented runtime families evaluated by EdgeEngine in Phase 6B."""
        return _RUNTIME_FAMILIES

    def unsupported_families(self) -> tuple[EdgeFamily, ...]:
        """Declared families that must remain fail-closed until implemented."""
        return _UNSUPPORTED_FAMILIES

    def __len__(self) -> int:
        return len(self._registry)
