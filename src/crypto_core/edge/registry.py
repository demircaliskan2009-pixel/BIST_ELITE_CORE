"""Edge Family Registry — maps EdgeFamily tags to evaluator instances.

The registry is the single source of truth for which edge families are
active and their configurations.  It is consumed by EdgeEngine.

Design:
  - Registry is immutable after construction (no runtime hot-swap).
  - Each family has exactly one evaluator instance.
  - Unknown family lookups return None (not an error — guards handle absence).

PRD reference: §1.6 Edge Health Score (EHS), §1.22 Edge Evolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from crypto_core.edge.families.funding import FundingConfig, FundingRateEdge
from crypto_core.edge.families.liquidation import LiquidationConfig, LiquidationSignalEdge
from crypto_core.edge.families.order_flow import OFIConfig, OrderFlowImbalanceEdge
from crypto_core.edge.families.volatility import VolatilityConfig, VolatilityTransitionEdge
from crypto_core.edge.models import EdgeFamily


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
            EdgeFamily.VOLATILITY_TRANSITION: VolatilityTransitionEdge(cfg.volatility),
            EdgeFamily.LIQUIDATION_SIGNAL: LiquidationSignalEdge(cfg.liquidation),
            EdgeFamily.FUNDING_RATE: FundingRateEdge(cfg.funding),
        }

    def get(self, family: str) -> object | None:
        """Return the evaluator for *family*, or None if not registered."""
        return self._registry.get(family)

    def families(self) -> list[str]:
        """All registered family tags."""
        return list(self._registry.keys())

    def __len__(self) -> int:
        return len(self._registry)
