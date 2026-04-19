"""External regime data plane — Phase 11A.

Deterministic management of options, event, and on-chain regime state
with explicit freshness tracking, staleness detection, and fail-closed
unavailable handling.

Composes the raw regime contracts from execution.regime_contracts (Phase 9B)
into an operationalized data plane with:
  - Per-dimension freshness assessment
  - Staleness threshold enforcement
  - Aggregate risk / availability / sufficiency assessment
  - Deterministic snapshot production
  - Serialization for persistence and reporting

Design rules:
  - Missing data remains UNAVAILABLE — never silently becomes normal.
  - Stale data remains STALE — never silently appears fresh.
  - No fake provider data fabricated.
  - All state is explicit and auditable.
  - Frozen snapshots for thread-safe read access.

PRD reference: §1.4 Edge Family D, §1.29 System State, §4 Data Pipeline.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum

from crypto_core.execution.regime_contracts import (
    CompositeRegimeState,
    DataFreshness,
    EventRegimeLevel,
    EventRegimeState,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
)
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreCorruptError, WriteResult

logger = logging.getLogger(__name__)

_NS_PER_S: int = 1_000_000_000
_EXTERNAL_REGIME_SNAPSHOT_NAME = "external_regime_state"


# ---------------------------------------------------------------------------
# Freshness model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionFreshness:
    """Freshness assessment for a single external regime dimension.

    freshness:        categorical freshness state.
    last_update_ns:   timestamp of last update, None if never received.
    staleness_seconds: seconds since last update, None if never received.
    source:           data source identifier, None if never received.
    """

    freshness: DataFreshness
    last_update_ns: int | None
    staleness_seconds: float | None
    source: str | None


# ---------------------------------------------------------------------------
# External regime snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalRegimeSnapshot:
    """Point-in-time external regime assessment with freshness tracking.

    Combines regime contract states with operational freshness metadata
    for truthful operator surfacing.  Frozen, deterministic.
    """

    snapshot_ns: int

    # Component states (from regime_contracts, may be None)
    options: OptionsRegimeState | None
    event: EventRegimeState | None
    on_chain: OnChainRegimeState | None

    # Freshness per dimension
    options_freshness: DimensionFreshness
    event_freshness: DimensionFreshness
    on_chain_freshness: DimensionFreshness

    # Aggregate assessments
    any_extreme: bool
    any_unavailable_critical: bool
    high_risk_regime_present: bool
    evidence_sufficient: bool

    # Dimension summaries
    available_dimensions: tuple[str, ...]
    unavailable_dimensions: tuple[str, ...]
    stale_dimensions: tuple[str, ...]

    regime_summary: str


class ExternalRegimeUpdateStatus(str, Enum):
    """Outcome classification for a regime update attempt."""

    ACCEPTED = "accepted"
    REJECTED_INVALID = "rejected_invalid"
    REJECTED_STALE = "rejected_stale"
    RESET = "reset"


@dataclass(frozen=True)
class ExternalRegimeUpdateRecord:
    """Deterministic record of one external regime update attempt."""

    dimension: str
    status: ExternalRegimeUpdateStatus
    accepted: bool
    received_at_ns: int
    state_snapshot_ns: int | None
    source_label: str | None
    level: str | None
    freshness: DataFreshness
    replaced_existing: bool
    reason: str


@dataclass(frozen=True)
class ExternalRegimePersistenceState:
    """Persistence / restore status for the managed external regime state."""

    evidence_store_configured: bool
    snapshot_name: str
    snapshot_present: bool
    restored_from_snapshot: bool
    history_limit: int


class ExternalRegimeStateCorruptError(RuntimeError):
    """Raised when persisted external regime state is malformed."""


# ---------------------------------------------------------------------------
# Data plane class
# ---------------------------------------------------------------------------


class ExternalRegimeDataPlane:
    """Manages external regime state with freshness tracking.

    Accepts updates from external providers and produces deterministic
    snapshots with freshness assessment.  Does NOT fabricate data — only
    tracks what was explicitly provided.

    Thread safety: NOT thread-safe — use from one thread.

    Usage::

        plane = ExternalRegimeDataPlane(staleness_threshold_s=3600)
        plane.update_options(options_state)
        plane.update_event(event_state)
        snap = plane.snapshot(now_ns)
    """

    def __init__(self, *, staleness_threshold_s: float = 3600.0) -> None:
        if staleness_threshold_s <= 0:
            raise ValueError(f"staleness_threshold_s must be > 0, got {staleness_threshold_s}")
        self._staleness_threshold_s = staleness_threshold_s

        self._options: OptionsRegimeState | None = None
        self._options_update_ns: int | None = None

        self._event: EventRegimeState | None = None
        self._event_update_ns: int | None = None

        self._on_chain: OnChainRegimeState | None = None
        self._on_chain_update_ns: int | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def staleness_threshold_s(self) -> float:
        """Configured staleness threshold in seconds."""
        return self._staleness_threshold_s

    @property
    def options_state(self) -> OptionsRegimeState | None:
        """Last received options regime state."""
        return self._options

    @property
    def event_state(self) -> EventRegimeState | None:
        """Last received event regime state."""
        return self._event

    @property
    def on_chain_state(self) -> OnChainRegimeState | None:
        """Last received on-chain regime state."""
        return self._on_chain

    # ------------------------------------------------------------------
    # Update methods (called by providers)
    # ------------------------------------------------------------------

    def update_options(self, state: OptionsRegimeState) -> None:
        """Update options regime state from provider."""
        self._options = state
        self._options_update_ns = state.snapshot_ns
        logger.debug("Options regime updated: level=%s", state.level.value)

    def update_event(self, state: EventRegimeState) -> None:
        """Update event regime state from provider."""
        self._event = state
        self._event_update_ns = state.snapshot_ns
        logger.debug("Event regime updated: level=%s", state.level.value)

    def update_on_chain(self, state: OnChainRegimeState) -> None:
        """Update on-chain regime state from provider."""
        self._on_chain = state
        self._on_chain_update_ns = state.snapshot_ns
        logger.debug("On-chain regime updated: level=%s", state.level.value)

    # ------------------------------------------------------------------
    # Snapshot production
    # ------------------------------------------------------------------

    def snapshot(self, now_ns: int) -> ExternalRegimeSnapshot:
        """Produce a deterministic external regime snapshot.

        Assesses freshness, staleness, availability, and aggregate
        risk for all dimensions at the given timestamp.

        Args:
            now_ns: current wall-clock timestamp in nanoseconds.

        Returns:
            Frozen ExternalRegimeSnapshot.
        """
        opt_fresh = self._build_dimension_freshness(self._options, self._options_update_ns, now_ns)
        evt_fresh = self._build_dimension_freshness(self._event, self._event_update_ns, now_ns)
        oc_fresh = self._build_dimension_freshness(self._on_chain, self._on_chain_update_ns, now_ns)

        # Classify dimensions
        available: list[str] = []
        unavailable: list[str] = []
        stale: list[str] = []

        for name, freshness in [
            ("options", opt_fresh),
            ("event", evt_fresh),
            ("on_chain", oc_fresh),
        ]:
            if freshness.freshness == DataFreshness.UNAVAILABLE:
                unavailable.append(name)
            elif freshness.freshness == DataFreshness.STALE:
                stale.append(name)
                available.append(name)  # available but stale
            elif freshness.freshness in (DataFreshness.FRESH, DataFreshness.DEGRADED):
                available.append(name)

        # Aggregate assessments
        any_extreme = self._check_any_extreme()
        any_unavailable_critical = len(unavailable) > 0
        high_risk = any_extreme or self._check_elevated_risk()

        # Evidence sufficiency: at least 2 of 3 dimensions fresh or degraded
        fresh_or_degraded_count = sum(
            1 for f in (opt_fresh, evt_fresh, oc_fresh) if f.freshness in (DataFreshness.FRESH, DataFreshness.DEGRADED)
        )
        evidence_sufficient = fresh_or_degraded_count >= 2

        summary = _build_summary(available, unavailable, stale, any_extreme, high_risk)

        return ExternalRegimeSnapshot(
            snapshot_ns=now_ns,
            options=self._options,
            event=self._event,
            on_chain=self._on_chain,
            options_freshness=opt_fresh,
            event_freshness=evt_fresh,
            on_chain_freshness=oc_fresh,
            any_extreme=any_extreme,
            any_unavailable_critical=any_unavailable_critical,
            high_risk_regime_present=high_risk,
            evidence_sufficient=evidence_sufficient,
            available_dimensions=tuple(available),
            unavailable_dimensions=tuple(unavailable),
            stale_dimensions=tuple(stale),
            regime_summary=summary,
        )

    def composite_regime(self, now_ns: int) -> CompositeRegimeState:
        """Produce a CompositeRegimeState for backward compatibility.

        Args:
            now_ns: current wall-clock timestamp.

        Returns:
            CompositeRegimeState from the existing regime_contracts module.
        """
        return CompositeRegimeState(
            snapshot_ns=now_ns,
            options=self._options,
            event=self._event,
            on_chain=self._on_chain,
        )

    def reset(self) -> None:
        """Clear all state.  Use between test cases for isolation."""
        self._options = None
        self._options_update_ns = None
        self._event = None
        self._event_update_ns = None
        self._on_chain = None
        self._on_chain_update_ns = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_dimension_freshness(
        self,
        state: OptionsRegimeState | EventRegimeState | OnChainRegimeState | None,
        update_ns: int | None,
        now_ns: int,
    ) -> DimensionFreshness:
        """Assess freshness for a single regime dimension."""
        # Never received
        if state is None or update_ns is None:
            return DimensionFreshness(
                freshness=DataFreshness.UNAVAILABLE,
                last_update_ns=None,
                staleness_seconds=None,
                source=None,
            )

        # Source reports unavailable
        if not state.is_available:
            return DimensionFreshness(
                freshness=DataFreshness.UNAVAILABLE,
                last_update_ns=update_ns,
                staleness_seconds=None,
                source=state.source,
            )

        # Compute staleness
        staleness_s = max(0.0, (now_ns - update_ns) / _NS_PER_S)

        # Stale check
        if staleness_s > self._staleness_threshold_s:
            return DimensionFreshness(
                freshness=DataFreshness.STALE,
                last_update_ns=update_ns,
                staleness_seconds=staleness_s,
                source=state.source,
            )

        # Degradation check: available but material evidence gaps
        if _has_evidence_gaps(state):
            return DimensionFreshness(
                freshness=DataFreshness.DEGRADED,
                last_update_ns=update_ns,
                staleness_seconds=staleness_s,
                source=state.source,
            )

        # Fresh
        return DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=update_ns,
            staleness_seconds=staleness_s,
            source=state.source,
        )

    def _check_any_extreme(self) -> bool:
        """True if any dimension indicates extreme / stress / active event."""
        if self._options is not None and self._options.is_extreme:
            return True
        if self._event is not None and self._event.is_active_or_pending:
            return True
        if self._on_chain is not None and self._on_chain.is_stress:
            return True
        return False

    def _check_elevated_risk(self) -> bool:
        """True if any dimension has elevated (non-extreme) risk conditions."""
        if self._options is not None and self._options.level in (
            OptionsRegimeLevel.ELEVATED,
            OptionsRegimeLevel.EXTREME,
        ):
            return True
        if self._event is not None and self._event.level == EventRegimeLevel.ACTIVE:
            return True
        if self._on_chain is not None and self._on_chain.level in (
            OnChainRegimeLevel.STRESS,
            OnChainRegimeLevel.WHALE_ACTIVE,
        ):
            return True
        return False


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _has_evidence_gaps(
    state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
) -> bool:
    """Check if available state has material evidence gaps (DEGRADED)."""
    if isinstance(state, OptionsRegimeState):
        return state.implied_vol_30d is None and state.implied_vol_7d is None
    if isinstance(state, OnChainRegimeState):
        return state.exchange_net_flow_24h_usd is None and state.whale_transfer_count_24h is None
    # EventRegimeState: no degradation concept for events
    return False


def _build_summary(
    available: list[str],
    unavailable: list[str],
    stale: list[str],
    any_extreme: bool,
    high_risk: bool,
) -> str:
    """Build a human-readable regime summary string."""
    parts: list[str] = []

    if not available and not stale:
        parts.append("No external regime data available.")
    else:
        if available:
            parts.append(f"Available: {', '.join(available)}.")
        if stale:
            parts.append(f"Stale: {', '.join(stale)}.")
        if unavailable:
            parts.append(f"Unavailable: {', '.join(unavailable)}.")

    if any_extreme:
        parts.append("EXTREME external regime conditions detected.")
    elif high_risk:
        parts.append("Elevated external risk conditions present.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def dimension_freshness_to_dict(f: DimensionFreshness) -> dict:
    """Serialize DimensionFreshness to a plain dict."""
    return {
        "freshness": f.freshness.value,
        "last_update_ns": f.last_update_ns,
        "staleness_seconds": f.staleness_seconds,
        "source": f.source,
    }


def dimension_freshness_from_dict(d: dict) -> DimensionFreshness:
    """Deserialize DimensionFreshness from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        return DimensionFreshness(
            freshness=DataFreshness(d["freshness"]),
            last_update_ns=d.get("last_update_ns"),
            staleness_seconds=d.get("staleness_seconds"),
            source=d.get("source"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed DimensionFreshness: {exc}") from exc


def external_regime_snapshot_to_dict(snap: ExternalRegimeSnapshot) -> dict:
    """Serialize ExternalRegimeSnapshot to a plain dict."""
    from crypto_core.execution.regime_contracts import (
        _event_to_dict,
        _onchain_to_dict,
        _options_to_dict,
    )

    return {
        "snapshot_ns": snap.snapshot_ns,
        "options": _options_to_dict(snap.options) if snap.options else None,
        "event": _event_to_dict(snap.event) if snap.event else None,
        "on_chain": _onchain_to_dict(snap.on_chain) if snap.on_chain else None,
        "options_freshness": dimension_freshness_to_dict(snap.options_freshness),
        "event_freshness": dimension_freshness_to_dict(snap.event_freshness),
        "on_chain_freshness": dimension_freshness_to_dict(snap.on_chain_freshness),
        "any_extreme": snap.any_extreme,
        "any_unavailable_critical": snap.any_unavailable_critical,
        "high_risk_regime_present": snap.high_risk_regime_present,
        "evidence_sufficient": snap.evidence_sufficient,
        "available_dimensions": list(snap.available_dimensions),
        "unavailable_dimensions": list(snap.unavailable_dimensions),
        "stale_dimensions": list(snap.stale_dimensions),
        "regime_summary": snap.regime_summary,
    }


def external_regime_snapshot_from_dict(d: dict) -> ExternalRegimeSnapshot:
    """Deserialize ExternalRegimeSnapshot from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    from crypto_core.execution.regime_contracts import (
        _event_from_dict,
        _onchain_from_dict,
        _options_from_dict,
    )

    try:
        return ExternalRegimeSnapshot(
            snapshot_ns=int(d["snapshot_ns"]),
            options=(_options_from_dict(d["options"]) if d.get("options") else None),
            event=_event_from_dict(d["event"]) if d.get("event") else None,
            on_chain=(_onchain_from_dict(d["on_chain"]) if d.get("on_chain") else None),
            options_freshness=dimension_freshness_from_dict(d["options_freshness"]),
            event_freshness=dimension_freshness_from_dict(d["event_freshness"]),
            on_chain_freshness=dimension_freshness_from_dict(d["on_chain_freshness"]),
            any_extreme=bool(d["any_extreme"]),
            any_unavailable_critical=bool(d["any_unavailable_critical"]),
            high_risk_regime_present=bool(d["high_risk_regime_present"]),
            evidence_sufficient=bool(d["evidence_sufficient"]),
            available_dimensions=tuple(d.get("available_dimensions", ())),
            unavailable_dimensions=tuple(d.get("unavailable_dimensions", ())),
            stale_dimensions=tuple(d.get("stale_dimensions", ())),
            regime_summary=str(d.get("regime_summary", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeSnapshot: {exc}") from exc


def external_regime_plane_to_dict(plane: ExternalRegimeDataPlane) -> dict:
    """Serialize the current data plane state for persistence."""
    from crypto_core.execution.regime_contracts import (
        _event_to_dict,
        _onchain_to_dict,
        _options_to_dict,
    )

    return {
        "staleness_threshold_s": plane.staleness_threshold_s,
        "options": _options_to_dict(plane.options_state) if plane.options_state else None,
        "event": _event_to_dict(plane.event_state) if plane.event_state else None,
        "on_chain": _onchain_to_dict(plane.on_chain_state) if plane.on_chain_state else None,
    }


def external_regime_plane_from_dict(d: dict) -> ExternalRegimeDataPlane:
    """Deserialize the data plane state from persistence."""
    from crypto_core.execution.regime_contracts import (
        _event_from_dict,
        _onchain_from_dict,
        _options_from_dict,
    )

    try:
        threshold = float(d["staleness_threshold_s"])
        plane = ExternalRegimeDataPlane(staleness_threshold_s=threshold)
        if d.get("options") is not None:
            plane.update_options(_options_from_dict(d["options"]))
        if d.get("event") is not None:
            plane.update_event(_event_from_dict(d["event"]))
        if d.get("on_chain") is not None:
            plane.update_on_chain(_onchain_from_dict(d["on_chain"]))
        return plane
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeDataPlane: {exc}") from exc


def external_regime_update_record_to_dict(record: ExternalRegimeUpdateRecord) -> dict:
    """Serialize an update record to a plain dict."""
    return {
        "dimension": record.dimension,
        "status": record.status.value,
        "accepted": record.accepted,
        "received_at_ns": record.received_at_ns,
        "state_snapshot_ns": record.state_snapshot_ns,
        "source_label": record.source_label,
        "level": record.level,
        "freshness": record.freshness.value,
        "replaced_existing": record.replaced_existing,
        "reason": record.reason,
    }


def external_regime_update_record_from_dict(d: dict) -> ExternalRegimeUpdateRecord:
    """Deserialize an update record from a plain dict."""
    try:
        return ExternalRegimeUpdateRecord(
            dimension=str(d["dimension"]),
            status=ExternalRegimeUpdateStatus(d["status"]),
            accepted=bool(d["accepted"]),
            received_at_ns=int(d["received_at_ns"]),
            state_snapshot_ns=(int(d["state_snapshot_ns"]) if d.get("state_snapshot_ns") is not None else None),
            source_label=d.get("source_label"),
            level=d.get("level"),
            freshness=DataFreshness(d["freshness"]),
            replaced_existing=bool(d["replaced_existing"]),
            reason=str(d.get("reason", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeUpdateRecord: {exc}") from exc


def external_regime_persistence_state_to_dict(state: ExternalRegimePersistenceState) -> dict:
    """Serialize persistence state to a plain dict."""
    return {
        "evidence_store_configured": state.evidence_store_configured,
        "snapshot_name": state.snapshot_name,
        "snapshot_present": state.snapshot_present,
        "restored_from_snapshot": state.restored_from_snapshot,
        "history_limit": state.history_limit,
    }


class ExternalRegimeManager:
    """Managed update / persistence lifecycle for external regime state.

    Reuses ExternalRegimeDataPlane as the underlying truth engine while adding:
      - deterministic update acceptance / rejection records,
      - bounded recent update history,
      - persistent current-state snapshots,
      - safe restore semantics,
      - operator-facing reporting helpers.
    """

    def __init__(
        self,
        *,
        plane: ExternalRegimeDataPlane | None = None,
        evidence_store: EvidenceStore | None = None,
        history_limit: int = 50,
    ) -> None:
        if history_limit <= 0:
            raise ValueError(f"history_limit must be > 0, got {history_limit}")
        self._plane = plane or ExternalRegimeDataPlane()
        self._evidence_store = evidence_store
        self._history_limit = history_limit
        self._history: deque[ExternalRegimeUpdateRecord] = deque(maxlen=history_limit)
        self._latest_update: ExternalRegimeUpdateRecord | None = None
        self._restored_from_snapshot = False

    @property
    def plane(self) -> ExternalRegimeDataPlane:
        """Underlying external regime data plane."""
        return self._plane

    @property
    def latest_update(self) -> ExternalRegimeUpdateRecord | None:
        """Most recent update attempt, accepted or rejected."""
        return self._latest_update

    @property
    def history_limit(self) -> int:
        """Maximum number of update records retained in memory."""
        return self._history_limit

    def recent_update_history(self) -> tuple[ExternalRegimeUpdateRecord, ...]:
        """Bounded recent update history, oldest first."""
        return tuple(self._history)

    def has_current_state(self) -> bool:
        """True when at least one regime dimension is currently populated."""
        return any(
            state is not None
            for state in (
                self._plane.options_state,
                self._plane.event_state,
                self._plane.on_chain_state,
            )
        )

    def snapshot(self, now_ns: int) -> ExternalRegimeSnapshot:
        """Current truthful external regime snapshot."""
        return self._plane.snapshot(now_ns)

    def update_options(
        self,
        state: OptionsRegimeState,
        *,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one options regime update with explicit acceptance semantics."""
        return self._apply_update(
            dimension="options",
            state=state,
            expected_type=OptionsRegimeState,
            current_state=self._plane.options_state,
            apply_update=self._plane.update_options,
            received_at_ns=received_at_ns,
        )

    def update_event(
        self,
        state: EventRegimeState,
        *,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one event regime update with explicit acceptance semantics."""
        return self._apply_update(
            dimension="event",
            state=state,
            expected_type=EventRegimeState,
            current_state=self._plane.event_state,
            apply_update=self._plane.update_event,
            received_at_ns=received_at_ns,
        )

    def update_on_chain(
        self,
        state: OnChainRegimeState,
        *,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one on-chain regime update with explicit acceptance semantics."""
        return self._apply_update(
            dimension="on_chain",
            state=state,
            expected_type=OnChainRegimeState,
            current_state=self._plane.on_chain_state,
            apply_update=self._plane.update_on_chain,
            received_at_ns=received_at_ns,
        )

    def update_composite(
        self,
        *,
        options: OptionsRegimeState | None = None,
        event: EventRegimeState | None = None,
        on_chain: OnChainRegimeState | None = None,
        received_at_ns: int | None = None,
    ) -> tuple[ExternalRegimeUpdateRecord, ...]:
        """Apply multiple dimension updates in one deterministic batch order."""
        results: list[ExternalRegimeUpdateRecord] = []
        if options is not None:
            results.append(self.update_options(options, received_at_ns=received_at_ns))
        if event is not None:
            results.append(self.update_event(event, received_at_ns=received_at_ns))
        if on_chain is not None:
            results.append(self.update_on_chain(on_chain, received_at_ns=received_at_ns))
        return tuple(results)

    def reset(
        self,
        *,
        received_at_ns: int,
        reason: str = "operator_reset",
        source_label: str = "operator_reset",
    ) -> ExternalRegimeUpdateRecord:
        """Explicitly clear all regime dimensions and persist the cleared state."""
        if not isinstance(received_at_ns, int) or received_at_ns < 0:
            raise ValueError(f"received_at_ns must be >= 0, got {received_at_ns!r}")
        replaced_existing = self.has_current_state()
        self._plane.reset()
        self._restored_from_snapshot = False
        record = ExternalRegimeUpdateRecord(
            dimension="all",
            status=ExternalRegimeUpdateStatus.RESET,
            accepted=True,
            received_at_ns=received_at_ns,
            state_snapshot_ns=None,
            source_label=source_label,
            level=None,
            freshness=DataFreshness.UNAVAILABLE,
            replaced_existing=replaced_existing,
            reason=reason,
        )
        self._record(record)
        return record

    def persist_state(self) -> WriteResult | None:
        """Persist the managed external regime state snapshot."""
        if self._evidence_store is None:
            return None
        return self._evidence_store.save_snapshot(
            _EXTERNAL_REGIME_SNAPSHOT_NAME,
            self._state_to_dict(),
        )

    def restore_state(self) -> bool:
        """Restore the last persisted external regime state, if present."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for external regime restore")
        if self.has_current_state():
            raise RuntimeError("Cannot restore external regime over existing in-memory state")
        if not self._evidence_store.snapshot_exists(_EXTERNAL_REGIME_SNAPSHOT_NAME):
            return False

        try:
            envelope = self._evidence_store.load_snapshot(_EXTERNAL_REGIME_SNAPSHOT_NAME)
        except EvidenceStoreCorruptError as exc:
            raise ExternalRegimeStateCorruptError(str(exc)) from exc

        data = envelope.get("data")
        if not isinstance(data, dict):
            raise ExternalRegimeStateCorruptError(
                f"External regime state 'data' must be a dict, got {type(data).__name__!r}"
            )

        required = {"plane", "history_limit", "recent_history", "persistence"}
        missing = required - set(data)
        if missing:
            raise ExternalRegimeStateCorruptError(f"External regime state missing required fields: {sorted(missing)!r}")

        try:
            plane = external_regime_plane_from_dict(data["plane"])
            history_limit = int(data["history_limit"])
            if history_limit <= 0:
                raise ValueError(f"history_limit must be > 0, got {history_limit}")
            history = [external_regime_update_record_from_dict(item) for item in data.get("recent_history", [])]
            latest_raw = data.get("latest_update")
            latest = (
                external_regime_update_record_from_dict(latest_raw)
                if latest_raw is not None
                else (history[-1] if history else None)
            )
        except ValueError as exc:
            raise ExternalRegimeStateCorruptError(str(exc)) from exc

        self._plane = plane
        self._history_limit = history_limit
        self._history = deque(history, maxlen=history_limit)
        self._latest_update = latest
        self._restored_from_snapshot = True
        self._append_audit_record(
            event_name="external_regime_restore",
            data={
                "snapshot_name": _EXTERNAL_REGIME_SNAPSHOT_NAME,
                "restored": True,
                "history_count": len(history),
                "has_current_state": self.has_current_state(),
            },
        )
        return True

    def persistence_state(self) -> ExternalRegimePersistenceState:
        """Current persistence / restore status."""
        snapshot_present = False
        if self._evidence_store is not None:
            snapshot_present = self._evidence_store.snapshot_exists(_EXTERNAL_REGIME_SNAPSHOT_NAME)
        return ExternalRegimePersistenceState(
            evidence_store_configured=self._evidence_store is not None,
            snapshot_name=_EXTERNAL_REGIME_SNAPSHOT_NAME,
            snapshot_present=snapshot_present,
            restored_from_snapshot=self._restored_from_snapshot,
            history_limit=self._history_limit,
        )

    def status_dict(self, now_ns: int) -> dict:
        """Operator-facing lifecycle view of current regime state."""
        snap = self.snapshot(now_ns)
        return {
            "current_snapshot": external_regime_snapshot_to_dict(snap),
            "latest_update": (
                external_regime_update_record_to_dict(self._latest_update) if self._latest_update is not None else None
            ),
            "recent_history": [external_regime_update_record_to_dict(record) for record in self._history],
            "persistence": external_regime_persistence_state_to_dict(self.persistence_state()),
        }

    def _apply_update(
        self,
        *,
        dimension: str,
        state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
        expected_type: type,
        current_state: OptionsRegimeState | EventRegimeState | OnChainRegimeState | None,
        apply_update,
        received_at_ns: int | None,
    ) -> ExternalRegimeUpdateRecord:
        received = state.snapshot_ns if received_at_ns is None else received_at_ns
        rejected = self._validate_update(
            dimension=dimension,
            state=state,
            expected_type=expected_type,
            current_state=current_state,
            received_at_ns=received,
        )
        if rejected is not None:
            self._record(rejected)
            return rejected

        replaced_existing = current_state is not None and state.snapshot_ns > current_state.snapshot_ns
        apply_update(state)
        snap = self._plane.snapshot(received)
        record = ExternalRegimeUpdateRecord(
            dimension=dimension,
            status=ExternalRegimeUpdateStatus.ACCEPTED,
            accepted=True,
            received_at_ns=received,
            state_snapshot_ns=state.snapshot_ns,
            source_label=state.source,
            level=state.level.value,
            freshness=self._dimension_freshness(snap, dimension),
            replaced_existing=replaced_existing,
            reason="accepted",
        )
        self._restored_from_snapshot = False
        self._record(record)
        return record

    def _validate_update(
        self,
        *,
        dimension: str,
        state: object,
        expected_type: type,
        current_state: OptionsRegimeState | EventRegimeState | OnChainRegimeState | None,
        received_at_ns: int,
    ) -> ExternalRegimeUpdateRecord | None:
        if not isinstance(received_at_ns, int) or received_at_ns < 0:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=0 if not isinstance(received_at_ns, int) else received_at_ns,
                source_label=None,
                reason=f"invalid_received_at_ns:{received_at_ns!r}",
            )

        if not isinstance(state, expected_type):
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=None,
                reason=f"invalid_type:{type(state).__name__}",
            )

        if not isinstance(state.snapshot_ns, int) or state.snapshot_ns < 0:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=state.source if isinstance(state.source, str) else None,
                reason=f"invalid_snapshot_ns:{state.snapshot_ns!r}",
            )

        if not isinstance(state.source, str) or not state.source.strip():
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=None,
                reason="missing_source_label",
            )

        symbol = getattr(state, "symbol", None)
        if dimension in {"options", "on_chain"} and (not isinstance(symbol, str) or not symbol.strip()):
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=state.source,
                reason="missing_symbol",
            )

        if current_state is not None and state.snapshot_ns < current_state.snapshot_ns:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_STALE,
                received_at_ns=received_at_ns,
                source_label=state.source,
                reason=f"stale_update:{state.snapshot_ns}<{current_state.snapshot_ns}",
                state_snapshot_ns=state.snapshot_ns,
                level=state.level.value,
            )

        if current_state is not None and state.snapshot_ns == current_state.snapshot_ns and state != current_state:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=state.source,
                reason="contradictory_same_timestamp",
                state_snapshot_ns=state.snapshot_ns,
                level=state.level.value,
            )

        return None

    def _record(self, record: ExternalRegimeUpdateRecord) -> None:
        self._latest_update = record
        self._history.append(record)
        self._append_audit_record(
            event_name="external_regime_update",
            data=external_regime_update_record_to_dict(record),
        )
        self.persist_state()

    def _append_audit_record(self, *, event_name: str, data: dict) -> None:
        if self._evidence_store is None:
            return
        payload = {"record_type": event_name, **data}
        self._evidence_store.append_evidence("audit_record", payload)

    @staticmethod
    def _dimension_freshness(snap: ExternalRegimeSnapshot, dimension: str) -> DataFreshness:
        if dimension == "options":
            return snap.options_freshness.freshness
        if dimension == "event":
            return snap.event_freshness.freshness
        if dimension == "on_chain":
            return snap.on_chain_freshness.freshness
        return DataFreshness.UNAVAILABLE

    @staticmethod
    def _rejected_record(
        *,
        dimension: str,
        status: ExternalRegimeUpdateStatus,
        received_at_ns: int,
        source_label: str | None,
        reason: str,
        state_snapshot_ns: int | None = None,
        level: str | None = None,
    ) -> ExternalRegimeUpdateRecord:
        return ExternalRegimeUpdateRecord(
            dimension=dimension,
            status=status,
            accepted=False,
            received_at_ns=received_at_ns,
            state_snapshot_ns=state_snapshot_ns,
            source_label=source_label,
            level=level,
            freshness=DataFreshness.UNAVAILABLE,
            replaced_existing=False,
            reason=reason,
        )

    def _state_to_dict(self) -> dict:
        return {
            "plane": external_regime_plane_to_dict(self._plane),
            "history_limit": self._history_limit,
            "latest_update": (
                external_regime_update_record_to_dict(self._latest_update) if self._latest_update is not None else None
            ),
            "recent_history": [external_regime_update_record_to_dict(record) for record in self._history],
            "persistence": external_regime_persistence_state_to_dict(self.persistence_state()),
        }
