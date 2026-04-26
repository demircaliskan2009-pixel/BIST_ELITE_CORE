"""Kill-Switch Trigger Engine v1 — deterministic KS level computation.

Computes a kill-switch level (0-4) from runtime health signals.
All logic is deterministic: same inputs → same output.
Fail-closed: any exception during computation → KS_LEVEL_HALT.

PRD reference: §1.19 Kill-Switch System.

v1 trigger subset (9 rules from available signals):
  T01 CRITICAL_EXCEPTION        → KS 4 (HALT)
  T02 SYSTEM_HALT               → KS 4 (HALT)
  T03 SYSTEM_CRISIS             → KS 3 (FORCE_EXIT)
  T04 DATA_FAILURE_REPEATED     → KS 3 (FORCE_EXIT)
  T05 DATA_FAILURE_SINGLE       → KS 2 (BLOCK_NEW)
  T06 TELEMETRY_ABSENT          → KS 2 (BLOCK_NEW)
  T07 RECOVERY_REPEATED         → KS 2 (BLOCK_NEW)
  T08 RECOVERY_ACTIVE           → KS 1 (REDUCE)
  T09 LATENCY_SEVERE            → KS 2 (BLOCK_NEW)
  T10 LATENCY_MODERATE          → KS 1 (REDUCE)
  T11 EXECUTION_CRITICAL        → KS 2 (BLOCK_NEW)
  T12 EXECUTION_DEGRADED        → KS 1 (REDUCE)
  T13 MANUAL_OVERRIDE           → KS 4 (HALT)

Future expansion (not yet computable without position tracker / trade history):
  T_FUTURE_1  daily_pnl_loss_pct > threshold
  T_FUTURE_2  portfolio CVaR exhaustion
  T_FUTURE_3  consecutive losing trades
  T_FUTURE_4  fill rate collapse
  T_FUTURE_5  cross-exchange price divergence
  T_FUTURE_6  funding rate extreme spike
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from crypto_core.risk.contracts import KS_LEVEL_BLOCK, KS_LEVEL_FLATTEN, KS_LEVEL_HALT, KS_LEVEL_NORMAL, KS_LEVEL_REDUCE
from crypto_core.state.models import SystemState, is_at_least

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trigger ID constants (canonical string labels for evidence + future routing)
# ---------------------------------------------------------------------------

TRIGGER_CRITICAL_EXCEPTION: str = "T01_CRITICAL_EXCEPTION"
TRIGGER_SYSTEM_HALT: str = "T02_SYSTEM_HALT"
TRIGGER_SYSTEM_CRISIS: str = "T03_SYSTEM_CRISIS"
TRIGGER_DATA_FAILURE_REPEATED: str = "T04_DATA_FAILURE_REPEATED"
TRIGGER_DATA_FAILURE_SINGLE: str = "T05_DATA_FAILURE_SINGLE"
TRIGGER_TELEMETRY_ABSENT: str = "T06_TELEMETRY_ABSENT"
TRIGGER_RECOVERY_REPEATED: str = "T07_RECOVERY_REPEATED"
TRIGGER_RECOVERY_ACTIVE: str = "T08_RECOVERY_ACTIVE"
TRIGGER_LATENCY_SEVERE: str = "T09_LATENCY_SEVERE"
TRIGGER_LATENCY_MODERATE: str = "T10_LATENCY_MODERATE"
TRIGGER_EXECUTION_CRITICAL: str = "T11_EXECUTION_CRITICAL"
TRIGGER_EXECUTION_DEGRADED: str = "T12_EXECUTION_DEGRADED"
TRIGGER_MANUAL_OVERRIDE: str = "T13_MANUAL_OVERRIDE"

#: Map from trigger ID to the KS level it mandates.
TRIGGER_LEVELS: dict[str, int] = {
    TRIGGER_CRITICAL_EXCEPTION: KS_LEVEL_HALT,
    TRIGGER_SYSTEM_HALT: KS_LEVEL_HALT,
    TRIGGER_MANUAL_OVERRIDE: KS_LEVEL_HALT,
    TRIGGER_SYSTEM_CRISIS: KS_LEVEL_FLATTEN,
    TRIGGER_DATA_FAILURE_REPEATED: KS_LEVEL_FLATTEN,
    TRIGGER_DATA_FAILURE_SINGLE: KS_LEVEL_BLOCK,
    TRIGGER_TELEMETRY_ABSENT: KS_LEVEL_BLOCK,
    TRIGGER_RECOVERY_REPEATED: KS_LEVEL_BLOCK,
    TRIGGER_LATENCY_SEVERE: KS_LEVEL_BLOCK,
    TRIGGER_EXECUTION_CRITICAL: KS_LEVEL_BLOCK,
    TRIGGER_RECOVERY_ACTIVE: KS_LEVEL_REDUCE,
    TRIGGER_LATENCY_MODERATE: KS_LEVEL_REDUCE,
    TRIGGER_EXECUTION_DEGRADED: KS_LEVEL_REDUCE,
}

# ---------------------------------------------------------------------------
# Typed input contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KillSwitchInput:
    """All runtime signals consumed by KillSwitchEngine.compute().

    Design rules:
      - Every field has a safe default (no trigger fires when defaults used).
      - Fields that are not yet computable remain at their safe defaults.
      - No field may be None — callers must supply explicit values.

    PRD §1.19 mapping:
      system_state             → T02, T03
      critical_exception       → T01
      manual_override          → T13
      data_failure_count       → T04 (>=2), T05 (>=1)
      telemetry_stale_ns       → T06
      telemetry_stale_threshold_ns → T06 config
      recovery_active          → T08
      recovery_loop_count      → T07
      latency_ms               → T09, T10
      latency_severe_ms        → T09 config
      latency_moderate_ms      → T10 config
      execution_quality        → T11 (CRITICAL), T12 (DEGRADED)
    """

    system_state: SystemState = SystemState.NORMAL

    # ── T01 / T13 ─────────────────────────────────────────────────────────
    #: True if an unhandled exception occurred in the pipeline this cycle
    critical_exception: bool = False
    #: True if an operator manually requested a halt
    manual_override: bool = False

    # ── T04 / T05 — data health ────────────────────────────────────────────
    #: Number of consecutive data health failures observed this cycle
    data_failure_count: int = 0
    #: >= this value triggers T04 (REPEATED severe failure)
    data_failure_repeated_threshold: int = 2

    # ── T06 — telemetry freshness ──────────────────────────────────────────
    #: Nanoseconds since last successful telemetry emit (0 = unknown/init)
    telemetry_stale_ns: int = 0
    #: Threshold in ns above which telemetry is considered absent (default 30s)
    telemetry_stale_threshold_ns: int = 30_000_000_000  # 30 seconds

    # ── T07 / T08 — recovery ──────────────────────────────────────────────
    #: True if the data feed recovery manager is currently active
    recovery_active: bool = False
    #: Number of recovery loop iterations completed since last clean state
    recovery_loop_count: int = 0
    #: >= this value triggers T07 (REPEATED recovery) on top of T08
    recovery_repeated_threshold: int = 3

    # ── T09 / T10 — latency ───────────────────────────────────────────────
    #: Observed pipeline latency in milliseconds this cycle (0 = not measured)
    latency_ms: float = 0.0
    #: Threshold above which latency is SEVERE → T09
    latency_severe_ms: float = 500.0
    #: Threshold above which latency is MODERATE → T10
    latency_moderate_ms: float = 200.0

    # ── T11 / T12 — execution quality ─────────────────────────────────────
    #: Execution quality descriptor; see ExecutionQuality constants below
    execution_quality: str = ""  # empty string = not measured → no trigger


# ---------------------------------------------------------------------------
# Execution quality level constants
# ---------------------------------------------------------------------------


class ExecutionQuality(str):
    """Discrete execution quality levels reported by the execution layer."""

    pass


ExecutionQuality.NORMAL = ExecutionQuality("normal")
ExecutionQuality.DEGRADED = ExecutionQuality("degraded")  # → T12 (KS 1)
ExecutionQuality.CRITICAL = ExecutionQuality("critical")  # → T11 (KS 2)

# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KillSwitchResult:
    """Immutable output of one KillSwitchEngine evaluation cycle.

    level: computed kill-switch level 0–4.
    active_triggers: all trigger IDs that fired this cycle.
    winning_trigger: the trigger that determined the final level (highest).
    evidence: structured dict for telemetry and audit.
    """

    level: int
    active_triggers: tuple[str, ...]
    winning_trigger: str | None  # None iff no triggers fired (level==0)
    evidence: dict[str, object]

    @property
    def is_blocking(self) -> bool:
        """True if the computed level will block new entries."""
        from crypto_core.risk.contracts import KS_BLOCK_THRESHOLD

        return self.level >= KS_BLOCK_THRESHOLD


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class KillSwitchEngine:
    """Deterministic kill-switch level computation engine.

    Evaluates all v1 trigger rules against a KillSwitchInput snapshot.
    Returns the highest mandated level.  Fail-closed on any exception.

    Usage::

        engine = KillSwitchEngine()
        result = engine.compute(ks_input)
        # pass result.level to PipelineOrchestrator.process(..., kill_switch_level=result.level)
    """

    def compute(self, ks_input: KillSwitchInput) -> KillSwitchResult:
        """Evaluate all trigger rules and return the computed KS result.

        Never raises.  Any exception → KS_LEVEL_HALT (fail-closed).
        """
        try:
            return self._do_compute(ks_input)
        except Exception:
            logger.exception("KillSwitchEngine.compute raised — fail-closed KS_LEVEL_HALT")
            return KillSwitchResult(
                level=KS_LEVEL_HALT,
                active_triggers=(TRIGGER_CRITICAL_EXCEPTION,),
                winning_trigger=TRIGGER_CRITICAL_EXCEPTION,
                evidence={"error": "exception_fail_closed", "level": KS_LEVEL_HALT},
            )

    # -----------------------------------------------------------------------
    # Trigger evaluation
    # -----------------------------------------------------------------------

    def _do_compute(self, inp: KillSwitchInput) -> KillSwitchResult:
        fired: list[str] = []

        # T01: critical exception in pipeline
        if inp.critical_exception:
            fired.append(TRIGGER_CRITICAL_EXCEPTION)

        # T13: manual operator halt
        if inp.manual_override:
            fired.append(TRIGGER_MANUAL_OVERRIDE)

        # T02: system state is HALT
        if inp.system_state == SystemState.HALT:
            fired.append(TRIGGER_SYSTEM_HALT)

        # T03: system state is CRISIS
        elif is_at_least(inp.system_state, SystemState.CRISIS):
            fired.append(TRIGGER_SYSTEM_CRISIS)

        # T04 / T05: data health failures
        if inp.data_failure_count >= inp.data_failure_repeated_threshold:
            fired.append(TRIGGER_DATA_FAILURE_REPEATED)
        elif inp.data_failure_count >= 1:
            fired.append(TRIGGER_DATA_FAILURE_SINGLE)

        # T06: telemetry stale / absent
        # 0 means "never emitted" — treat as absent if threshold > 0
        if inp.telemetry_stale_threshold_ns > 0 and inp.telemetry_stale_ns >= inp.telemetry_stale_threshold_ns:
            fired.append(TRIGGER_TELEMETRY_ABSENT)

        # T07 / T08: recovery
        if inp.recovery_active:
            if inp.recovery_loop_count >= inp.recovery_repeated_threshold:
                fired.append(TRIGGER_RECOVERY_REPEATED)
            else:
                fired.append(TRIGGER_RECOVERY_ACTIVE)

        # T09 / T10: latency (only if measured — latency_ms > 0)
        if inp.latency_ms > 0.0:
            if inp.latency_ms >= inp.latency_severe_ms:
                fired.append(TRIGGER_LATENCY_SEVERE)
            elif inp.latency_ms >= inp.latency_moderate_ms:
                fired.append(TRIGGER_LATENCY_MODERATE)

        # T11 / T12: execution quality (only if set)
        if inp.execution_quality == ExecutionQuality.CRITICAL:
            fired.append(TRIGGER_EXECUTION_CRITICAL)
        elif inp.execution_quality == ExecutionQuality.DEGRADED:
            fired.append(TRIGGER_EXECUTION_DEGRADED)

        # Determine winning level (highest severity wins)
        if not fired:
            return KillSwitchResult(
                level=KS_LEVEL_NORMAL,
                active_triggers=(),
                winning_trigger=None,
                evidence={"level": KS_LEVEL_NORMAL, "active_trigger_count": 0},
            )

        winning = max(fired, key=lambda t: TRIGGER_LEVELS[t])
        level = TRIGGER_LEVELS[winning]

        evidence: dict[str, object] = {
            "level": level,
            "winning_trigger": winning,
            "active_triggers": fired,
            "active_trigger_count": len(fired),
        }

        return KillSwitchResult(
            level=level,
            active_triggers=tuple(fired),
            winning_trigger=winning,
            evidence=evidence,
        )
