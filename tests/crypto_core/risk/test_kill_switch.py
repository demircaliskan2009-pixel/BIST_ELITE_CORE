"""Tests for KillSwitchEngine v1 (PRD §1.19)."""

from __future__ import annotations

from crypto_core.risk.contracts import (
    KS_LEVEL_BLOCK,
    KS_LEVEL_FLATTEN,
    KS_LEVEL_HALT,
    KS_LEVEL_NORMAL,
    KS_LEVEL_REDUCE,
)
from crypto_core.risk.kill_switch import (
    TRIGGER_CRITICAL_EXCEPTION,
    TRIGGER_DATA_FAILURE_REPEATED,
    TRIGGER_DATA_FAILURE_SINGLE,
    TRIGGER_EXECUTION_CRITICAL,
    TRIGGER_EXECUTION_DEGRADED,
    TRIGGER_LATENCY_MODERATE,
    TRIGGER_LATENCY_SEVERE,
    TRIGGER_MANUAL_OVERRIDE,
    TRIGGER_RECOVERY_ACTIVE,
    TRIGGER_RECOVERY_REPEATED,
    TRIGGER_SYSTEM_CRISIS,
    TRIGGER_SYSTEM_HALT,
    TRIGGER_TELEMETRY_ABSENT,
    ExecutionQuality,
    KillSwitchEngine,
    KillSwitchInput,
    KillSwitchResult,
)
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine() -> KillSwitchEngine:
    return KillSwitchEngine()


def _normal_input(**overrides: object) -> KillSwitchInput:
    """KillSwitchInput with all-safe defaults, with optional field overrides."""
    base = {
        "system_state": SystemState.NORMAL,
    }
    base.update(overrides)  # type: ignore[arg-type]
    return KillSwitchInput(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# No triggers
# ---------------------------------------------------------------------------


class TestNoTriggers:
    def test_all_defaults_returns_ks_normal(self) -> None:
        result = _engine().compute(_normal_input())
        assert result.level == KS_LEVEL_NORMAL
        assert result.active_triggers == ()
        assert result.winning_trigger is None
        assert result.is_blocking is False

    def test_evidence_has_zero_trigger_count(self) -> None:
        result = _engine().compute(_normal_input())
        assert result.evidence["active_trigger_count"] == 0
        assert result.evidence["level"] == KS_LEVEL_NORMAL

    def test_deterministic_repeated_run_identical(self) -> None:
        inp = _normal_input()
        e = _engine()
        r1 = e.compute(inp)
        r2 = e.compute(inp)
        assert r1.level == r2.level
        assert r1.active_triggers == r2.active_triggers
        assert r1.winning_trigger == r2.winning_trigger


# ---------------------------------------------------------------------------
# Individual trigger rules
# ---------------------------------------------------------------------------


class TestCriticalException:
    def test_critical_exception_returns_halt(self) -> None:
        result = _engine().compute(_normal_input(critical_exception=True))
        assert result.level == KS_LEVEL_HALT
        assert TRIGGER_CRITICAL_EXCEPTION in result.active_triggers
        assert result.winning_trigger == TRIGGER_CRITICAL_EXCEPTION


class TestManualOverride:
    def test_manual_override_returns_halt(self) -> None:
        result = _engine().compute(_normal_input(manual_override=True))
        assert result.level == KS_LEVEL_HALT
        assert TRIGGER_MANUAL_OVERRIDE in result.active_triggers
        assert result.winning_trigger == TRIGGER_MANUAL_OVERRIDE


class TestSystemState:
    def test_halt_state_returns_ks_halt(self) -> None:
        result = _engine().compute(_normal_input(system_state=SystemState.HALT))
        assert result.level == KS_LEVEL_HALT
        assert TRIGGER_SYSTEM_HALT in result.active_triggers

    def test_crisis_state_returns_ks_force_exit(self) -> None:
        result = _engine().compute(_normal_input(system_state=SystemState.CRISIS))
        assert result.level == KS_LEVEL_FLATTEN
        assert TRIGGER_SYSTEM_CRISIS in result.active_triggers
        assert result.winning_trigger == TRIGGER_SYSTEM_CRISIS

    def test_defensive_state_returns_ks_normal(self) -> None:
        # DEFENSIVE is not CRISIS or HALT — no KS trigger for it at this level
        result = _engine().compute(_normal_input(system_state=SystemState.DEFENSIVE))
        assert result.level == KS_LEVEL_NORMAL

    def test_degraded_state_returns_ks_normal(self) -> None:
        result = _engine().compute(_normal_input(system_state=SystemState.DEGRADED))
        assert result.level == KS_LEVEL_NORMAL


class TestDataFailure:
    def test_single_failure_returns_block_new(self) -> None:
        result = _engine().compute(_normal_input(data_failure_count=1))
        assert result.level == KS_LEVEL_BLOCK
        assert TRIGGER_DATA_FAILURE_SINGLE in result.active_triggers

    def test_repeated_failure_returns_force_exit(self) -> None:
        result = _engine().compute(_normal_input(data_failure_count=2))
        assert result.level == KS_LEVEL_FLATTEN
        assert TRIGGER_DATA_FAILURE_REPEATED in result.active_triggers

    def test_repeated_failure_above_threshold(self) -> None:
        result = _engine().compute(_normal_input(data_failure_count=5))
        assert result.level == KS_LEVEL_FLATTEN
        assert TRIGGER_DATA_FAILURE_REPEATED in result.active_triggers
        assert TRIGGER_DATA_FAILURE_SINGLE not in result.active_triggers

    def test_zero_failures_no_trigger(self) -> None:
        result = _engine().compute(_normal_input(data_failure_count=0))
        assert TRIGGER_DATA_FAILURE_SINGLE not in result.active_triggers
        assert TRIGGER_DATA_FAILURE_REPEATED not in result.active_triggers

    def test_custom_repeated_threshold(self) -> None:
        # Threshold=5 — count=3 should be SINGLE only
        result = _engine().compute(_normal_input(data_failure_count=3, data_failure_repeated_threshold=5))
        assert TRIGGER_DATA_FAILURE_SINGLE in result.active_triggers
        assert TRIGGER_DATA_FAILURE_REPEATED not in result.active_triggers


class TestTelemetry:
    def test_telemetry_stale_at_threshold_returns_block(self) -> None:
        threshold = 30_000_000_000  # 30s in ns
        result = _engine().compute(_normal_input(telemetry_stale_ns=threshold))
        assert result.level == KS_LEVEL_BLOCK
        assert TRIGGER_TELEMETRY_ABSENT in result.active_triggers

    def test_telemetry_stale_above_threshold(self) -> None:
        result = _engine().compute(
            _normal_input(telemetry_stale_ns=60_000_000_000, telemetry_stale_threshold_ns=30_000_000_000)
        )
        assert TRIGGER_TELEMETRY_ABSENT in result.active_triggers
        assert result.level == KS_LEVEL_BLOCK

    def test_telemetry_zero_stale_no_trigger(self) -> None:
        # telemetry_stale_ns=0 means freshly emitted or init — no trigger
        result = _engine().compute(_normal_input(telemetry_stale_ns=0))
        assert TRIGGER_TELEMETRY_ABSENT not in result.active_triggers

    def test_telemetry_zero_threshold_disables_check(self) -> None:
        # threshold=0 disables the check entirely
        result = _engine().compute(_normal_input(telemetry_stale_ns=999_999_999_999, telemetry_stale_threshold_ns=0))
        assert TRIGGER_TELEMETRY_ABSENT not in result.active_triggers


class TestRecovery:
    def test_recovery_active_returns_reduce(self) -> None:
        result = _engine().compute(_normal_input(recovery_active=True))
        assert result.level == KS_LEVEL_REDUCE
        assert TRIGGER_RECOVERY_ACTIVE in result.active_triggers
        assert result.winning_trigger == TRIGGER_RECOVERY_ACTIVE

    def test_recovery_repeated_returns_block(self) -> None:
        result = _engine().compute(_normal_input(recovery_active=True, recovery_loop_count=3))
        assert result.level == KS_LEVEL_BLOCK
        assert TRIGGER_RECOVERY_REPEATED in result.active_triggers
        assert TRIGGER_RECOVERY_ACTIVE not in result.active_triggers  # escalated away

    def test_recovery_not_active_no_trigger(self) -> None:
        result = _engine().compute(_normal_input(recovery_active=False, recovery_loop_count=99))
        assert TRIGGER_RECOVERY_ACTIVE not in result.active_triggers
        assert TRIGGER_RECOVERY_REPEATED not in result.active_triggers


class TestLatency:
    def test_severe_latency_returns_block(self) -> None:
        result = _engine().compute(_normal_input(latency_ms=600.0))
        assert result.level == KS_LEVEL_BLOCK
        assert TRIGGER_LATENCY_SEVERE in result.active_triggers

    def test_moderate_latency_returns_reduce(self) -> None:
        result = _engine().compute(_normal_input(latency_ms=250.0))
        assert result.level == KS_LEVEL_REDUCE
        assert TRIGGER_LATENCY_MODERATE in result.active_triggers

    def test_exactly_at_severe_threshold(self) -> None:
        result = _engine().compute(_normal_input(latency_ms=500.0))
        assert TRIGGER_LATENCY_SEVERE in result.active_triggers

    def test_exactly_at_moderate_threshold(self) -> None:
        result = _engine().compute(_normal_input(latency_ms=200.0))
        assert TRIGGER_LATENCY_MODERATE in result.active_triggers

    def test_below_moderate_no_trigger(self) -> None:
        result = _engine().compute(_normal_input(latency_ms=50.0))
        assert TRIGGER_LATENCY_MODERATE not in result.active_triggers
        assert TRIGGER_LATENCY_SEVERE not in result.active_triggers

    def test_zero_latency_no_trigger(self) -> None:
        result = _engine().compute(_normal_input(latency_ms=0.0))
        assert TRIGGER_LATENCY_MODERATE not in result.active_triggers


class TestExecutionQuality:
    def test_degraded_returns_reduce(self) -> None:
        result = _engine().compute(_normal_input(execution_quality=ExecutionQuality.DEGRADED))
        assert result.level == KS_LEVEL_REDUCE
        assert TRIGGER_EXECUTION_DEGRADED in result.active_triggers

    def test_critical_returns_block(self) -> None:
        result = _engine().compute(_normal_input(execution_quality=ExecutionQuality.CRITICAL))
        assert result.level == KS_LEVEL_BLOCK
        assert TRIGGER_EXECUTION_CRITICAL in result.active_triggers

    def test_normal_quality_no_trigger(self) -> None:
        result = _engine().compute(_normal_input(execution_quality=ExecutionQuality.NORMAL))
        assert TRIGGER_EXECUTION_DEGRADED not in result.active_triggers
        assert TRIGGER_EXECUTION_CRITICAL not in result.active_triggers

    def test_empty_quality_no_trigger(self) -> None:
        result = _engine().compute(_normal_input(execution_quality=""))
        assert TRIGGER_EXECUTION_DEGRADED not in result.active_triggers


# ---------------------------------------------------------------------------
# Multi-trigger: highest severity wins
# ---------------------------------------------------------------------------


class TestMultiTrigger:
    def test_recovery_and_latency_moderate_returns_reduce(self) -> None:
        result = _engine().compute(_normal_input(recovery_active=True, latency_ms=250.0))
        assert result.level == KS_LEVEL_REDUCE
        assert len(result.active_triggers) == 2

    def test_crisis_state_and_data_failure_returns_force_exit(self) -> None:
        # Both are FLATTEN (KS3) — still FLATTEN
        result = _engine().compute(_normal_input(system_state=SystemState.CRISIS, data_failure_count=2))
        assert result.level == KS_LEVEL_FLATTEN
        assert TRIGGER_SYSTEM_CRISIS in result.active_triggers
        assert TRIGGER_DATA_FAILURE_REPEATED in result.active_triggers

    def test_manual_override_always_wins(self) -> None:
        # Even with all lower triggers active, manual override escalates to HALT
        result = _engine().compute(
            _normal_input(
                recovery_active=True,
                latency_ms=600.0,
                data_failure_count=2,
                system_state=SystemState.CRISIS,
                manual_override=True,
            )
        )
        assert result.level == KS_LEVEL_HALT
        assert result.winning_trigger == TRIGGER_MANUAL_OVERRIDE

    def test_halt_state_and_all_lower_triggers_returns_halt(self) -> None:
        result = _engine().compute(
            _normal_input(
                system_state=SystemState.HALT,
                recovery_active=True,
                latency_ms=300.0,
            )
        )
        assert result.level == KS_LEVEL_HALT
        assert TRIGGER_SYSTEM_HALT in result.active_triggers

    def test_multiple_triggers_evidence_complete(self) -> None:
        result = _engine().compute(_normal_input(recovery_active=True, data_failure_count=1))
        assert result.evidence["active_trigger_count"] == 2
        assert result.evidence["winning_trigger"] is not None
        assert len(result.active_triggers) == 2

    def test_deterministic_multi_trigger(self) -> None:
        inp = _normal_input(
            system_state=SystemState.CRISIS,
            recovery_active=True,
            latency_ms=300.0,
        )
        e = _engine()
        r1 = e.compute(inp)
        r2 = e.compute(inp)
        assert r1.level == r2.level
        assert r1.winning_trigger == r2.winning_trigger
        assert set(r1.active_triggers) == set(r2.active_triggers)


# ---------------------------------------------------------------------------
# Fail-closed: exception handling
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_exception_during_compute_returns_halt(self) -> None:
        """Passing an invalid system_state triggers the fail-closed path."""

        class _BadInput:
            """Deliberately malformed — accessing .system_state raises."""

            @property
            def system_state(self) -> SystemState:  # type: ignore[return]
                raise RuntimeError("simulated engine failure")

            critical_exception = False
            manual_override = False
            data_failure_count = 0
            data_failure_repeated_threshold = 2
            telemetry_stale_ns = 0
            telemetry_stale_threshold_ns = 30_000_000_000
            recovery_active = False
            recovery_loop_count = 0
            recovery_repeated_threshold = 3
            latency_ms = 0.0
            latency_severe_ms = 500.0
            latency_moderate_ms = 200.0
            execution_quality = ""

        result = _engine().compute(_BadInput())  # type: ignore[arg-type]
        assert result.level == KS_LEVEL_HALT
        assert TRIGGER_CRITICAL_EXCEPTION in result.active_triggers
        assert result.evidence.get("error") == "exception_fail_closed"


# ---------------------------------------------------------------------------
# KillSwitchResult properties
# ---------------------------------------------------------------------------


class TestKillSwitchResult:
    def test_is_blocking_ks2(self) -> None:
        r = KillSwitchResult(
            level=KS_LEVEL_BLOCK,
            active_triggers=(TRIGGER_DATA_FAILURE_SINGLE,),
            winning_trigger=TRIGGER_DATA_FAILURE_SINGLE,
            evidence={},
        )
        assert r.is_blocking is True

    def test_is_not_blocking_ks1(self) -> None:
        r = KillSwitchResult(
            level=KS_LEVEL_REDUCE,
            active_triggers=(TRIGGER_RECOVERY_ACTIVE,),
            winning_trigger=TRIGGER_RECOVERY_ACTIVE,
            evidence={},
        )
        assert r.is_blocking is False

    def test_is_not_blocking_ks0(self) -> None:
        r = KillSwitchResult(
            level=KS_LEVEL_NORMAL,
            active_triggers=(),
            winning_trigger=None,
            evidence={},
        )
        assert r.is_blocking is False
