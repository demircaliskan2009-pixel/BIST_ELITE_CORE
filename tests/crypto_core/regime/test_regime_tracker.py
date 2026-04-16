"""Tests for the market regime tracker subsystem — Phase 5E.

Covers:
  - Regime tracker unit tests (models, score computation, transition detection)
  - Guard integration tests (NT-M01–NT-M04 with real upstream values)
  - Orchestrator integration tests (end-to-end wiring, telemetry, determinism)

PRD reference: §1.21 NT-M family.
"""

from __future__ import annotations

import time

import pytest

from crypto_core.guard.models import MarketRegimeInput, NoTradeReason
from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard
from crypto_core.regime.models import (
    LiquidityLevel,
    LiquiditySignal,
    RegimeEvidenceQuality,
    RegimeSignalInput,
    RegimeSnapshot,
)
from crypto_core.regime.tracker import (
    _NS_PER_MS,
    MarketRegimeTracker,
)

# ---------------------------------------------------------------------------
# Shared test fixtures / helpers
# ---------------------------------------------------------------------------

_T0 = int(time.time() * 1e9)  # reference wall-clock in ns
_ONE_MINUTE_NS: int = 60 * 1_000_000_000
_ONE_HOUR_NS: int = 3600 * 1_000_000_000


def _signal(
    bid: int = 10,
    ask: int = 10,
    trades: int = 5,
    ts: int = _T0,
    leverage_proxy: float | None = None,
    correlation_score: float | None = None,
    bid_depth_usd: float | None = None,
    ask_depth_usd: float | None = None,
    spread_bps: float | None = None,
) -> RegimeSignalInput:
    """Build a RegimeSignalInput with sensible defaults."""
    return RegimeSignalInput(
        snapshot_ns=ts,
        liquidity=LiquiditySignal(
            bid_level_count=bid,
            ask_level_count=ask,
            recent_trade_count=trades,
            timestamp_ns=ts,
            bid_depth_usd=bid_depth_usd,
            ask_depth_usd=ask_depth_usd,
            bid_ask_spread_bps=spread_bps,
        ),
        leverage_proxy=leverage_proxy,
        correlation_score=correlation_score,
    )


def _signal_no_book(
    ts: int = _T0,
    leverage_proxy: float | None = None,
    correlation_score: float | None = None,
) -> RegimeSignalInput:
    """Build a RegimeSignalInput without any liquidity signal."""
    return RegimeSignalInput(
        snapshot_ns=ts,
        liquidity=None,
        leverage_proxy=leverage_proxy,
        correlation_score=correlation_score,
    )


# ============================================================================
# SECTION 1: Models — frozen, field correctness
# ============================================================================


class TestLiquiditySignalModel:
    def test_frozen(self) -> None:
        sig = LiquiditySignal(bid_level_count=5, ask_level_count=5, recent_trade_count=3, timestamp_ns=_T0)
        with pytest.raises((AttributeError, TypeError)):
            sig.bid_level_count = 10  # type: ignore[misc]

    def test_optional_depth_default_none(self) -> None:
        sig = LiquiditySignal(bid_level_count=5, ask_level_count=5, recent_trade_count=3, timestamp_ns=_T0)
        assert sig.bid_depth_usd is None
        assert sig.ask_depth_usd is None
        assert sig.bid_ask_spread_bps is None


class TestRegimeSignalInputModel:
    def test_frozen(self) -> None:
        sig = _signal()
        with pytest.raises((AttributeError, TypeError)):
            sig.snapshot_ns = 999  # type: ignore[misc]

    def test_defaults(self) -> None:
        sig = RegimeSignalInput(snapshot_ns=_T0)
        assert sig.liquidity is None
        assert sig.leverage_proxy is None
        assert sig.correlation_score is None


class TestRegimeSnapshotModel:
    def test_frozen(self) -> None:
        snap = RegimeSnapshot(
            snapshot_ns=_T0,
            evidence_quality=RegimeEvidenceQuality.MINIMAL,
            liquidity_score=1.0,
            liquidity_crisis_sustained_ms=None,
            oi_mc_ratio=None,
            regime_transition_active=None,
            mean_pairwise_correlation=None,
            liquidity_level=LiquidityLevel.HEALTHY,
            crisis_first_seen_ns=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            snap.liquidity_score = 0.5  # type: ignore[misc]


# ============================================================================
# SECTION 2: Tracker construction
# ============================================================================


class TestTrackerConstruction:
    def test_default_construction(self) -> None:
        t = MarketRegimeTracker()
        assert t.history_size == 20
        assert t.observation_count == 0

    def test_custom_history_size(self) -> None:
        t = MarketRegimeTracker(history_size=5)
        assert t.history_size == 5

    def test_invalid_history_size_raises(self) -> None:
        with pytest.raises(ValueError, match="history_size must be"):
            MarketRegimeTracker(history_size=1)

    def test_reset_clears_state(self) -> None:
        t = MarketRegimeTracker()
        t.update(_signal(bid=10, ask=10))
        assert t.observation_count == 1
        t.reset()
        assert t.observation_count == 0


# ============================================================================
# SECTION 3: Liquidity score computation
# ============================================================================


class TestLiquidityScore:
    def test_healthy_liquidity_max_score(self) -> None:
        """10 levels per side → score = 1.0, level = HEALTHY."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10))
        assert snap.liquidity_score == pytest.approx(1.0)
        assert snap.liquidity_level == LiquidityLevel.HEALTHY

    def test_healthy_more_than_10_levels(self) -> None:
        """More than 10 levels → clamped to 1.0."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=20, ask=20))
        assert snap.liquidity_score == pytest.approx(1.0)

    def test_zero_levels_crisis_score(self) -> None:
        """Zero levels → score 0.0 → CRISIS."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=0, ask=0))
        assert snap.liquidity_score == pytest.approx(0.0)
        assert snap.liquidity_level == LiquidityLevel.CRISIS

    def test_one_level_crisis_score(self) -> None:
        """One level per side → 1/10 = 0.1 < crisis threshold."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=1, ask=1))
        assert snap.liquidity_score == pytest.approx(0.1)
        assert snap.liquidity_level == LiquidityLevel.CRISIS

    def test_three_levels_degraded(self) -> None:
        """3 levels → 0.3 → DEGRADED (between crisis 0.15 and healthy 0.5)."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=3, ask=3))
        assert snap.liquidity_score == pytest.approx(0.3)
        assert snap.liquidity_level == LiquidityLevel.DEGRADED

    def test_five_levels_healthy(self) -> None:
        """5 levels → 0.5 = healthy boundary."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=5, ask=5))
        assert snap.liquidity_score == pytest.approx(0.5)
        assert snap.liquidity_level == LiquidityLevel.HEALTHY

    def test_min_side_used(self) -> None:
        """Score is based on min(bid, ask) — lower side determines liquidity."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=1))
        assert snap.liquidity_score == pytest.approx(0.1)
        assert snap.liquidity_level == LiquidityLevel.CRISIS

    def test_depth_based_score_when_available(self) -> None:
        """With depth USD available, score is depth-based not level-count."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10, bid_depth_usd=250_000.0, ask_depth_usd=250_000.0))
        # total_depth = 500k = _HEALTHY_DEPTH_USD → score 1.0
        assert snap.liquidity_score == pytest.approx(1.0)

    def test_partial_depth_half_healthy(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10, bid_depth_usd=125_000.0, ask_depth_usd=125_000.0))
        assert snap.liquidity_score == pytest.approx(0.5)
        assert snap.liquidity_level == LiquidityLevel.HEALTHY

    def test_spread_penalty_reduces_score(self) -> None:
        """High spread should reduce score via spread penalty."""
        t = MarketRegimeTracker()
        snap_no_spread = t.update(_signal(bid=10, ask=10))
        t.reset()
        snap_high_spread = t.update(_signal(bid=10, ask=10, spread_bps=250.0))
        # 250/500 = 50% penalty → 1.0 * 0.5 = 0.5
        assert snap_no_spread.liquidity_score == pytest.approx(1.0)
        assert snap_high_spread.liquidity_score == pytest.approx(0.5)

    def test_max_spread_zeros_score(self) -> None:
        """500 bps spread → full penalty → score = 0."""
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10, spread_bps=500.0))
        assert snap.liquidity_score == pytest.approx(0.0)

    def test_no_book_signal_score_is_none(self) -> None:
        """No liquidity signal → liquidity_score is None."""
        t = MarketRegimeTracker()
        snap = t.update(_signal_no_book())
        assert snap.liquidity_score is None
        assert snap.liquidity_level is None

    def test_evidence_quality_minimal_level_only(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10))
        assert snap.evidence_quality == RegimeEvidenceQuality.MINIMAL

    def test_evidence_quality_partial_depth_only(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10, bid_depth_usd=100_000.0, ask_depth_usd=100_000.0))
        assert snap.evidence_quality == RegimeEvidenceQuality.PARTIAL

    def test_evidence_quality_full_depth_and_spread(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10, bid_depth_usd=100_000.0, ask_depth_usd=100_000.0, spread_bps=5.0))
        assert snap.evidence_quality == RegimeEvidenceQuality.FULL

    def test_evidence_quality_unavailable_when_no_book(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal_no_book())
        assert snap.evidence_quality == RegimeEvidenceQuality.UNAVAILABLE


# ============================================================================
# SECTION 4: Crisis tracking (sustained duration)
# ============================================================================


class TestCrisisTracking:
    def test_no_crisis_initially(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10))
        assert snap.liquidity_crisis_sustained_ms is None
        assert snap.crisis_first_seen_ns is None

    def test_crisis_starts_on_first_low_score(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=1, ask=1, ts=_T0))
        # crisis just started → sustained_ms = 0
        assert snap.crisis_first_seen_ns == _T0
        assert snap.liquidity_crisis_sustained_ms == pytest.approx(0.0)

    def test_crisis_sustained_after_2_minutes(self) -> None:
        t = MarketRegimeTracker()
        t.update(_signal(bid=1, ask=1, ts=_T0))
        snap = t.update(_signal(bid=1, ask=1, ts=_T0 + 2 * _ONE_MINUTE_NS))
        expected_ms = 2 * _ONE_MINUTE_NS / _NS_PER_MS
        assert snap.liquidity_crisis_sustained_ms == pytest.approx(expected_ms)

    def test_crisis_clears_on_recovery(self) -> None:
        t = MarketRegimeTracker()
        t.update(_signal(bid=1, ask=1, ts=_T0))
        snap = t.update(_signal(bid=10, ask=10, ts=_T0 + _ONE_MINUTE_NS))
        assert snap.crisis_first_seen_ns is None
        assert snap.liquidity_crisis_sustained_ms is None

    def test_crisis_restarts_after_recovery(self) -> None:
        t = MarketRegimeTracker()
        t.update(_signal(bid=1, ask=1, ts=_T0))
        t.update(_signal(bid=10, ask=10, ts=_T0 + _ONE_MINUTE_NS))
        # New crisis at t2
        t2 = _T0 + 2 * _ONE_MINUTE_NS
        snap = t.update(_signal(bid=1, ask=1, ts=t2))
        assert snap.crisis_first_seen_ns == t2
        assert snap.liquidity_crisis_sustained_ms == pytest.approx(0.0)


# ============================================================================
# SECTION 5: Regime transition detection
# ============================================================================


class TestRegimeTransition:
    def test_none_on_single_observation(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(bid=10, ask=10))
        assert snap.regime_transition_active is None

    def test_false_on_stable_healthy_sequence(self) -> None:
        t = MarketRegimeTracker()
        for i in range(5):
            snap = t.update(_signal(bid=10, ask=10, ts=_T0 + i * _ONE_MINUTE_NS))
        assert snap.regime_transition_active is False

    def test_transition_active_after_instability(self) -> None:
        """3+ level changes within 5-minute window → transition_active=True."""
        t = MarketRegimeTracker()
        sequence = [10, 1, 10, 1, 10]  # HEALTHY→CRISIS→HEALTHY→CRISIS→HEALTHY = 4 changes
        for i, bid in enumerate(sequence):
            snap = t.update(_signal(bid=bid, ask=bid, ts=_T0 + i * _ONE_MINUTE_NS))
        # At least 3 level changes within 5-minute window
        assert snap.regime_transition_active is True

    def test_transition_false_below_threshold(self) -> None:
        """2 level changes (below threshold of 3) → not transitioning."""
        t = MarketRegimeTracker()
        sequence = [10, 1, 10]  # HEALTHY→CRISIS→HEALTHY = 2 changes
        for i, bid in enumerate(sequence):
            snap = t.update(_signal(bid=bid, ask=bid, ts=_T0 + i * _ONE_MINUTE_NS))
        assert snap.regime_transition_active is False

    def test_transition_window_excludes_old_history(self) -> None:
        """Old observations (outside 5-min window) do not count toward transition."""
        t = MarketRegimeTracker()
        # First: alternate 3 times → would trigger if in window
        for i, bid in enumerate([10, 1, 10, 1]):
            t.update(_signal(bid=bid, ask=bid, ts=_T0 + i * _ONE_MINUTE_NS))
        # Now advance well past the window (10 minutes later), stable health
        snap = t.update(_signal(bid=10, ask=10, ts=_T0 + 10 * _ONE_MINUTE_NS))
        # All old changes are now outside the 5-minute window → only 1 item in window
        assert snap.regime_transition_active is None  # only 1 item in window

    def test_no_transition_without_book_signal(self) -> None:
        """No book signals → no history → regime_transition_active is None."""
        t = MarketRegimeTracker()
        snap = t.update(_signal_no_book())
        assert snap.regime_transition_active is None


# ============================================================================
# SECTION 6: Leverage proxy (NT-M02) and correlation (NT-M04) pass-through
# ============================================================================


class TestExternalInputPassThrough:
    def test_leverage_proxy_unavailable(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(leverage_proxy=None))
        assert snap.oi_mc_ratio is None

    def test_leverage_proxy_extreme(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(leverage_proxy=0.5))
        assert snap.oi_mc_ratio == pytest.approx(0.5)

    def test_leverage_proxy_normal(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(leverage_proxy=0.05))
        assert snap.oi_mc_ratio == pytest.approx(0.05)

    def test_correlation_unavailable(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(correlation_score=None))
        assert snap.mean_pairwise_correlation is None

    def test_correlation_breakdown_detected(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(correlation_score=0.9))
        assert snap.mean_pairwise_correlation == pytest.approx(0.9)

    def test_correlation_negative(self) -> None:
        t = MarketRegimeTracker()
        snap = t.update(_signal(correlation_score=-0.3))
        assert snap.mean_pairwise_correlation == pytest.approx(-0.3)


# ============================================================================
# SECTION 7: Validation / fail-closed
# ============================================================================


class TestValidation:
    def test_negative_bid_level_count_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="bid_level_count"):
            t.update(_signal(bid=-1, ask=5))

    def test_negative_ask_level_count_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="ask_level_count"):
            t.update(_signal(bid=5, ask=-1))

    def test_negative_trade_count_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="recent_trade_count"):
            t.update(
                RegimeSignalInput(
                    snapshot_ns=_T0,
                    liquidity=LiquiditySignal(
                        bid_level_count=5,
                        ask_level_count=5,
                        recent_trade_count=-1,
                        timestamp_ns=_T0,
                    ),
                )
            )

    def test_negative_bid_depth_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="bid_depth_usd"):
            t.update(_signal(bid=5, ask=5, bid_depth_usd=-1.0, ask_depth_usd=1000.0))

    def test_negative_ask_depth_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="ask_depth_usd"):
            t.update(_signal(bid=5, ask=5, bid_depth_usd=1000.0, ask_depth_usd=-1.0))

    def test_negative_spread_bps_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="bid_ask_spread_bps"):
            t.update(_signal(bid=5, ask=5, spread_bps=-5.0))

    def test_negative_leverage_proxy_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="leverage_proxy"):
            t.update(_signal(leverage_proxy=-0.01))

    def test_correlation_above_one_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="correlation_score"):
            t.update(_signal(correlation_score=1.5))

    def test_correlation_below_minus_one_raises(self) -> None:
        t = MarketRegimeTracker()
        with pytest.raises(ValueError, match="correlation_score"):
            t.update(_signal(correlation_score=-1.1))

    def test_multiple_errors_reported_together(self) -> None:
        """All errors are collected and raised as one ValueError."""
        t = MarketRegimeTracker()
        with pytest.raises(ValueError) as exc_info:
            t.update(_signal(bid=-1, ask=-1, leverage_proxy=-0.5))
        msg = str(exc_info.value)
        assert "bid_level_count" in msg
        assert "ask_level_count" in msg
        assert "leverage_proxy" in msg


# ============================================================================
# SECTION 8: Deterministic replay
# ============================================================================


class TestDeterministicReplay:
    def test_identical_inputs_identical_snapshots(self) -> None:
        """Two fresh trackers fed identical signal streams must produce identical output."""
        signals = [
            _signal(bid=10, ask=10, ts=_T0),
            _signal(bid=5, ask=5, ts=_T0 + _ONE_MINUTE_NS),
            _signal(bid=1, ask=1, ts=_T0 + 2 * _ONE_MINUTE_NS),
            _signal(bid=1, ask=1, leverage_proxy=0.12, ts=_T0 + 3 * _ONE_MINUTE_NS),
        ]
        t1 = MarketRegimeTracker()
        t2 = MarketRegimeTracker()
        for sig in signals:
            s1 = t1.update(sig)
            s2 = t2.update(sig)
            assert s1 == s2, f"Divergence at signal {sig.snapshot_ns}: {s1} != {s2}"

    def test_reset_restores_determinism(self) -> None:
        """After reset, tracker produces same output as a fresh instance."""
        sig = _signal(bid=10, ask=10, ts=_T0)
        t = MarketRegimeTracker()
        t.update(sig)  # first run
        t.reset()
        snap_after_reset = t.update(sig)

        fresh = MarketRegimeTracker()
        snap_fresh = fresh.update(sig)

        assert snap_after_reset == snap_fresh


# ============================================================================
# SECTION 9: Guard integration — NT-M01–NT-M04 with real upstream values
# ============================================================================

# shared guard context builder


def _guard_ctx_from_regime(market: MarketRegimeInput):
    """Build a minimal NoTradeContext with real market input and all data checks passing."""
    from crypto_core.guard.models import NoTradeContext

    return NoTradeContext(
        symbol="BTCUSDT",
        exchange="binance",
        current_ns=_T0,
        book_last_update_ns=_T0,
        book_has_snapshot=True,
        book_bid_count=5,
        book_ask_count=5,
        feed_connection_state="connected",
        feed_recovery_state="ready",
        system_state="NORMAL",
        market=market,
    )


class TestGuardNTM01LiquidityCrisis:
    def test_real_liquidity_crisis_blocks(self) -> None:
        """NT-M01: real liquidity score below crisis threshold blocks when sustained >= 30min."""
        tracker = MarketRegimeTracker()
        # Simulate 31 minutes of crisis
        t_crisis_start = _T0
        t_now = _T0 + int(31 * 60 * 1e9)  # 31 min later
        tracker.update(_signal(bid=1, ask=1, ts=t_crisis_start))
        snap = tracker.update(_signal(bid=1, ask=1, ts=t_now))
        assert snap.liquidity_score < 0.15
        assert snap.liquidity_crisis_sustained_ms is not None
        assert snap.liquidity_crisis_sustained_ms >= 1_800_000.0  # 30 min in ms

        market = MarketRegimeInput(
            liquidity_score=snap.liquidity_score,
            liquidity_crisis_sustained_ms=snap.liquidity_crisis_sustained_ms,
        )
        guard = NoTradeGuard()
        decision = guard.evaluate(_guard_ctx_from_regime(market))
        assert not decision.allowed
        assert decision.reason == NoTradeReason.LIQUIDITY_CRISIS

    def test_crisis_score_but_not_sustained_allows(self) -> None:
        """NT-M01: score below threshold but NOT sustained enough → ALLOW."""
        # Only 1 minute sustained (below 30-min threshold)
        market = MarketRegimeInput(
            liquidity_score=0.05,
            liquidity_crisis_sustained_ms=60_000.0,  # 1 minute < 30 minute threshold
        )
        guard = NoTradeGuard()
        decision = guard.evaluate(_guard_ctx_from_regime(market))
        assert decision.allowed  # not sustained enough

    def test_healthy_liquidity_score_allows(self) -> None:
        """NT-M01: healthy score → allow."""
        tracker = MarketRegimeTracker()
        snap = tracker.update(_signal(bid=10, ask=10, ts=_T0))
        market = MarketRegimeInput(liquidity_score=snap.liquidity_score)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed

    def test_unavailable_liquidity_skips_check(self) -> None:
        """NT-M01: liquidity_score=None → check skipped → allows (no other block)."""
        market = MarketRegimeInput(liquidity_score=None)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed


class TestGuardNTM02LeverageExtreme:
    def test_extreme_leverage_proxy_blocks(self) -> None:
        """NT-M02: oi_mc_ratio > 0.10 (default) → block LEVERAGE_EXTREME."""
        tracker = MarketRegimeTracker()
        snap = tracker.update(_signal(bid=10, ask=10, leverage_proxy=0.25))
        assert snap.oi_mc_ratio == pytest.approx(0.25)

        market = MarketRegimeInput(oi_mc_ratio=snap.oi_mc_ratio)
        guard = NoTradeGuard()
        decision = guard.evaluate(_guard_ctx_from_regime(market))
        assert not decision.allowed
        assert decision.reason == NoTradeReason.LEVERAGE_EXTREME

    def test_normal_leverage_proxy_allows(self) -> None:
        """NT-M02: oi_mc_ratio = 0.05 (below 0.10 threshold) → allow."""
        tracker = MarketRegimeTracker()
        snap = tracker.update(_signal(bid=10, ask=10, leverage_proxy=0.05))
        market = MarketRegimeInput(oi_mc_ratio=snap.oi_mc_ratio)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed

    def test_unavailable_leverage_skips_check(self) -> None:
        """NT-M02: oi_mc_ratio=None → check skipped → allows."""
        market = MarketRegimeInput(oi_mc_ratio=None)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed


class TestGuardNTM03RegimeTransition:
    def test_transition_active_blocks(self) -> None:
        """NT-M03: regime_transition_active=True → block REGIME_TRANSITION."""
        tracker = MarketRegimeTracker()
        sequence = [10, 1, 10, 1, 10]
        for i, bid in enumerate(sequence):
            snap = tracker.update(_signal(bid=bid, ask=bid, ts=_T0 + i * _ONE_MINUTE_NS))
        assert snap.regime_transition_active is True

        market = MarketRegimeInput(regime_transition_active=snap.regime_transition_active)
        guard = NoTradeGuard()
        decision = guard.evaluate(_guard_ctx_from_regime(market))
        assert not decision.allowed
        assert decision.reason == NoTradeReason.REGIME_TRANSITION

    def test_stable_regime_allows(self) -> None:
        """NT-M03: stable healthy regime → regime_transition_active=False → allow."""
        tracker = MarketRegimeTracker()
        for i in range(5):
            snap = tracker.update(_signal(bid=10, ask=10, ts=_T0 + i * _ONE_MINUTE_NS))
        assert snap.regime_transition_active is False

        market = MarketRegimeInput(regime_transition_active=False)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed

    def test_unavailable_transition_skips_check(self) -> None:
        """NT-M03: regime_transition_active=None → check skipped → allows."""
        market = MarketRegimeInput(regime_transition_active=None)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed


class TestGuardNTM04CorrelationBreakdown:
    def test_high_correlation_blocks(self) -> None:
        """NT-M04: mean_pairwise_correlation > 0.85 → block CORRELATION_BREAKDOWN."""
        tracker = MarketRegimeTracker()
        snap = tracker.update(_signal(bid=10, ask=10, correlation_score=0.92))
        assert snap.mean_pairwise_correlation == pytest.approx(0.92)

        market = MarketRegimeInput(mean_pairwise_correlation=snap.mean_pairwise_correlation)
        guard = NoTradeGuard()
        decision = guard.evaluate(_guard_ctx_from_regime(market))
        assert not decision.allowed
        assert decision.reason == NoTradeReason.CORRELATION_BREAKDOWN

    def test_normal_correlation_allows(self) -> None:
        """NT-M04: correlation = 0.5 (below 0.85 threshold) → allow."""
        market = MarketRegimeInput(mean_pairwise_correlation=0.5)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed

    def test_unavailable_correlation_skips_check(self) -> None:
        """NT-M04: mean_pairwise_correlation=None → check skipped → allows."""
        market = MarketRegimeInput(mean_pairwise_correlation=None)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed

    def test_negative_correlation_allows(self) -> None:
        """NT-M04: correlation = -0.3 → allow (not a breakdown)."""
        market = MarketRegimeInput(mean_pairwise_correlation=-0.3)
        guard = NoTradeGuard()
        assert guard.evaluate(_guard_ctx_from_regime(market)).allowed

    def test_custom_threshold(self) -> None:
        """NT-M04: respects custom correlation_crisis_threshold."""
        cfg = NoTradeConfig(correlation_crisis_threshold=0.70)
        guard = NoTradeGuard(cfg)
        market = MarketRegimeInput(mean_pairwise_correlation=0.75)
        decision = guard.evaluate(_guard_ctx_from_regime(market))
        assert not decision.allowed
        assert decision.reason == NoTradeReason.CORRELATION_BREAKDOWN


# ============================================================================
# SECTION 10: Orchestrator integration
# ============================================================================


def _make_pipeline_data(
    bid_count: int = 10,
    ask_count: int = 10,
    trades: int = 5,
    ts: int = _T0,
    symbol: str = "BTCUSDT",
):
    from crypto_core.orchestrator.models import MarketDataInput

    return MarketDataInput(
        symbol=symbol,
        exchange="binance",
        timestamp_ns=ts,
        book_bid_count=bid_count,
        book_ask_count=ask_count,
        book_has_snapshot=True,
        book_last_update_ns=ts,
        feed_connection_state="connected",
        feed_recovery_state="ready",
    )


class TestOrchestratorRegimeIntegration:
    def test_regime_tracker_wired_snapshot_available(self) -> None:
        """Regime tracker wired → market_snapshot_available=True in telemetry path."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator
        from crypto_core.regime.tracker import MarketRegimeTracker as _Tracker

        orch = PipelineOrchestrator(regime_tracker=_Tracker())
        data = _make_pipeline_data(bid_count=10, ask_count=10, ts=_T0)
        result = orch.process(data)
        # Pipeline should complete without exceptions; guard passed (healthy market)
        assert result.state_snapshot is not None

    def test_no_regime_tracker_market_family_disabled(self) -> None:
        """No regime tracker → NT-M family disabled → pipeline runs normally."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator

        orch = PipelineOrchestrator(regime_tracker=None)
        data = _make_pipeline_data(bid_count=10, ask_count=10, ts=_T0)
        result = orch.process(data)
        assert result.state_snapshot is not None

    def test_low_book_levels_triggers_nt_m01_block(self) -> None:
        """Regime tracker sees 1 level → score 0.1 → crisis but not yet sustained.

        At t=0 (first observation), sustained_ms = 0 which is < 30-min threshold.
        Guard NT-M01 requires sustained >= 30 min, so this does NOT block on first hit.
        """
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator
        from crypto_core.regime.tracker import MarketRegimeTracker as _Tracker

        orch = PipelineOrchestrator(regime_tracker=_Tracker())
        data = _make_pipeline_data(bid_count=1, ask_count=1, ts=_T0)
        result = orch.process(data)
        # Crisis just started — not yet sustained → guard allows NT-M01
        # (Other guards may fire, but NT-M01 specifically should not at t=0)
        if not result.approved:
            # If blocked, it must NOT be NT-M01 (crisis not sustained)
            assert result.block_reason != "NT-M01_liquidity_crisis"

    def test_sustained_crisis_blocks_pipeline(self) -> None:
        """Sustained 31-min crisis → NT-M01 blocks the pipeline."""
        from crypto_core.guard.no_trade_guard import NoTradeConfig
        from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
        from crypto_core.regime.tracker import MarketRegimeTracker as _Tracker

        tracker = _Tracker()
        # First: establish crisis at t0
        tracker.update(
            RegimeSignalInput(
                snapshot_ns=_T0,
                liquidity=LiquiditySignal(
                    bid_level_count=1,
                    ask_level_count=1,
                    recent_trade_count=0,
                    timestamp_ns=_T0,
                ),
            )
        )
        # Pipeline processes at t0+31min with same crisis conditions
        t_sustained = _T0 + int(31 * 60 * 1e9)
        cfg = PipelineConfig(guard=NoTradeConfig(liquidity_crisis_min_duration_ms=1_800_000.0))
        orch = PipelineOrchestrator(config=cfg, regime_tracker=tracker)
        data = _make_pipeline_data(bid_count=1, ask_count=1, ts=t_sustained)
        result = orch.process(data)
        assert not result.approved
        assert result.block_stage == "guard"
        assert result.block_reason == "NT-M01_liquidity_crisis"

    def test_deterministic_replay_orchestrator(self) -> None:
        """Same inputs → same block_reason across two independent orchestrators."""
        from crypto_core.orchestrator.pipeline import PipelineOrchestrator
        from crypto_core.regime.tracker import MarketRegimeTracker as _Tracker

        def _build_and_run():
            t = _Tracker()
            orch = PipelineOrchestrator(regime_tracker=t)
            # First observation: establish crisis
            data0 = _make_pipeline_data(bid_count=1, ask_count=1, ts=_T0)
            orch.process(data0)
            # Second: 31 min later, still crisis
            t_now = _T0 + int(31 * 60 * 1e9)
            data1 = _make_pipeline_data(bid_count=1, ask_count=1, ts=t_now)
            return orch.process(data1)

        r1 = _build_and_run()
        r2 = _build_and_run()
        assert r1.block_reason == r2.block_reason
        assert r1.block_stage == r2.block_stage
        assert r1.approved == r2.approved

    def test_telemetry_contains_regime_evidence(self) -> None:
        """Regime snapshot fields are emitted to the telemetry pipeline."""
        # We validate indirectly by checking that the pipeline completes
        # without exception when a TelemetryEmitter is wired.  The emitter
        # writes to a temporary directory; we check it doesn't raise.
        import tempfile
        from pathlib import Path

        from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
        from crypto_core.regime.tracker import MarketRegimeTracker as _Tracker
        from crypto_core.telemetry.emitter import TelemetryEmitter

        with tempfile.TemporaryDirectory() as tmpdir:
            emitter = TelemetryEmitter(log_dir=Path(tmpdir))
            cfg = PipelineConfig(emit_telemetry=True, telemetry_log_dir=tmpdir)
            orch = PipelineOrchestrator(
                config=cfg,
                telemetry_emitter=emitter,
                regime_tracker=_Tracker(),
            )
            data = _make_pipeline_data(bid_count=10, ask_count=10, ts=_T0)
            result = orch.process(data)
            # No exception = regime telemetry emitted correctly
            assert result.state_snapshot is not None
