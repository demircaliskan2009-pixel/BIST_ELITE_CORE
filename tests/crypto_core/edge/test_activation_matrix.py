"""Tests for the Phase 6C activation matrix."""

from __future__ import annotations

import pytest

from crypto_core.edge.activation import (
    ActivationContext,
    ActivationMatrix,
    ExecutionCondition,
    LiquidityCondition,
    RegimeState,
    SpreadCondition,
    VolatilityCondition,
)
from crypto_core.edge.models import EdgeFamily

_MATRIX = ActivationMatrix()


def _ctx(
    *,
    system_state: str = "NORMAL",
    feed_connection_state: str = "connected",
    feed_recovery_state: str = "ready",
    mark_price_available: bool = False,
    regime_state: str | None = RegimeState.RANGE,
    liquidity_condition: str | None = LiquidityCondition.NORMAL,
    execution_condition: str | None = ExecutionCondition.OPTIMAL,
    spread_condition: str | None = SpreadCondition.STABLE,
    volatility_condition: str | None = VolatilityCondition.MED,
    regime_transition_active: bool | None = False,
    edge_health_score: float | None = 0.8,
    edge_fsm_state: str | None = "ACTIVE",
    edge_allocation_factor: float | None = 1.0,
) -> ActivationContext:
    return ActivationContext(
        system_state=system_state,
        feed_connection_state=feed_connection_state,
        feed_recovery_state=feed_recovery_state,
        mark_price_available=mark_price_available,
        regime_state=regime_state,
        liquidity_condition=liquidity_condition,
        execution_condition=execution_condition,
        spread_condition=spread_condition,
        volatility_condition=volatility_condition,
        regime_transition_active=regime_transition_active,
        edge_health_score=edge_health_score,
        edge_fsm_state=edge_fsm_state,
        edge_allocation_factor=edge_allocation_factor,
    )


class TestUnsupportedFamilies:
    @pytest.mark.parametrize(
        "family",
        [
            EdgeFamily.CROSS_EXCHANGE_SPREAD,
            EdgeFamily.LATENCY_ARBITRAGE,
            EdgeFamily.VOL_SURFACE_SKEW,
        ],
    )
    def test_unsupported_families_remain_blocked(self, family: EdgeFamily) -> None:
        decision = _MATRIX.evaluate(family, _ctx())
        assert decision.allowed is False
        assert decision.reason == "family_not_implemented"


class TestGlobalBlocks:
    def test_defensive_blocks_family(self) -> None:
        decision = _MATRIX.evaluate(EdgeFamily.ORDER_FLOW_IMBALANCE, _ctx(system_state="DEFENSIVE"))
        assert decision.allowed is False
        assert decision.reason == "system_state_restricted:DEFENSIVE"

    def test_disconnected_blocks_family(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(feed_connection_state="disconnected"),
        )
        assert decision.allowed is False
        assert decision.reason == "data_disconnected:disconnected"

    def test_recovering_blocks_family(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(feed_recovery_state="recovering"),
        )
        assert decision.allowed is False
        assert decision.reason == "data_recovering"


class TestRequiredInputs:
    def test_missing_regime_blocks_ofi(self) -> None:
        decision = _MATRIX.evaluate(EdgeFamily.ORDER_FLOW_IMBALANCE, _ctx(regime_state=None))
        assert decision.allowed is False
        assert decision.reason == "activation_input_unavailable:regime_state"

    def test_missing_execution_blocks_ofi(self) -> None:
        decision = _MATRIX.evaluate(EdgeFamily.ORDER_FLOW_IMBALANCE, _ctx(execution_condition=None))
        assert decision.allowed is False
        assert decision.reason == "activation_input_unavailable:execution_condition"

    def test_missing_spread_blocks_funding(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True, spread_condition=None),
        )
        assert decision.allowed is False
        assert decision.reason == "activation_input_unavailable:spread_condition"


class TestHardRules:
    def test_unknown_regime_blocks_non_funding(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(regime_state=RegimeState.UNKNOWN),
        )
        assert decision.allowed is False
        assert decision.reason == "regime_unknown_family_blocked"

    def test_unknown_regime_allows_funding_at_reduced_scale(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(
                mark_price_available=True,
                regime_state=RegimeState.UNKNOWN,
            ),
        )
        assert decision.allowed is True
        assert decision.reason == "allowed_reduced"
        assert decision.allocation_scale == pytest.approx(0.25)

    def test_spread_blown_blocks_ofi(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(spread_condition=SpreadCondition.BLOWN),
        )
        assert decision.allowed is False
        assert decision.reason == "spread_blown_family_blocked"

    def test_spread_blown_allows_liquidation_reduced(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.LIQUIDATION_SIGNAL,
            _ctx(
                regime_state=RegimeState.HIGH_VOL,
                spread_condition=SpreadCondition.BLOWN,
                volatility_condition=VolatilityCondition.HIGH,
                liquidity_condition=LiquidityCondition.THIN,
            ),
        )
        assert decision.allowed is True
        assert decision.reason == "allowed_reduced"
        assert decision.allocation_scale == pytest.approx(0.5)

    def test_liquidity_dry_blocks_all(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True, liquidity_condition=LiquidityCondition.DRY),
        )
        assert decision.allowed is False
        assert decision.reason == "liquidity_dry_blocked"


class TestFamilyRules:
    def test_funding_requires_mark_price(self) -> None:
        decision = _MATRIX.evaluate(EdgeFamily.FUNDING_RATE, _ctx(mark_price_available=False))
        assert decision.allowed is False
        assert decision.reason == "funding_feed_unavailable"

    def test_funding_disallows_trending_regime(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True, regime_state=RegimeState.TRENDING),
        )
        assert decision.allowed is False
        assert decision.reason == "regime_disallowed"

    def test_liquidation_requires_high_vol_context(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.LIQUIDATION_SIGNAL,
            _ctx(
                regime_state=RegimeState.RANGE,
                volatility_condition=VolatilityCondition.MED,
            ),
        )
        assert decision.allowed is False
        assert decision.reason in {"regime_disallowed", "volatility_disallowed"}

    def test_volatility_family_requires_transition_and_optimal_exec(self) -> None:
        no_transition = _MATRIX.evaluate(
            EdgeFamily.VOLATILITY_TRANSITION,
            _ctx(regime_transition_active=False),
        )
        impaired = _MATRIX.evaluate(
            EdgeFamily.VOLATILITY_TRANSITION,
            _ctx(regime_transition_active=True, execution_condition=ExecutionCondition.DEGRADED),
        )
        assert no_transition.allowed is False
        assert no_transition.reason == "regime_transition_required"
        assert impaired.allowed is False
        assert impaired.reason == "execution_disallowed"


class TestHealthIntegration:
    def test_warning_health_reduces_allocation(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(
                edge_fsm_state="WARNING",
                edge_health_score=0.55,
                edge_allocation_factor=0.8125,
            ),
        )
        assert decision.allowed is True
        assert decision.reason == "allowed_reduced"
        assert decision.allocation_scale == pytest.approx(0.8125)

    def test_initializing_health_allows_reduced(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(edge_fsm_state=None, edge_health_score=None, edge_allocation_factor=None),
        )
        assert decision.allowed is True
        assert decision.reason == "allowed_reduced"
        assert decision.allocation_scale == pytest.approx(0.25)

    def test_quarantine_blocks_family(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(edge_fsm_state="QUARANTINE", edge_health_score=0.2),
        )
        assert decision.allowed is False
        assert decision.reason == "edge_quarantined"

    def test_low_health_blocks_family(self) -> None:
        decision = _MATRIX.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(edge_fsm_state="WARNING", edge_health_score=0.2),
        )
        assert decision.allowed is False
        assert decision.reason == "edge_health_low"


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        ctx = _ctx(mark_price_available=True, regime_state=RegimeState.RANGE)
        d1 = _MATRIX.evaluate(EdgeFamily.FUNDING_RATE, ctx)
        d2 = _MATRIX.evaluate(EdgeFamily.FUNDING_RATE, ctx)
        assert d1 == d2
