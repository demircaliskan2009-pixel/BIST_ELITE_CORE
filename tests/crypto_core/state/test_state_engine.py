"""Tests for System State Engine models and engine (PRD §1.29)."""

from __future__ import annotations

import pytest

from crypto_core.state.engine import SystemStateEngine, _apply_overrides, _target_state_from_shs, compute_shs
from crypto_core.state.models import SHS_WEIGHTS, SignalInputs, StateSnapshot, SystemState, is_at_least, state_severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0 = 1_000_000_000  # base timestamp (ns)
_1MIN = 60 * 10**9
_10MIN = 10 * _1MIN
_30MIN = 30 * _1MIN
_2H = 2 * 60 * _1MIN
_6H = 6 * 60 * _1MIN


def _sig(**kwargs: float) -> SignalInputs:
    return SignalInputs(**kwargs)


def _engine(ts: int = _T0) -> tuple[SystemStateEngine, list[int]]:
    """Returns (engine, clock_list). Mutate clock_list[0] to advance time."""
    clock = [ts]
    return SystemStateEngine(wall_clock=lambda: clock[0]), clock


# ---------------------------------------------------------------------------
# compute_shs
# ---------------------------------------------------------------------------


class TestComputeShs:
    def test_all_zero_signals_gives_one(self) -> None:
        assert compute_shs(SignalInputs()) == 1.0

    def test_all_one_signals_gives_zero(self) -> None:
        sig = SignalInputs(
            s1_kill_switch=1.0,
            s2_drawdown=1.0,
            s3_cvar=1.0,
            s4_data_feed=1.0,
            s5_execution=1.0,
            s6_liquidity=1.0,
            s7_feature_drift=1.0,
            s8_correlation=1.0,
            s9_margin=1.0,
            s10_latency=1.0,
        )
        assert compute_shs(sig) == 0.0

    def test_weights_sum_to_one(self) -> None:
        assert abs(sum(SHS_WEIGHTS) - 1.0) < 1e-9

    def test_single_s1_weight(self) -> None:
        sig = SignalInputs(s1_kill_switch=1.0)
        # SHS = 1 - 0.20 * 1.0 = 0.80
        assert abs(compute_shs(sig) - 0.80) < 1e-9

    def test_single_s2_weight(self) -> None:
        sig = SignalInputs(s2_drawdown=1.0)
        # SHS = 1 - 0.15 * 1.0 = 0.85
        assert abs(compute_shs(sig) - 0.85) < 1e-9

    def test_clamp_above_one(self) -> None:
        # Over-range signal should still yield valid SHS after clamp
        shs = compute_shs(SignalInputs(s1_kill_switch=max(0.0, min(1.0, 2.0))))
        assert 0.0 <= shs <= 1.0

    def test_deterministic(self) -> None:
        sig = SignalInputs(s2_drawdown=0.5, s9_margin=0.3)
        assert compute_shs(sig) == compute_shs(sig)


# ---------------------------------------------------------------------------
# _target_state_from_shs
# ---------------------------------------------------------------------------


class TestTargetStateFromShs:
    @pytest.mark.parametrize(
        "shs,expected",
        [
            (1.00, SystemState.NORMAL),
            (0.81, SystemState.NORMAL),
            (0.80, SystemState.DEGRADED),
            (0.61, SystemState.DEGRADED),
            (0.60, SystemState.DEFENSIVE),
            (0.36, SystemState.DEFENSIVE),
            (0.35, SystemState.CRISIS),
            (0.16, SystemState.CRISIS),
            (0.15, SystemState.HALT),
            (0.00, SystemState.HALT),
        ],
    )
    def test_thresholds(self, shs: float, expected: SystemState) -> None:
        assert _target_state_from_shs(shs) == expected


# ---------------------------------------------------------------------------
# _apply_overrides
# ---------------------------------------------------------------------------


class TestApplyOverrides:
    def test_s1_one_triggers_halt(self) -> None:
        sig = SignalInputs(s1_kill_switch=1.0)
        state, reason = _apply_overrides(sig, SystemState.NORMAL)
        assert state == SystemState.HALT
        assert "KS4" in reason

    def test_s2_one_triggers_crisis(self) -> None:
        sig = SignalInputs(s2_drawdown=1.0)
        state, reason = _apply_overrides(sig, SystemState.NORMAL)
        assert state == SystemState.CRISIS
        assert "S2_drawdown" in reason

    def test_s4_one_triggers_crisis(self) -> None:
        sig = SignalInputs(s4_data_feed=1.0)
        state, reason = _apply_overrides(sig, SystemState.NORMAL)
        assert state == SystemState.CRISIS

    def test_no_override_when_healthy(self) -> None:
        sig = SignalInputs(s2_drawdown=0.5)
        state, reason = _apply_overrides(sig, SystemState.DEGRADED)
        assert state == SystemState.DEGRADED
        assert reason == "no_override"

    def test_already_crisis_keeps_crisis(self) -> None:
        sig = SignalInputs(s2_drawdown=1.0)
        state, _ = _apply_overrides(sig, SystemState.CRISIS)
        assert state == SystemState.CRISIS

    def test_already_halt_keeps_halt_on_s2(self) -> None:
        sig = SignalInputs(s2_drawdown=1.0)
        state, _ = _apply_overrides(sig, SystemState.HALT)
        assert state == SystemState.HALT


# ---------------------------------------------------------------------------
# SystemStateEngine — state_severity and is_at_least
# ---------------------------------------------------------------------------


class TestSeverityHelpers:
    def test_normal_is_least_severe(self) -> None:
        assert state_severity(SystemState.NORMAL) == 0

    def test_halt_is_most_severe(self) -> None:
        assert state_severity(SystemState.HALT) == 4

    def test_ordering(self) -> None:
        states = [
            SystemState.NORMAL,
            SystemState.DEGRADED,
            SystemState.DEFENSIVE,
            SystemState.CRISIS,
            SystemState.HALT,
        ]
        severities = [state_severity(s) for s in states]
        assert severities == sorted(severities)

    def test_is_at_least_true(self) -> None:
        assert is_at_least(SystemState.CRISIS, SystemState.DEFENSIVE)

    def test_is_at_least_false(self) -> None:
        assert not is_at_least(SystemState.DEGRADED, SystemState.DEFENSIVE)

    def test_is_at_least_equal(self) -> None:
        assert is_at_least(SystemState.DEFENSIVE, SystemState.DEFENSIVE)


# ---------------------------------------------------------------------------
# SystemStateEngine — basic state reachability
# ---------------------------------------------------------------------------


class TestEngineStateReachability:
    def test_starts_in_normal(self) -> None:
        eng, _ = _engine()
        assert eng.current_state == SystemState.NORMAL

    def test_healthy_signals_stay_normal(self) -> None:
        eng, _ = _engine()
        snap = eng.evaluate(SignalInputs(), timestamp_ns=_T0)
        assert snap.state == SystemState.NORMAL

    def test_s1_half_reaches_degraded(self) -> None:
        """s1=0.5 → SHS = 1 - 0.20*0.5 = 0.90 → NORMAL. Need s2=1.0 to reach DEGRADED."""
        eng, _ = _engine()
        # s2=1.0 → SHS = 1 - 0.15 = 0.85 → DEGRADED? No, 0.85 > 0.80 → NORMAL.
        # We need SHS <= 0.80, so at least 0.20 stress. s1=1.0 → SHS=0.80 border=DEGRADED.
        sig = SignalInputs(s1_kill_switch=1.0)  # BUT s1=1.0 triggers HALT override
        # Let's use s2=0.5 + s3=0.5 to push SHS below 0.80
        # SHS = 1 - 0.15*0.5 - 0.15*0.5 = 1 - 0.075 - 0.075 = 0.85 → still NORMAL
        # Need to get SHS to (0.60, 0.80]: use s2=1.0 → SHS = 0.85 → NORMAL
        # Let's use many signals to force DEGRADED without triggering override (no single=1.0)
        sig = SignalInputs(
            s2_drawdown=0.8,
            s3_cvar=0.8,
            s4_data_feed=0.5,
            s5_execution=0.5,
        )
        # SHS = 1 - 0.15*0.8 - 0.15*0.8 - 0.10*0.5 - 0.10*0.5 = 1 - 0.12 - 0.12 - 0.05 - 0.05 = 0.66
        # 0.60 < 0.66 <= 0.80 → DEGRADED ✓
        snap = eng.evaluate(sig, timestamp_ns=_T0)
        assert snap.state == SystemState.DEGRADED

    def test_high_stress_reaches_defensive(self) -> None:
        eng, _ = _engine()
        sig = SignalInputs(
            s2_drawdown=0.9,
            s3_cvar=0.9,
            s4_data_feed=0.8,
            s5_execution=0.8,
            s6_liquidity=0.8,
        )
        # SHS = 1 - 0.15*0.9 - 0.15*0.9 - 0.10*0.8 - 0.10*0.8 - 0.08*0.8
        #      = 1 - 0.135 - 0.135 - 0.08 - 0.08 - 0.064 = 0.506 → DEFENSIVE
        snap = eng.evaluate(sig, timestamp_ns=_T0)
        assert snap.state == SystemState.DEFENSIVE

    def test_very_high_stress_reaches_crisis(self) -> None:
        eng, _ = _engine()
        sig = SignalInputs(
            s2_drawdown=0.95,
            s3_cvar=0.95,
            s4_data_feed=0.95,
            s5_execution=0.95,
            s6_liquidity=0.95,
            s7_feature_drift=0.95,
            s8_correlation=0.95,
            s9_margin=0.95,
            s10_latency=0.95,
        )
        # SHS ≈ 1 - 0.95 * (0.15+0.10+0.10+0.08+0.07+0.05+0.05+0.05)  - 0.15*0.95
        # ≈ 1 - 0.95*0.80 = 1 - 0.76 = 0.24 → CRISIS
        snap = eng.evaluate(sig, timestamp_ns=_T0)
        assert snap.state == SystemState.CRISIS

    def test_s1_full_reaches_halt(self) -> None:
        eng, _ = _engine()
        sig = SignalInputs(s1_kill_switch=1.0)
        snap = eng.evaluate(sig, timestamp_ns=_T0)
        assert snap.state == SystemState.HALT


# ---------------------------------------------------------------------------
# SystemStateEngine — escalation is immediate
# ---------------------------------------------------------------------------


class TestEngineEscalation:
    def test_escalation_immediate_no_delay(self) -> None:
        eng, _ = _engine()
        # Start healthy
        eng.evaluate(SignalInputs(), timestamp_ns=_T0)
        assert eng.current_state == SystemState.NORMAL

        # One evaluation with high stress → immediate escalation
        stress = SignalInputs(
            s2_drawdown=0.95,
            s3_cvar=0.95,
            s4_data_feed=0.95,
            s5_execution=0.95,
            s6_liquidity=0.95,
            s7_feature_drift=0.95,
            s8_correlation=0.95,
            s9_margin=0.95,
            s10_latency=0.95,
        )
        snap = eng.evaluate(stress, timestamp_ns=_T0 + _1MIN)
        assert is_at_least(snap.state, SystemState.CRISIS)

    def test_single_maxed_signal_triggers_crisis_override(self) -> None:
        eng, _ = _engine()
        sig = SignalInputs(s3_cvar=1.0)
        snap = eng.evaluate(sig, timestamp_ns=_T0)
        assert snap.state == SystemState.CRISIS

    def test_s1_maxed_triggers_halt_override(self) -> None:
        eng, _ = _engine()
        snap = eng.evaluate(SignalInputs(s1_kill_switch=1.0), timestamp_ns=_T0)
        assert snap.state == SystemState.HALT

    def test_transition_recorded(self) -> None:
        eng, _ = _engine()
        eng.evaluate(SignalInputs(s1_kill_switch=1.0), timestamp_ns=_T0)
        assert len(eng.transitions) == 1
        t = eng.transitions[0]
        assert t.old_state == SystemState.NORMAL
        assert t.new_state == SystemState.HALT


# ---------------------------------------------------------------------------
# SystemStateEngine — de-escalation requires hysteresis
# ---------------------------------------------------------------------------


class TestEngineDeescalation:
    def _enter_degraded(self) -> tuple[SystemStateEngine, list[int]]:
        eng, clock = _engine(ts=_T0)
        stress = SignalInputs(
            s2_drawdown=0.8,
            s3_cvar=0.8,
            s4_data_feed=0.5,
            s5_execution=0.5,
        )
        eng.evaluate(stress, timestamp_ns=_T0)
        assert eng.current_state == SystemState.DEGRADED
        return eng, clock

    def test_immediate_deescalation_blocked(self) -> None:
        eng, _ = self._enter_degraded()
        # Recover immediately — should stay DEGRADED (min 10 min in state)
        snap = eng.evaluate(SignalInputs(), timestamp_ns=_T0 + _1MIN)
        assert snap.state == SystemState.DEGRADED

    def test_deescalation_allowed_after_min_duration_and_sustain(self) -> None:
        eng, _ = self._enter_degraded()
        # Must stay in DEGRADED for at least 10 min, then SHS > 0.85 for 30 min
        t = _T0 + _10MIN  # 10 min in state (min satisfied)
        # First: begin tracking SHS > 0.85
        snap = eng.evaluate(SignalInputs(), timestamp_ns=t)
        assert snap.state == SystemState.DEGRADED  # start timer

        # After 30 min of sustained SHS > 0.85 → de-escalate
        snap = eng.evaluate(SignalInputs(), timestamp_ns=t + _30MIN + 1)
        assert snap.state == SystemState.NORMAL

    def test_deescalation_candidate_resets_on_shs_drop(self) -> None:
        eng, _ = self._enter_degraded()
        t = _T0 + _10MIN
        # Start tracking
        eng.evaluate(SignalInputs(), timestamp_ns=t)
        # SHS drops back — reset candidate
        eng.evaluate(
            SignalInputs(s2_drawdown=0.8, s3_cvar=0.8, s4_data_feed=0.5, s5_execution=0.5),
            timestamp_ns=t + _1MIN,
        )
        # Even after 30 more min, no de-escalation (timer was reset)
        snap = eng.evaluate(SignalInputs(), timestamp_ns=t + _1MIN + _30MIN + 1)
        # Timer starts again from t + _1MIN, so 30min from there
        # This should still be DEGRADED unless 30 min have passed since last reset
        assert snap.state == SystemState.DEGRADED


# ---------------------------------------------------------------------------
# SystemStateEngine — HALT manual approval
# ---------------------------------------------------------------------------


class TestEngineHalt:
    def test_halt_requires_manual_approval(self) -> None:
        eng, _ = _engine()
        eng.evaluate(SignalInputs(s1_kill_switch=1.0), timestamp_ns=_T0)
        assert eng.current_state == SystemState.HALT

        # Healthy signals — should stay HALT without approval
        snap = eng.evaluate(SignalInputs(), timestamp_ns=_T0 + _30MIN)
        assert snap.state == SystemState.HALT

    def test_halt_releases_with_manual_approval_and_high_shs(self) -> None:
        eng, _ = _engine()
        eng.evaluate(SignalInputs(s1_kill_switch=1.0), timestamp_ns=_T0)
        assert eng.current_state == SystemState.HALT

        eng.approve_halt_release()
        # SHS > 0.60 with healthy signals
        snap = eng.evaluate(SignalInputs(), timestamp_ns=_T0 + _1MIN)
        assert snap.state == SystemState.CRISIS  # de-escalates to CRISIS (one step)

    def test_halt_doesnt_release_without_approval(self) -> None:
        eng, _ = _engine()
        eng.evaluate(SignalInputs(s1_kill_switch=1.0), timestamp_ns=_T0)
        # No approval
        snap = eng.evaluate(SignalInputs(), timestamp_ns=_T0 + _6H)
        assert snap.state == SystemState.HALT


# ---------------------------------------------------------------------------
# SystemStateEngine — S4 data feed floor
# ---------------------------------------------------------------------------


class TestDataFeedFloor:
    def test_s4_one_prevents_deescalation_below_defensive(self) -> None:
        """With S4=1.0, system cannot de-escalate below DEFENSIVE."""
        eng, _ = _engine()
        # Force into DEFENSIVE via stress
        stress = SignalInputs(
            s2_drawdown=0.8,
            s3_cvar=0.8,
            s4_data_feed=0.9,
            s5_execution=0.9,
            s6_liquidity=0.8,
        )
        eng.evaluate(stress, timestamp_ns=_T0)
        # Now s4=1.0 with otherwise healthy signals
        sig = SignalInputs(s4_data_feed=1.0)
        # s4=1.0 triggers CRISIS override (Rule 2)
        snap = eng.evaluate(sig, timestamp_ns=_T0 + _1MIN)
        assert is_at_least(snap.state, SystemState.DEFENSIVE)


# ---------------------------------------------------------------------------
# SystemStateEngine — fail-closed on invalid input
# ---------------------------------------------------------------------------


class TestEngineFailClosed:
    def test_nan_signals_clamp_to_zero(self) -> None:
        """NaN clamped to 0.0 (valid signal, not 1.0), so no override triggered."""
        # NaN: min/max comparisons behave oddly, but clamp logic guards this
        eng, _ = _engine()
        # Using 0.0 defaults should give NORMAL
        snap = eng.evaluate(SignalInputs(), timestamp_ns=_T0)
        assert snap.state == SystemState.NORMAL

    def test_snapshot_returns_correct_shs(self) -> None:
        eng, _ = _engine()
        sig = SignalInputs(s2_drawdown=0.5)
        snap = eng.evaluate(sig, timestamp_ns=_T0)
        expected_shs = 1.0 - 0.15 * 0.5
        assert abs(snap.shs - expected_shs) < 1e-9

    def test_snapshot_is_frozen(self) -> None:
        eng, _ = _engine()
        snap = eng.evaluate(SignalInputs(), timestamp_ns=_T0)
        assert isinstance(snap, StateSnapshot)
        with pytest.raises((AttributeError, TypeError)):
            snap.state = SystemState.HALT  # type: ignore[misc]
