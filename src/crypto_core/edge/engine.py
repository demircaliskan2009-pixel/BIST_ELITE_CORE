"""Edge Engine — coordinates edge family evaluation with guard, state, and
activation matrix integration.

Integrates:
  - NoTradeGuard (mandatory engine-level gate)
  - SystemStateEngine current state (engine-level gate)
    - ActivationMatrix (per-family gate, PRD §1.5)
  - EdgeFamilyRegistry (single source of truth for runtime family coverage)

Evaluation order:
  1. no_trade blocked       → all families return invalid
  2. system_state DEFENSIVE → all families return invalid
  3. Per family:
      a. ActivationMatrix  → blocked: invalid signal with activation reason
      b. Family evaluator  → valid or invalid signal per family logic
      c. Runtime audit     → activation + PRD mapping + evaluation state

PRD reference: §1.1–§1.13.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from crypto_core.data.models.events import LiquidationEvent, MarkPriceEvent, TradeEvent
from crypto_core.edge.activation import ActivationContext, ActivationDecision, ActivationMatrix
from crypto_core.edge.families.funding import FundingConfig, FundingSafetyContext
from crypto_core.edge.families.liquidation import LiquidationConfig
from crypto_core.edge.families.order_flow import OFIConfig
from crypto_core.edge.families.volatility import VolatilityConfig
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection, edge_prd_family_code, edge_prd_family_name
from crypto_core.edge.registry import EdgeFamilyRegistry, RegistryConfig
from crypto_core.edge_health.models import EdgeHealthSnapshot
from crypto_core.guard.models import NoTradeDecision
from crypto_core.regime.models import RegimeSnapshot
from crypto_core.service.external_regime import ExternalRegimeSafetyPolicy, ExternalRegimeSnapshot
from crypto_core.state.models import SystemState, is_at_least

logger = logging.getLogger(__name__)


@dataclass
class EdgeEngineConfig:
    """Edge engine configuration per runtime family."""

    ofi: OFIConfig = None  # type: ignore[assignment]
    funding: FundingConfig = None  # type: ignore[assignment]
    volatility: VolatilityConfig = None  # type: ignore[assignment]
    liquidation: LiquidationConfig = None  # type: ignore[assignment]
    external_regime_policy: ExternalRegimeSafetyPolicy | None = None

    def __post_init__(self) -> None:
        if self.ofi is None:
            self.ofi = OFIConfig()
        if self.funding is None:
            self.funding = FundingConfig()
        if self.volatility is None:
            self.volatility = VolatilityConfig()
        if self.liquidation is None:
            self.liquidation = LiquidationConfig()
        if self.external_regime_policy is None:
            self.external_regime_policy = ExternalRegimeSafetyPolicy()


class EdgeEngine:
    """Evaluates all Phase 6B runtime edge families for one market data snapshot.

    Engine-level gates (apply to all families):
      - NoTradeDecision.allowed=False → all signals blocked (invalid).
      - SystemState >= DEFENSIVE      → all signals blocked (invalid).

    Per-family gates (ActivationMatrix, PRD §1.5):
      - Family not implemented (E/F/G) → blocked: family_not_implemented.
    - Missing activation dimensions   → blocked: activation_input_unavailable:*
    - Family edge disabled / low EHS → blocked: edge_disabled / edge_health_low.
      - Data feed disconnected         → blocked: data_disconnected.
      - Data feed recovering           → blocked: data_recovering.
      - Funding family: no mark-price  → blocked: funding_feed_unavailable.

    Runtime families (Phase 6B):
      A — OrderFlowImbalanceEdge   (always evaluated when activation allows)
    B — FundingRateEdge          (requires mark_price_event + funding safety context)
      D — VolatilityTransitionEdge (project tag retained; maps to PRD Family D)
    C — LiquidationSignalEdge    (project tag retained; maps to PRD Family C, requires liquidation feed)

    Telemetry integration:
      Caller is responsible for wrapping calls in telemetry timing.

    Usage::

        engine = EdgeEngine()
        signals = engine.evaluate(trades, symbol, exchange, no_trade, state, ts_ns)
    """

    def __init__(self, config: EdgeEngineConfig | None = None) -> None:
        cfg = config or EdgeEngineConfig()
        self._registry = EdgeFamilyRegistry(
            RegistryConfig(
                ofi=cfg.ofi,
                funding=cfg.funding,
                volatility=cfg.volatility,
                liquidation=cfg.liquidation,
            )
        )
        self._activation = ActivationMatrix(external_regime_policy=cfg.external_regime_policy)
        self._runtime_families: tuple[EdgeFamily, ...] = self._registry.runtime_families()

    @property
    def runtime_families(self) -> tuple[EdgeFamily, ...]:
        """Ordered runtime family coverage evaluated by the engine."""
        return self._runtime_families

    def evaluate(
        self,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        no_trade: NoTradeDecision,
        system_state: SystemState,
        timestamp_ns: int,
        mark_price_event: MarkPriceEvent | None = None,
        liquidation_events: list[LiquidationEvent] | tuple[LiquidationEvent, ...] | None = None,
        feed_connection_state: str = "connected",
        feed_recovery_state: str = "ready",
        regime_state: str | None = None,
        liquidity_condition: str | None = None,
        execution_condition: str | None = None,
        spread_condition: str | None = None,
        volatility_condition: str | None = None,
        funding_safety_context: FundingSafetyContext | None = None,
        market_regime: RegimeSnapshot | None = None,
        family_edge_health: dict[EdgeFamily, EdgeHealthSnapshot] | None = None,
        external_regime: ExternalRegimeSnapshot | None = None,
    ) -> list[EdgeSignal]:
        """Evaluate all runtime edge families."""
        if not no_trade.allowed:
            return [
                self._engine_blocked_signal(
                    family=fam,
                    symbol=symbol,
                    exchange=exchange,
                    timestamp_ns=timestamp_ns,
                    reason=f"no_trade_blocked:{no_trade.reason}",
                    evidence_extra={"no_trade_reason": str(no_trade.reason)},
                )
                for fam in self._runtime_families
            ]

        if is_at_least(system_state, SystemState.DEFENSIVE):
            return [
                self._engine_blocked_signal(
                    family=fam,
                    symbol=symbol,
                    exchange=exchange,
                    timestamp_ns=timestamp_ns,
                    reason=f"system_state_blocked:{system_state}",
                    evidence_extra={"system_state": str(system_state)},
                )
                for fam in self._runtime_families
            ]

        signals: list[EdgeSignal] = []
        for fam in self._runtime_families:
            family_health = family_edge_health.get(fam) if family_edge_health is not None else None
            activation_ctx = ActivationContext(
                system_state=str(system_state),
                feed_connection_state=feed_connection_state,
                feed_recovery_state=feed_recovery_state,
                mark_price_available=mark_price_event is not None,
                regime_state=regime_state,
                liquidity_condition=liquidity_condition,
                execution_condition=execution_condition,
                spread_condition=spread_condition,
                volatility_condition=volatility_condition,
                regime_transition_active=market_regime.regime_transition_active if market_regime is not None else None,
                edge_health_score=family_health.ehs_score if family_health is not None else None,
                edge_fsm_state=family_health.fsm_state.value if family_health is not None else None,
                edge_allocation_factor=family_health.allocation_factor if family_health is not None else None,
                external_regime=external_regime,
            )
            activation = self._activation.evaluate(fam, activation_ctx)
            if not activation.allowed:
                signals.append(self._activation_blocked_signal(fam, symbol, exchange, timestamp_ns, activation))
                continue
            signals.append(
                self._with_runtime_evidence(
                    self._evaluate_family(
                        fam,
                        trades,
                        symbol,
                        exchange,
                        timestamp_ns,
                        mark_price_event=mark_price_event,
                        liquidation_events=liquidation_events,
                        funding_safety_context=funding_safety_context,
                    ),
                    activation,
                )
            )

        return signals

    def _evaluate_family(
        self,
        family: EdgeFamily,
        trades: list[TradeEvent] | tuple[TradeEvent, ...],
        symbol: str,
        exchange: str,
        timestamp_ns: int,
        mark_price_event: MarkPriceEvent | None = None,
        liquidation_events: list[LiquidationEvent] | tuple[LiquidationEvent, ...] | None = None,
        funding_safety_context: FundingSafetyContext | None = None,
    ) -> EdgeSignal:
        try:
            evaluator = self._registry.get(family)
            if evaluator is None:
                return EdgeSignal.invalid(family, symbol, exchange, "unknown_family", timestamp_ns)
            if family == EdgeFamily.FUNDING_RATE:
                return evaluator.evaluate(
                    trades,
                    symbol,
                    exchange,
                    timestamp_ns,
                    mark_price_event=mark_price_event,
                    safety_context=funding_safety_context,
                )
            if family == EdgeFamily.LIQUIDATION_SIGNAL:
                return evaluator.evaluate(
                    trades,
                    symbol,
                    exchange,
                    timestamp_ns,
                    liquidation_events=liquidation_events,
                )
            return evaluator.evaluate(trades, symbol, exchange, timestamp_ns)
        except Exception:
            logger.exception("Edge family %s raised — fail-closed", family)
            return EdgeSignal.invalid(
                family,
                symbol,
                exchange,
                f"evaluator_exception:{family}",
                timestamp_ns,
            )

    @staticmethod
    def _runtime_metadata(family: EdgeFamily) -> dict[str, object]:
        return {
            "project_family_tag": str(family),
            "prd_family_code": edge_prd_family_code(family),
            "prd_family_name": edge_prd_family_name(family),
        }

    def _engine_blocked_signal(
        self,
        family: EdgeFamily,
        symbol: str,
        exchange: str,
        timestamp_ns: int,
        reason: str,
        evidence_extra: dict[str, object] | None = None,
    ) -> EdgeSignal:
        evidence = {
            **self._runtime_metadata(family),
            "status": "blocked",
            "evaluation_state": "blocked",
            "activation_state": "engine_blocked",
            **(evidence_extra or {}),
        }
        return EdgeSignal.invalid(family, symbol, exchange, reason, timestamp_ns, evidence)

    def _activation_blocked_signal(
        self,
        family: EdgeFamily,
        symbol: str,
        exchange: str,
        timestamp_ns: int,
        activation: ActivationDecision,
    ) -> EdgeSignal:
        evidence = {
            **self._runtime_metadata(family),
            "status": "blocked",
            "evaluation_state": "blocked",
            "activation_state": "blocked",
            "activation_reason": activation.reason,
            "activation_allocation_scale": activation.allocation_scale,
            "activation_evidence": activation.evidence,
            "missing_inputs": activation.evidence.get("missing_inputs", []),
        }
        return EdgeSignal.invalid(
            family,
            symbol,
            exchange,
            f"activation_blocked:{activation.reason}",
            timestamp_ns,
            evidence,
        )

    def _with_runtime_evidence(self, signal: EdgeSignal, activation: ActivationDecision) -> EdgeSignal:
        evidence = dict(signal.evidence)
        evidence.update(
            {
                **self._runtime_metadata(signal.family),
                "activation_state": "allowed",
                "activation_reason": activation.reason,
                "activation_allocation_scale": activation.allocation_scale,
                "activation_evidence": activation.evidence,
                "missing_inputs": activation.evidence.get("missing_inputs", []),
                "evaluation_state": self._evaluation_state(signal),
            }
        )
        evidence.setdefault("status", evidence["evaluation_state"])
        return replace(signal, evidence=evidence)

    @staticmethod
    def _evaluation_state(signal: EdgeSignal) -> str:
        if signal.is_valid:
            return "neutral" if signal.direction == SignalDirection.NEUTRAL else "valid"
        if signal.evidence.get("status") == "unavailable":
            return "unavailable"
        block_reason = signal.block_reason or ""
        unavailable_markers = (
            "unavailable",
            "insufficient_trades",
            "no_trades",
            "zero_price",
        )
        if any(marker in block_reason for marker in unavailable_markers):
            return "unavailable"
        return "blocked"
