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
from dataclasses import dataclass

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

logger = logging.getLogger(__name__)

_NS_PER_S: int = 1_000_000_000


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
