"""Venue metadata availability model — Phase 9B.

Explicit machine-readable states for venue metadata freshness:
fees, funding rates, and operational status.  When live metadata is
unavailable, the system must degrade to conservative estimates or
block execution — never silently use stale data.

Design invariants:
  - All models are frozen (immutable, hashable, auditable).
  - UNAVAILABLE / STALE are explicit first-class states, not hidden defaults.
  - Fail-closed: critical unavailable metadata → execution should block.
  - Conservative fallback: ESTIMATED fee/funding uses worst-case values.

PRD reference: §7 Execution Engine, §4 Data Layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Freshness enum
# ---------------------------------------------------------------------------


class MetadataFreshness(str, Enum):
    """Freshness state of a venue metadata field.

    LIVE:        sourced from live API within the freshness window.
    ESTIMATED:   derived from a model or recent historical data.
    STALE:       was once live but has exceeded the freshness window.
    UNAVAILABLE: never received or API returned error.
    """

    LIVE = "live"
    ESTIMATED = "estimated"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Fee metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeeMetadata:
    """Venue fee tier metadata with freshness tracking.

    maker_fee_bps: maker fee in basis points.
    taker_fee_bps: taker fee in basis points.
    maker_rebate_bps: maker rebate (positive = rebate received).
    freshness: how current this data is.
    source: where the data came from (e.g., "api_v1", "hardcoded_default").
    observed_at_ns: when the data was last fetched/computed.
    fee_tier: the venue's fee tier label if known (e.g., "VIP1").
    """

    maker_fee_bps: float
    taker_fee_bps: float
    freshness: MetadataFreshness
    source: str
    observed_at_ns: int
    maker_rebate_bps: float = 0.0
    fee_tier: str | None = None

    @property
    def is_usable(self) -> bool:
        """True if the fee data is fresh enough for execution decisions."""
        return self.freshness in (MetadataFreshness.LIVE, MetadataFreshness.ESTIMATED)

    @property
    def is_conservative(self) -> bool:
        """True if the fee data requires conservative assumptions."""
        return self.freshness != MetadataFreshness.LIVE


# ---------------------------------------------------------------------------
# Funding metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FundingMetadata:
    """Venue funding rate metadata with freshness tracking.

    funding_rate_bps: current/predicted funding rate in bps per period.
    next_funding_ns: timestamp of the next funding settlement.
    period_hours: funding period in hours (typically 8).
    freshness: how current this data is.
    source: data source identifier.
    observed_at_ns: when the data was last fetched.
    """

    funding_rate_bps: float | None
    freshness: MetadataFreshness
    source: str
    observed_at_ns: int
    next_funding_ns: int | None = None
    period_hours: float = 8.0

    @property
    def is_usable(self) -> bool:
        """True if funding data is fresh enough for cost estimation."""
        return self.freshness in (MetadataFreshness.LIVE, MetadataFreshness.ESTIMATED)


# ---------------------------------------------------------------------------
# Operational status metadata
# ---------------------------------------------------------------------------


class VenueOperationalStatus(str, Enum):
    """Operational health of a venue."""

    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    OUTAGE = "outage"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OperationalMetadata:
    """Venue operational status metadata.

    status: current operational state.
    freshness: how current this observation is.
    message: optional human-readable status message.
    observed_at_ns: when the status was last checked.
    """

    status: VenueOperationalStatus
    freshness: MetadataFreshness
    observed_at_ns: int
    message: str | None = None

    @property
    def is_tradeable(self) -> bool:
        """True if the venue is in a tradeable state."""
        return self.status == VenueOperationalStatus.OPERATIONAL


# ---------------------------------------------------------------------------
# Composite venue metadata snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueMetadataSnapshot:
    """Complete metadata snapshot for a single venue+symbol pair.

    Aggregates fee, funding, and operational metadata into a single
    auditable point-in-time snapshot.

    venue: exchange identifier.
    symbol: instrument symbol.
    fees: fee tier metadata (None = completely unavailable).
    funding: funding rate metadata (None = completely unavailable).
    operational: operational status (None = unknown).
    snapshot_ns: when this snapshot was assembled.
    evidence: audit metadata.
    """

    venue: str
    symbol: str
    snapshot_ns: int
    fees: FeeMetadata | None = None
    funding: FundingMetadata | None = None
    operational: OperationalMetadata | None = None
    evidence: dict = field(default_factory=dict)

    @property
    def execution_permitted(self) -> bool:
        """True only if all critical metadata is usable.

        Fail-closed: missing fee data or non-tradeable venue → False.
        """
        if self.fees is None or not self.fees.is_usable:
            return False
        if self.operational is not None and not self.operational.is_tradeable:
            return False
        return True

    @property
    def has_funding_data(self) -> bool:
        """True if funding rate data is available for cost estimation."""
        return self.funding is not None and self.funding.is_usable

    @property
    def worst_case_fee_bps(self) -> float:
        """Return worst-case (taker) fee bps, or conservative default if unavailable."""
        if self.fees is not None:
            return self.fees.taker_fee_bps
        return _DEFAULT_CONSERVATIVE_TAKER_FEE_BPS

    @property
    def freshness_summary(self) -> dict[str, str]:
        """Return freshness of each metadata component."""
        return {
            "fees": self.fees.freshness.value if self.fees else "unavailable",
            "funding": self.funding.freshness.value if self.funding else "unavailable",
            "operational": self.operational.freshness.value if self.operational else "unavailable",
        }


# Conservative default when fee data is completely unavailable.
_DEFAULT_CONSERVATIVE_TAKER_FEE_BPS: float = 10.0


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def build_hardcoded_fee_metadata(
    venue: str,
    snapshot_ns: int,
) -> FeeMetadata | None:
    """Build FeeMetadata from hardcoded defaults.

    Returns None if the venue is not in the known defaults.
    Freshness is explicitly ESTIMATED (not LIVE).
    """
    defaults = _HARDCODED_FEE_DEFAULTS.get(venue)
    if defaults is None:
        return None
    return FeeMetadata(
        maker_fee_bps=defaults[0],
        taker_fee_bps=defaults[1],
        freshness=MetadataFreshness.ESTIMATED,
        source="hardcoded_default",
        observed_at_ns=snapshot_ns,
    )


# Hardcoded venue fee defaults (maker_bps, taker_bps).
# Explicitly ESTIMATED freshness — not live.
_HARDCODED_FEE_DEFAULTS: dict[str, tuple[float, float]] = {
    "binance": (2.0, 5.0),
    "bybit": (1.0, 5.5),
}


def build_unavailable_metadata(
    venue: str,
    symbol: str,
    snapshot_ns: int,
) -> VenueMetadataSnapshot:
    """Build a fully-unavailable metadata snapshot.

    Used when no metadata source has been contacted.
    execution_permitted will be False (fail-closed).
    """
    return VenueMetadataSnapshot(
        venue=venue,
        symbol=symbol,
        snapshot_ns=snapshot_ns,
        fees=None,
        funding=None,
        operational=None,
        evidence={"source": "build_unavailable_metadata", "reason": "no_metadata_source"},
    )


def venue_metadata_to_dict(snap: VenueMetadataSnapshot) -> dict:
    """Serialize a VenueMetadataSnapshot to a plain dict."""
    return {
        "venue": snap.venue,
        "symbol": snap.symbol,
        "snapshot_ns": snap.snapshot_ns,
        "execution_permitted": snap.execution_permitted,
        "fees": _fee_to_dict(snap.fees) if snap.fees else None,
        "funding": _funding_to_dict(snap.funding) if snap.funding else None,
        "operational": _operational_to_dict(snap.operational) if snap.operational else None,
        "freshness_summary": snap.freshness_summary,
        "evidence": snap.evidence,
    }


def venue_metadata_from_dict(d: dict) -> VenueMetadataSnapshot:
    """Deserialize a VenueMetadataSnapshot from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        fees_raw = d.get("fees")
        funding_raw = d.get("funding")
        ops_raw = d.get("operational")

        return VenueMetadataSnapshot(
            venue=d["venue"],
            symbol=d["symbol"],
            snapshot_ns=int(d["snapshot_ns"]),
            fees=_fee_from_dict(fees_raw) if fees_raw else None,
            funding=_funding_from_dict(funding_raw) if funding_raw else None,
            operational=_operational_from_dict(ops_raw) if ops_raw else None,
            evidence=d.get("evidence", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed venue metadata: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal serialization helpers
# ---------------------------------------------------------------------------


def _fee_to_dict(f: FeeMetadata) -> dict:
    return {
        "maker_fee_bps": f.maker_fee_bps,
        "taker_fee_bps": f.taker_fee_bps,
        "maker_rebate_bps": f.maker_rebate_bps,
        "freshness": f.freshness.value,
        "source": f.source,
        "observed_at_ns": f.observed_at_ns,
        "fee_tier": f.fee_tier,
    }


def _fee_from_dict(d: dict) -> FeeMetadata:
    return FeeMetadata(
        maker_fee_bps=float(d["maker_fee_bps"]),
        taker_fee_bps=float(d["taker_fee_bps"]),
        maker_rebate_bps=float(d.get("maker_rebate_bps", 0.0)),
        freshness=MetadataFreshness(d["freshness"]),
        source=d["source"],
        observed_at_ns=int(d["observed_at_ns"]),
        fee_tier=d.get("fee_tier"),
    )


def _funding_to_dict(f: FundingMetadata) -> dict:
    return {
        "funding_rate_bps": f.funding_rate_bps,
        "freshness": f.freshness.value,
        "source": f.source,
        "observed_at_ns": f.observed_at_ns,
        "next_funding_ns": f.next_funding_ns,
        "period_hours": f.period_hours,
    }


def _funding_from_dict(d: dict) -> FundingMetadata:
    return FundingMetadata(
        funding_rate_bps=d.get("funding_rate_bps"),
        freshness=MetadataFreshness(d["freshness"]),
        source=d["source"],
        observed_at_ns=int(d["observed_at_ns"]),
        next_funding_ns=d.get("next_funding_ns"),
        period_hours=float(d.get("period_hours", 8.0)),
    )


def _operational_to_dict(o: OperationalMetadata) -> dict:
    return {
        "status": o.status.value,
        "freshness": o.freshness.value,
        "observed_at_ns": o.observed_at_ns,
        "message": o.message,
    }


def _operational_from_dict(d: dict) -> OperationalMetadata:
    return OperationalMetadata(
        status=VenueOperationalStatus(d["status"]),
        freshness=MetadataFreshness(d["freshness"]),
        observed_at_ns=int(d["observed_at_ns"]),
        message=d.get("message"),
    )
