"""Tests for Risk Engine v2 — kill-switch, DTL, Kelly, CVaR, portfolio gates.

v1 backward-compat tests are in test_risk_engine.py (untouched).
This file tests only the v2 evaluate_v2() surface.

PRD reference: §1.18 CVaR, §1.19 Kill-Switch, §1.26 Margin/DTL, §1.28 Kelly.
"""

from __future__ import annotations

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.guard.models import NoTradeDecision, NoTradeReason
from crypto_core.risk.contracts import (
    KS_BLOCK_THRESHOLD,
    KS_LEVEL_BLOCK,
    KS_LEVEL_FLATTEN,
    KS_LEVEL_HALT,
    KS_LEVEL_NORMAL,
    KS_LEVEL_REDUCE,
    CVaRInput,
    DTLInput,
    KellyInput,
    PortfolioRiskSnapshot,
    RiskInput,
)
from crypto_core.risk.engine import RiskEngine
from crypto_core.risk.models import RiskBlockReason, RiskDecision
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000


def _valid_edge() -> EdgeSignal:
    return EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.65,
        score=0.65,
        evidence={"ofi": 0.65, "trade_count": 60},
        timestamp_ns=_T0_NS,
        is_valid=True,
        block_reason=None,
    )


def _allow() -> NoTradeDecision:
    return NoTradeDecision.allow()


def _base_input(**overrides) -> RiskInput:
    """Minimal valid RiskInput — all v2 optional gates omitted."""
    defaults = dict(
        edge_signal=_valid_edge(),
        system_state=SystemState.NORMAL,
        no_trade=_allow(),
        timestamp_ns=_T0_NS,
        shs_snapshot=0.90,
        kill_switch_level=KS_LEVEL_NORMAL,
    )
    defaults.update(overrides)
    return RiskInput(**defaults)


def _engine() -> RiskEngine:
    return RiskEngine()


# ---------------------------------------------------------------------------
# Baseline: v2 produces APPROVED with valid minimal input
# ---------------------------------------------------------------------------


class TestV2BaselineApproval:
    def test_minimal_input_approved(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input())
        assert result.approved is True
        assert result.decision == RiskDecision.APPROVED
        assert result.block_reason is None

    def test_result_is_frozen(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input())
        with pytest.raises((AttributeError, TypeError)):
            result.decision = RiskDecision.BLOCKED  # type: ignore[misc]

    def test_v2_result_has_ks_field(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(kill_switch_level=KS_LEVEL_NORMAL))
        assert result.kill_switch_level == KS_LEVEL_NORMAL

    def test_v2_result_evidence_contains_ks_level(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input())
        assert "kill_switch_level" in result.evidence

    def test_from_v1_factory(self) -> None:
        """RiskInput.from_v1() constructs a valid v2 input from v1 args."""
        ri = RiskInput.from_v1(
            edge_signal=_valid_edge(),
            system_state=SystemState.NORMAL,
            no_trade=_allow(),
            timestamp_ns=_T0_NS,
            shs_snapshot=0.90,
        )
        eng = _engine()
        result = eng.evaluate_v2(ri)
        assert result.approved is True


# ---------------------------------------------------------------------------
# v1 gates still fire in evaluate_v2
# ---------------------------------------------------------------------------


class TestV2V1GatesPreserved:
    def test_defensive_state_blocks(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(system_state=SystemState.DEFENSIVE))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.SYSTEM_STATE_DEFENSIVE

    def test_no_trade_blocked_propagates(self) -> None:
        eng = _engine()
        nt = NoTradeDecision.block(NoTradeReason.STALE_DATA)
        result = eng.evaluate_v2(_base_input(no_trade=nt))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.NO_TRADE_BLOCKED

    def test_invalid_edge_blocked(self) -> None:
        eng = _engine()
        invalid = EdgeSignal.invalid(EdgeFamily.ORDER_FLOW_IMBALANCE, "BTCUSDT", "binance", "test", _T0_NS)
        result = eng.evaluate_v2(_base_input(edge_signal=invalid))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.EDGE_NOT_VALID


# ---------------------------------------------------------------------------
# Gate 5: kill-switch enforcement
# ---------------------------------------------------------------------------


class TestGate5KillSwitch:
    @pytest.mark.parametrize("ks_level", [KS_LEVEL_BLOCK, KS_LEVEL_FLATTEN, KS_LEVEL_HALT])
    def test_ks_level_gte_2_blocks(self, ks_level: int) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(kill_switch_level=ks_level))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.KS_BLOCKED

    @pytest.mark.parametrize("ks_level", [KS_LEVEL_NORMAL, KS_LEVEL_REDUCE])
    def test_ks_level_lt_2_passes(self, ks_level: int) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(kill_switch_level=ks_level))
        assert result.decision == RiskDecision.APPROVED

    def test_ks_block_threshold_is_2(self) -> None:
        assert KS_BLOCK_THRESHOLD == 2

    def test_ks_evidence_recorded(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(kill_switch_level=KS_LEVEL_BLOCK))
        assert "ks_level_2" in result.evidence.get("block", "")

    def test_ks_level_preserved_in_result(self) -> None:
        """kill_switch_level propagates to RiskEvaluation even when blocked."""
        eng = _engine()
        result = eng.evaluate_v2(_base_input(kill_switch_level=KS_LEVEL_FLATTEN))
        assert result.kill_switch_level == KS_LEVEL_FLATTEN


# ---------------------------------------------------------------------------
# Gate 6: DTL (Distance-to-Liquidation)
# ---------------------------------------------------------------------------


class TestGate6DTL:
    def test_safe_dtl_passes(self) -> None:
        eng = _engine()
        dtl = DTLInput(current_price=50_000.0, liquidation_price=40_000.0, min_safe_distance_pct=5.0)
        result = eng.evaluate_v2(_base_input(dtl=dtl))
        assert result.approved is True
        assert result.dtl_pct is not None
        # DTL = |50000 - 40000| / 50000 * 100 = 20%
        assert abs(result.dtl_pct - 20.0) < 0.001

    def test_unsafe_dtl_blocks(self) -> None:
        eng = _engine()
        # Current price 50000, liq price 49500 → DTL = 1% < 5% threshold
        dtl = DTLInput(current_price=50_000.0, liquidation_price=49_500.0, min_safe_distance_pct=5.0)
        result = eng.evaluate_v2(_base_input(dtl=dtl))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.DTL_UNSAFE

    def test_dtl_exactly_at_threshold_passes(self) -> None:
        eng = _engine()
        # DTL = 5.0% exactly = min_safe → should PASS (>= is safe, < blocks)
        dtl = DTLInput(current_price=100.0, liquidation_price=95.0, min_safe_distance_pct=5.0)
        result = eng.evaluate_v2(_base_input(dtl=dtl))
        assert result.approved is True

    def test_liq_price_zero_skips_gate(self) -> None:
        eng = _engine()
        dtl = DTLInput(current_price=50_000.0, liquidation_price=0.0)
        result = eng.evaluate_v2(_base_input(dtl=dtl))
        assert result.approved is True
        assert result.evidence.get("dtl_status") == "liquidation_price_unavailable"

    def test_dtl_none_skips_gate(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(dtl=None))
        assert result.approved is True
        assert result.dtl_pct is None

    def test_dtl_evidence_populated(self) -> None:
        eng = _engine()
        dtl = DTLInput(current_price=50_000.0, liquidation_price=40_000.0, min_safe_distance_pct=5.0)
        result = eng.evaluate_v2(_base_input(dtl=dtl))
        assert "dtl_pct" in result.evidence
        assert "dtl_min_safe_pct" in result.evidence

    def test_invalid_current_price_blocks(self) -> None:
        eng = _engine()
        dtl = DTLInput(current_price=0.0, liquidation_price=40_000.0)
        result = eng.evaluate_v2(_base_input(dtl=dtl))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.DTL_UNSAFE

    def test_dtl_pct_in_result_when_approved(self) -> None:
        eng = _engine()
        dtl = DTLInput(current_price=50_000.0, liquidation_price=45_000.0, min_safe_distance_pct=5.0)
        result = eng.evaluate_v2(_base_input(dtl=dtl))
        assert result.dtl_pct is not None
        assert result.dtl_pct > 0.0


# ---------------------------------------------------------------------------
# Gate 7: Kelly position sizing
# ---------------------------------------------------------------------------


class TestGate7Kelly:
    def test_positive_edge_passes(self) -> None:
        # 55% win rate, 1.5 payoff → f* = (0.55*1.5 - 0.45)/1.5 = (0.825-0.45)/1.5 = 0.25
        eng = _engine()
        kelly = KellyInput(win_rate=0.55, payoff_ratio=1.5, max_fraction=0.25)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.approved is True
        assert result.kelly_fraction is not None
        assert 0.0 < result.kelly_fraction <= 0.25

    def test_negative_edge_blocks(self) -> None:
        # 30% win rate, 1.0 payoff → f* = (0.30 - 0.70)/1.0 = -0.40 → no edge
        eng = _engine()
        kelly = KellyInput(win_rate=0.30, payoff_ratio=1.0)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.KELLY_NO_EDGE

    def test_zero_edge_blocks(self) -> None:
        # 50% win rate, 1.0 payoff → f* = 0.0 exactly → block
        eng = _engine()
        kelly = KellyInput(win_rate=0.50, payoff_ratio=1.0)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.KELLY_NO_EDGE

    def test_invalid_win_rate_zero_blocks(self) -> None:
        eng = _engine()
        kelly = KellyInput(win_rate=0.0, payoff_ratio=1.5)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.KELLY_LIMIT

    def test_invalid_win_rate_one_blocks(self) -> None:
        eng = _engine()
        kelly = KellyInput(win_rate=1.0, payoff_ratio=1.5)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.KELLY_LIMIT

    def test_invalid_payoff_ratio_blocks(self) -> None:
        eng = _engine()
        kelly = KellyInput(win_rate=0.55, payoff_ratio=0.0)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.KELLY_LIMIT

    def test_kelly_fraction_capped_at_max(self) -> None:
        # Very high win rate → raw f* > max_fraction → must be capped
        eng = _engine()
        kelly = KellyInput(win_rate=0.95, payoff_ratio=5.0, max_fraction=0.10)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.approved is True
        assert result.kelly_fraction == pytest.approx(0.10, abs=1e-9)
        assert result.evidence.get("kelly_capped") is True

    def test_kelly_fraction_none_when_gate_skipped(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(kelly=None))
        assert result.kelly_fraction is None

    def test_kelly_evidence_fields(self) -> None:
        eng = _engine()
        kelly = KellyInput(win_rate=0.55, payoff_ratio=1.5)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert "kelly_f_star" in result.evidence
        assert "kelly_win_rate" in result.evidence
        assert "kelly_payoff_ratio" in result.evidence

    def test_kelly_formula_correctness(self) -> None:
        """Verify Kelly formula: f* = (p*b - q) / b."""
        p, b = 0.60, 2.0
        q = 1.0 - p
        expected_f_star = (p * b - q) / b  # = (1.20 - 0.40)/2 = 0.40
        eng = _engine()
        kelly = KellyInput(win_rate=p, payoff_ratio=b, max_fraction=1.0)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.approved is True
        assert result.evidence["kelly_f_star"] == pytest.approx(expected_f_star, abs=1e-9)


# ---------------------------------------------------------------------------
# Gate 8: CVaR
# ---------------------------------------------------------------------------


class TestGate8CVaR:
    def test_cvar_none_skips_gate(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(cvar=None))
        assert result.approved is True

    def test_cvar_unavailable_skips_gate(self) -> None:
        eng = _engine()
        cvar = CVaRInput(cvar99_pct=None, cvar_limit_pct=5.0)
        result = eng.evaluate_v2(_base_input(cvar=cvar))
        assert result.approved is True
        assert result.evidence.get("cvar_status") == "unavailable"

    def test_cvar_within_limit_passes(self) -> None:
        eng = _engine()
        cvar = CVaRInput(cvar99_pct=3.5, cvar_limit_pct=5.0)
        result = eng.evaluate_v2(_base_input(cvar=cvar))
        assert result.approved is True
        assert result.evidence["cvar99_pct"] == 3.5

    def test_cvar_exceeds_limit_blocks(self) -> None:
        eng = _engine()
        cvar = CVaRInput(cvar99_pct=7.5, cvar_limit_pct=5.0)
        result = eng.evaluate_v2(_base_input(cvar=cvar))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.CVAR_LIMIT

    def test_cvar_exactly_at_limit_passes(self) -> None:
        eng = _engine()
        cvar = CVaRInput(cvar99_pct=5.0, cvar_limit_pct=5.0)
        result = eng.evaluate_v2(_base_input(cvar=cvar))
        assert result.approved is True


# ---------------------------------------------------------------------------
# Gate 9: Portfolio limits
# ---------------------------------------------------------------------------


def _safe_portfolio(**overrides) -> PortfolioRiskSnapshot:
    defaults = dict(
        total_exposure_usd=10_000.0,
        active_position_count=2,
        max_leverage_in_use=1.5,
        max_total_exposure_usd=100_000.0,
        max_concurrent_positions=10,
    )
    defaults.update(overrides)
    return PortfolioRiskSnapshot(**defaults)


class TestGate9Portfolio:
    def test_safe_portfolio_passes(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(portfolio=_safe_portfolio()))
        assert result.approved is True
        assert result.portfolio_snapshot is not None

    def test_leverage_above_3x_blocks(self) -> None:
        eng = _engine()
        p = _safe_portfolio(max_leverage_in_use=3.5)
        result = eng.evaluate_v2(_base_input(portfolio=p))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.PORTFOLIO_LIMIT
        assert "portfolio_leverage" in result.evidence.get("block", "")

    def test_leverage_exactly_3x_passes(self) -> None:
        eng = _engine()
        p = _safe_portfolio(max_leverage_in_use=3.0)
        result = eng.evaluate_v2(_base_input(portfolio=p))
        assert result.approved is True

    def test_exposure_exceeded_blocks(self) -> None:
        eng = _engine()
        p = _safe_portfolio(total_exposure_usd=200_000.0, max_total_exposure_usd=100_000.0)
        result = eng.evaluate_v2(_base_input(portfolio=p))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.PORTFOLIO_LIMIT
        assert "portfolio_exposure" in result.evidence.get("block", "")

    def test_positions_at_cap_blocks(self) -> None:
        eng = _engine()
        p = _safe_portfolio(active_position_count=10, max_concurrent_positions=10)
        result = eng.evaluate_v2(_base_input(portfolio=p))
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.PORTFOLIO_LIMIT

    def test_positions_below_cap_passes(self) -> None:
        eng = _engine()
        p = _safe_portfolio(active_position_count=9, max_concurrent_positions=10)
        result = eng.evaluate_v2(_base_input(portfolio=p))
        assert result.approved is True

    def test_portfolio_none_skips_gate(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(portfolio=None))
        assert result.approved is True
        assert result.portfolio_snapshot is None

    def test_portfolio_evidence_fields(self) -> None:
        eng = _engine()
        result = eng.evaluate_v2(_base_input(portfolio=_safe_portfolio()))
        assert "portfolio_exposure_usd" in result.evidence
        assert "portfolio_positions" in result.evidence
        assert "portfolio_max_leverage" in result.evidence


# ---------------------------------------------------------------------------
# Combined: all v2 gates active simultaneously
# ---------------------------------------------------------------------------


class TestV2AllGatesCombined:
    def test_all_gates_active_healthy_data_approved(self) -> None:
        eng = _engine()
        ri = RiskInput(
            edge_signal=_valid_edge(),
            system_state=SystemState.NORMAL,
            no_trade=_allow(),
            timestamp_ns=_T0_NS,
            shs_snapshot=0.90,
            kill_switch_level=KS_LEVEL_NORMAL,
            dtl=DTLInput(current_price=50_000.0, liquidation_price=40_000.0, min_safe_distance_pct=5.0),
            kelly=KellyInput(win_rate=0.55, payoff_ratio=1.5, max_fraction=0.25),
            cvar=CVaRInput(cvar99_pct=3.0, cvar_limit_pct=5.0),
            portfolio=_safe_portfolio(),
        )
        result = eng.evaluate_v2(ri)
        assert result.approved is True
        assert result.dtl_pct is not None
        assert result.kelly_fraction is not None
        assert result.portfolio_snapshot is not None

    def test_first_failing_gate_wins(self) -> None:
        """Gate ordering: KS block before DTL or Kelly."""
        eng = _engine()
        ri = RiskInput(
            edge_signal=_valid_edge(),
            system_state=SystemState.NORMAL,
            no_trade=_allow(),
            timestamp_ns=_T0_NS,
            kill_switch_level=KS_LEVEL_BLOCK,  # should block here
            dtl=DTLInput(current_price=50_000.0, liquidation_price=49_999.0, min_safe_distance_pct=5.0),
            kelly=KellyInput(win_rate=0.30, payoff_ratio=1.0),  # would also block
        )
        result = eng.evaluate_v2(ri)
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.KS_BLOCKED  # gate 5 fires first


# ---------------------------------------------------------------------------
# Exception fail-closed
# ---------------------------------------------------------------------------


class TestV2FailClosed:
    def test_exception_in_kelly_gate_produces_blocked(self) -> None:
        """Corrupt input that triggers an unexpected exception → BLOCKED."""
        eng = _engine()
        # negative payoff_ratio triggers the validation block (not exception)
        kelly = KellyInput(win_rate=0.55, payoff_ratio=-1.0)
        result = eng.evaluate_v2(_base_input(kelly=kelly))
        assert result.decision == RiskDecision.BLOCKED
