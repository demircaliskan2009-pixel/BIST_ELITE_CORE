"""Edge health tracker engine — partial PRDV4-aligned EHS for Phase 6C.

The tracker replaces the old mean-confidence-only proxy with a deterministic
partial EHS composed of four PRD-aligned slots:

  - sharpe      → confidence proxy fallback
  - hit-rate    → valid-signal ratio proxy fallback
  - drawdown    → confidence drawdown proxy
  - stability   → rolling score/confidence CV proxy

Realized trade-outcome inputs are still unavailable at this phase, so the
tracker makes the fallback explicit in per-component evidence instead of
fabricating Sharpe, hit rate, or PnL drawdown histories.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field

from crypto_core.edge_health.models import (
    EdgeEHSComponent,
    EdgeFSMState,
    EdgeHealthSnapshot,
    EdgeHealthTrackerSnapshot,
    EdgeSignalRecord,
    UtilizationBand,
)
from crypto_core.guard.models import EdgeHealthInput

logger = logging.getLogger(__name__)

_DEFAULT_WINDOW_SIZE: int = 50
_MIN_OBSERVATIONS_REQUIRED: int = 5

_ACTIVE_THRESHOLD: float = 0.70
_WARNING_THRESHOLD: float = 0.30
_EHS_VALID_THRESHOLD: float = 0.50
_UTIL_WARNING_THRESHOLD: float = 50.0
_UTIL_RED_THRESHOLD: float = 80.0
_INITIALIZING_ALLOCATION_FACTOR: float = 0.25

_QUARANTINE_DISABLED_TRANSITIONS: int = 2
_QUARANTINE_LOOKBACK_NS: int = 30 * 24 * 3600 * 1_000_000_000
_QUARANTINE_DURATION_NS: int = 14 * 24 * 3600 * 1_000_000_000

_COMPONENT_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("sharpe", 0.30),
    ("hitrate", 0.25),
    ("drawdown", 0.25),
    ("stability", 0.20),
)


class EdgeSignalRecordError(ValueError):
    """Raised when an EdgeSignalRecord has invalid field values."""


@dataclass
class _LifecycleState:
    """Mutable lifecycle tracking for one edge key."""

    last_base_state: EdgeFSMState | None = None
    disabled_transition_ns: deque[int] = field(default_factory=deque)
    quarantine_until_ns: int | None = None


class EdgeHealthTracker:
    """Deterministic edge health tracker with explicit EHS component evidence."""

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
        self._history: dict[tuple[str, str, str], deque[EdgeSignalRecord]] = defaultdict(
            lambda: deque(maxlen=self._window_size)
        )
        self._disabled: set[tuple[str, str, str]] = set()
        self._lifecycle: dict[tuple[str, str, str], _LifecycleState] = {}

    def record_signal(self, record: EdgeSignalRecord) -> None:
        errors = _validate_record(record)
        if errors:
            raise EdgeSignalRecordError("; ".join(errors))
        key = (record.family, record.symbol, record.exchange)
        self._history[key].append(record)
        self._refresh_lifecycle_state(key, record.timestamp_ns)

    def record_signals(self, signals: list) -> None:
        for sig in signals:
            try:
                rec = EdgeSignalRecord(
                    family=str(sig.family),
                    symbol=sig.symbol,
                    exchange=sig.exchange,
                    is_valid=sig.is_valid,
                    confidence=float(sig.confidence),
                    timestamp_ns=sig.timestamp_ns,
                    utilization_pct=None,
                    score=float(sig.score),
                )
                self.record_signal(rec)
            except EdgeSignalRecordError:
                logger.warning("EdgeHealthTracker: invalid signal record skipped — %s", sig)
            except AttributeError:
                logger.warning("EdgeHealthTracker: signal missing expected attribute — %s", sig)

    def disable_edge(self, family: str, symbol: str, exchange: str) -> None:
        self._disabled.add((family, symbol, exchange))

    def enable_edge(self, family: str, symbol: str, exchange: str) -> None:
        self._disabled.discard((family, symbol, exchange))

    def snapshot_for_key(
        self,
        family: str,
        symbol: str,
        exchange: str,
        snapshot_ns: int,
    ) -> EdgeHealthSnapshot:
        key = (family, symbol, exchange)
        records = list(self._history.get(key, []))
        components = _compute_ehs_components(records, self._min_observations)
        ehs = _compute_ehs(components)
        base_fsm = _classify_fsm(ehs)

        lifecycle = self._lifecycle.get(key)
        quarantine_until_ns = lifecycle.quarantine_until_ns if lifecycle is not None else None
        explicitly_disabled = key in self._disabled
        if explicitly_disabled:
            fsm = EdgeFSMState.DISABLED
        elif quarantine_until_ns is not None and snapshot_ns < quarantine_until_ns:
            fsm = EdgeFSMState.QUARANTINE
        else:
            fsm = base_fsm

        last_util = records[-1].utilization_pct if records else None
        util_band = _classify_utilization(last_util)
        allocation_factor = _allocation_factor(ehs, fsm)
        component_availability_ratio = _component_availability_ratio(components)
        is_valid = (
            ehs is not None
            and ehs >= _EHS_VALID_THRESHOLD
            and fsm
            not in (
                EdgeFSMState.DISABLED,
                EdgeFSMState.QUARANTINE,
            )
        )

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
            allocation_factor=allocation_factor,
            component_availability_ratio=component_availability_ratio,
            quarantine_until_ns=quarantine_until_ns,
            ehs_components=components,
        )

    def to_edge_health_input(
        self,
        symbol: str,
        exchange: str,
        snapshot_ns: int,
    ) -> EdgeHealthInput | None:
        history_keys = {k for k in self._history if k[1] == symbol and k[2] == exchange}
        disabled_keys = {k for k in self._disabled if k[1] == symbol and k[2] == exchange}
        all_keys = history_keys | disabled_keys
        if not all_keys:
            return None

        snapshots = [self.snapshot_for_key(f, s, e, snapshot_ns) for (f, s, e) in all_keys]
        ehs_values = [snap.ehs_score for snap in snapshots if snap.ehs_score is not None]
        min_ehs = min(ehs_values) if ehs_values else None

        fsm_priority = {
            EdgeFSMState.QUARANTINE: 4,
            EdgeFSMState.DISABLED: 3,
            EdgeFSMState.WARNING: 2,
            EdgeFSMState.ACTIVE: 1,
        }
        worst_fsm = max(snapshots, key=lambda snap: fsm_priority[snap.fsm_state]).fsm_state

        util_values = [snap.utilization_pct for snap in snapshots if snap.utilization_pct is not None]
        max_util = max(util_values) if util_values else None

        families_with_history = [snap for snap in snapshots if snap.ehs_score is not None]
        if not families_with_history:
            valid_count: int | None = None
        else:
            valid_count = sum(1 for snap in families_with_history if snap.is_valid_edge)

        return EdgeHealthInput(
            edge_health_score=min_ehs,
            edge_fsm_state=worst_fsm.value,
            edge_utilization_pct=max_util,
            valid_edge_count=valid_count,
        )

    def tracker_snapshot(self, snapshot_ns: int) -> EdgeHealthTrackerSnapshot:
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
                warning_edge_count=0,
                quarantine_edge_count=0,
                family_snapshots=(),
            )

        snapshots = tuple(self.snapshot_for_key(f, s, e, snapshot_ns) for (f, s, e) in all_keys)
        ehs_values = [snap.ehs_score for snap in snapshots if snap.ehs_score is not None]
        families_with_history = [snap for snap in snapshots if snap.ehs_score is not None]
        valid_count = sum(1 for snap in families_with_history if snap.is_valid_edge) if families_with_history else None
        disabled_count = sum(1 for snap in snapshots if snap.fsm_state == EdgeFSMState.DISABLED)
        warning_count = sum(1 for snap in snapshots if snap.fsm_state == EdgeFSMState.WARNING)
        quarantine_count = sum(1 for snap in snapshots if snap.fsm_state == EdgeFSMState.QUARANTINE)
        active_count = sum(1 for snap in snapshots if snap.fsm_state in (EdgeFSMState.ACTIVE, EdgeFSMState.WARNING))
        red_count = sum(1 for snap in snapshots if snap.utilization_band == UtilizationBand.RED)

        return EdgeHealthTrackerSnapshot(
            valid_edge_count=valid_count,
            disabled_edge_count=disabled_count,
            active_edge_count=active_count,
            min_ehs=min(ehs_values) if ehs_values else None,
            max_ehs=max(ehs_values) if ehs_values else None,
            capacity_red_count=red_count,
            snapshot_ns=snapshot_ns,
            warning_edge_count=warning_count,
            quarantine_edge_count=quarantine_count,
            family_snapshots=snapshots,
        )

    def reset(self) -> None:
        self._history.clear()
        self._disabled.clear()
        self._lifecycle.clear()

    @property
    def window_size(self) -> int:
        return self._window_size

    @property
    def min_observations(self) -> int:
        return self._min_observations

    @property
    def tracked_key_count(self) -> int:
        return len(set(self._history.keys()) | self._disabled)

    def _refresh_lifecycle_state(self, key: tuple[str, str, str], snapshot_ns: int) -> None:
        records = list(self._history.get(key, []))
        components = _compute_ehs_components(records, self._min_observations)
        ehs = _compute_ehs(components)
        base_state = _classify_fsm(ehs)

        state = self._lifecycle.setdefault(key, _LifecycleState())
        _prune_disabled_transitions(state.disabled_transition_ns, snapshot_ns)
        if state.last_base_state != EdgeFSMState.DISABLED and base_state == EdgeFSMState.DISABLED:
            state.disabled_transition_ns.append(snapshot_ns)
        if len(state.disabled_transition_ns) >= _QUARANTINE_DISABLED_TRANSITIONS:
            current_until = state.quarantine_until_ns or 0
            state.quarantine_until_ns = max(current_until, snapshot_ns + _QUARANTINE_DURATION_NS)
        state.last_base_state = base_state


def _compute_ehs_components(
    records: list[EdgeSignalRecord],
    min_observations: int,
) -> tuple[EdgeEHSComponent, ...]:
    if len(records) < min_observations:
        return tuple(
            EdgeEHSComponent(
                name=name,
                weight=weight,
                score=None,
                available=False,
                source="unavailable",
                evidence={
                    "reason": "insufficient_observations",
                    "observation_count": len(records),
                    "required": min_observations,
                },
            )
            for name, weight in _COMPONENT_WEIGHTS
        )

    observation_count = len(records)
    confidences = [record.confidence for record in records]
    valid_count = sum(1 for record in records if record.is_valid)
    mean_confidence = sum(confidences) / observation_count
    valid_ratio = valid_count / observation_count

    prefix_means: list[float] = []
    running_total = 0.0
    for idx, confidence in enumerate(confidences, start=1):
        running_total += confidence
        if idx >= min_observations:
            prefix_means.append(running_total / idx)
    peak_mean_confidence = max(prefix_means) if prefix_means else mean_confidence
    drawdown_score = 0.0 if peak_mean_confidence <= 0.0 else min(1.0, mean_confidence / peak_mean_confidence)

    stability_values = [abs(record.score) for record in records if abs(record.score) > 1e-12]
    stability_source = "abs_signal_score_cv_proxy"
    if len(stability_values) < 3:
        stability_values = [confidence for confidence in confidences if confidence > 1e-12]
        stability_source = "confidence_cv_proxy"

    if len(stability_values) >= 3:
        stability_mean = sum(stability_values) / len(stability_values)
        if stability_mean > 1e-12:
            stability_cv = _stddev(stability_values) / stability_mean
            stability_score = max(0.0, min(1.0, 1.0 - stability_cv / 2.0))
            stability_available = True
        else:
            stability_cv = None
            stability_score = None
            stability_available = False
    else:
        stability_cv = None
        stability_score = None
        stability_available = False

    return (
        EdgeEHSComponent(
            name="sharpe",
            weight=0.30,
            score=max(0.0, min(1.0, mean_confidence)),
            available=True,
            source="confidence_proxy",
            evidence={
                "realized_available": False,
                "fallback_used": True,
                "mean_confidence": mean_confidence,
                "observation_count": observation_count,
            },
        ),
        EdgeEHSComponent(
            name="hitrate",
            weight=0.25,
            score=max(0.0, min(1.0, valid_ratio)),
            available=True,
            source="valid_signal_ratio_proxy",
            evidence={
                "realized_available": False,
                "fallback_used": True,
                "valid_count": valid_count,
                "observation_count": observation_count,
            },
        ),
        EdgeEHSComponent(
            name="drawdown",
            weight=0.25,
            score=max(0.0, min(1.0, drawdown_score)),
            available=True,
            source="confidence_drawdown_proxy",
            evidence={
                "realized_available": False,
                "fallback_used": True,
                "current_mean_confidence": mean_confidence,
                "peak_mean_confidence": peak_mean_confidence,
            },
        ),
        EdgeEHSComponent(
            name="stability",
            weight=0.20,
            score=stability_score,
            available=stability_available,
            source=stability_source,
            evidence={
                "realized_available": False,
                "fallback_used": True,
                "cv": stability_cv,
                "sample_count": len(stability_values),
            },
        ),
    )


def _compute_ehs(
    records_or_components: list[EdgeSignalRecord] | tuple[EdgeEHSComponent, ...],
    min_observations: int | None = None,
) -> float | None:
    if records_or_components and isinstance(records_or_components[0], EdgeSignalRecord):  # type: ignore[index]
        min_obs = _MIN_OBSERVATIONS_REQUIRED if min_observations is None else min_observations
        components = _compute_ehs_components(records_or_components, min_obs)  # type: ignore[arg-type]
    else:
        components = records_or_components  # type: ignore[assignment]
    available = [component for component in components if component.available and component.score is not None]
    if not available:
        return None
    weight_total = sum(component.weight for component in available)
    if weight_total <= 0.0:
        return None
    weighted_score = sum(component.weight * float(component.score) for component in available) / weight_total
    return max(0.0, min(1.0, weighted_score))


def _classify_fsm(ehs: float | None) -> EdgeFSMState:
    if ehs is None:
        return EdgeFSMState.WARNING
    if ehs < _WARNING_THRESHOLD:
        return EdgeFSMState.DISABLED
    if ehs < _ACTIVE_THRESHOLD:
        return EdgeFSMState.WARNING
    return EdgeFSMState.ACTIVE


def _allocation_factor(ehs: float | None, fsm: EdgeFSMState) -> float:
    if fsm in (EdgeFSMState.DISABLED, EdgeFSMState.QUARANTINE):
        return 0.0
    if ehs is None:
        return _INITIALIZING_ALLOCATION_FACTOR
    if ehs >= _ACTIVE_THRESHOLD:
        return 1.0
    if ehs < _WARNING_THRESHOLD:
        return 0.0
    return 0.5 + 0.5 * ((ehs - _WARNING_THRESHOLD) / (_ACTIVE_THRESHOLD - _WARNING_THRESHOLD))


def _component_availability_ratio(components: tuple[EdgeEHSComponent, ...]) -> float:
    total_weight = sum(component.weight for component in components)
    if total_weight <= 0.0:
        return 0.0
    available_weight = sum(component.weight for component in components if component.available)
    return available_weight / total_weight


def _classify_utilization(pct: float | None) -> UtilizationBand | None:
    if pct is None:
        return None
    if pct >= _UTIL_RED_THRESHOLD:
        return UtilizationBand.RED
    if pct >= _UTIL_WARNING_THRESHOLD:
        return UtilizationBand.WARNING
    return UtilizationBand.SAFE


def _validate_record(record: EdgeSignalRecord) -> list[str]:
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
    if not math.isfinite(record.score):
        errors.append(f"score must be finite, got {record.score}")
    return errors


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _prune_disabled_transitions(transitions: deque[int], snapshot_ns: int) -> None:
    cutoff = snapshot_ns - _QUARANTINE_LOOKBACK_NS
    while transitions and transitions[0] < cutoff:
        transitions.popleft()
