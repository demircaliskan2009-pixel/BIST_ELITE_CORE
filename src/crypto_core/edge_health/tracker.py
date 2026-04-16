"""Edge health tracker engine — Phase 5F.

Deterministic, bounded-memory tracker that computes edge health snapshots
from observed edge signal history.

V1 EHS proxy formula:
  ehs_score = mean(confidence) over the last `window_size` signal records.
  confidence = 0.0 for invalid signals (per EdgeSignal contract).
  Therefore:
    - All signals blocked  → ehs ≈ 0.0 → DISABLED
    - All signals valid with high confidence → ehs ≈ 1.0 → ACTIVE
    - Mix → interpolated [0, 1]

  This formula is:
    - Monotone in signal validity (more valid → higher score)
    - Sensitivity-to-confidence (stronger signals → higher score)
    - No fake Sharpe/hit-rate — requires only what the pipeline provides

Upgrade path to full PRD EHS:
  When realized trade outcomes are recorded, replace mean(confidence) with a
  multi-component EHS decomposition (hit-rate × avg_return × stability).

State management:
  Buffer size  : configurable, default _DEFAULT_WINDOW_SIZE = 50
  Min samples  : _MIN_OBSERVATIONS_REQUIRED = 5 before EHS is computed
  DISABLED floor: ehs < _DISABLE_THRESHOLD (0.10) → DISABLED state
  DEGRADED band : _DISABLE_THRESHOLD <= ehs < _DEGRADED_THRESHOLD (0.30)
  ACTIVE floor  : ehs >= _DEGRADED_THRESHOLD

  Explicit disable: operator can disable any family via disable_edge().

Fail-closed:
  Malformed records → raises EdgeSignalRecordError immediately.
  All other exceptions propagate to caller (pipeline should catch).

PRD reference: §1.6 EHS lifecycle, §1.21 NT-E01–NT-E04.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque

from crypto_core.edge_health.models import (
    EdgeFSMState,
    EdgeHealthSnapshot,
    EdgeHealthTrackerSnapshot,
    EdgeSignalRecord,
    UtilizationBand,
)
from crypto_core.guard.models import EdgeHealthInput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Maximum signals retained per (family, symbol, exchange) key.
_DEFAULT_WINDOW_SIZE: int = 50

#: Minimum observations required before EHS is computed (not None).
_MIN_OBSERVATIONS_REQUIRED: int = 5

#: EHS below this → DISABLED state (NT-E02 will fire).
_DISABLE_THRESHOLD: float = 0.10

#: EHS below this → DEGRADED state (between DISABLED and ACTIVE).
_DEGRADED_THRESHOLD: float = 0.30

#: EHS at or above this → edge is counted as "valid" for NT-E04.
_EHS_VALID_THRESHOLD: float = 0.50

#: Utilization at or above this → WARNING band.
_UTIL_WARNING_THRESHOLD: float = 50.0

#: Utilization at or above this → RED band (NT-E03 zone).
_UTIL_RED_THRESHOLD: float = 80.0


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class EdgeSignalRecordError(ValueError):
    """Raised when an EdgeSignalRecord has invalid field values (fail-closed)."""


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class EdgeHealthTracker:
    """Deterministic edge health tracker.

    Maintains per-(family, symbol, exchange) rolling history of signal records.
    Produces EdgeHealthInput for NoTradeGuard and EdgeHealthTrackerSnapshot
    for telemetry.

    Thread safety: NOT thread-safe. Use one instance per pipeline thread.

    Ordering invariant:
      record_signals() must be called AFTER the edge stage, never before.
      to_edge_health_input() must be called BEFORE the guard stage, using
      history from the PREVIOUS cycle. This ensures:
        - Guard uses evidence from past cycles (deterministic)
        - Current cycle's signals are recorded for the next evaluation

    Usage::

        tracker = EdgeHealthTracker()
        # Before guard:
        edge_input = tracker.to_edge_health_input("BTCUSDT", "binance", ts)
        # After edge stage:
        tracker.record_signals(edge_signals)
    """

    def __init__(
        self,
        window_size: int = _DEFAULT_WINDOW_SIZE,
        min_observations: int = _MIN_OBSERVATIONS_REQUIRED,
    ) -> None:
        if window_size < 2:
            raise ValueError(f"window_size must be >= 2, got {window_size}")
        if min_observations < 1:
            raise ValueError(f"min_observations must be >= 1, got {min_observations}")
        if min_observations > window_size:
            raise ValueError(f"min_observations ({min_observations}) must be <= window_size ({window_size})")

        self._window_size = window_size
        self._min_observations = min_observations

        # Per-key rolling history: key = (family, symbol, exchange)
        self._history: dict[tuple[str, str, str], deque[EdgeSignalRecord]] = defaultdict(
            lambda: deque(maxlen=self._window_size)
        )
        # Explicitly disabled keys (operator-level override)
        self._disabled: set[tuple[str, str, str]] = set()

    # -----------------------------------------------------------------------
    # Public: record signals
    # -----------------------------------------------------------------------

    def record_signal(self, record: EdgeSignalRecord) -> None:
        """Record one edge signal observation into rolling history.

        Raises:
            EdgeSignalRecordError: if any field is invalid (fail-closed).
        """
        errors = _validate_record(record)
        if errors:
            raise EdgeSignalRecordError("; ".join(errors))
        key = (record.family, record.symbol, record.exchange)
        self._history[key].append(record)

    def record_signals(self, signals: list) -> None:
        """Record a batch of EdgeSignal objects from the edge engine.

        Converts EdgeSignal objects to EdgeSignalRecord automatically.
        Silently skips signals that lack the expected attributes (defensive).

        Args:
            signals: list of EdgeSignal dataclass instances.
        """
        for sig in signals:
            try:
                rec = EdgeSignalRecord(
                    family=str(sig.family),
                    symbol=sig.symbol,
                    exchange=sig.exchange,
                    is_valid=sig.is_valid,
                    confidence=float(sig.confidence),
                    timestamp_ns=sig.timestamp_ns,
                    # utilization_pct not yet in EdgeSignal — remains None until Phase 5G+
                    utilization_pct=None,
                )
                self.record_signal(rec)
            except EdgeSignalRecordError:
                logger.warning("EdgeHealthTracker: invalid signal record skipped — %s", sig)
            except AttributeError:
                logger.warning("EdgeHealthTracker: signal missing expected attribute — %s", sig)

    # -----------------------------------------------------------------------
    # Public: explicit enable/disable
    # -----------------------------------------------------------------------

    def disable_edge(self, family: str, symbol: str, exchange: str) -> None:
        """Explicitly disable an edge family for a (symbol, exchange).

        Once disabled, edge_fsm_state=DISABLED and is_valid_edge=False
        regardless of EHS score. Use for operator-driven edge shutdowns.
        """
        self._disabled.add((family, symbol, exchange))

    def enable_edge(self, family: str, symbol: str, exchange: str) -> None:
        """Re-enable an explicitly disabled edge.

        Note: EHS score remains from history — the edge may still be in
        DEGRADED or DISABLED state based on its score if EHS < _DISABLE_THRESHOLD.
        """
        self._disabled.discard((family, symbol, exchange))

    # -----------------------------------------------------------------------
    # Public: snapshot queries
    # -----------------------------------------------------------------------

    def snapshot_for_key(
        self,
        family: str,
        symbol: str,
        exchange: str,
        snapshot_ns: int,
    ) -> EdgeHealthSnapshot:
        """Compute an immutable health snapshot for a specific key.

        Returns a snapshot with DISABLED state if explicitly disabled.
        Returns a snapshot with ehs_score=None if insufficient history.
        """
        key = (family, symbol, exchange)
        explicitly_disabled = key in self._disabled
        records = list(self._history.get(key, []))

        if explicitly_disabled:
            ehs = _compute_ehs(records, self._min_observations)
            last_util = records[-1].utilization_pct if records else None
            return EdgeHealthSnapshot(
                family=family,
                symbol=symbol,
                exchange=exchange,
                ehs_score=ehs,
                fsm_state=EdgeFSMState.DISABLED,
                utilization_pct=last_util,
                utilization_band=_classify_utilization(last_util),
                observation_count=len(records),
                is_valid_edge=False,
                snapshot_ns=snapshot_ns,
            )

        ehs = _compute_ehs(records, self._min_observations)
        fsm = _classify_fsm(ehs)
        last_util = records[-1].utilization_pct if records else None
        util_band = _classify_utilization(last_util)
        is_valid = ehs is not None and ehs >= _EHS_VALID_THRESHOLD and fsm != EdgeFSMState.DISABLED

        return EdgeHealthSnapshot(
            family=family,
            symbol=symbol,
            exchange=exchange,
            ehs_score=ehs,
            fsm_state=fsm,
            utilization_pct=last_util,
            utilization_band=util_band,
            observation_count=len(records),
            is_valid_edge=is_valid,
            snapshot_ns=snapshot_ns,
        )

    def to_edge_health_input(
        self,
        symbol: str,
        exchange: str,
        snapshot_ns: int,
    ) -> EdgeHealthInput | None:
        """Produce an EdgeHealthInput for the NoTradeGuard NT-E family.

        Returns:
            None — if no (family, symbol, exchange) key has been tracked yet.
                   Guard receives edge=None → NT-E family disabled.
            EdgeHealthInput — once history exists; fields may be None if
                              individual metrics are unavailable.

        Aggregation strategy (worst-case / most conservative):
          NT-E01 edge_health_score : minimum EHS across families with history.
          NT-E02 edge_fsm_state    : worst FSM state (DISABLED > DEGRADED > ACTIVE).
          NT-E03 edge_utilization_pct: maximum utilization across families.
          NT-E04 valid_edge_count  : count of families with ehs >= threshold;
                                     None if no family has sufficient history.
        """
        # Collect all keys for this (symbol, exchange)
        history_keys = {k for k in self._history if k[1] == symbol and k[2] == exchange}
        disabled_keys = {k for k in self._disabled if k[1] == symbol and k[2] == exchange}
        all_keys = history_keys | disabled_keys

        if not all_keys:
            return None

        snapshots = [self.snapshot_for_key(f, s, e, snapshot_ns) for (f, s, e) in all_keys]

        # NT-E01: minimum EHS (most conservative)
        ehs_values = [s.ehs_score for s in snapshots if s.ehs_score is not None]
        min_ehs: float | None = min(ehs_values) if ehs_values else None

        # NT-E02: worst FSM state
        fsm_states = [s.fsm_state for s in snapshots]
        worst_fsm: EdgeFSMState
        if EdgeFSMState.DISABLED in fsm_states:
            worst_fsm = EdgeFSMState.DISABLED
        elif EdgeFSMState.DEGRADED in fsm_states:
            worst_fsm = EdgeFSMState.DEGRADED
        else:
            worst_fsm = EdgeFSMState.ACTIVE

        # NT-E03: maximum utilization (worst-case capacity)
        util_values = [s.utilization_pct for s in snapshots if s.utilization_pct is not None]
        max_util: float | None = max(util_values) if util_values else None

        # NT-E04: valid edge count (only count families with sufficient history)
        families_with_history = [s for s in snapshots if s.ehs_score is not None]
        valid_count: int | None
        if not families_with_history:
            # No family has reached min_observations yet — unavailable, not "0"
            valid_count = None
        else:
            valid_count = sum(1 for s in families_with_history if s.is_valid_edge)

        return EdgeHealthInput(
            edge_health_score=min_ehs,
            edge_fsm_state=worst_fsm.value,
            edge_utilization_pct=max_util,
            valid_edge_count=valid_count,
        )

    def tracker_snapshot(self, snapshot_ns: int) -> EdgeHealthTrackerSnapshot:
        """Aggregate snapshot across all currently tracked keys.

        Used for orchestrator telemetry. Returns stable summaries even
        with no history (all counts = 0, EHS values = None).
        """
        history_keys = set(self._history.keys())
        all_keys = history_keys | self._disabled

        if not all_keys:
            return EdgeHealthTrackerSnapshot(
                valid_edge_count=None,
                disabled_edge_count=0,
                active_edge_count=0,
                min_ehs=None,
                max_ehs=None,
                capacity_red_count=0,
                snapshot_ns=snapshot_ns,
                family_snapshots=(),
            )

        snapshots = tuple(self.snapshot_for_key(f, s, e, snapshot_ns) for (f, s, e) in all_keys)

        # Aggregate
        ehs_values = [s.ehs_score for s in snapshots if s.ehs_score is not None]
        families_with_history = [s for s in snapshots if s.ehs_score is not None]
        valid_count = sum(1 for s in families_with_history if s.is_valid_edge) if families_with_history else None
        disabled_count = sum(1 for s in snapshots if s.fsm_state == EdgeFSMState.DISABLED)
        active_count = sum(1 for s in snapshots if s.fsm_state != EdgeFSMState.DISABLED)
        red_count = sum(1 for s in snapshots if s.utilization_band == UtilizationBand.RED)

        return EdgeHealthTrackerSnapshot(
            valid_edge_count=valid_count,
            disabled_edge_count=disabled_count,
            active_edge_count=active_count,
            min_ehs=min(ehs_values) if ehs_values else None,
            max_ehs=max(ehs_values) if ehs_values else None,
            capacity_red_count=red_count,
            snapshot_ns=snapshot_ns,
            family_snapshots=snapshots,
        )

    def reset(self) -> None:
        """Clear all history and disabled state.

        Use between independent test cases to guarantee isolation.
        """
        self._history.clear()
        self._disabled.clear()

    @property
    def window_size(self) -> int:
        """Configured maximum history window size per key."""
        return self._window_size

    @property
    def min_observations(self) -> int:
        """Minimum observations required before EHS is computed."""
        return self._min_observations

    @property
    def tracked_key_count(self) -> int:
        """Number of distinct (family, symbol, exchange) keys tracked."""
        return len(set(self._history.keys()) | self._disabled)


# ---------------------------------------------------------------------------
# Module-level helpers (stateless, pure functions)
# ---------------------------------------------------------------------------


def _compute_ehs(
    records: list[EdgeSignalRecord],
    min_observations: int,
) -> float | None:
    """Compute V1 EHS proxy score from a list of signal records.

    Formula: mean(confidence) over the window.
    Since confidence=0.0 for invalid signals, this naturally penalises
    blocked signals without requiring separate hit-rate tracking.

    Returns None if len(records) < min_observations.
    """
    if len(records) < min_observations:
        return None
    return sum(r.confidence for r in records) / len(records)


def _classify_fsm(ehs: float | None) -> EdgeFSMState:
    """Map a continuous EHS score to an EdgeFSMState.

    None (insufficient history) → ACTIVE (cannot claim disabled without evidence).
    ehs < _DISABLE_THRESHOLD    → DISABLED
    ehs < _DEGRADED_THRESHOLD   → DEGRADED
    ehs >= _DEGRADED_THRESHOLD  → ACTIVE
    """
    if ehs is None:
        return EdgeFSMState.ACTIVE
    if ehs < _DISABLE_THRESHOLD:
        return EdgeFSMState.DISABLED
    if ehs < _DEGRADED_THRESHOLD:
        return EdgeFSMState.DEGRADED
    return EdgeFSMState.ACTIVE


def _classify_utilization(pct: float | None) -> UtilizationBand | None:
    """Map a utilization percentage to a UtilizationBand.

    Returns None if pct is None (unavailable).
    """
    if pct is None:
        return None
    if pct >= _UTIL_RED_THRESHOLD:
        return UtilizationBand.RED
    if pct >= _UTIL_WARNING_THRESHOLD:
        return UtilizationBand.WARNING
    return UtilizationBand.SAFE


def _validate_record(record: EdgeSignalRecord) -> list[str]:
    """Return a list of validation error messages (empty = valid).

    All errors are collected before returning so the caller sees a full
    picture in one exception.
    """
    errors: list[str] = []
    if not record.family:
        errors.append("family must not be empty")
    if not record.symbol:
        errors.append("symbol must not be empty")
    if not record.exchange:
        errors.append("exchange must not be empty")
    if not (0.0 <= record.confidence <= 1.0):
        errors.append(f"confidence must be in [0.0, 1.0], got {record.confidence}")
    if record.utilization_pct is not None and not (0.0 <= record.utilization_pct <= 100.0):
        errors.append(f"utilization_pct must be in [0, 100], got {record.utilization_pct}")
    return errors
