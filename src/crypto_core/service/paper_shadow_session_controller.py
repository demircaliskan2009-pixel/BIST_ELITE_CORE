"""Paper/shadow session controller - Phase 15M.

Deterministic lifecycle surface for paper/shadow activation plans.

Design rules:
  - Session lifecycle only: prepare/start/tick/stop/finalize/reset/restore.
  - No execution wiring, order routing, alpha, ranking, or allocation logic.
  - Fail closed on missing readiness, malformed restore, or unsafe real-trading flags.
  - PAPER/SHADOW ONLY.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum

from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    SleeveAdmissionCorruptError,
    paper_shadow_activation_plan_to_dict,
)


class PaperShadowSessionStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FINALIZED = "finalized"
    BLOCKED = "blocked"
    FAILED = "failed"


class PaperShadowSessionCorruptError(RuntimeError):
    pass


class RuntimeMonitorStatus(str, Enum):
    NOT_READY = "not_ready"
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class GuardrailAction(str, Enum):
    NONE = "none"
    WARN = "warn"
    PAUSE_SESSION = "pause_session"
    STOP_SESSION = "stop_session"
    BLOCK_FINALIZE = "block_finalize"


class MarketEventType(str, Enum):
    TRADE = "trade"
    MARK_PRICE = "mark_price"
    INDEX_PRICE = "index_price"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    BOOK_TICK = "book_tick"


@dataclass(frozen=True)
class MarketEvent:
    symbol: str
    venue: str
    ts_ns: int
    event_type: MarketEventType
    price: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None


@dataclass(frozen=True)
class MarketEventBatch:
    batch_id: str
    events: tuple[MarketEvent, ...]


@dataclass(frozen=True)
class MarketEventCursor:
    symbol: str
    venue: str
    last_event_ns: int


@dataclass(frozen=True)
class RuntimeMonitorSnapshot:
    status: RuntimeMonitorStatus = RuntimeMonitorStatus.NOT_READY
    event_count: int = 0
    stale_feed_detected: bool = False
    symbol_coverage_ok: bool = False
    venue_coverage_ok: bool = False
    price_validity_ok: bool = False
    event_gap_count: int = 0
    last_event_ns: int | None = None
    monitored_symbols: tuple[str, ...] = ()
    monitored_venues: tuple[str, ...] = ()
    required_symbols: tuple[str, ...] = ()
    required_venues: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ("no_market_events",)


@dataclass(frozen=True)
class GuardrailSnapshot:
    primary_action: GuardrailAction = GuardrailAction.BLOCK_FINALIZE
    actions: tuple[GuardrailAction, ...] = (GuardrailAction.BLOCK_FINALIZE, GuardrailAction.WARN)
    reason_codes: tuple[str, ...] = ("no_market_events",)
    monitor_status: RuntimeMonitorStatus = RuntimeMonitorStatus.NOT_READY
    block_finalize: bool = True
    should_pause_session: bool = False
    should_stop_session: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    paper_only: bool = True


@dataclass(frozen=True)
class PaperShadowSessionSnapshot:
    session_id: str
    status: PaperShadowSessionStatus
    as_of_ns: int
    plan_id: str = "unknown"
    plan_status: str = "unknown"
    source_manifest_status: str = "unknown"
    prepared_at_ns: int | None = None
    started_at_ns: int | None = None
    last_tick_at_ns: int | None = None
    stopped_at_ns: int | None = None
    finalized_at_ns: int | None = None
    tick_count: int = 0
    active_sleeves_seen: tuple[str, ...] = ()
    blockers_seen: tuple[str, ...] = ()
    event_count: int = 0
    symbols_seen: tuple[str, ...] = ()
    venues_seen: tuple[str, ...] = ()
    first_event_ns: int | None = None
    last_event_ns: int | None = None
    rejected_event_count: int = 0
    market_event_cursors: tuple[MarketEventCursor, ...] = ()
    runtime_monitor: RuntimeMonitorSnapshot = field(default_factory=RuntimeMonitorSnapshot)
    guardrail: GuardrailSnapshot = field(default_factory=GuardrailSnapshot)
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    active_sleeves: tuple[str, ...] = ()
    inactive_sleeves: tuple[str, ...] = ()
    admitted_unallocated_sleeves: tuple[str, ...] = ()
    activation_blockers: tuple[str, ...] = ()
    evidence_blockers: tuple[str, ...] = ()
    governance_blockers: tuple[str, ...] = ()
    operator_summary: str = "Paper/shadow session has not been prepared."


class PaperShadowSessionController:
    """Manage deterministic paper/shadow session lifecycle evidence."""

    def __init__(
        self,
        *,
        session_id: str = "paper-shadow-session-unprepared",
        clock_ns: Callable[[], int] | None = None,
        required_market_symbols: tuple[str, ...] = (),
        required_market_venues: tuple[str, ...] = (),
        max_market_event_gap_ns: int | None = None,
        snapshot: PaperShadowSessionSnapshot | None = None,
    ) -> None:
        self._clock_ns = time.time_ns if clock_ns is None else clock_ns
        self._required_market_symbols = _sorted_unique(required_market_symbols)
        self._required_market_venues = _sorted_unique(required_market_venues)
        self._max_market_event_gap_ns = _optional_non_negative_int(
            max_market_event_gap_ns,
            "max_market_event_gap_ns",
        )
        self._snapshot = (
            paper_shadow_session_snapshot_from_dict(paper_shadow_session_snapshot_to_dict(snapshot))
            if snapshot is not None
            else PaperShadowSessionSnapshot(
                session_id=session_id,
                status=PaperShadowSessionStatus.CREATED,
                as_of_ns=0,
            )
        )
        _validate_session_snapshot(self._snapshot)

    @property
    def current_snapshot(self) -> PaperShadowSessionSnapshot:
        return self._snapshot

    def snapshot(self) -> PaperShadowSessionSnapshot:
        return self._snapshot

    def report(self) -> PaperShadowSessionSnapshot:
        return self._snapshot

    def guardrail_snapshot(self) -> GuardrailSnapshot:
        return self._snapshot.guardrail

    def prepare(self, plan: PaperShadowActivationPlan) -> PaperShadowSessionSnapshot:
        _validate_activation_plan_for_session(plan)
        now = self._now_ns()
        status = (
            PaperShadowSessionStatus.READY
            if plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
            else PaperShadowSessionStatus.BLOCKED
        )
        blockers = _sorted_unique(
            (
                *plan.activation_blockers,
                *plan.evidence_blockers,
                *plan.governance_blockers,
            )
        )
        monitor = build_runtime_monitor_snapshot(
            event_count=0,
            monitored_symbols=(),
            monitored_venues=(),
            required_symbols=self._required_market_symbols,
            required_venues=self._required_market_venues,
        )
        return self._apply_snapshot(
            PaperShadowSessionSnapshot(
                session_id=_session_id_for_plan(plan),
                status=status,
                as_of_ns=now,
                plan_id=plan.plan_id,
                plan_status=plan.activation_status.value,
                source_manifest_status=plan.source_manifest_status.value,
                prepared_at_ns=now,
                tick_count=0,
                active_sleeves_seen=(),
                blockers_seen=blockers,
                runtime_monitor=monitor,
                guardrail=build_guardrail_snapshot(
                    monitor,
                    session_status=status,
                    rejected_event_count=0,
                    paper_only=True,
                    real_orders_enabled=False,
                    real_money_enabled=False,
                ),
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                active_sleeves=plan.active_sleeves,
                inactive_sleeves=plan.inactive_sleeves,
                admitted_unallocated_sleeves=plan.admitted_unallocated_sleeves,
                activation_blockers=plan.activation_blockers,
                evidence_blockers=plan.evidence_blockers,
                governance_blockers=plan.governance_blockers,
                operator_summary=_operator_summary(status, 0, plan.active_sleeves, blockers),
            )
        )

    def start(self) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.READY:
            raise PaperShadowSessionCorruptError("paper/shadow session can only start from READY state")
        now = self._now_ns()
        return self._apply_snapshot(
            replace(
                self._snapshot,
                status=PaperShadowSessionStatus.RUNNING,
                as_of_ns=now,
                started_at_ns=now,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.RUNNING,
                    self._snapshot.tick_count,
                    self._snapshot.active_sleeves,
                    self._snapshot.blockers_seen,
                ),
            ),
        )

    def record_tick(
        self,
        *,
        active_sleeves_seen: tuple[str, ...] = (),
        blockers_seen: tuple[str, ...] = (),
    ) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
            raise PaperShadowSessionCorruptError("paper/shadow session cannot record ticks before start")
        now = self._now_ns()
        seen = _sorted_unique((*self._snapshot.active_sleeves_seen, *active_sleeves_seen))
        blockers = _sorted_unique((*self._snapshot.blockers_seen, *blockers_seen))
        return self._apply_snapshot(
            replace(
                self._snapshot,
                as_of_ns=now,
                last_tick_at_ns=now,
                tick_count=self._snapshot.tick_count + 1,
                active_sleeves_seen=seen,
                blockers_seen=blockers,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.RUNNING,
                    self._snapshot.tick_count + 1,
                    self._snapshot.active_sleeves,
                    blockers,
                ),
            ),
        )

    def record_market_event_batch(self, batch: MarketEventBatch | dict) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
            raise PaperShadowSessionCorruptError("paper/shadow session cannot record market events before start")
        try:
            normalized = market_event_batch_from_dict(batch) if isinstance(batch, dict) else _normalize_batch(batch)
            _validate_batch_against_session(self._snapshot, normalized)
        except PaperShadowSessionCorruptError:
            self._record_rejected_events(_rejected_event_increment(batch))
            raise
        now = self._now_ns()
        events = normalized.events
        event_count = len(events)
        symbols = _sorted_unique((*self._snapshot.symbols_seen, *(event.symbol for event in events)))
        venues = _sorted_unique((*self._snapshot.venues_seen, *(event.venue for event in events)))
        first_event_ns = min(event.ts_ns for event in events)
        last_event_ns = max(event.ts_ns for event in events)
        event_gap_count = _market_event_gap_count(
            self._snapshot.market_event_cursors,
            events,
            self._max_market_event_gap_ns,
        )
        cursors = _merge_market_event_cursors(self._snapshot.market_event_cursors, events)
        total_event_count = self._snapshot.event_count + event_count
        total_event_gap_count = self._snapshot.runtime_monitor.event_gap_count + event_gap_count
        session_first_event_ns = (
            first_event_ns
            if self._snapshot.first_event_ns is None
            else min(self._snapshot.first_event_ns, first_event_ns)
        )
        session_last_event_ns = (
            last_event_ns if self._snapshot.last_event_ns is None else max(self._snapshot.last_event_ns, last_event_ns)
        )
        monitor = build_runtime_monitor_snapshot(
            event_count=total_event_count,
            monitored_symbols=symbols,
            monitored_venues=venues,
            required_symbols=self._required_market_symbols,
            required_venues=self._required_market_venues,
            price_validity_ok=True,
            event_gap_count=total_event_gap_count,
            last_event_ns=session_last_event_ns,
        )
        guardrail = build_guardrail_snapshot(
            monitor,
            session_status=self._snapshot.status,
            rejected_event_count=self._snapshot.rejected_event_count,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
        return self._apply_snapshot(
            replace(
                self._snapshot,
                as_of_ns=now,
                last_tick_at_ns=now,
                tick_count=self._snapshot.tick_count + 1,
                event_count=total_event_count,
                symbols_seen=symbols,
                venues_seen=venues,
                first_event_ns=session_first_event_ns,
                last_event_ns=session_last_event_ns,
                market_event_cursors=cursors,
                runtime_monitor=monitor,
                guardrail=guardrail,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.RUNNING,
                    self._snapshot.tick_count + 1,
                    self._snapshot.active_sleeves,
                    self._snapshot.blockers_seen,
                ),
            )
        )

    def tick_from_market_events(self, batch: MarketEventBatch | dict) -> PaperShadowSessionSnapshot:
        return self.record_market_event_batch(batch)

    def apply_guardrails(self) -> PaperShadowSessionSnapshot:
        guardrail = self._snapshot.guardrail
        if guardrail.should_stop_session and self._snapshot.status == PaperShadowSessionStatus.RUNNING:
            now = self._now_ns()
            blockers = _sorted_unique((*self._snapshot.blockers_seen, *guardrail.reason_codes))
            return self._apply_snapshot(
                replace(
                    self._snapshot,
                    status=PaperShadowSessionStatus.STOPPED,
                    as_of_ns=now,
                    stopped_at_ns=now,
                    blockers_seen=blockers,
                    paper_only=True,
                    real_orders_enabled=False,
                    real_money_enabled=False,
                    operator_summary=_operator_summary(
                        PaperShadowSessionStatus.STOPPED,
                        self._snapshot.tick_count,
                        self._snapshot.active_sleeves,
                        blockers,
                    ),
                )
            )
        if guardrail.should_pause_session and self._snapshot.status == PaperShadowSessionStatus.RUNNING:
            now = self._now_ns()
            blockers = _sorted_unique((*self._snapshot.blockers_seen, *guardrail.reason_codes))
            return self._apply_snapshot(
                replace(
                    self._snapshot,
                    status=PaperShadowSessionStatus.BLOCKED,
                    as_of_ns=now,
                    blockers_seen=blockers,
                    paper_only=True,
                    real_orders_enabled=False,
                    real_money_enabled=False,
                    operator_summary=_operator_summary(
                        PaperShadowSessionStatus.BLOCKED,
                        self._snapshot.tick_count,
                        self._snapshot.active_sleeves,
                        blockers,
                    ),
                )
            )
        return self._snapshot

    def stop(self, *, blockers_seen: tuple[str, ...] = ()) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
            raise PaperShadowSessionCorruptError("paper/shadow session can only stop from RUNNING state")
        now = self._now_ns()
        blockers = _sorted_unique((*self._snapshot.blockers_seen, *blockers_seen))
        return self._apply_snapshot(
            replace(
                self._snapshot,
                status=PaperShadowSessionStatus.STOPPED,
                as_of_ns=now,
                stopped_at_ns=now,
                blockers_seen=blockers,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.STOPPED,
                    self._snapshot.tick_count,
                    self._snapshot.active_sleeves,
                    blockers,
                ),
            ),
        )

    def finalize(self) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.STOPPED:
            raise PaperShadowSessionCorruptError("paper/shadow session can only finalize from STOPPED state")
        if self._snapshot.guardrail.block_finalize:
            raise PaperShadowSessionCorruptError("paper/shadow session guardrails block finalize")
        now = self._now_ns()
        return self._apply_snapshot(
            replace(
                self._snapshot,
                status=PaperShadowSessionStatus.FINALIZED,
                as_of_ns=now,
                finalized_at_ns=now,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.FINALIZED,
                    self._snapshot.tick_count,
                    self._snapshot.active_sleeves,
                    self._snapshot.blockers_seen,
                ),
            ),
        )

    def reset(self) -> PaperShadowSessionSnapshot:
        return self._apply_snapshot(
            PaperShadowSessionSnapshot(
                session_id="paper-shadow-session-unprepared",
                status=PaperShadowSessionStatus.CREATED,
                as_of_ns=0,
            )
        )

    def restore(self, snapshot: PaperShadowSessionSnapshot | dict) -> PaperShadowSessionSnapshot:
        restored = (
            snapshot
            if isinstance(snapshot, PaperShadowSessionSnapshot)
            else paper_shadow_session_snapshot_from_dict(snapshot)
        )
        _validate_session_snapshot(restored)
        self._snapshot = restored
        return self._snapshot

    def to_dict(self) -> dict:
        return paper_shadow_session_snapshot_to_dict(self._snapshot)

    def _now_ns(self) -> int:
        now = self._clock_ns()
        if not isinstance(now, int) or isinstance(now, bool) or now < 0:
            raise PaperShadowSessionCorruptError("clock_ns must return a non-negative int")
        return now

    def _apply_snapshot(self, snapshot: PaperShadowSessionSnapshot) -> PaperShadowSessionSnapshot:
        _validate_session_snapshot(snapshot)
        self._snapshot = snapshot
        return self._snapshot

    def _record_rejected_events(self, count: int) -> None:
        if count <= 0:
            count = 1
        rejected_count = self._snapshot.rejected_event_count + count
        guardrail = build_guardrail_snapshot(
            self._snapshot.runtime_monitor,
            session_status=self._snapshot.status,
            rejected_event_count=rejected_count,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
        self._snapshot = replace(
            self._snapshot,
            rejected_event_count=rejected_count,
            guardrail=guardrail,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
        _validate_session_snapshot(self._snapshot)


def paper_shadow_session_snapshot_to_dict(snapshot: PaperShadowSessionSnapshot) -> dict:
    _validate_session_snapshot(snapshot)
    return {
        "session_id": snapshot.session_id,
        "status": snapshot.status.value,
        "as_of_ns": snapshot.as_of_ns,
        "plan_id": snapshot.plan_id,
        "plan_status": snapshot.plan_status,
        "source_manifest_status": snapshot.source_manifest_status,
        "prepared_at_ns": snapshot.prepared_at_ns,
        "started_at_ns": snapshot.started_at_ns,
        "last_tick_at_ns": snapshot.last_tick_at_ns,
        "stopped_at_ns": snapshot.stopped_at_ns,
        "finalized_at_ns": snapshot.finalized_at_ns,
        "tick_count": snapshot.tick_count,
        "active_sleeves_seen": list(snapshot.active_sleeves_seen),
        "blockers_seen": list(snapshot.blockers_seen),
        "event_count": snapshot.event_count,
        "symbols_seen": list(snapshot.symbols_seen),
        "venues_seen": list(snapshot.venues_seen),
        "first_event_ns": snapshot.first_event_ns,
        "last_event_ns": snapshot.last_event_ns,
        "rejected_event_count": snapshot.rejected_event_count,
        "market_event_cursors": [market_event_cursor_to_dict(cursor) for cursor in snapshot.market_event_cursors],
        "runtime_monitor": runtime_monitor_snapshot_to_dict(snapshot.runtime_monitor),
        "guardrail": guardrail_snapshot_to_dict(snapshot.guardrail),
        "paper_only": snapshot.paper_only,
        "real_orders_enabled": snapshot.real_orders_enabled,
        "real_money_enabled": snapshot.real_money_enabled,
        "active_sleeves": list(snapshot.active_sleeves),
        "inactive_sleeves": list(snapshot.inactive_sleeves),
        "admitted_unallocated_sleeves": list(snapshot.admitted_unallocated_sleeves),
        "activation_blockers": list(snapshot.activation_blockers),
        "evidence_blockers": list(snapshot.evidence_blockers),
        "governance_blockers": list(snapshot.governance_blockers),
        "operator_summary": snapshot.operator_summary,
    }


def paper_shadow_session_snapshot_from_dict(data: dict) -> PaperShadowSessionSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow session snapshot must be a dict, got {type(data).__name__!r}"
        )
    status = _session_status_or_default(data.get("status"), PaperShadowSessionStatus.CREATED)
    event_count = _require_non_negative_int(data.get("event_count", 0), "event_count")
    symbols_seen = _sorted_unique(data.get("symbols_seen", ()))
    venues_seen = _sorted_unique(data.get("venues_seen", ()))
    last_event_ns = _optional_non_negative_int(data.get("last_event_ns"), "last_event_ns")
    monitor_value = data.get("runtime_monitor")
    runtime_monitor = (
        runtime_monitor_snapshot_from_dict(_dict_value(monitor_value, "runtime_monitor"))
        if monitor_value is not None
        else build_runtime_monitor_snapshot(
            event_count=event_count,
            monitored_symbols=symbols_seen,
            monitored_venues=venues_seen,
            last_event_ns=last_event_ns,
        )
    )
    rejected_event_count = _require_non_negative_int(data.get("rejected_event_count", 0), "rejected_event_count")
    paper_only = _bool_or_default(data, "paper_only", True)
    real_orders_enabled = _bool_or_default(data, "real_orders_enabled", False)
    real_money_enabled = _bool_or_default(data, "real_money_enabled", False)
    guardrail_value = data.get("guardrail")
    guardrail = (
        guardrail_snapshot_from_dict(_dict_value(guardrail_value, "guardrail"))
        if guardrail_value is not None
        else build_guardrail_snapshot(
            runtime_monitor,
            session_status=status,
            rejected_event_count=rejected_event_count,
            paper_only=paper_only,
            real_orders_enabled=real_orders_enabled,
            real_money_enabled=real_money_enabled,
        )
    )
    snapshot = PaperShadowSessionSnapshot(
        session_id=_string_or_default(data.get("session_id"), "paper-shadow-session-legacy"),
        status=status,
        as_of_ns=_require_non_negative_int(data.get("as_of_ns", 0), "as_of_ns"),
        plan_id=_string_or_default(data.get("plan_id"), "unknown"),
        plan_status=_string_or_default(data.get("plan_status"), "unknown"),
        source_manifest_status=_string_or_default(data.get("source_manifest_status"), "unknown"),
        prepared_at_ns=_optional_non_negative_int(data.get("prepared_at_ns"), "prepared_at_ns"),
        started_at_ns=_optional_non_negative_int(data.get("started_at_ns"), "started_at_ns"),
        last_tick_at_ns=_optional_non_negative_int(data.get("last_tick_at_ns"), "last_tick_at_ns"),
        stopped_at_ns=_optional_non_negative_int(data.get("stopped_at_ns"), "stopped_at_ns"),
        finalized_at_ns=_optional_non_negative_int(data.get("finalized_at_ns"), "finalized_at_ns"),
        tick_count=_require_non_negative_int(data.get("tick_count", 0), "tick_count"),
        active_sleeves_seen=_sorted_unique(data.get("active_sleeves_seen", ())),
        blockers_seen=_sorted_unique(data.get("blockers_seen", ())),
        event_count=event_count,
        symbols_seen=symbols_seen,
        venues_seen=venues_seen,
        first_event_ns=_optional_non_negative_int(data.get("first_event_ns"), "first_event_ns"),
        last_event_ns=last_event_ns,
        rejected_event_count=rejected_event_count,
        market_event_cursors=_market_event_cursors_from_data(data.get("market_event_cursors", ())),
        runtime_monitor=runtime_monitor,
        guardrail=guardrail,
        paper_only=paper_only,
        real_orders_enabled=real_orders_enabled,
        real_money_enabled=real_money_enabled,
        active_sleeves=_sorted_unique(data.get("active_sleeves", ())),
        inactive_sleeves=_sorted_unique(data.get("inactive_sleeves", ())),
        admitted_unallocated_sleeves=_sorted_unique(data.get("admitted_unallocated_sleeves", ())),
        activation_blockers=_sorted_unique(data.get("activation_blockers", ())),
        evidence_blockers=_sorted_unique(data.get("evidence_blockers", ())),
        governance_blockers=_sorted_unique(data.get("governance_blockers", ())),
        operator_summary=_string_or_default(
            data.get("operator_summary"),
            _operator_summary(status, _require_non_negative_int(data.get("tick_count", 0), "tick_count"), (), ()),
        ),
    )
    _validate_session_snapshot(snapshot)
    return snapshot


def build_market_event_batch(
    events: tuple[MarketEvent, ...],
    *,
    batch_id: str | None = None,
) -> MarketEventBatch:
    original = MarketEventBatch(
        batch_id=batch_id or _market_event_batch_id(events),
        events=tuple(events),
    )
    return _normalize_batch(original)


def market_event_to_dict(event: MarketEvent) -> dict:
    _validate_market_event(event)
    return {
        "symbol": event.symbol,
        "venue": event.venue,
        "ts_ns": event.ts_ns,
        "event_type": event.event_type.value,
        "price": event.price,
        "mark_price": event.mark_price,
        "index_price": event.index_price,
        "funding_rate": event.funding_rate,
        "open_interest": event.open_interest,
    }


def market_event_from_dict(data: dict) -> MarketEvent:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Market event must be a dict, got {type(data).__name__!r}")
    event = MarketEvent(
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        ts_ns=_require_non_negative_int(data.get("ts_ns"), "ts_ns"),
        event_type=_market_event_type_from_value(data.get("event_type")),
        price=_optional_non_negative_float(data.get("price"), "price"),
        mark_price=_optional_non_negative_float(data.get("mark_price"), "mark_price"),
        index_price=_optional_non_negative_float(data.get("index_price"), "index_price"),
        funding_rate=_optional_float(data.get("funding_rate"), "funding_rate"),
        open_interest=_optional_non_negative_float(data.get("open_interest"), "open_interest"),
    )
    _validate_market_event(event)
    return event


def market_event_batch_to_dict(batch: MarketEventBatch) -> dict:
    normalized = _normalize_batch(batch)
    return {
        "batch_id": normalized.batch_id,
        "events": [market_event_to_dict(event) for event in normalized.events],
    }


def market_event_batch_from_dict(data: dict) -> MarketEventBatch:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Market event batch must be a dict, got {type(data).__name__!r}")
    events_value = data.get("events")
    if not isinstance(events_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("Market event batch field 'events' must be a list/tuple")
    events = tuple(market_event_from_dict(_dict_value(item, "events")) for item in events_value)
    return build_market_event_batch(
        events,
        batch_id=_string_or_default(data.get("batch_id"), _market_event_batch_id(events)),
    )


def market_event_cursor_to_dict(cursor: MarketEventCursor) -> dict:
    _validate_market_event_cursor(cursor)
    return {
        "symbol": cursor.symbol,
        "venue": cursor.venue,
        "last_event_ns": cursor.last_event_ns,
    }


def market_event_cursor_from_dict(data: dict) -> MarketEventCursor:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Market event cursor must be a dict, got {type(data).__name__!r}")
    cursor = MarketEventCursor(
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        last_event_ns=_require_non_negative_int(data.get("last_event_ns"), "last_event_ns"),
    )
    _validate_market_event_cursor(cursor)
    return cursor


def build_runtime_monitor_snapshot(
    *,
    event_count: int,
    monitored_symbols: tuple[str, ...],
    monitored_venues: tuple[str, ...],
    required_symbols: tuple[str, ...] = (),
    required_venues: tuple[str, ...] = (),
    price_validity_ok: bool | None = None,
    event_gap_count: int = 0,
    last_event_ns: int | None = None,
) -> RuntimeMonitorSnapshot:
    event_count = _require_non_negative_int(event_count, "event_count")
    monitored_symbols = _sorted_unique(monitored_symbols)
    monitored_venues = _sorted_unique(monitored_venues)
    required_symbols = _sorted_unique(required_symbols)
    required_venues = _sorted_unique(required_venues)
    event_gap_count = _require_non_negative_int(event_gap_count, "event_gap_count")
    last_event_ns = _optional_non_negative_int(last_event_ns, "last_event_ns")
    has_events = event_count > 0
    resolved_price_validity_ok = (
        has_events
        if price_validity_ok is None
        else _require_bool(
            price_validity_ok,
            "price_validity_ok",
        )
    )
    symbol_coverage_ok = has_events and (
        bool(monitored_symbols) if not required_symbols else set(required_symbols).issubset(set(monitored_symbols))
    )
    venue_coverage_ok = has_events and (
        bool(monitored_venues) if not required_venues else set(required_venues).issubset(set(monitored_venues))
    )
    stale_feed_detected = event_gap_count > 0
    reason_codes = _runtime_monitor_reason_codes(
        has_events=has_events,
        stale_feed_detected=stale_feed_detected,
        symbol_coverage_ok=symbol_coverage_ok,
        venue_coverage_ok=venue_coverage_ok,
        price_validity_ok=resolved_price_validity_ok,
    )
    if not has_events:
        status = RuntimeMonitorStatus.NOT_READY
    elif reason_codes:
        status = RuntimeMonitorStatus.DEGRADED
    else:
        status = RuntimeMonitorStatus.HEALTHY
    monitor = RuntimeMonitorSnapshot(
        status=status,
        event_count=event_count,
        stale_feed_detected=stale_feed_detected,
        symbol_coverage_ok=symbol_coverage_ok,
        venue_coverage_ok=venue_coverage_ok,
        price_validity_ok=resolved_price_validity_ok,
        event_gap_count=event_gap_count,
        last_event_ns=last_event_ns,
        monitored_symbols=monitored_symbols,
        monitored_venues=monitored_venues,
        required_symbols=required_symbols,
        required_venues=required_venues,
        reason_codes=reason_codes,
    )
    _validate_runtime_monitor_snapshot(monitor)
    return monitor


def runtime_monitor_snapshot_to_dict(monitor: RuntimeMonitorSnapshot) -> dict:
    _validate_runtime_monitor_snapshot(monitor)
    return {
        "status": monitor.status.value,
        "event_count": monitor.event_count,
        "stale_feed_detected": monitor.stale_feed_detected,
        "symbol_coverage_ok": monitor.symbol_coverage_ok,
        "venue_coverage_ok": monitor.venue_coverage_ok,
        "price_validity_ok": monitor.price_validity_ok,
        "event_gap_count": monitor.event_gap_count,
        "last_event_ns": monitor.last_event_ns,
        "monitored_symbols": list(monitor.monitored_symbols),
        "monitored_venues": list(monitor.monitored_venues),
        "required_symbols": list(monitor.required_symbols),
        "required_venues": list(monitor.required_venues),
        "reason_codes": list(monitor.reason_codes),
    }


def runtime_monitor_snapshot_from_dict(data: dict) -> RuntimeMonitorSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Runtime monitor must be a dict, got {type(data).__name__!r}")
    monitor = RuntimeMonitorSnapshot(
        status=_runtime_monitor_status_from_value(data.get("status")),
        event_count=_require_non_negative_int(data.get("event_count", 0), "event_count"),
        stale_feed_detected=_bool_or_default(data, "stale_feed_detected", False),
        symbol_coverage_ok=_bool_or_default(data, "symbol_coverage_ok", False),
        venue_coverage_ok=_bool_or_default(data, "venue_coverage_ok", False),
        price_validity_ok=_bool_or_default(data, "price_validity_ok", False),
        event_gap_count=_require_non_negative_int(data.get("event_gap_count", 0), "event_gap_count"),
        last_event_ns=_optional_non_negative_int(data.get("last_event_ns"), "last_event_ns"),
        monitored_symbols=_sorted_unique(data.get("monitored_symbols", ())),
        monitored_venues=_sorted_unique(data.get("monitored_venues", ())),
        required_symbols=_sorted_unique(data.get("required_symbols", ())),
        required_venues=_sorted_unique(data.get("required_venues", ())),
        reason_codes=_sorted_unique(data.get("reason_codes", ())),
    )
    _validate_runtime_monitor_snapshot(monitor)
    return monitor


def build_guardrail_snapshot(
    monitor: RuntimeMonitorSnapshot,
    *,
    session_status: PaperShadowSessionStatus,
    rejected_event_count: int = 0,
    paper_only: bool = True,
    real_orders_enabled: bool = False,
    real_money_enabled: bool = False,
) -> GuardrailSnapshot:
    _validate_runtime_monitor_snapshot(monitor)
    if not isinstance(session_status, PaperShadowSessionStatus):
        raise PaperShadowSessionCorruptError("guardrail session_status must be a PaperShadowSessionStatus")
    rejected_event_count = _require_non_negative_int(rejected_event_count, "rejected_event_count")
    paper_only = _require_bool(paper_only, "paper_only")
    real_orders_enabled = _require_bool(real_orders_enabled, "real_orders_enabled")
    real_money_enabled = _require_bool(real_money_enabled, "real_money_enabled")
    reasons: list[str] = []
    actions: list[GuardrailAction] = []
    if not paper_only or real_orders_enabled or real_money_enabled:
        reasons.append("unsafe_real_trading_flags")
        actions.extend((GuardrailAction.STOP_SESSION, GuardrailAction.BLOCK_FINALIZE))
    has_events = monitor.event_count > 0
    if not has_events:
        reasons.append("no_market_events")
        actions.extend((GuardrailAction.WARN, GuardrailAction.BLOCK_FINALIZE))
    if has_events and monitor.stale_feed_detected:
        reasons.append("stale_feed_detected")
        actions.extend((GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if has_events and not monitor.symbol_coverage_ok:
        reasons.append("missing_symbol_coverage")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if has_events and not monitor.venue_coverage_ok:
        reasons.append("missing_venue_coverage")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if has_events and not monitor.price_validity_ok:
        reasons.append("price_validity_failed")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if rejected_event_count > 0:
        reasons.append("rejected_market_events")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if not actions:
        actions.append(GuardrailAction.NONE)
    resolved_actions = _sorted_unique_actions(actions)
    primary_action = _primary_guardrail_action(resolved_actions)
    guardrail = GuardrailSnapshot(
        primary_action=primary_action,
        actions=resolved_actions,
        reason_codes=_sorted_unique(reasons),
        monitor_status=monitor.status,
        block_finalize=GuardrailAction.BLOCK_FINALIZE in resolved_actions,
        should_pause_session=GuardrailAction.PAUSE_SESSION in resolved_actions,
        should_stop_session=GuardrailAction.STOP_SESSION in resolved_actions,
        real_orders_enabled=real_orders_enabled,
        real_money_enabled=real_money_enabled,
        paper_only=paper_only,
    )
    _validate_guardrail_snapshot(guardrail)
    return guardrail


def guardrail_snapshot_to_dict(guardrail: GuardrailSnapshot) -> dict:
    _validate_guardrail_snapshot(guardrail)
    return {
        "primary_action": guardrail.primary_action.value,
        "actions": [action.value for action in guardrail.actions],
        "reason_codes": list(guardrail.reason_codes),
        "monitor_status": guardrail.monitor_status.value,
        "block_finalize": guardrail.block_finalize,
        "should_pause_session": guardrail.should_pause_session,
        "should_stop_session": guardrail.should_stop_session,
        "real_orders_enabled": guardrail.real_orders_enabled,
        "real_money_enabled": guardrail.real_money_enabled,
        "paper_only": guardrail.paper_only,
    }


def guardrail_snapshot_from_dict(data: dict) -> GuardrailSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Guardrail snapshot must be a dict, got {type(data).__name__!r}")
    actions = _guardrail_actions_from_data(data.get("actions", ()))
    primary_action = _guardrail_action_from_value(data.get("primary_action", _primary_guardrail_action(actions).value))
    guardrail = GuardrailSnapshot(
        primary_action=primary_action,
        actions=actions,
        reason_codes=_sorted_unique(data.get("reason_codes", ())),
        monitor_status=_runtime_monitor_status_from_value(data.get("monitor_status")),
        block_finalize=_bool_or_default(data, "block_finalize", GuardrailAction.BLOCK_FINALIZE in actions),
        should_pause_session=_bool_or_default(data, "should_pause_session", GuardrailAction.PAUSE_SESSION in actions),
        should_stop_session=_bool_or_default(data, "should_stop_session", GuardrailAction.STOP_SESSION in actions),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        paper_only=_bool_or_default(data, "paper_only", True),
    )
    _validate_guardrail_snapshot(guardrail)
    return guardrail


def _validate_activation_plan_for_session(plan: PaperShadowActivationPlan) -> None:
    try:
        paper_shadow_activation_plan_to_dict(plan)
    except SleeveAdmissionCorruptError as exc:
        raise PaperShadowSessionCorruptError(str(exc)) from exc
    if not plan.paper_only or plan.real_orders_enabled or plan.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper/shadow session plan contains unsafe real-trading flags")


def _validate_session_snapshot(snapshot: PaperShadowSessionSnapshot) -> None:
    if not isinstance(snapshot, PaperShadowSessionSnapshot):
        raise PaperShadowSessionCorruptError("paper/shadow session snapshot must be a PaperShadowSessionSnapshot")
    if not isinstance(snapshot.session_id, str) or not snapshot.session_id:
        raise PaperShadowSessionCorruptError("paper/shadow session_id must be a non-empty string")
    if not isinstance(snapshot.status, PaperShadowSessionStatus):
        raise PaperShadowSessionCorruptError("paper/shadow session status must be a PaperShadowSessionStatus")
    if not isinstance(snapshot.as_of_ns, int) or isinstance(snapshot.as_of_ns, bool) or snapshot.as_of_ns < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session as_of_ns must be a non-negative int")
    if snapshot.prepared_at_ns is not None and snapshot.as_of_ns < snapshot.prepared_at_ns:
        raise PaperShadowSessionCorruptError("paper/shadow session as_of_ns cannot predate prepare")
    for field_name in (
        "active_sleeves_seen",
        "blockers_seen",
        "symbols_seen",
        "venues_seen",
        "active_sleeves",
        "inactive_sleeves",
        "admitted_unallocated_sleeves",
        "activation_blockers",
        "evidence_blockers",
        "governance_blockers",
    ):
        value = getattr(snapshot, field_name)
        if value != _sorted_unique(value):
            raise PaperShadowSessionCorruptError(f"paper/shadow session {field_name} must be sorted unique strings")
    if not snapshot.paper_only:
        raise PaperShadowSessionCorruptError("paper/shadow session must remain paper_only")
    if snapshot.real_orders_enabled:
        raise PaperShadowSessionCorruptError("paper/shadow session cannot enable real orders")
    if snapshot.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper/shadow session cannot enable real money")
    if snapshot.tick_count < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session tick_count cannot be negative")
    if snapshot.tick_count > 0 and snapshot.last_tick_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow session ticks require last_tick_at_ns")
    if snapshot.event_count < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session event_count cannot be negative")
    if snapshot.rejected_event_count < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session rejected_event_count cannot be negative")
    if snapshot.event_count > 0:
        if snapshot.first_event_ns is None or snapshot.last_event_ns is None:
            raise PaperShadowSessionCorruptError("paper/shadow session events require first/last event timestamps")
        if snapshot.first_event_ns > snapshot.last_event_ns:
            raise PaperShadowSessionCorruptError(
                "paper/shadow first event timestamp cannot exceed last event timestamp"
            )
        if not snapshot.symbols_seen or not snapshot.venues_seen:
            raise PaperShadowSessionCorruptError("paper/shadow session events require symbol and venue counters")
    if snapshot.event_count == 0 and (snapshot.first_event_ns is not None or snapshot.last_event_ns is not None):
        raise PaperShadowSessionCorruptError("paper/shadow session without events cannot carry event timestamps")
    for cursor in snapshot.market_event_cursors:
        _validate_market_event_cursor(cursor)
    cursor_pairs = tuple((cursor.symbol, cursor.venue) for cursor in snapshot.market_event_cursors)
    if cursor_pairs != tuple(sorted(cursor_pairs)) or len(cursor_pairs) != len(set(cursor_pairs)):
        raise PaperShadowSessionCorruptError("paper/shadow session market event cursors must be sorted unique")
    _validate_runtime_monitor_snapshot(snapshot.runtime_monitor)
    if snapshot.runtime_monitor.event_count != snapshot.event_count:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor event_count must match session")
    if snapshot.runtime_monitor.monitored_symbols != snapshot.symbols_seen:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor symbols must match session")
    if snapshot.runtime_monitor.monitored_venues != snapshot.venues_seen:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor venues must match session")
    if snapshot.runtime_monitor.last_event_ns != snapshot.last_event_ns:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor last_event_ns must match session")
    _validate_guardrail_snapshot(snapshot.guardrail)
    expected_guardrail = build_guardrail_snapshot(
        snapshot.runtime_monitor,
        session_status=snapshot.status,
        rejected_event_count=snapshot.rejected_event_count,
        paper_only=snapshot.paper_only,
        real_orders_enabled=snapshot.real_orders_enabled,
        real_money_enabled=snapshot.real_money_enabled,
    )
    if snapshot.guardrail != expected_guardrail:
        raise PaperShadowSessionCorruptError("paper/shadow guardrail snapshot does not match session truth")
    if set(snapshot.active_sleeves) & set(snapshot.inactive_sleeves):
        raise PaperShadowSessionCorruptError("paper/shadow session active and inactive sleeves overlap")
    if not set(snapshot.active_sleeves_seen).issubset(set(snapshot.active_sleeves)):
        raise PaperShadowSessionCorruptError("paper/shadow session saw sleeves outside the active manifest set")
    if snapshot.status == PaperShadowSessionStatus.READY and snapshot.prepared_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow READY session requires prepared_at_ns")
    if snapshot.status == PaperShadowSessionStatus.RUNNING and snapshot.started_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow RUNNING session requires started_at_ns")
    if snapshot.status == PaperShadowSessionStatus.STOPPED and snapshot.stopped_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow STOPPED session requires stopped_at_ns")
    if snapshot.status == PaperShadowSessionStatus.FINALIZED:
        if snapshot.stopped_at_ns is None or snapshot.finalized_at_ns is None:
            raise PaperShadowSessionCorruptError("paper/shadow FINALIZED session requires stop and finalize timestamps")
    if snapshot.status == PaperShadowSessionStatus.BLOCKED and not snapshot.blockers_seen:
        raise PaperShadowSessionCorruptError("paper/shadow BLOCKED session requires blockers")
    if (
        snapshot.status
        in {
            PaperShadowSessionStatus.RUNNING,
            PaperShadowSessionStatus.STOPPED,
            PaperShadowSessionStatus.FINALIZED,
        }
        and snapshot.prepared_at_ns is None
    ):
        raise PaperShadowSessionCorruptError("paper/shadow active lifecycle states require prepared_at_ns")
    if (
        snapshot.status
        in {
            PaperShadowSessionStatus.RUNNING,
            PaperShadowSessionStatus.STOPPED,
            PaperShadowSessionStatus.FINALIZED,
        }
        and snapshot.started_at_ns is None
    ):
        raise PaperShadowSessionCorruptError("paper/shadow active lifecycle states require started_at_ns")
    if snapshot.prepared_at_ns is not None and snapshot.started_at_ns is not None:
        if snapshot.started_at_ns < snapshot.prepared_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session start cannot predate prepare")
    if snapshot.started_at_ns is not None and snapshot.last_tick_at_ns is not None:
        if snapshot.last_tick_at_ns < snapshot.started_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session tick cannot predate start")
    if snapshot.started_at_ns is not None and snapshot.stopped_at_ns is not None:
        if snapshot.stopped_at_ns < snapshot.started_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session stop cannot predate start")
    if snapshot.last_tick_at_ns is not None and snapshot.stopped_at_ns is not None:
        if snapshot.stopped_at_ns < snapshot.last_tick_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session stop cannot predate latest tick")
    if snapshot.stopped_at_ns is not None and snapshot.finalized_at_ns is not None:
        if snapshot.finalized_at_ns < snapshot.stopped_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session finalize cannot predate stop")


def _operator_summary(
    status: PaperShadowSessionStatus,
    tick_count: int,
    active_sleeves: tuple[str, ...],
    blockers: tuple[str, ...],
) -> str:
    return f"session_status={status.value}; ticks={tick_count}; active={len(active_sleeves)}; blockers={len(blockers)}"


def _session_id_for_plan(plan: PaperShadowActivationPlan) -> str:
    return f"paper-shadow-session-{plan.plan_id}"


def _normalize_batch(batch: MarketEventBatch) -> MarketEventBatch:
    _validate_market_event_batch(batch)
    return MarketEventBatch(
        batch_id=batch.batch_id,
        events=tuple(sorted(batch.events, key=_market_event_sort_key)),
    )


def _validate_market_event_batch(batch: MarketEventBatch) -> None:
    if not isinstance(batch, MarketEventBatch):
        raise PaperShadowSessionCorruptError("market event batch must be a MarketEventBatch")
    if not isinstance(batch.batch_id, str) or not batch.batch_id:
        raise PaperShadowSessionCorruptError("market event batch_id must be a non-empty string")
    if not isinstance(batch.events, tuple):
        raise PaperShadowSessionCorruptError("market event batch events must be a tuple")
    if not batch.events:
        raise PaperShadowSessionCorruptError("market event batch must contain at least one event")
    last_by_pair: dict[tuple[str, str], int] = {}
    for event in batch.events:
        _validate_market_event(event)
        pair = (event.symbol, event.venue)
        previous = last_by_pair.get(pair)
        if previous is not None and event.ts_ns < previous:
            raise PaperShadowSessionCorruptError("market event batch timestamps must be monotonic per symbol/venue")
        last_by_pair[pair] = event.ts_ns


def _validate_market_event(event: MarketEvent) -> None:
    if not isinstance(event, MarketEvent):
        raise PaperShadowSessionCorruptError("market event must be a MarketEvent")
    _require_non_empty_str(event.symbol, "symbol")
    _require_non_empty_str(event.venue, "venue")
    _require_non_negative_int(event.ts_ns, "ts_ns")
    if not isinstance(event.event_type, MarketEventType):
        raise PaperShadowSessionCorruptError("market event_type must be a MarketEventType")
    _optional_non_negative_float(event.price, "price")
    _optional_non_negative_float(event.mark_price, "mark_price")
    _optional_non_negative_float(event.index_price, "index_price")
    _optional_float(event.funding_rate, "funding_rate")
    _optional_non_negative_float(event.open_interest, "open_interest")
    if all(
        value is None
        for value in (
            event.price,
            event.mark_price,
            event.index_price,
            event.funding_rate,
            event.open_interest,
        )
    ):
        raise PaperShadowSessionCorruptError("market event must carry at least one market field")


def _validate_batch_against_session(snapshot: PaperShadowSessionSnapshot, batch: MarketEventBatch) -> None:
    cursor_lookup = {(cursor.symbol, cursor.venue): cursor.last_event_ns for cursor in snapshot.market_event_cursors}
    for event in batch.events:
        previous = cursor_lookup.get((event.symbol, event.venue))
        if previous is not None and event.ts_ns < previous:
            raise PaperShadowSessionCorruptError("market event timestamp regressed from session cursor")


def _merge_market_event_cursors(
    cursors: tuple[MarketEventCursor, ...],
    events: tuple[MarketEvent, ...],
) -> tuple[MarketEventCursor, ...]:
    latest = {(cursor.symbol, cursor.venue): cursor.last_event_ns for cursor in cursors}
    for event in events:
        pair = (event.symbol, event.venue)
        latest[pair] = max(latest.get(pair, event.ts_ns), event.ts_ns)
    return tuple(
        MarketEventCursor(symbol=symbol, venue=venue, last_event_ns=ts_ns)
        for (symbol, venue), ts_ns in sorted(latest.items())
    )


def _market_event_gap_count(
    cursors: tuple[MarketEventCursor, ...],
    events: tuple[MarketEvent, ...],
    max_gap_ns: int | None,
) -> int:
    if max_gap_ns is None:
        return 0
    max_gap_ns = _require_non_negative_int(max_gap_ns, "max_market_event_gap_ns")
    grouped: dict[tuple[str, str], list[int]] = {}
    for cursor in cursors:
        grouped.setdefault((cursor.symbol, cursor.venue), []).append(cursor.last_event_ns)
    for event in events:
        grouped.setdefault((event.symbol, event.venue), []).append(event.ts_ns)
    gap_count = 0
    for timestamps in grouped.values():
        ordered = sorted(timestamps)
        for previous, current in zip(ordered, ordered[1:]):
            if current - previous > max_gap_ns:
                gap_count += 1
    return gap_count


def _market_event_cursors_from_data(value: object) -> tuple[MarketEventCursor, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperShadowSessionCorruptError("market event cursors must be a list/tuple")
    cursors = tuple(market_event_cursor_from_dict(_dict_value(item, "market_event_cursors")) for item in value)
    for cursor in cursors:
        _validate_market_event_cursor(cursor)
    pairs = tuple((cursor.symbol, cursor.venue) for cursor in cursors)
    if pairs != tuple(sorted(pairs)) or len(pairs) != len(set(pairs)):
        raise PaperShadowSessionCorruptError("market event cursors must be sorted unique")
    return cursors


def _validate_market_event_cursor(cursor: MarketEventCursor) -> None:
    if not isinstance(cursor, MarketEventCursor):
        raise PaperShadowSessionCorruptError("market event cursor must be a MarketEventCursor")
    _require_non_empty_str(cursor.symbol, "symbol")
    _require_non_empty_str(cursor.venue, "venue")
    _require_non_negative_int(cursor.last_event_ns, "last_event_ns")


def _validate_runtime_monitor_snapshot(monitor: RuntimeMonitorSnapshot) -> None:
    if not isinstance(monitor, RuntimeMonitorSnapshot):
        raise PaperShadowSessionCorruptError("runtime monitor must be a RuntimeMonitorSnapshot")
    if not isinstance(monitor.status, RuntimeMonitorStatus):
        raise PaperShadowSessionCorruptError("runtime monitor status must be a RuntimeMonitorStatus")
    _require_non_negative_int(monitor.event_count, "event_count")
    _require_bool(monitor.stale_feed_detected, "stale_feed_detected")
    _require_bool(monitor.symbol_coverage_ok, "symbol_coverage_ok")
    _require_bool(monitor.venue_coverage_ok, "venue_coverage_ok")
    _require_bool(monitor.price_validity_ok, "price_validity_ok")
    _require_non_negative_int(monitor.event_gap_count, "event_gap_count")
    _optional_non_negative_int(monitor.last_event_ns, "last_event_ns")
    if monitor.monitored_symbols != _sorted_unique(monitor.monitored_symbols):
        raise PaperShadowSessionCorruptError("runtime monitor symbols must be sorted unique")
    if monitor.monitored_venues != _sorted_unique(monitor.monitored_venues):
        raise PaperShadowSessionCorruptError("runtime monitor venues must be sorted unique")
    if monitor.required_symbols != _sorted_unique(monitor.required_symbols):
        raise PaperShadowSessionCorruptError("runtime monitor required symbols must be sorted unique")
    if monitor.required_venues != _sorted_unique(monitor.required_venues):
        raise PaperShadowSessionCorruptError("runtime monitor required venues must be sorted unique")
    if monitor.reason_codes != _sorted_unique(monitor.reason_codes):
        raise PaperShadowSessionCorruptError("runtime monitor reason codes must be sorted unique")
    if monitor.event_count == 0:
        if monitor.status == RuntimeMonitorStatus.HEALTHY:
            raise PaperShadowSessionCorruptError("runtime monitor cannot be healthy without events")
        if monitor.last_event_ns is not None:
            raise PaperShadowSessionCorruptError("runtime monitor without events cannot carry last_event_ns")
        if monitor.symbol_coverage_ok or monitor.venue_coverage_ok or monitor.price_validity_ok:
            raise PaperShadowSessionCorruptError("runtime monitor without events cannot report healthy checks")
    if monitor.event_count > 0 and monitor.last_event_ns is None:
        raise PaperShadowSessionCorruptError("runtime monitor with events requires last_event_ns")
    if monitor.stale_feed_detected != (monitor.event_gap_count > 0):
        raise PaperShadowSessionCorruptError("runtime monitor stale flag must match event gaps")
    if monitor.status == RuntimeMonitorStatus.HEALTHY and monitor.reason_codes:
        raise PaperShadowSessionCorruptError("runtime monitor healthy state cannot carry reason codes")
    if monitor.status == RuntimeMonitorStatus.HEALTHY and (
        monitor.stale_feed_detected
        or not monitor.symbol_coverage_ok
        or not monitor.venue_coverage_ok
        or not monitor.price_validity_ok
    ):
        raise PaperShadowSessionCorruptError("runtime monitor healthy state requires all checks ok")
    expected_status = (
        RuntimeMonitorStatus.NOT_READY
        if monitor.event_count == 0
        else RuntimeMonitorStatus.DEGRADED
        if monitor.reason_codes
        else RuntimeMonitorStatus.HEALTHY
    )
    if monitor.status != expected_status:
        raise PaperShadowSessionCorruptError("runtime monitor status does not match checks")


def _validate_guardrail_snapshot(guardrail: GuardrailSnapshot) -> None:
    if not isinstance(guardrail, GuardrailSnapshot):
        raise PaperShadowSessionCorruptError("guardrail snapshot must be a GuardrailSnapshot")
    if not isinstance(guardrail.primary_action, GuardrailAction):
        raise PaperShadowSessionCorruptError("guardrail primary_action must be a GuardrailAction")
    if not guardrail.actions:
        raise PaperShadowSessionCorruptError("guardrail actions cannot be empty")
    if guardrail.actions != _sorted_unique_actions(guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail actions must be sorted unique")
    if guardrail.primary_action != _primary_guardrail_action(guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail primary_action does not match actions")
    if guardrail.reason_codes != _sorted_unique(guardrail.reason_codes):
        raise PaperShadowSessionCorruptError("guardrail reason codes must be sorted unique")
    if not isinstance(guardrail.monitor_status, RuntimeMonitorStatus):
        raise PaperShadowSessionCorruptError("guardrail monitor_status must be a RuntimeMonitorStatus")
    if guardrail.block_finalize != (GuardrailAction.BLOCK_FINALIZE in guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail block_finalize flag does not match actions")
    if guardrail.should_pause_session != (GuardrailAction.PAUSE_SESSION in guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail pause flag does not match actions")
    if guardrail.should_stop_session != (GuardrailAction.STOP_SESSION in guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail stop flag does not match actions")
    _require_bool(guardrail.paper_only, "paper_only")
    _require_bool(guardrail.real_orders_enabled, "real_orders_enabled")
    _require_bool(guardrail.real_money_enabled, "real_money_enabled")
    if GuardrailAction.NONE in guardrail.actions and guardrail.actions != (GuardrailAction.NONE,):
        raise PaperShadowSessionCorruptError("guardrail NONE action cannot be combined with other actions")
    if guardrail.actions == (GuardrailAction.NONE,) and guardrail.reason_codes:
        raise PaperShadowSessionCorruptError("guardrail NONE action cannot carry reason codes")
    if (not guardrail.paper_only or guardrail.real_orders_enabled or guardrail.real_money_enabled) and (
        GuardrailAction.STOP_SESSION not in guardrail.actions or GuardrailAction.BLOCK_FINALIZE not in guardrail.actions
    ):
        raise PaperShadowSessionCorruptError("guardrail unsafe real-trading flags require stop and block actions")
    if guardrail.monitor_status != RuntimeMonitorStatus.HEALTHY and GuardrailAction.NONE in guardrail.actions:
        raise PaperShadowSessionCorruptError("guardrail cannot be NONE with unhealthy monitor")


def _runtime_monitor_reason_codes(
    *,
    has_events: bool,
    stale_feed_detected: bool,
    symbol_coverage_ok: bool,
    venue_coverage_ok: bool,
    price_validity_ok: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not has_events:
        reasons.append("no_market_events")
    if stale_feed_detected:
        reasons.append("stale_feed_detected")
    if not symbol_coverage_ok:
        reasons.append("missing_symbol_coverage")
    if not venue_coverage_ok:
        reasons.append("missing_venue_coverage")
    if not price_validity_ok:
        reasons.append("price_validity_failed")
    return _sorted_unique(reasons)


def _runtime_monitor_status_from_value(value: object) -> RuntimeMonitorStatus:
    if isinstance(value, RuntimeMonitorStatus):
        return value
    if value is None:
        return RuntimeMonitorStatus.NOT_READY
    try:
        return RuntimeMonitorStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid runtime monitor status: {value!r}") from exc


def _guardrail_action_from_value(value: object) -> GuardrailAction:
    if isinstance(value, GuardrailAction):
        return value
    try:
        return GuardrailAction(_require_non_empty_str(value, "guardrail_action"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid guardrail action: {value!r}") from exc


def _guardrail_actions_from_data(value: object) -> tuple[GuardrailAction, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperShadowSessionCorruptError("guardrail actions must be a list/tuple")
    return _sorted_unique_actions(tuple(_guardrail_action_from_value(item) for item in value))


def _sorted_unique_actions(actions: tuple[GuardrailAction, ...] | list[GuardrailAction]) -> tuple[GuardrailAction, ...]:
    if not isinstance(actions, (list, tuple)):
        raise PaperShadowSessionCorruptError("guardrail actions must be a list/tuple")
    seen: list[GuardrailAction] = []
    for action in actions:
        if not isinstance(action, GuardrailAction):
            raise PaperShadowSessionCorruptError("guardrail actions must be GuardrailAction values")
        if action not in seen:
            seen.append(action)
    order = {
        GuardrailAction.STOP_SESSION: 0,
        GuardrailAction.PAUSE_SESSION: 1,
        GuardrailAction.BLOCK_FINALIZE: 2,
        GuardrailAction.WARN: 3,
        GuardrailAction.NONE: 4,
    }
    return tuple(sorted(seen, key=lambda item: order[item]))


def _primary_guardrail_action(actions: tuple[GuardrailAction, ...]) -> GuardrailAction:
    ordered = _sorted_unique_actions(actions)
    if not ordered:
        raise PaperShadowSessionCorruptError("guardrail actions cannot be empty")
    return ordered[0]


def _market_event_batch_id(events: tuple[MarketEvent, ...]) -> str:
    if not events:
        return "market-event-batch-empty"
    ordered = tuple(sorted(events, key=_market_event_sort_key))
    first_ts = ordered[0].ts_ns
    last_ts = ordered[-1].ts_ns
    return f"market-event-batch-{first_ts}-{last_ts}-{len(ordered)}"


def _market_event_sort_key(event: MarketEvent) -> tuple[int, str, str, str]:
    return (event.ts_ns, event.symbol, event.venue, event.event_type.value)


def _market_event_type_from_value(value: object) -> MarketEventType:
    if isinstance(value, MarketEventType):
        return value
    try:
        return MarketEventType(_require_non_empty_str(value, "event_type"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid market event_type: {value!r}") from exc


def _rejected_event_increment(batch: object) -> int:
    if isinstance(batch, MarketEventBatch):
        return max(1, len(batch.events))
    if isinstance(batch, dict):
        events = batch.get("events")
        if isinstance(events, (list, tuple)):
            return max(1, len(events))
    return 1


def _optional_non_negative_float(value: object, field_name: str) -> float | None:
    parsed = _optional_float(value, field_name)
    if parsed is not None and parsed < 0.0:
        raise PaperShadowSessionCorruptError(f"market event field {field_name!r} cannot be negative")
    return parsed


def _optional_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PaperShadowSessionCorruptError(f"market event field {field_name!r} must be numeric or None")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise PaperShadowSessionCorruptError(f"market event field {field_name!r} must be finite")
    return parsed


def _session_status_or_default(value: object, default: PaperShadowSessionStatus) -> PaperShadowSessionStatus:
    if value is None:
        return default
    if isinstance(value, PaperShadowSessionStatus):
        return value
    try:
        return PaperShadowSessionStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper/shadow session status: {value!r}") from exc


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PaperShadowSessionCorruptError(f"paper/shadow session field {field_name!r} must be a non-empty string")
    return value


def _string_or_default(value: object, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise PaperShadowSessionCorruptError("paper/shadow session string fields must be strings")
    return value or default


def _require_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PaperShadowSessionCorruptError(f"paper/shadow session field {field_name!r} must be a non-negative int")
    return value


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_non_negative_int(value, field_name)


def _bool_or_default(data: dict, field_name: str, default: bool) -> bool:
    value = data.get(field_name, default)
    return _require_bool(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PaperShadowSessionCorruptError(f"paper/shadow session field {field_name!r} must be bool")
    return value


def _dict_value(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise PaperShadowSessionCorruptError(f"{field_name} must contain dict entries")
    return dict(value)


def _sorted_unique(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper/shadow session string collections must be list/tuple")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise PaperShadowSessionCorruptError("paper/shadow session string collections require non-empty strings")
        if value not in result:
            result.append(value)
    return tuple(sorted(result))
