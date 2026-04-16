"""Tests for No-Trade Guard — all blocking paths and allow path (PRD §1.21)."""

from __future__ import annotations

import pytest

from crypto_core.guard.models import (
    BlockSeverity,
    EdgeHealthInput,
    MarketRegimeInput,
    NoTradeContext,
    NoTradeDecision,
    NoTradeReason,
    RiskGuardInput,
    TemporalInput,
)
from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000  # base timestamp in ns (arbitrary)
_NS_PER_MS = 1_000_000
_NS_PER_S = 1_000_000_000


def _good_ctx(**overrides: object) -> NoTradeContext:
    """Returns a fully healthy context — all checks should pass."""
    defaults: dict[str, object] = {
        "symbol": "BTCUSDT",
        "exchange": "binance",
        "current_ns": _T0_NS,
        "book_last_update_ns": _T0_NS - 100 * _NS_PER_MS,  # 100ms ago
        "book_has_snapshot": True,
        "book_bid_count": 5,
        "book_ask_count": 5,
        "feed_connection_state": "connected",
        "feed_recovery_state": "ready",
        "supported_symbols": frozenset({"BTCUSDT", "ETHUSDT"}),
        "system_state": SystemState.NORMAL,
        "latency_ms": 10.0,
        "telemetry_last_emit_ns": _T0_NS - 1 * _NS_PER_S,  # 1 second ago
    }
    defaults.update(overrides)
    return NoTradeContext(**defaults)  # type: ignore[arg-type]


def _guard(**cfg_overrides: object) -> NoTradeGuard:
    return NoTradeGuard(NoTradeConfig(**cfg_overrides))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Allow path
# ---------------------------------------------------------------------------


class TestAllowPath:
    def test_healthy_context_allows_trading(self) -> None:
        guard = _guard()
        decision = guard.evaluate(_good_ctx())
        assert decision.allowed is True
        assert decision.reason is None
        assert decision.severity is None

    def test_allow_evidence_populated(self) -> None:
        guard = _guard()
        decision = guard.evaluate(_good_ctx())
        assert "symbol" in decision.evidence

    def test_deterministic_repeated_calls(self) -> None:
        guard = _guard()
        ctx = _good_ctx()
        d1 = guard.evaluate(ctx)
        d2 = guard.evaluate(ctx)
        assert d1.allowed == d2.allowed


# ---------------------------------------------------------------------------
# NT-D01: Stale data
# ---------------------------------------------------------------------------


class TestStaleData:
    def test_stale_data_blocks(self) -> None:
        guard = _guard(stale_data_threshold_ms=5_000)
        # book updated 10 seconds ago
        ctx = _good_ctx(book_last_update_ns=_T0_NS - 10 * _NS_PER_S)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.STALE_DATA
        assert d.severity == BlockSeverity.SOFT
        assert "age_ms" in d.evidence

    def test_fresh_data_passes(self) -> None:
        guard = _guard(stale_data_threshold_ms=5_000)
        ctx = _good_ctx(book_last_update_ns=_T0_NS - 100 * _NS_PER_MS)
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_never_updated_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_last_update_ns=0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.STALE_DATA


# ---------------------------------------------------------------------------
# NT-D02: Invalid book
# ---------------------------------------------------------------------------


class TestInvalidBook:
    def test_zero_bids_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_bid_count=0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.INVALID_BOOK
        assert d.severity == BlockSeverity.HARD

    def test_zero_asks_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_ask_count=0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.INVALID_BOOK

    def test_sufficient_levels_passes(self) -> None:
        guard = _guard(min_book_bid_levels=1, min_book_ask_levels=1)
        ctx = _good_ctx(book_bid_count=1, book_ask_count=1)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-D03: Missing snapshot
# ---------------------------------------------------------------------------


class TestMissingSnapshot:
    def test_no_snapshot_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_has_snapshot=False)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.MISSING_SNAPSHOT
        assert d.severity == BlockSeverity.HARD

    def test_snapshot_present_passes(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_has_snapshot=True)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-D04: Unsupported symbol
# ---------------------------------------------------------------------------


class TestUnsupportedSymbol:
    def test_unsupported_symbol_blocks(self) -> None:
        guard = _guard(supported_symbols=frozenset({"ETHUSDT"}))
        ctx = _good_ctx(symbol="BTCUSDT", supported_symbols=frozenset())
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.UNSUPPORTED_SYMBOL
        assert d.severity == BlockSeverity.HARD

    def test_supported_symbol_passes(self) -> None:
        guard = _guard(supported_symbols=frozenset({"BTCUSDT"}))
        ctx = _good_ctx(symbol="BTCUSDT")
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_empty_supported_set_skips_check(self) -> None:
        guard = _guard(supported_symbols=frozenset())
        ctx = _good_ctx(symbol="XYZUSDT", supported_symbols=frozenset())
        d = guard.evaluate(ctx)
        # No supported_symbols configured → skip check
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-D05: Recovery active
# ---------------------------------------------------------------------------


class TestRecoveryActive:
    @pytest.mark.parametrize(
        "recovery_state",
        ["snapshotting", "replaying", "validating"],
    )
    def test_recovery_states_block(self, recovery_state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(feed_recovery_state=recovery_state)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.RECOVERY_ACTIVE
        assert d.severity == BlockSeverity.SOFT

    @pytest.mark.parametrize(
        "conn_state",
        ["reconnecting", "failed", "disconnected", "connecting"],
    )
    def test_unhealthy_connection_states_block(self, conn_state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(feed_connection_state=conn_state, feed_recovery_state="idle")
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.RECOVERY_ACTIVE

    def test_ready_state_passes(self) -> None:
        guard = _guard()
        ctx = _good_ctx(feed_recovery_state="ready", feed_connection_state="connected")
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-X01: System state defensive
# ---------------------------------------------------------------------------


class TestSystemStateBlock:
    @pytest.mark.parametrize(
        "state",
        [SystemState.DEFENSIVE, SystemState.CRISIS, SystemState.HALT],
    )
    def test_defensive_and_above_blocks(self, state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(system_state=state)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.SYSTEM_STATE_DEFENSIVE
        assert d.severity == BlockSeverity.CRITICAL

    @pytest.mark.parametrize(
        "state",
        [SystemState.NORMAL, SystemState.DEGRADED],
    )
    def test_normal_and_degraded_passes(self, state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(system_state=state)
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_custom_block_threshold(self) -> None:
        guard = _guard(block_at_state=SystemState.DEGRADED)
        ctx = _good_ctx(system_state=SystemState.DEGRADED)
        d = guard.evaluate(ctx)
        assert d.allowed is False


# ---------------------------------------------------------------------------
# NT-X02: Latency budget breach
# ---------------------------------------------------------------------------


class TestLatencyBudget:
    def test_latency_over_budget_blocks(self) -> None:
        guard = _guard(latency_budget_ms=100.0)
        ctx = _good_ctx(latency_ms=200.0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.LATENCY_BUDGET_BREACH
        assert d.severity == BlockSeverity.SOFT
        assert d.evidence["latency_ms"] == 200.0

    def test_latency_within_budget_passes(self) -> None:
        guard = _guard(latency_budget_ms=500.0)
        ctx = _good_ctx(latency_ms=50.0)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-X03: Telemetry unavailable
# ---------------------------------------------------------------------------


class TestTelemetryUnavailable:
    def test_stale_telemetry_blocks(self) -> None:
        guard = _guard(telemetry_window_ms=60_000)
        # Telemetry last emitted 5 minutes ago
        ctx = _good_ctx(telemetry_last_emit_ns=_T0_NS - 5 * 60 * _NS_PER_S)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.TELEMETRY_UNAVAILABLE
        assert d.severity == BlockSeverity.HARD

    def test_fresh_telemetry_passes(self) -> None:
        guard = _guard(telemetry_window_ms=60_000)
        ctx = _good_ctx(telemetry_last_emit_ns=_T0_NS - 1 * _NS_PER_S)
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_never_emitted_telemetry_allows_default(self) -> None:
        guard = _guard()
        # telemetry_last_emit_ns=0 → first-start, permissive
        ctx = _good_ctx(telemetry_last_emit_ns=0)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NoTradeDecision factory methods
# ---------------------------------------------------------------------------


class TestNoTradeDecisionFactories:
    def test_allow_factory(self) -> None:
        d = NoTradeDecision.allow({"key": "val"})
        assert d.allowed is True
        assert d.reason is None
        assert d.severity is None
        assert d.evidence == {"key": "val"}

    def test_block_factory_sets_severity(self) -> None:
        d = NoTradeDecision.block(NoTradeReason.STALE_DATA, {"age_ms": 9999})
        assert d.allowed is False
        assert d.severity == BlockSeverity.SOFT

    def test_block_is_frozen(self) -> None:
        d = NoTradeDecision.allow()
        with pytest.raises((AttributeError, TypeError)):
            d.allowed = False  # type: ignore[misc]


# ===========================================================================
# HELPERS for new family tests
# ===========================================================================


def _healthy_risk(**overrides: object) -> RiskGuardInput:
    """RiskGuardInput that passes all NT-R rules."""
    defaults: dict[str, object] = {
        "kill_switch_level": 0,
        "daily_pnl_pct": 0.0,
        "open_risk_pct": 1.0,
        "max_single_position_pct": 10.0,
        "portfolio_cvar99_pct": 1.0,
        "margin_used_pct": 30.0,
    }
    defaults.update(overrides)
    return RiskGuardInput(**defaults)  # type: ignore[arg-type]


def _healthy_market(**overrides: object) -> MarketRegimeInput:
    """MarketRegimeInput that passes all NT-M rules."""
    defaults: dict[str, object] = {
        "liquidity_score": 0.80,
        "liquidity_crisis_sustained_ms": 0.0,
        "oi_mc_ratio": 0.05,
        "regime_transition_active": False,
        "mean_pairwise_correlation": 0.30,
    }
    defaults.update(overrides)
    return MarketRegimeInput(**defaults)  # type: ignore[arg-type]


def _healthy_edge(**overrides: object) -> EdgeHealthInput:
    """EdgeHealthInput that passes all NT-E rules."""
    defaults: dict[str, object] = {
        "edge_health_score": 0.70,
        "edge_fsm_state": "ACTIVE",
        "edge_utilization_pct": 50.0,
        "valid_edge_count": 2,
    }
    defaults.update(overrides)
    return EdgeHealthInput(**defaults)  # type: ignore[arg-type]


def _healthy_temporal(current_ns: int = _T0_NS, **overrides: object) -> TemporalInput:
    """TemporalInput that passes all NT-T rules (engine started 10 min ago)."""
    defaults: dict[str, object] = {
        "engine_start_ns": current_ns - 10 * 60 * _NS_PER_S,  # 10 min ago
        "ks_cooldown_active": False,
        "high_impact_event_window_active": False,
    }
    defaults.update(overrides)
    return TemporalInput(**defaults)  # type: ignore[arg-type]


def _full_healthy_ctx(**overrides: object) -> NoTradeContext:
    """Context with all 4 new family inputs supplied and passing."""
    base = _good_ctx()
    extra: dict[str, object] = {
        "risk": _healthy_risk(),
        "market": _healthy_market(),
        "edge": _healthy_edge(),
        "temporal": _healthy_temporal(current_ns=_T0_NS),
    }
    extra.update(overrides)
    # Rebuild using base fields + overrides
    base_dict = {
        f.name: getattr(base, f.name)
        for f in base.__dataclass_fields__.values()  # type: ignore[attr-defined]
    }
    base_dict.update(extra)
    return NoTradeContext(**base_dict)  # type: ignore[arg-type]


# ===========================================================================
# NT-R family: Risk limits
# ===========================================================================


class TestRiskFamilyKsActive:
    """NT-R01: Kill-switch active."""

    def test_ks_level_at_threshold_blocks(self) -> None:
        guard = _guard(ks_block_threshold=2)
        ctx = _full_healthy_ctx(risk=_healthy_risk(kill_switch_level=2))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.KS_ACTIVE
        assert d.severity == BlockSeverity.CRITICAL

    def test_ks_level_above_threshold_blocks(self) -> None:
        guard = _guard(ks_block_threshold=2)
        ctx = _full_healthy_ctx(risk=_healthy_risk(kill_switch_level=5))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.KS_ACTIVE

    def test_ks_level_below_threshold_passes(self) -> None:
        guard = _guard(ks_block_threshold=2)
        ctx = _full_healthy_ctx(risk=_healthy_risk(kill_switch_level=1))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_evidence_contains_ks_level(self) -> None:
        guard = _guard(ks_block_threshold=2)
        ctx = _full_healthy_ctx(risk=_healthy_risk(kill_switch_level=3))
        d = guard.evaluate(ctx)
        assert d.evidence["ks_level"] == 3
        assert d.evidence["threshold"] == 2


class TestRiskFamilyDailyLoss:
    """NT-R02: Daily loss limit."""

    def test_daily_loss_exceeds_limit_blocks(self) -> None:
        guard = _guard(daily_loss_limit_pct=2.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(daily_pnl_pct=-2.5))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.DAILY_LOSS_LIMIT
        assert d.severity == BlockSeverity.HARD

    def test_daily_loss_at_exactly_limit_passes(self) -> None:
        guard = _guard(daily_loss_limit_pct=2.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(daily_pnl_pct=-2.0))
        d = guard.evaluate(ctx)
        # -2.0 < -2.0 is False → passes
        assert d.allowed is True

    def test_daily_gain_passes(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(risk=_healthy_risk(daily_pnl_pct=1.0))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_daily_pnl_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(risk=_healthy_risk(daily_pnl_pct=None))
        d = guard.evaluate(ctx)
        # Skip NT-R02 — must not block
        assert d.allowed is True
        # Verify skipped_checks is documented
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-R02" in s for s in skipped)


class TestRiskFamilyOpenRiskCap:
    """NT-R03: Open risk cap."""

    def test_open_risk_over_cap_blocks(self) -> None:
        guard = _guard(open_risk_cap_pct=4.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(open_risk_pct=5.0))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.OPEN_RISK_CAP

    def test_open_risk_at_cap_passes(self) -> None:
        guard = _guard(open_risk_cap_pct=4.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(open_risk_pct=4.0))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_open_risk_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(risk=_healthy_risk(open_risk_pct=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-R03" in s for s in skipped)


class TestRiskFamilyPositionConcentration:
    """NT-R04: Position concentration."""

    def test_position_over_cap_blocks(self) -> None:
        guard = _guard(position_concentration_cap_pct=25.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(max_single_position_pct=30.0))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.POSITION_CONCENTRATION

    def test_position_at_cap_passes(self) -> None:
        guard = _guard(position_concentration_cap_pct=25.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(max_single_position_pct=25.0))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_concentration_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(risk=_healthy_risk(max_single_position_pct=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-R04" in s for s in skipped)


class TestRiskFamilyCVaR:
    """NT-R05: CVaR budget exhausted."""

    def test_cvar_at_budget_blocks(self) -> None:
        guard = _guard(cvar_budget_pct=5.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(portfolio_cvar99_pct=5.0))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.CVAR_BUDGET_EXHAUSTED

    def test_cvar_above_budget_blocks(self) -> None:
        guard = _guard(cvar_budget_pct=5.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(portfolio_cvar99_pct=6.5))
        d = guard.evaluate(ctx)
        assert d.allowed is False

    def test_cvar_below_budget_passes(self) -> None:
        guard = _guard(cvar_budget_pct=5.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(portfolio_cvar99_pct=3.0))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_cvar_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(risk=_healthy_risk(portfolio_cvar99_pct=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-R05" in s for s in skipped)


class TestRiskFamilyMarginUtilization:
    """NT-R06: Margin utilization."""

    def test_margin_over_cap_blocks(self) -> None:
        guard = _guard(margin_utilization_cap_pct=80.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(margin_used_pct=85.0))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.MARGIN_UTILIZATION

    def test_margin_at_cap_passes(self) -> None:
        guard = _guard(margin_utilization_cap_pct=80.0)
        ctx = _full_healthy_ctx(risk=_healthy_risk(margin_used_pct=80.0))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_margin_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(risk=_healthy_risk(margin_used_pct=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-R06" in s for s in skipped)


class TestRiskFamilyGroupDisabled:
    """Risk input None disables entire NT-R family."""

    def test_risk_none_skips_family(self) -> None:
        guard = _guard(ks_block_threshold=1)
        # Even if KS level would block, with risk=None the family is skipped
        ctx = _full_healthy_ctx(risk=None)
        # Guard should still allow if other families pass
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-R" in s for s in skipped)


# ===========================================================================
# NT-M family: Market / regime
# ===========================================================================


class TestMarketFamilyLiquidityCrisis:
    """NT-M01: Liquidity regime CRISIS."""

    def test_liquidity_crisis_sustained_blocks(self) -> None:
        guard = _guard(
            liquidity_crisis_threshold=0.15,
            liquidity_crisis_min_duration_ms=30 * 60 * 1000.0,
        )
        ctx = _full_healthy_ctx(
            market=_healthy_market(
                liquidity_score=0.10,
                liquidity_crisis_sustained_ms=35 * 60 * 1000.0,  # 35 min > 30 min
            )
        )
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.LIQUIDITY_CRISIS
        assert d.severity == BlockSeverity.HARD

    def test_liquidity_crisis_not_yet_sustained_passes(self) -> None:
        guard = _guard(
            liquidity_crisis_threshold=0.15,
            liquidity_crisis_min_duration_ms=30 * 60 * 1000.0,
        )
        ctx = _full_healthy_ctx(
            market=_healthy_market(
                liquidity_score=0.10,
                liquidity_crisis_sustained_ms=5 * 60 * 1000.0,  # only 5 min
            )
        )
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_liquidity_crisis_sustained_ms_none_blocks_immediately(self) -> None:
        """If liquidity is low but duration is unavailable, fail-closed → block."""
        guard = _guard(liquidity_crisis_threshold=0.15)
        ctx = _full_healthy_ctx(
            market=_healthy_market(
                liquidity_score=0.10,
                liquidity_crisis_sustained_ms=None,
            )
        )
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.LIQUIDITY_CRISIS

    def test_liquidity_above_threshold_passes(self) -> None:
        guard = _guard(liquidity_crisis_threshold=0.15)
        ctx = _full_healthy_ctx(market=_healthy_market(liquidity_score=0.80))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_liquidity_score_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(market=_healthy_market(liquidity_score=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-M01" in s for s in skipped)


class TestMarketFamilyLeverageExtreme:
    """NT-M02: Leverage regime EXTREME."""

    def test_oi_mc_over_threshold_blocks(self) -> None:
        guard = _guard(oi_mc_extreme_threshold=0.10)
        ctx = _full_healthy_ctx(market=_healthy_market(oi_mc_ratio=0.15))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.LEVERAGE_EXTREME
        assert d.severity == BlockSeverity.HARD

    def test_oi_mc_at_threshold_passes(self) -> None:
        guard = _guard(oi_mc_extreme_threshold=0.10)
        ctx = _full_healthy_ctx(market=_healthy_market(oi_mc_ratio=0.10))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_oi_mc_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(market=_healthy_market(oi_mc_ratio=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-M02" in s for s in skipped)


class TestMarketFamilyRegimeTransition:
    """NT-M03: Regime transition in progress."""

    def test_regime_transition_active_blocks(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(market=_healthy_market(regime_transition_active=True))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.REGIME_TRANSITION
        assert d.severity == BlockSeverity.SOFT

    def test_regime_stable_passes(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(market=_healthy_market(regime_transition_active=False))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_regime_transition_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(market=_healthy_market(regime_transition_active=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-M03" in s for s in skipped)


class TestMarketFamilyCorrelationBreakdown:
    """NT-M04: Correlation breakdown."""

    def test_correlation_over_threshold_blocks(self) -> None:
        guard = _guard(correlation_crisis_threshold=0.85)
        ctx = _full_healthy_ctx(market=_healthy_market(mean_pairwise_correlation=0.92))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.CORRELATION_BREAKDOWN
        assert d.severity == BlockSeverity.HARD

    def test_correlation_at_threshold_passes(self) -> None:
        guard = _guard(correlation_crisis_threshold=0.85)
        ctx = _full_healthy_ctx(market=_healthy_market(mean_pairwise_correlation=0.85))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_correlation_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(market=_healthy_market(mean_pairwise_correlation=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-M04" in s for s in skipped)


class TestMarketFamilyGroupDisabled:
    """market=None disables entire NT-M family."""

    def test_market_none_skips_family(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(market=None)
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-M" in s for s in skipped)


# ===========================================================================
# NT-E family: Edge health
# ===========================================================================


class TestEdgeFamilyHealthScore:
    """NT-E01: Edge health score too low."""

    def test_ehs_below_min_blocks(self) -> None:
        guard = _guard(ehs_min_threshold=0.30)
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_health_score=0.20))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.EDGE_HEALTH_LOW
        assert d.severity == BlockSeverity.SOFT

    def test_ehs_at_min_passes(self) -> None:
        guard = _guard(ehs_min_threshold=0.30)
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_health_score=0.30))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_ehs_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_health_score=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-E01" in s for s in skipped)


class TestEdgeFamilyDisabled:
    """NT-E02: Edge in DISABLED state."""

    def test_edge_disabled_state_blocks(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_fsm_state="DISABLED"))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.EDGE_DISABLED
        assert d.severity == BlockSeverity.HARD

    def test_edge_disabled_case_insensitive(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_fsm_state="disabled"))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.EDGE_DISABLED

    def test_edge_active_passes(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_fsm_state="ACTIVE"))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_edge_fsm_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_fsm_state=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-E02" in s for s in skipped)


class TestEdgeFamilyCapacityRed:
    """NT-E03: Edge capacity RED."""

    def test_utilization_at_threshold_blocks(self) -> None:
        guard = _guard(edge_utilization_red_threshold=80.0)
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_utilization_pct=80.0))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.EDGE_CAPACITY_RED
        assert d.severity == BlockSeverity.SOFT

    def test_utilization_above_threshold_blocks(self) -> None:
        guard = _guard(edge_utilization_red_threshold=80.0)
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_utilization_pct=95.0))
        d = guard.evaluate(ctx)
        assert d.allowed is False

    def test_utilization_below_threshold_passes(self) -> None:
        guard = _guard(edge_utilization_red_threshold=80.0)
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_utilization_pct=60.0))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_utilization_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(edge_utilization_pct=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-E03" in s for s in skipped)


class TestEdgeFamilyNoValidEdge:
    """NT-E04: No valid edge for asset."""

    def test_zero_valid_edges_blocks(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(valid_edge_count=0))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.NO_VALID_EDGE
        assert d.severity == BlockSeverity.HARD

    def test_one_valid_edge_passes(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(valid_edge_count=1))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_valid_edge_count_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=_healthy_edge(valid_edge_count=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-E04" in s for s in skipped)


class TestEdgeFamilyGroupDisabled:
    """edge=None disables entire NT-E family."""

    def test_edge_none_skips_family(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(edge=None)
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-E" in s for s in skipped)


# ===========================================================================
# NT-T family: Temporal restrictions
# ===========================================================================


class TestTemporalFamilyStartupWarmup:
    """NT-T01: System startup warmup."""

    def test_within_warmup_period_blocks(self) -> None:
        guard = _guard(startup_warmup_ms=300_000.0)  # 5 min
        # Engine started 2 minutes ago
        start_ns = _T0_NS - 2 * 60 * _NS_PER_S
        ctx = _full_healthy_ctx(
            temporal=_healthy_temporal(
                engine_start_ns=start_ns,
                ks_cooldown_active=False,
                high_impact_event_window_active=False,
            )
        )
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.STARTUP_WARMUP
        assert d.severity == BlockSeverity.SOFT
        assert d.evidence["age_ms"] < 300_000.0

    def test_after_warmup_period_passes(self) -> None:
        guard = _guard(startup_warmup_ms=300_000.0)
        # Engine started 10 minutes ago
        start_ns = _T0_NS - 10 * 60 * _NS_PER_S
        ctx = _full_healthy_ctx(temporal=_healthy_temporal(engine_start_ns=start_ns))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_engine_start_ns_zero_disables_check(self) -> None:
        guard = _guard(startup_warmup_ms=300_000.0)
        ctx = _full_healthy_ctx(
            temporal=TemporalInput(
                engine_start_ns=0,
                ks_cooldown_active=False,
                high_impact_event_window_active=False,
            )
        )
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-T01" in s for s in skipped)


class TestTemporalFamilyKsCooldown:
    """NT-T02: Post-kill-switch cool-down."""

    def test_ks_cooldown_active_blocks(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(temporal=_healthy_temporal(ks_cooldown_active=True))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.KS_COOLDOWN
        assert d.severity == BlockSeverity.SOFT

    def test_ks_cooldown_inactive_passes(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(temporal=_healthy_temporal(ks_cooldown_active=False))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_ks_cooldown_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(temporal=_healthy_temporal(ks_cooldown_active=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-T02" in s for s in skipped)


class TestTemporalFamilyHighImpactEvent:
    """NT-T03: High-impact event window."""

    def test_event_window_active_blocks(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(temporal=_healthy_temporal(high_impact_event_window_active=True))
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.HIGH_IMPACT_EVENT
        assert d.severity == BlockSeverity.SOFT

    def test_no_event_window_passes(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(temporal=_healthy_temporal(high_impact_event_window_active=False))
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_event_window_unavailable_skips(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(temporal=_healthy_temporal(high_impact_event_window_active=None))
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-T03" in s for s in skipped)


class TestTemporalFamilyGroupDisabled:
    """temporal=None disables entire NT-T family."""

    def test_temporal_none_skips_family(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(temporal=None)
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-T" in s for s in skipped)


# ===========================================================================
# Rule ordering tests — PRD order: Data > Risk > Market > Edge > Exec > Temporal
# ===========================================================================


class TestRuleOrdering:
    """First blocking rule in PRD priority order wins."""

    def test_data_rule_blocks_before_risk(self) -> None:
        """NT-D (stale data) fires before NT-R (KS active)."""
        guard = _guard(stale_data_threshold_ms=100.0, ks_block_threshold=1)
        ctx = _full_healthy_ctx(
            book_last_update_ns=_T0_NS - 10 * _NS_PER_S,  # stale
            risk=_healthy_risk(kill_switch_level=5),  # also would block
        )
        d = guard.evaluate(ctx)
        assert d.reason == NoTradeReason.STALE_DATA

    def test_risk_blocks_before_market(self) -> None:
        """NT-R (KS) fires before NT-M (regime)."""
        guard = _guard(ks_block_threshold=1)
        ctx = _full_healthy_ctx(
            risk=_healthy_risk(kill_switch_level=2),
            market=_healthy_market(regime_transition_active=True),
        )
        d = guard.evaluate(ctx)
        assert d.reason == NoTradeReason.KS_ACTIVE

    def test_market_blocks_before_edge(self) -> None:
        """NT-M fires before NT-E."""
        guard = _guard()
        ctx = _full_healthy_ctx(
            market=_healthy_market(regime_transition_active=True),
            edge=_healthy_edge(valid_edge_count=0),
        )
        d = guard.evaluate(ctx)
        assert d.reason == NoTradeReason.REGIME_TRANSITION

    def test_edge_blocks_before_execution(self) -> None:
        """NT-E fires before NT-X."""
        guard = _guard()
        ctx = _full_healthy_ctx(
            edge=_healthy_edge(valid_edge_count=0),
            system_state=SystemState.DEFENSIVE,
        )
        d = guard.evaluate(ctx)
        assert d.reason == NoTradeReason.NO_VALID_EDGE

    def test_execution_blocks_before_temporal(self) -> None:
        """NT-X fires before NT-T."""
        guard = _guard(startup_warmup_ms=300_000.0)
        start_ns = _T0_NS - 2 * 60 * _NS_PER_S  # within warmup
        ctx = _full_healthy_ctx(
            system_state=SystemState.DEFENSIVE,
            temporal=_healthy_temporal(engine_start_ns=start_ns),
        )
        d = guard.evaluate(ctx)
        assert d.reason == NoTradeReason.SYSTEM_STATE_DEFENSIVE

    def test_deterministic_repeated_evaluation(self) -> None:
        """Same context always produces same result."""
        guard = _guard(ks_block_threshold=1)
        ctx = _full_healthy_ctx(risk=_healthy_risk(kill_switch_level=3))
        results = [guard.evaluate(ctx) for _ in range(5)]
        assert all(r.reason == results[0].reason for r in results)


# ===========================================================================
# Skipped-checks audit trail
# ===========================================================================


class TestSkippedChecksAudit:
    """Guard must document all explicitly skipped checks in evidence."""

    def test_all_families_none_documents_all_skipped(self) -> None:
        guard = _guard()
        ctx = _good_ctx()  # no risk/market/edge/temporal → all None
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        # Each family should be represented
        skipped_str = " ".join(skipped)
        assert "NT-R" in skipped_str
        assert "NT-M" in skipped_str
        assert "NT-E" in skipped_str
        assert "NT-T" in skipped_str

    def test_partial_unavailability_documented(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx(
            risk=_healthy_risk(daily_pnl_pct=None, open_risk_pct=None),
        )
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        assert any("NT-R02" in s for s in skipped)
        assert any("NT-R03" in s for s in skipped)

    def test_no_skipped_when_all_inputs_provided(self) -> None:
        guard = _guard()
        ctx = _full_healthy_ctx()
        d = guard.evaluate(ctx)
        assert d.allowed is True
        skipped = d.evidence.get("skipped_checks", [])
        # All temporal checks pass (engine_start=0 is 1 skip, but that's expected)
        # Verify no risk/market/edge skips
        skipped_str = " ".join(skipped)
        assert "NT-R02" not in skipped_str
        assert "NT-R03" not in skipped_str
        assert "NT-M01" not in skipped_str


# ===========================================================================
# Backward compatibility — existing tests still work with new families=None
# ===========================================================================


class TestBackwardCompatibility:
    """_good_ctx() produces risk/market/edge/temporal=None → new families skipped."""

    def test_good_ctx_without_new_fields_still_allows(self) -> None:
        guard = _guard()
        ctx = _good_ctx()
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_existing_data_rules_unaffected_by_new_families(self) -> None:
        guard = _guard()
        # Stale data should still block even with no new families
        ctx = _good_ctx(book_last_update_ns=0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.STALE_DATA

    def test_existing_execution_rules_unaffected(self) -> None:
        guard = _guard()
        ctx = _good_ctx(system_state=SystemState.CRISIS)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.SYSTEM_STATE_DEFENSIVE
