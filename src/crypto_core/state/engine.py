"""System State Engine — deterministic SHS evaluation and state transitions (§1.29).

Single source of truth for system operational state.
All callers receive the current state from this engine — never compute state elsewhere.

PRD reference: §1.29 — Global System State Engine.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from crypto_core.state.models import (
    DEESC_EXIT_SHS,
    DEESC_MIN_IN_STATE_S,
    DEESC_SUSTAINED_S,
    SHS_WEIGHTS,
    SIGNAL_NAMES,
    SignalInputs,
    StateSnapshot,
    SystemState,
    TransitionRecord,
    state_severity,
)

logger = logging.getLogger(__name__)

WallClockNs = Callable[[], int]


# ---------------------------------------------------------------------------
# Pure functions (testable without engine state)
# ---------------------------------------------------------------------------


def compute_shs(signals: SignalInputs) -> float:
    """Compute the Composite System Health Score.

    SHS = 1 - sum(w_i * s_i),  clamped to [0.0, 1.0].

    Deterministic: same inputs → same output.  No side effects.
    """
    raw = sum(w * s for w, s in zip(SHS_WEIGHTS, signals.as_tuple()))
    return max(0.0, min(1.0, 1.0 - raw))


def _clamp_signals(signals: SignalInputs) -> SignalInputs:
    """Return new SignalInputs with all values clamped to [0.0, 1.0]."""
    t = signals.as_tuple()
    clamped = tuple(max(0.0, min(1.0, v)) for v in t)
    return SignalInputs(*clamped)


def _target_state_from_shs(shs: float) -> SystemState:
    """Map SHS to target state using PRD §1.29 thresholds (ignores hysteresis)."""
    if shs > 0.80:
        return SystemState.NORMAL
    if shs > 0.60:
        return SystemState.DEGRADED
    if shs > 0.35:
        return SystemState.DEFENSIVE
    if shs > 0.15:
        return SystemState.CRISIS
    return SystemState.HALT


def _apply_overrides(
    signals: SignalInputs, shs_target: SystemState
) -> tuple[SystemState, str]:
    """Apply critical override rules per §1.29.

    Returns (final_state, override_reason).

    Override priority (highest first):
      1. S1 = 1.0  → KS-4 level → immediate HALT
      2. Any si = 1.0 → immediate CRISIS (unless already HALT from rule 1)
      3. S4 = 1.0  → floor is DEFENSIVE (enforced in de-escalation, not here)
    """
    s = signals.as_tuple()

    # Rule 1: KS-4 (s1 = 1.0) → HALT
    if s[0] >= 1.0:
        return SystemState.HALT, "override_KS4_halt"

    # Rule 2: any single signal maxed → minimum CRISIS
    for name, val in zip(SIGNAL_NAMES, s):
        if val >= 1.0:
            if state_severity(shs_target) < state_severity(SystemState.CRISIS):
                return SystemState.CRISIS, f"override_signal_maxed:{name}"
            # shs_target is already CRISIS or HALT — keep it
            return shs_target, f"override_already_severe:{name}"

    return shs_target, "no_override"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SystemStateEngine:
    """Evaluates and maintains system operational state (§1.29).

    Responsibilities:
      1. Accept SignalInputs on every evaluation cycle (~10 s).
      2. Compute SHS.
      3. Apply critical override rules.
      4. Apply hysteresis for de-escalation.
      5. Record all transitions in an audit log.
      6. Expose current_state as the single source of truth.

    Fail-closed: any exception during evaluation returns HALT snapshot.

    Thread-safety: NOT thread-safe.  Caller must serialize.

    Usage::

        engine = SystemStateEngine()
        snap = engine.evaluate(signals, timestamp_ns=time.time_ns())
        if is_at_least(snap.state, SystemState.DEFENSIVE):
            # block trading
    """

    _MAX_HISTORY = 1_000

    def __init__(
        self,
        wall_clock: WallClockNs | None = None,
        initial_state: SystemState = SystemState.NORMAL,
    ) -> None:
        self._wall_clock: WallClockNs = wall_clock or time.time_ns
        self._current_state: SystemState = initial_state
        self._state_entered_ns: int = self._wall_clock()

        # Hysteresis tracking
        self._deesc_candidate: SystemState | None = None
        self._deesc_candidate_since_ns: int = 0

        # HALT manual-approval flag
        self._halt_manual_approved: bool = False

        # Audit log (capped)
        self._transitions: list[TransitionRecord] = []

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def evaluate(self, signals: SignalInputs, timestamp_ns: int | None = None) -> StateSnapshot:
        """Evaluate system health and return an immutable StateSnapshot.

        The engine's internal state is updated as a side-effect.

        On any unhandled exception: returns a HALT snapshot (fail-closed).
        """
        ts = timestamp_ns if timestamp_ns is not None else self._wall_clock()
        try:
            return self._do_evaluate(signals, ts)
        except Exception:
            logger.exception("SystemStateEngine.evaluate raised — fail-closed HALT")
            self._force_halt(ts, "exception_fail_closed", signals)
            return StateSnapshot(ts, SystemState.HALT, 0.0, signals, "exception_fail_closed")

    def approve_halt_release(self) -> None:
        """Grant manual approval to allow HALT → lower state de-escalation.

        Per PRD §1.29: HALT requires manual approval AND SHS > 0.60.
        """
        self._halt_manual_approved = True
        logger.warning("HALT manual release approved — awaiting SHS > 0.60")

    def revoke_halt_approval(self) -> None:
        """Revoke any pending manual HALT-release approval."""
        self._halt_manual_approved = False

    @property
    def current_state(self) -> SystemState:
        """Current operational state — single source of truth."""
        return self._current_state

    @property
    def transitions(self) -> list[TransitionRecord]:
        """Read-only copy of transition audit log (last 1000 records)."""
        return list(self._transitions)

    # -----------------------------------------------------------------------
    # Internal evaluation
    # -----------------------------------------------------------------------

    def _do_evaluate(self, raw_signals: SignalInputs, ts: int) -> StateSnapshot:
        signals = _clamp_signals(raw_signals)
        shs = compute_shs(signals)

        # Step 1: target state from SHS bands
        shs_target = _target_state_from_shs(shs)

        # Step 2: critical overrides
        target, override_reason = _apply_overrides(signals, shs_target)

        # Step 3: escalation is immediate (no hysteresis)
        if state_severity(target) > state_severity(self._current_state):
            reason = f"escalation:{target}:{override_reason}:shs={shs:.4f}"
            self._do_transition(ts, target, reason, signals, shs)
            return StateSnapshot(ts, self._current_state, shs, signals, reason)

        # Step 4: de-escalation requires hysteresis
        if state_severity(target) < state_severity(self._current_state):
            new_state = self._try_deescalate(ts, target, shs, signals)
            reason = f"deescalation_eval:{new_state}:shs={shs:.4f}"
            return StateSnapshot(ts, new_state, shs, signals, reason)

        # No change — reset de-escalation candidate if SHS no longer supports it
        exit_shs = DEESC_EXIT_SHS.get(str(self._current_state), 2.0)
        if shs <= exit_shs:
            self._deesc_candidate = None
            self._deesc_candidate_since_ns = 0

        reason = f"stable:{self._current_state}:shs={shs:.4f}"
        return StateSnapshot(ts, self._current_state, shs, signals, reason)

    def _try_deescalate(
        self,
        ts: int,
        candidate: SystemState,
        shs: float,
        signals: SignalInputs,
    ) -> SystemState:
        """Evaluate hysteresis conditions for de-escalation.

        Returns the state after applying all hysteresis rules.
        """
        current = self._current_state

        # HALT requires manual approval — bypass all hysteresis timers
        if current == SystemState.HALT:
            if not self._halt_manual_approved:
                return current
            if shs <= 0.60:
                return current
            # SHS > 0.60 AND manual approved → immediate de-escalation to CRISIS
            reason = f"deescalation:HALT→CRISIS:manual_approved:shs={shs:.4f}"
            self._do_transition(ts, SystemState.CRISIS, reason, signals, shs)
            return SystemState.CRISIS

        # Data feed complete loss: cannot de-escalate below DEFENSIVE
        if signals.s4_data_feed >= 1.0:
            min_floor = SystemState.DEFENSIVE
            if state_severity(candidate) < state_severity(min_floor):
                return current  # floor is DEFENSIVE

        # Check SHS exit threshold
        exit_shs = DEESC_EXIT_SHS.get(str(current), 2.0)
        if shs <= exit_shs:
            # Not above exit threshold — reset candidate
            self._deesc_candidate = None
            self._deesc_candidate_since_ns = 0
            return current

        # Track when exit threshold was first met
        if self._deesc_candidate != candidate:
            self._deesc_candidate = candidate
            self._deesc_candidate_since_ns = ts
            return current  # start timer, no transition yet

        # Check minimum time already spent in current state
        time_in_state_s = (ts - self._state_entered_ns) / 1e9
        min_in_state_s = DEESC_MIN_IN_STATE_S.get(str(current), 0.0)
        if time_in_state_s < min_in_state_s:
            return current

        # Check sustained exit-threshold duration
        sustained_s = (ts - self._deesc_candidate_since_ns) / 1e9
        required_s = DEESC_SUSTAINED_S.get(str(current), float("inf"))
        if sustained_s < required_s:
            return current

        # All conditions met — de-escalate
        reason = (
            f"deescalation:{current}→{candidate}:shs={shs:.4f}"
            f":sustained={sustained_s:.0f}s:in_state={time_in_state_s:.0f}s"
        )
        self._do_transition(ts, candidate, reason, signals, shs)
        return candidate

    def _do_transition(
        self,
        ts: int,
        new_state: SystemState,
        reason: str,
        signals: SignalInputs,
        shs: float,
    ) -> None:
        """Record a state transition and update internal state."""
        old = self._current_state
        self._current_state = new_state
        self._state_entered_ns = ts
        self._deesc_candidate = None
        self._deesc_candidate_since_ns = 0
        if new_state != SystemState.HALT:
            self._halt_manual_approved = False

        record = TransitionRecord(
            timestamp_ns=ts,
            old_state=old,
            new_state=new_state,
            shs=shs,
            signals=signals,
            trigger_reason=reason,
        )
        self._transitions.append(record)
        if len(self._transitions) > self._MAX_HISTORY:
            self._transitions = self._transitions[-self._MAX_HISTORY :]

        logger.warning(
            "SystemState %s → %s (SHS=%.4f) %s", old, new_state, shs, reason
        )

    def _force_halt(
        self, ts: int, reason: str, signals: SignalInputs
    ) -> None:
        """Force-transition to HALT without any checks."""
        if self._current_state != SystemState.HALT:
            self._do_transition(ts, SystemState.HALT, reason, signals, 0.0)
