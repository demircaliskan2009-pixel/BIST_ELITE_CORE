"""TCA closed loop — fill → markout → TCA persistence automation (Phase 9C).

Closes the gap between execution fills and measured TCA evidence by
automatically:
  1. Registering markout observations on every fill.
  2. Advancing markout horizons when price updates arrive.
  3. Persisting TCA records when sufficient evidence exists.
  4. Persisting attribution records when available.
  5. Maintaining dedup invariants for deterministic replay safety.

Design invariants:
  - Idempotent: replaying the same fill sequence produces no duplicate records.
  - Fail-closed: if markout or TCA cannot be computed, state is explicit PENDING.
  - No fabricated prices: all mid prices come from external observation.
  - Thread safety: NOT guaranteed — single-threaded pipeline use only.
  - The loop does NOT own the TCAStore or MarkoutObserver — they are injected.

PRD reference: §7 Execution Engine, §1.14 TCA.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from crypto_core.execution.attribution import TradeAttribution
from crypto_core.execution.markout import (
    MarkoutObservationSet,
    MarkoutObserver,
)
from crypto_core.execution.tca import (
    TCARecord,
    build_tca_record,
)
from crypto_core.execution.tca_store import TCAStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TCAEmitStatus(str, Enum):
    """Status of a TCA emission attempt."""

    EMITTED = "emitted"
    DEFERRED = "deferred"
    ALREADY_EMITTED = "already_emitted"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Fill registration result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FillRegistrationResult:
    """Result of registering a fill in the TCA loop.

    order_id: the fill's order identifier.
    markout_registered: True if markout observation was registered.
    initial_tca_status: status of the initial TCA record emission.
    evidence: audit metadata.
    """

    order_id: str
    markout_registered: bool
    initial_tca_status: TCAEmitStatus
    evidence: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Price update result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceUpdateResult:
    """Result of a price observation cycle.

    resolved_order_ids: orders with newly resolved markout horizons.
    expired_order_ids: orders with newly expired markout horizons.
    tca_emitted_order_ids: orders for which a completed TCA was emitted.
    harvested_count: number of fully complete observation sets harvested.
    """

    resolved_order_ids: tuple[str, ...] = ()
    expired_order_ids: tuple[str, ...] = ()
    tca_emitted_order_ids: tuple[str, ...] = ()
    harvested_count: int = 0


# ---------------------------------------------------------------------------
# ExecutionTCALoop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TCALoopConfig:
    """Configuration for the TCA closed loop.

    auto_persist_on_complete: if True, auto-append TCA to store when markout
        completes. If False, only register markout, caller persists manually.
    emit_initial_pending_tca: if True, emit an initial PENDING TCA record on
        fill registration (before markout completes).
    """

    auto_persist_on_complete: bool = True
    emit_initial_pending_tca: bool = False


class ExecutionTCALoop:
    """Closed-loop TCA engine: fill → markout → TCA persistence.

    Wires MarkoutObserver and TCAStore together with dedup logic.

    Usage::

        loop = ExecutionTCALoop(
            markout_observer=observer,
            tca_store=store,
        )

        # On fill:
        result = loop.on_fill(
            order_id="abc", fill_price=50000.0, fill_timestamp_ns=ts,
            is_buy=True, symbol="BTCUSDT", exchange="binance",
            decision_price=49990.0, arrival_price=49995.0,
            expected_slippage_bps=2.0,
        )

        # On each price update:
        update = loop.on_price_update("BTCUSDT", "binance", 50010.0, current_ns)

    Invariants:
      - Each order_id can only be registered once (dedup).
      - Each order_id produces at most one persisted TCA record (dedup).
      - harvest_and_persist() is idempotent for already-persisted orders.
      - Replay of the same fill sequence produces no duplicates.
    """

    def __init__(
        self,
        markout_observer: MarkoutObserver,
        tca_store: TCAStore | None = None,
        config: TCALoopConfig | None = None,
    ) -> None:
        self._observer = markout_observer
        self._store = tca_store
        self._config = config or TCALoopConfig()

        # Dedup tracking: order_ids that have been registered
        self._registered_order_ids: set[str] = set()
        # Dedup tracking: order_ids for which a complete TCA has been persisted
        self._persisted_tca_ids: set[str] = set()
        # Dedup tracking: order_ids for which attribution has been persisted
        self._persisted_attribution_ids: set[str] = set()

        # Fill context cache: order_id → fill details for TCA building
        self._fill_context: dict[str, _FillContext] = {}

    def load_persisted_ids(self, tca_order_ids: set[str], attribution_order_ids: set[str]) -> None:
        """Bootstrap dedup sets from previously persisted records.

        Call this on startup/recovery to prevent re-emitting records
        that were already persisted in a prior run.
        """
        self._persisted_tca_ids.update(tca_order_ids)
        self._persisted_attribution_ids.update(attribution_order_ids)
        self._registered_order_ids.update(tca_order_ids)

    def on_fill(
        self,
        *,
        order_id: str,
        fill_price: float,
        fill_timestamp_ns: int,
        is_buy: bool,
        symbol: str,
        exchange: str,
        size: float = 0.0,
        requested_size: float = 0.0,
        decision_price: float | None = None,
        arrival_price: float | None = None,
        expected_slippage_bps: float | None = None,
        spread_cost_bps: float | None = None,
        impact_cost_bps: float | None = None,
        fee_cost_bps: float | None = None,
        funding_cost_bps: float | None = None,
        fill_role: str = "unknown",
        regime_tag: str = "unknown",
        event_tag: str | None = None,
        route_venue: str | None = None,
        route_cost_bps: float | None = None,
    ) -> FillRegistrationResult:
        """Register a fill for markout observation and TCA tracking.

        Idempotent: if order_id was already registered, returns ALREADY_EMITTED.
        """
        # Dedup: reject duplicate registrations
        if order_id in self._registered_order_ids:
            return FillRegistrationResult(
                order_id=order_id,
                markout_registered=False,
                initial_tca_status=TCAEmitStatus.ALREADY_EMITTED,
                evidence={"reason": "duplicate_registration"},
            )

        # Register markout
        markout_ok = False
        try:
            self._observer.register_fill(
                order_id=order_id,
                fill_price=fill_price,
                fill_timestamp_ns=fill_timestamp_ns,
                is_buy=is_buy,
                symbol=symbol,
                exchange=exchange,
            )
            markout_ok = True
        except ValueError as exc:
            logger.warning("Markout registration failed for %s: %s", order_id, exc)

        # Cache fill context for later TCA building
        self._fill_context[order_id] = _FillContext(
            order_id=order_id,
            fill_price=fill_price,
            fill_timestamp_ns=fill_timestamp_ns,
            is_buy=is_buy,
            symbol=symbol,
            exchange=exchange,
            size=size,
            requested_size=requested_size,
            decision_price=decision_price,
            arrival_price=arrival_price,
            expected_slippage_bps=expected_slippage_bps,
            spread_cost_bps=spread_cost_bps,
            impact_cost_bps=impact_cost_bps,
            fee_cost_bps=fee_cost_bps,
            funding_cost_bps=funding_cost_bps,
            fill_role=fill_role,
            regime_tag=regime_tag,
            event_tag=event_tag,
            route_venue=route_venue,
            route_cost_bps=route_cost_bps,
        )

        self._registered_order_ids.add(order_id)

        # Optionally emit initial PENDING TCA record
        tca_status = TCAEmitStatus.DEFERRED
        if self._config.emit_initial_pending_tca and self._store is not None:
            if order_id not in self._persisted_tca_ids:
                record = self._build_tca_from_context(
                    self._fill_context[order_id],
                    markout_obs=None,
                )
                self._store.append_tca(record)
                tca_status = TCAEmitStatus.EMITTED

        return FillRegistrationResult(
            order_id=order_id,
            markout_registered=markout_ok,
            initial_tca_status=tca_status,
            evidence={
                "markout_ok": markout_ok,
                "tca_status": tca_status.value,
                "route_venue": route_venue,
                "route_cost_bps": route_cost_bps,
            },
        )

    def on_price_update(
        self,
        symbol: str,
        exchange: str,
        mid_price: float,
        observation_ns: int,
    ) -> PriceUpdateResult:
        """Supply a price observation, advance markout horizons, persist completed TCA.

        This is the main loop driver — call once per price tick.
        """
        # Advance markout horizons
        resolved = self._observer.observe_price(symbol, exchange, mid_price, observation_ns)

        # Expire stale horizons
        expired = self._observer.expire_stale(observation_ns)

        # Harvest complete observation sets and persist TCA
        tca_emitted: list[str] = []
        harvested = self._observer.harvest_complete()

        for obs_set in harvested:
            oid = obs_set.order_id
            if oid in self._persisted_tca_ids:
                continue  # dedup

            ctx = self._fill_context.get(oid)
            if ctx is None:
                logger.warning("No fill context for harvested order %s — skipping TCA", oid)
                continue

            if self._config.auto_persist_on_complete and self._store is not None:
                record = self._build_tca_from_context(ctx, markout_obs=obs_set)
                self._store.append_tca(record)
                self._persisted_tca_ids.add(oid)
                tca_emitted.append(oid)
                logger.debug("TCA persisted for order %s (status=%s)", oid, record.status.value)

        return PriceUpdateResult(
            resolved_order_ids=tuple(resolved),
            expired_order_ids=tuple(expired),
            tca_emitted_order_ids=tuple(tca_emitted),
            harvested_count=len(harvested),
        )

    def persist_attribution(
        self,
        attribution: TradeAttribution,
    ) -> TCAEmitStatus:
        """Persist an attribution record with dedup protection.

        Returns ALREADY_EMITTED if the order_id was already persisted.
        Returns UNAVAILABLE if no TCA store is configured.
        """
        if self._store is None:
            return TCAEmitStatus.UNAVAILABLE

        if attribution.order_id in self._persisted_attribution_ids:
            return TCAEmitStatus.ALREADY_EMITTED

        self._store.append_attribution(attribution)
        self._persisted_attribution_ids.add(attribution.order_id)
        return TCAEmitStatus.EMITTED

    def get_pending_order_ids(self) -> list[str]:
        """Return order IDs with pending (incomplete) markout observations."""
        return self._observer.tracked_order_ids()

    def get_persisted_tca_ids(self) -> frozenset[str]:
        """Return order IDs for which a TCA record has been persisted."""
        return frozenset(self._persisted_tca_ids)

    def get_persisted_attribution_ids(self) -> frozenset[str]:
        """Return order IDs for which attribution has been persisted."""
        return frozenset(self._persisted_attribution_ids)

    @property
    def registered_count(self) -> int:
        """Total fills registered in this session."""
        return len(self._registered_order_ids)

    @property
    def persisted_tca_count(self) -> int:
        """Total TCA records persisted in this session."""
        return len(self._persisted_tca_ids)

    @property
    def persisted_attribution_count(self) -> int:
        """Total attribution records persisted in this session."""
        return len(self._persisted_attribution_ids)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tca_from_context(
        ctx: _FillContext,
        markout_obs: MarkoutObservationSet | None,
    ) -> TCARecord:
        """Build a TCARecord from fill context and optional markout observations."""
        markout_mids: dict[int, float | None] | None = None
        if markout_obs is not None:
            markout_mids = {}
            for h in markout_obs.horizons:
                markout_mids[h.horizon_seconds] = h.mid_price_at_horizon

        return build_tca_record(
            order_id=ctx.order_id,
            symbol=ctx.symbol,
            exchange=ctx.exchange,
            intent="buy" if ctx.is_buy else "sell",
            timestamp_ns=ctx.fill_timestamp_ns,
            decision_price=ctx.decision_price,
            arrival_price=ctx.arrival_price,
            execution_price=ctx.fill_price,
            expected_slippage_bps=ctx.expected_slippage_bps,
            spread_cost_bps=ctx.spread_cost_bps,
            impact_cost_bps=ctx.impact_cost_bps,
            fee_cost_bps=ctx.fee_cost_bps,
            funding_cost_bps=ctx.funding_cost_bps,
            filled_quantity=ctx.size if ctx.size > 0 else None,
            requested_quantity=ctx.requested_size if ctx.requested_size > 0 else None,
            fill_role=_safe_fill_role(ctx.fill_role),
            markout_mids=markout_mids,
            regime_tag=_safe_regime_tag(ctx.regime_tag),
            event_tag=ctx.event_tag,
        )


# ---------------------------------------------------------------------------
# Internal fill context cache
# ---------------------------------------------------------------------------


@dataclass
class _FillContext:
    """Mutable internal fill context for TCA building."""

    order_id: str
    fill_price: float
    fill_timestamp_ns: int
    is_buy: bool
    symbol: str
    exchange: str
    size: float = 0.0
    requested_size: float = 0.0
    decision_price: float | None = None
    arrival_price: float | None = None
    expected_slippage_bps: float | None = None
    spread_cost_bps: float | None = None
    impact_cost_bps: float | None = None
    fee_cost_bps: float | None = None
    funding_cost_bps: float | None = None
    fill_role: str = "unknown"
    regime_tag: str = "unknown"
    event_tag: str | None = None
    route_venue: str | None = None
    route_cost_bps: float | None = None


# ---------------------------------------------------------------------------
# Safe enum conversion helpers
# ---------------------------------------------------------------------------


def _safe_fill_role(role: str) -> object:
    """Convert string to FillRole enum safely."""
    from crypto_core.execution.tca import FillRole

    try:
        return FillRole(role)
    except ValueError:
        return FillRole.UNKNOWN


def _safe_regime_tag(tag: str) -> object:
    """Convert string to RegimeTag enum safely."""
    from crypto_core.execution.tca import RegimeTag

    try:
        return RegimeTag(tag)
    except ValueError:
        return RegimeTag.UNKNOWN
