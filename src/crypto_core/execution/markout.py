"""Markout observation lifecycle — Phase 9B.

Manages the full lifecycle of post-fill markout observations:
  pending → ready / expired / unavailable

Each fill registers pending observations at configured horizon offsets.
When future mid-price observations arrive, pending horizons resolve to
ready.  Horizons that exceed their expiry window become expired.

Design invariants:
  - All snapshot models are frozen (immutable, hashable, auditable).
  - Missing mid-price at a horizon is explicit PENDING / EXPIRED, never fabricated.
  - Fail-closed: if a fill cannot be registered (bad inputs) → ValueError.
  - Thread safety: NOT guaranteed — single-threaded pipeline use only.
  - No live data invented; all prices are externally supplied.

PRD reference: §7 Execution Engine, §1.14 TCA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MarkoutHorizonStatus(str, Enum):
    """Status of a single markout horizon observation."""

    PENDING = "pending"
    READY = "ready"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


class MarkoutSetStatus(str, Enum):
    """Aggregate status of all horizons for a single fill."""

    ALL_PENDING = "all_pending"
    PARTIAL = "partial"
    ALL_READY = "all_ready"
    ALL_EXPIRED = "all_expired"
    MIXED_EXPIRED = "mixed_expired"


# ---------------------------------------------------------------------------
# Frozen observation models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HorizonObservation:
    """Single horizon observation for a fill.

    horizon_seconds: the target observation offset from fill time.
    status: current lifecycle state.
    mid_price_at_horizon: observed mid price (None until READY).
    markout_bps: signed bps move from fill to horizon mid (None until READY).
    observed_at_ns: timestamp when the observation was recorded (None until READY).
    """

    horizon_seconds: int
    status: MarkoutHorizonStatus
    mid_price_at_horizon: float | None = None
    markout_bps: float | None = None
    observed_at_ns: int | None = None


@dataclass(frozen=True)
class MarkoutObservationSet:
    """Complete markout observation set for a single fill.

    order_id: parent order identifier.
    fill_price: execution price of the fill.
    fill_timestamp_ns: when the fill occurred.
    is_buy: direction of the fill.
    symbol: instrument symbol.
    exchange: venue identifier.
    horizons: tuple of HorizonObservation (one per configured horizon).
    set_status: aggregate status derived from individual horizons.
    evidence: audit metadata dict.
    """

    order_id: str
    fill_price: float
    fill_timestamp_ns: int
    is_buy: bool
    symbol: str
    exchange: str
    horizons: tuple[HorizonObservation, ...]
    set_status: MarkoutSetStatus
    evidence: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pending tracking (mutable, internal)
# ---------------------------------------------------------------------------


@dataclass
class _PendingHorizon:
    """Mutable internal tracker for a single pending horizon."""

    horizon_seconds: int
    target_ns: int  # fill_timestamp_ns + horizon_seconds * 1_000_000_000
    mid_price: float | None = None
    markout_bps: float | None = None
    observed_at_ns: int | None = None
    resolved: bool = False
    expired: bool = False


@dataclass
class _PendingFill:
    """Mutable internal tracker for all horizons of one fill."""

    order_id: str
    fill_price: float
    fill_timestamp_ns: int
    is_buy: bool
    symbol: str
    exchange: str
    horizons: list[_PendingHorizon] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MARKOUT_HORIZONS: tuple[int, ...] = (1, 5, 30, 60, 300)

# How long after target_ns to wait before expiring a horizon (seconds).
DEFAULT_EXPIRY_GRACE_SECONDS: int = 60


@dataclass(frozen=True)
class MarkoutObserverConfig:
    """Configuration for the MarkoutObserver.

    horizons: tuple of horizon offsets in seconds.
    expiry_grace_seconds: seconds after target time before a horizon expires.
    """

    horizons: tuple[int, ...] = DEFAULT_MARKOUT_HORIZONS
    expiry_grace_seconds: int = DEFAULT_EXPIRY_GRACE_SECONDS


# ---------------------------------------------------------------------------
# MarkoutObserver
# ---------------------------------------------------------------------------


class MarkoutObserver:
    """Manages the lifecycle of markout observations across fills.

    Usage::

        observer = MarkoutObserver()
        observer.register_fill("order1", 50000.0, fill_ts_ns, True, "BTCUSDT", "binance")

        # As price observations arrive:
        resolved = observer.observe_price("BTCUSDT", "binance", 50010.0, current_ns)

        # Get snapshot:
        obs_set = observer.get_observation_set("order1")

        # Expire stale horizons:
        expired = observer.expire_stale(current_ns)

    Invariants:
      - register_fill validates inputs; raises ValueError on bad data.
      - observe_price matches by (symbol, exchange) and resolves eligible horizons.
      - expire_stale marks overdue horizons as expired.
      - get_observation_set returns a frozen snapshot.
      - Completed fills (all horizons resolved or expired) can be harvested and removed.
    """

    def __init__(self, config: MarkoutObserverConfig | None = None) -> None:
        self._config = config or MarkoutObserverConfig()
        self._pending: dict[str, _PendingFill] = {}

    @property
    def pending_count(self) -> int:
        """Number of fills with at least one unresolved horizon."""
        return len(self._pending)

    def register_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_timestamp_ns: int,
        is_buy: bool,
        symbol: str,
        exchange: str,
    ) -> None:
        """Register a new fill for markout tracking.

        Raises ValueError if inputs are invalid (fail-closed).
        """
        if not order_id:
            raise ValueError("order_id must be non-empty")
        if fill_price <= 0:
            raise ValueError(f"fill_price must be positive, got {fill_price}")
        if fill_timestamp_ns <= 0:
            raise ValueError(f"fill_timestamp_ns must be positive, got {fill_timestamp_ns}")
        if not symbol or not exchange:
            raise ValueError("symbol and exchange must be non-empty")

        horizons = []
        for h in self._config.horizons:
            target_ns = fill_timestamp_ns + h * 1_000_000_000
            horizons.append(_PendingHorizon(horizon_seconds=h, target_ns=target_ns))

        self._pending[order_id] = _PendingFill(
            order_id=order_id,
            fill_price=fill_price,
            fill_timestamp_ns=fill_timestamp_ns,
            is_buy=is_buy,
            symbol=symbol,
            exchange=exchange,
            horizons=horizons,
        )

    def observe_price(
        self,
        symbol: str,
        exchange: str,
        mid_price: float,
        observation_ns: int,
    ) -> list[str]:
        """Supply a mid-price observation and resolve eligible pending horizons.

        Returns list of order_ids that had at least one horizon resolved.
        """
        if mid_price <= 0:
            return []

        resolved_orders: list[str] = []

        for order_id, pf in self._pending.items():
            if pf.symbol != symbol or pf.exchange != exchange:
                continue

            any_resolved = False
            for ph in pf.horizons:
                if ph.resolved or ph.expired:
                    continue
                # Resolve if observation is at or past the target time.
                if observation_ns >= ph.target_ns:
                    ph.mid_price = mid_price
                    ph.markout_bps = _compute_markout_bps(
                        pf.fill_price,
                        mid_price,
                        pf.is_buy,
                    )
                    ph.observed_at_ns = observation_ns
                    ph.resolved = True
                    any_resolved = True

            if any_resolved:
                resolved_orders.append(order_id)

        return resolved_orders

    def expire_stale(self, current_ns: int) -> list[str]:
        """Mark overdue unresolved horizons as expired.

        Returns list of order_ids that had at least one horizon expired.
        """
        grace_ns = self._config.expiry_grace_seconds * 1_000_000_000
        expired_orders: list[str] = []

        for order_id, pf in self._pending.items():
            any_expired = False
            for ph in pf.horizons:
                if ph.resolved or ph.expired:
                    continue
                if current_ns > ph.target_ns + grace_ns:
                    ph.expired = True
                    any_expired = True
            if any_expired:
                expired_orders.append(order_id)

        return expired_orders

    def get_observation_set(self, order_id: str) -> MarkoutObservationSet | None:
        """Return a frozen snapshot of the observation set for an order.

        Returns None if the order is not tracked.
        """
        pf = self._pending.get(order_id)
        if pf is None:
            return None

        horizon_obs = []
        for ph in pf.horizons:
            if ph.resolved:
                status = MarkoutHorizonStatus.READY
            elif ph.expired:
                status = MarkoutHorizonStatus.EXPIRED
            else:
                status = MarkoutHorizonStatus.PENDING

            horizon_obs.append(
                HorizonObservation(
                    horizon_seconds=ph.horizon_seconds,
                    status=status,
                    mid_price_at_horizon=ph.mid_price,
                    markout_bps=ph.markout_bps,
                    observed_at_ns=ph.observed_at_ns,
                )
            )

        set_status = _derive_set_status(horizon_obs)

        return MarkoutObservationSet(
            order_id=pf.order_id,
            fill_price=pf.fill_price,
            fill_timestamp_ns=pf.fill_timestamp_ns,
            is_buy=pf.is_buy,
            symbol=pf.symbol,
            exchange=pf.exchange,
            horizons=tuple(horizon_obs),
            set_status=set_status,
            evidence={
                "observer": "MarkoutObserver",
                "config_horizons": list(self._config.horizons),
                "expiry_grace_seconds": self._config.expiry_grace_seconds,
            },
        )

    def is_complete(self, order_id: str) -> bool:
        """True if all horizons for the order are resolved or expired."""
        pf = self._pending.get(order_id)
        if pf is None:
            return False
        return all(ph.resolved or ph.expired for ph in pf.horizons)

    def harvest_complete(self) -> list[MarkoutObservationSet]:
        """Remove and return all observation sets that are fully resolved/expired."""
        complete_ids = [oid for oid in self._pending if self.is_complete(oid)]
        results = []
        for oid in complete_ids:
            obs = self.get_observation_set(oid)
            if obs is not None:
                results.append(obs)
            del self._pending[oid]
        return results

    def tracked_order_ids(self) -> list[str]:
        """Return all currently tracked order IDs."""
        return list(self._pending.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_markout_bps(
    fill_price: float,
    mid_at_horizon: float,
    is_buy: bool,
) -> float | None:
    """Compute signed markout in bps from fill to horizon mid.

    Positive = favorable move (price moved in the fill's favor).
    """
    if fill_price <= 0:
        return None
    raw_bps = (mid_at_horizon - fill_price) / fill_price * 10_000
    return raw_bps if is_buy else -raw_bps


def _derive_set_status(
    horizons: list[HorizonObservation],
) -> MarkoutSetStatus:
    """Derive aggregate status from individual horizon statuses."""
    if not horizons:
        return MarkoutSetStatus.ALL_EXPIRED

    statuses = {h.status for h in horizons}

    if statuses == {MarkoutHorizonStatus.PENDING}:
        return MarkoutSetStatus.ALL_PENDING
    if statuses == {MarkoutHorizonStatus.READY}:
        return MarkoutSetStatus.ALL_READY
    if statuses == {MarkoutHorizonStatus.EXPIRED}:
        return MarkoutSetStatus.ALL_EXPIRED
    if MarkoutHorizonStatus.EXPIRED in statuses and MarkoutHorizonStatus.READY in statuses:
        return MarkoutSetStatus.MIXED_EXPIRED
    return MarkoutSetStatus.PARTIAL


def observation_set_to_dict(obs: MarkoutObservationSet) -> dict:
    """Serialize a MarkoutObservationSet to a plain dict for persistence."""
    return {
        "order_id": obs.order_id,
        "fill_price": obs.fill_price,
        "fill_timestamp_ns": obs.fill_timestamp_ns,
        "is_buy": obs.is_buy,
        "symbol": obs.symbol,
        "exchange": obs.exchange,
        "set_status": obs.set_status.value,
        "horizons": [
            {
                "horizon_seconds": h.horizon_seconds,
                "status": h.status.value,
                "mid_price_at_horizon": h.mid_price_at_horizon,
                "markout_bps": h.markout_bps,
                "observed_at_ns": h.observed_at_ns,
            }
            for h in obs.horizons
        ],
        "evidence": obs.evidence,
    }


def observation_set_from_dict(d: dict) -> MarkoutObservationSet:
    """Deserialize a MarkoutObservationSet from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        horizons = tuple(
            HorizonObservation(
                horizon_seconds=int(h["horizon_seconds"]),
                status=MarkoutHorizonStatus(h["status"]),
                mid_price_at_horizon=h.get("mid_price_at_horizon"),
                markout_bps=h.get("markout_bps"),
                observed_at_ns=h.get("observed_at_ns"),
            )
            for h in d["horizons"]
        )
        return MarkoutObservationSet(
            order_id=d["order_id"],
            fill_price=float(d["fill_price"]),
            fill_timestamp_ns=int(d["fill_timestamp_ns"]),
            is_buy=bool(d["is_buy"]),
            symbol=d["symbol"],
            exchange=d["exchange"],
            horizons=horizons,
            set_status=MarkoutSetStatus(d["set_status"]),
            evidence=d.get("evidence", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed observation set: {exc}") from exc
