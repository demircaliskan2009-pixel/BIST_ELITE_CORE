"""Tests for ActivationMatrix — Phase 6B activation gate (PRD §1.5)."""

from __future__ import annotations

import pytest

from crypto_core.edge.activation import ActivationContext, ActivationMatrix
from crypto_core.edge.models import EdgeFamily

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NORMAL = "NORMAL"
_DEGRADED = "DEGRADED"
_DEFENSIVE = "DEFENSIVE"


def _ctx(
    system_state: str = _NORMAL,
    feed_connection_state: str = "connected",
    feed_recovery_state: str = "ready",
    mark_price_available: bool = False,
    liquidity_score: float | None = None,
    regime_transition_active: bool | None = None,
    edge_health_score: float | None = None,
    edge_fsm_state: str | None = None,
) -> ActivationContext:
    return ActivationContext(
        system_state=system_state,
        feed_connection_state=feed_connection_state,
        feed_recovery_state=feed_recovery_state,
        mark_price_available=mark_price_available,
        liquidity_score=liquidity_score,
        regime_transition_active=regime_transition_active,
        edge_health_score=edge_health_score,
        edge_fsm_state=edge_fsm_state,
    )


_matrix = ActivationMatrix()


# ---------------------------------------------------------------------------
# Rule 1: Unsupported families (E, F, G)
# ---------------------------------------------------------------------------


class TestUnsupportedFamilies:
    @pytest.mark.parametrize(
        "family",
        [
            EdgeFamily.CROSS_EXCHANGE_SPREAD,
            EdgeFamily.LATENCY_ARBITRAGE,
            EdgeFamily.VOL_SURFACE_SKEW,
        ],
    )
    def test_unsupported_family_always_blocked(self, family: EdgeFamily) -> None:
        """E/F/G must never activate regardless of system state."""
        for state in (_NORMAL, _DEGRADED, _DEFENSIVE):
            decision = _matrix.evaluate(family, _ctx(system_state=state))
            assert decision.allowed is False
            assert decision.reason == "family_not_implemented"

    def test_unsupported_family_evidence_has_supported_list(self) -> None:
        decision = _matrix.evaluate(EdgeFamily.CROSS_EXCHANGE_SPREAD, _ctx())
        assert "supported_families" in decision.evidence
        assert EdgeFamily.ORDER_FLOW_IMBALANCE in decision.evidence["supported_families"]

    def test_unsupported_blocked_even_with_mark_price(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.CROSS_EXCHANGE_SPREAD,
            _ctx(mark_price_available=True),
        )
        assert decision.allowed is False
        assert decision.reason == "family_not_implemented"


# ---------------------------------------------------------------------------
# Rule 2: Data disconnected
# ---------------------------------------------------------------------------


class TestDataDisconnected:
    @pytest.mark.parametrize(
        "state",
        ["disconnected", "error", "timeout", "stale"],
    )
    def test_disconnected_blocks_all_implemented_families(self, state: str) -> None:
        for family in (
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            EdgeFamily.VOLATILITY_TRANSITION,
            EdgeFamily.LIQUIDATION_SIGNAL,
        ):
            decision = _matrix.evaluate(family, _ctx(feed_connection_state=state))
            assert decision.allowed is False
            assert "data_disconnected" in decision.reason

    def test_connected_state_allows_ofi(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(feed_connection_state="connected"),
        )
        assert decision.allowed is True

    def test_ready_state_allows_ofi(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(feed_connection_state="ready"),
        )
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# Rule 3: Data recovering
# ---------------------------------------------------------------------------


class TestDataRecovering:
    def test_recovering_blocks_all_implemented_families(self) -> None:
        for family in (
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            EdgeFamily.FUNDING_RATE,
            EdgeFamily.VOLATILITY_TRANSITION,
            EdgeFamily.LIQUIDATION_SIGNAL,
        ):
            decision = _matrix.evaluate(
                family,
                _ctx(feed_recovery_state="recovering", mark_price_available=True),
            )
            assert decision.allowed is False
            assert decision.reason == "data_recovering"

    def test_ready_recovery_state_allows_ofi(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(feed_recovery_state="ready"),
        )
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# Rule 4: Funding feed requirement
# ---------------------------------------------------------------------------


class TestFundingActivation:
    def test_funding_blocked_without_mark_price(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=False),
        )
        assert decision.allowed is False
        assert decision.reason == "funding_feed_unavailable"

    def test_funding_allowed_with_mark_price(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True),
        )
        assert decision.allowed is True
        assert decision.reason == "allowed_partial_context"

    def test_funding_evidence_contains_hint(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=False),
        )
        assert "hint" in decision.evidence

    def test_funding_recovering_overrides_mark_price(self) -> None:
        """Data recovering takes precedence over mark-price availability."""
        decision = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(feed_recovery_state="recovering", mark_price_available=True),
        )
        assert decision.allowed is False
        assert decision.reason == "data_recovering"


class TestSystemStateAndLiquidityRules:
    def test_defensive_state_blocked(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(system_state=_DEFENSIVE),
        )
        assert decision.allowed is False
        assert decision.reason == "system_state_restricted:DEFENSIVE"

    def test_order_flow_requires_healthy_liquidity(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(liquidity_score=0.20),
        )
        assert decision.allowed is False
        assert decision.reason == "liquidity_below_family_threshold"

    def test_volatility_requires_healthy_liquidity(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.VOLATILITY_TRANSITION,
            _ctx(liquidity_score=0.20),
        )
        assert decision.allowed is False
        assert decision.reason == "liquidity_below_family_threshold"

    def test_funding_allows_degraded_but_not_crisis_liquidity(self) -> None:
        allowed = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True, liquidity_score=0.20),
        )
        blocked = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True, liquidity_score=0.10),
        )
        assert allowed.allowed is True
        assert blocked.allowed is False
        assert blocked.reason == "liquidity_below_family_threshold"

    def test_liquidation_blocked_in_liquidity_crisis(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.LIQUIDATION_SIGNAL,
            _ctx(liquidity_score=0.10),
        )
        assert decision.allowed is False
        assert decision.reason == "liquidity_below_family_threshold"


class TestTransitionAndEdgeHealthRules:
    def test_order_flow_blocked_during_transition(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(liquidity_score=0.60, regime_transition_active=True),
        )
        assert decision.allowed is False
        assert decision.reason == "regime_transition_blocked"

    def test_funding_blocked_during_transition(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True, liquidity_score=0.60, regime_transition_active=True),
        )
        assert decision.allowed is False
        assert decision.reason == "regime_transition_blocked"

    def test_liquidation_not_blocked_by_transition(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.LIQUIDATION_SIGNAL,
            _ctx(liquidity_score=0.60, regime_transition_active=True),
        )
        assert decision.allowed is True

    def test_edge_disabled_blocks_family(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(liquidity_score=0.60, edge_fsm_state="DISABLED"),
        )
        assert decision.allowed is False
        assert decision.reason == "edge_disabled"

    def test_edge_health_low_blocks_family(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(liquidity_score=0.60, edge_health_score=0.20, edge_fsm_state="ACTIVE"),
        )
        assert decision.allowed is False
        assert decision.reason == "edge_health_low"


# ---------------------------------------------------------------------------
# Rule priority: unsupported > disconnected > recovering > funding
# ---------------------------------------------------------------------------


class TestRulePriority:
    def test_unsupported_beats_disconnected(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.CROSS_EXCHANGE_SPREAD,
            _ctx(feed_connection_state="disconnected"),
        )
        assert decision.reason == "family_not_implemented"

    def test_disconnected_beats_recovering(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(feed_connection_state="disconnected", feed_recovery_state="recovering"),
        )
        assert "data_disconnected" in decision.reason

    def test_recovering_beats_funding_feed_check(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(feed_recovery_state="recovering", mark_price_available=False),
        )
        assert decision.reason == "data_recovering"


# ---------------------------------------------------------------------------
# Allowed cases: OFI, VOLATILITY, LIQUIDATION on healthy context
# ---------------------------------------------------------------------------


class TestAllowedCases:
    @pytest.mark.parametrize(
        "family",
        [
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            EdgeFamily.VOLATILITY_TRANSITION,
            EdgeFamily.LIQUIDATION_SIGNAL,
        ],
    )
    def test_implemented_families_allowed_on_healthy_context(self, family: EdgeFamily) -> None:
        decision = _matrix.evaluate(
            family,
            _ctx(liquidity_score=0.60, edge_health_score=0.80, edge_fsm_state="ACTIVE"),
        )
        assert decision.allowed is True
        assert decision.reason == "allowed_partial_context"

    def test_funding_allowed_when_mark_price_present(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.FUNDING_RATE,
            _ctx(mark_price_available=True, liquidity_score=0.20, edge_health_score=0.80, edge_fsm_state="ACTIVE"),
        )
        assert decision.allowed is True

    def test_allowed_reason_without_missing_inputs(self) -> None:
        decision = _matrix.evaluate(
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            _ctx(
                liquidity_score=0.60,
                regime_transition_active=False,
                edge_health_score=0.80,
                edge_fsm_state="ACTIVE",
            ),
        )
        assert decision.allowed is True
        assert decision.reason == "allowed"
        assert decision.evidence["missing_inputs"] == []

    def test_evidence_always_populated(self) -> None:
        for family in (
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            EdgeFamily.CROSS_EXCHANGE_SPREAD,
        ):
            decision = _matrix.evaluate(family, _ctx())
            assert isinstance(decision.evidence, dict)
            assert "family" in decision.evidence

    def test_decision_is_frozen(self) -> None:
        decision = _matrix.evaluate(EdgeFamily.ORDER_FLOW_IMBALANCE, _ctx())
        with pytest.raises((AttributeError, TypeError)):
            decision.allowed = False  # type: ignore[misc]

    def test_deterministic_same_inputs_same_output(self) -> None:
        ctx = _ctx(liquidity_score=0.60, edge_health_score=0.70, edge_fsm_state="ACTIVE")
        d1 = _matrix.evaluate(EdgeFamily.ORDER_FLOW_IMBALANCE, ctx)
        d2 = _matrix.evaluate(EdgeFamily.ORDER_FLOW_IMBALANCE, ctx)
        assert d1.allowed == d2.allowed
        assert d1.reason == d2.reason
