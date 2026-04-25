"""Paper/shadow session controller - Phase 15M.

Deterministic lifecycle surface for paper/shadow activation plans.

Design rules:
  - Session lifecycle only: prepare/start/tick/stop/finalize/reset/restore.
  - No execution wiring, order routing, alpha, ranking, or allocation logic.
  - Fail closed on missing readiness, malformed restore, or unsafe real-trading flags.
  - PAPER/SHADOW ONLY.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
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
        snapshot: PaperShadowSessionSnapshot | None = None,
    ) -> None:
        self._clock_ns = time.time_ns if clock_ns is None else clock_ns
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
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
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
    if not isinstance(value, bool):
        raise PaperShadowSessionCorruptError(f"paper/shadow session field {field_name!r} must be bool")
    return value


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
