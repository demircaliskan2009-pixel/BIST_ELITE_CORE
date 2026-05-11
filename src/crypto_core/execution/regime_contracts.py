"""Regime state contracts for options / event / on-chain flows — Phase 9B.

Typed contract layer for regime states that do not yet have full
implementations.  These contracts allow future implementation modules
to integrate safely and deterministically without ad-hoc guessing.

Every contract:
  - Has explicit UNKNOWN / UNAVAILABLE states for missing data.
  - Is a frozen dataclass (immutable, hashable, auditable).
  - Never fabricates intelligence — only encodes structure.
  - Includes evidence dict for auditability.

PRD reference: §1.4 Edge Family D (Event-Driven), §1.29 System State.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ===================================================================
# Cross-cutting enums — Phase 11A
# ===================================================================


class DataFreshness(str, Enum):
    """Freshness assessment for an external data dimension.

    FRESH:       data within acceptable staleness window.
    STALE:       data past staleness threshold.
    DEGRADED:    data partially available or has quality gaps.
    UNAVAILABLE: no data ever received or source reports unavailable.
    """

    FRESH = "fresh"
    STALE = "stale"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class EventSeverity(str, Enum):
    """Severity / importance of a scheduled or breaking event.

    LOW:      minor event, minimal expected market impact.
    MEDIUM:   moderate event, some positioning expected.
    HIGH:     major event, significant market impact likely.
    CRITICAL: extreme event, trading halt / regime shift likely.
    UNKNOWN:  severity not assessed or not available.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


# ===================================================================
# Options regime state
# ===================================================================


class OptionsRegimeLevel(str, Enum):
    """Options market regime classification.

    NORMAL:      implied vol within historical norms.
    ELEVATED:    IV above 1σ of recent history.
    EXTREME:     IV above 2σ or skew inversion detected.
    SUPPRESSED:  IV abnormally low (risk of vol expansion).
    UNAVAILABLE: no options data available.
    """

    NORMAL = "normal"
    ELEVATED = "elevated"
    EXTREME = "extreme"
    SUPPRESSED = "suppressed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class OptionsRegimeState:
    """Point-in-time options regime observation.

    symbol: underlying symbol.
    level: categorical regime classification.
    implied_vol_30d: 30-day implied volatility (annualized). None = unavailable.
    implied_vol_7d: 7-day implied volatility. None = unavailable.
    put_call_ratio: put/call open interest ratio. None = unavailable.
    skew_25d: 25-delta skew (puts minus calls). None = unavailable.
    term_structure_slope: slope of IV term structure. None = unavailable.
    snapshot_ns: observation timestamp.
    source: data source identifier.
    evidence: audit metadata.
    """

    symbol: str
    level: OptionsRegimeLevel
    snapshot_ns: int
    source: str
    implied_vol_30d: float | None = None
    implied_vol_7d: float | None = None
    put_call_ratio: float | None = None
    skew_25d: float | None = None
    term_structure_slope: float | None = None
    evidence: dict = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.level != OptionsRegimeLevel.UNAVAILABLE

    @property
    def is_extreme(self) -> bool:
        return self.level == OptionsRegimeLevel.EXTREME


# ===================================================================
# Event regime state
# ===================================================================


class EventRegimeLevel(str, Enum):
    """Scheduled / breaking event regime classification.

    QUIET:       no significant scheduled events in the window.
    PENDING:     major event scheduled within the observation window.
    ACTIVE:      event is currently unfolding (e.g., FOMC announcement).
    AFTERMATH:   event recently completed; market still absorbing.
    UNAVAILABLE: no event calendar data available.
    """

    QUIET = "quiet"
    PENDING = "pending"
    ACTIVE = "active"
    AFTERMATH = "aftermath"
    UNAVAILABLE = "unavailable"


class EventCategory(str, Enum):
    """Category of scheduled event."""

    MACRO = "macro"  # FOMC, CPI, NFP
    REGULATORY = "regulatory"  # SEC decisions, legislation
    PROTOCOL = "protocol"  # hard forks, upgrades, halvings
    LISTING = "listing"  # new exchange listings / delistings
    EARNINGS = "earnings"  # relevant company earnings (crypto-adjacent)
    UNLOCK = "unlock"  # token unlock / vesting cliff
    GOVERNANCE = "governance"  # DAO votes, protocol governance
    ETF = "etf"  # ETF approval / rejection / flow events
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EventRegimeState:
    """Point-in-time event regime observation.

    level: current event regime classification.
    event_category: type of the dominant event (if any).
    event_label: human-readable event name (e.g., "FOMC_2026_04").
    hours_until_event: hours until next event (None = no scheduled event).
    hours_since_event: hours since last event (None = no recent event).
    impact_estimate: expected market impact [0, 1] (None = unknown).
    snapshot_ns: observation timestamp.
    source: data source identifier.
    evidence: audit metadata.
    """

    level: EventRegimeLevel
    snapshot_ns: int
    source: str
    event_category: EventCategory = EventCategory.UNKNOWN
    event_label: str | None = None
    hours_until_event: float | None = None
    hours_since_event: float | None = None
    impact_estimate: float | None = None
    evidence: dict = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.level != EventRegimeLevel.UNAVAILABLE

    @property
    def is_active_or_pending(self) -> bool:
        return self.level in (EventRegimeLevel.PENDING, EventRegimeLevel.ACTIVE)


# ===================================================================
# On-chain / flow regime state
# ===================================================================


class OnChainRegimeLevel(str, Enum):
    """On-chain flow regime classification.

    NORMAL:      on-chain metrics within historical norms.
    ACCUMULATION: significant net inflows to cold wallets / staking.
    DISTRIBUTION: significant net outflows from exchanges.
    WHALE_ACTIVE: large single-entity transfers detected.
    STRESS:      abnormal on-chain activity (e.g., liquidation cascades).
    UNAVAILABLE: no on-chain data available.
    """

    NORMAL = "normal"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    WHALE_ACTIVE = "whale_active"
    STRESS = "stress"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class OnChainRegimeState:
    """Point-in-time on-chain flow regime observation.

    symbol: underlying symbol (e.g., "BTCUSDT" or "BTC" for chain-native).
    level: categorical regime classification.
    exchange_net_flow_24h_usd: net exchange flow in USD (positive = inflow).
    whale_transfer_count_24h: large transfers (>$1M) in 24h.
    active_addresses_7d_change_pct: 7d change in active addresses.
    staking_ratio_change_7d_pct: 7d change in staking ratio.
    snapshot_ns: observation timestamp.
    source: data source identifier (e.g., "glassnode", "nansen").
    evidence: audit metadata.
    """

    symbol: str
    level: OnChainRegimeLevel
    snapshot_ns: int
    source: str
    exchange_net_flow_24h_usd: float | None = None
    whale_transfer_count_24h: int | None = None
    active_addresses_7d_change_pct: float | None = None
    staking_ratio_change_7d_pct: float | None = None
    evidence: dict = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.level != OnChainRegimeLevel.UNAVAILABLE

    @property
    def is_stress(self) -> bool:
        return self.level == OnChainRegimeLevel.STRESS


# ===================================================================
# Composite regime envelope
# ===================================================================


@dataclass(frozen=True)
class CompositeRegimeState:
    """Combined regime state across all regime dimensions.

    Used by the edge activation matrix and system state engine to make
    regime-aware decisions.  Any dimension that is None means that
    particular regime source is not yet integrated.
    """

    snapshot_ns: int
    options: OptionsRegimeState | None = None
    event: EventRegimeState | None = None
    on_chain: OnChainRegimeState | None = None
    evidence: dict = field(default_factory=dict)

    @property
    def any_extreme(self) -> bool:
        """True if any available regime dimension indicates extreme conditions."""
        if self.options is not None and self.options.is_extreme:
            return True
        if self.event is not None and self.event.is_active_or_pending:
            return True
        if self.on_chain is not None and self.on_chain.is_stress:
            return True
        return False

    @property
    def available_dimensions(self) -> list[str]:
        """List of regime dimensions that have available data."""
        dims = []
        if self.options is not None and self.options.is_available:
            dims.append("options")
        if self.event is not None and self.event.is_available:
            dims.append("event")
        if self.on_chain is not None and self.on_chain.is_available:
            dims.append("on_chain")
        return dims

    @property
    def unavailable_dimensions(self) -> list[str]:
        """List of regime dimensions that are unavailable."""
        dims = []
        if self.options is None or not self.options.is_available:
            dims.append("options")
        if self.event is None or not self.event.is_available:
            dims.append("event")
        if self.on_chain is None or not self.on_chain.is_available:
            dims.append("on_chain")
        return dims


# ===================================================================
# Serialization
# ===================================================================


def composite_regime_to_dict(state: CompositeRegimeState) -> dict:
    """Serialize CompositeRegimeState to a plain dict."""
    return {
        "snapshot_ns": state.snapshot_ns,
        "options": _options_to_dict(state.options) if state.options else None,
        "event": _event_to_dict(state.event) if state.event else None,
        "on_chain": _onchain_to_dict(state.on_chain) if state.on_chain else None,
        "any_extreme": state.any_extreme,
        "available_dimensions": state.available_dimensions,
        "unavailable_dimensions": state.unavailable_dimensions,
        "evidence": state.evidence,
    }


def composite_regime_from_dict(d: dict) -> CompositeRegimeState:
    """Deserialize CompositeRegimeState from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        return CompositeRegimeState(
            snapshot_ns=int(d["snapshot_ns"]),
            options=_options_from_dict(d["options"]) if d.get("options") else None,
            event=_event_from_dict(d["event"]) if d.get("event") else None,
            on_chain=_onchain_from_dict(d["on_chain"]) if d.get("on_chain") else None,
            evidence=d.get("evidence", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed composite regime state: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal serialization helpers
# ---------------------------------------------------------------------------


def _options_to_dict(o: OptionsRegimeState) -> dict:
    return {
        "symbol": o.symbol,
        "level": o.level.value,
        "snapshot_ns": o.snapshot_ns,
        "source": o.source,
        "implied_vol_30d": o.implied_vol_30d,
        "implied_vol_7d": o.implied_vol_7d,
        "put_call_ratio": o.put_call_ratio,
        "skew_25d": o.skew_25d,
        "term_structure_slope": o.term_structure_slope,
        "evidence": o.evidence,
    }


def _options_from_dict(d: dict) -> OptionsRegimeState:
    return OptionsRegimeState(
        symbol=d["symbol"],
        level=OptionsRegimeLevel(d["level"]),
        snapshot_ns=int(d["snapshot_ns"]),
        source=d["source"],
        implied_vol_30d=d.get("implied_vol_30d"),
        implied_vol_7d=d.get("implied_vol_7d"),
        put_call_ratio=d.get("put_call_ratio"),
        skew_25d=d.get("skew_25d"),
        term_structure_slope=d.get("term_structure_slope"),
        evidence=d.get("evidence", {}),
    )


def _event_to_dict(e: EventRegimeState) -> dict:
    return {
        "level": e.level.value,
        "snapshot_ns": e.snapshot_ns,
        "source": e.source,
        "event_category": e.event_category.value,
        "event_label": e.event_label,
        "hours_until_event": e.hours_until_event,
        "hours_since_event": e.hours_since_event,
        "impact_estimate": e.impact_estimate,
        "evidence": e.evidence,
    }


def _event_from_dict(d: dict) -> EventRegimeState:
    return EventRegimeState(
        level=EventRegimeLevel(d["level"]),
        snapshot_ns=int(d["snapshot_ns"]),
        source=d["source"],
        event_category=EventCategory(d.get("event_category", "unknown")),
        event_label=d.get("event_label"),
        hours_until_event=d.get("hours_until_event"),
        hours_since_event=d.get("hours_since_event"),
        impact_estimate=d.get("impact_estimate"),
        evidence=d.get("evidence", {}),
    )


def _onchain_to_dict(o: OnChainRegimeState) -> dict:
    return {
        "symbol": o.symbol,
        "level": o.level.value,
        "snapshot_ns": o.snapshot_ns,
        "source": o.source,
        "exchange_net_flow_24h_usd": o.exchange_net_flow_24h_usd,
        "whale_transfer_count_24h": o.whale_transfer_count_24h,
        "active_addresses_7d_change_pct": o.active_addresses_7d_change_pct,
        "staking_ratio_change_7d_pct": o.staking_ratio_change_7d_pct,
        "evidence": o.evidence,
    }


def _onchain_from_dict(d: dict) -> OnChainRegimeState:
    return OnChainRegimeState(
        symbol=d["symbol"],
        level=OnChainRegimeLevel(d["level"]),
        snapshot_ns=int(d["snapshot_ns"]),
        source=d["source"],
        exchange_net_flow_24h_usd=d.get("exchange_net_flow_24h_usd"),
        whale_transfer_count_24h=d.get("whale_transfer_count_24h"),
        active_addresses_7d_change_pct=d.get("active_addresses_7d_change_pct"),
        staking_ratio_change_7d_pct=d.get("staking_ratio_change_7d_pct"),
        evidence=d.get("evidence", {}),
    )
