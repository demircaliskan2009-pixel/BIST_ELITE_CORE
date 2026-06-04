"""Paper governor lifecycle current-state view — Phase 16H.

Summarizes the append-only governor ledger chain (a ``PortfolioGovernorLedgerStore`` or an ordered
tuple of ``PortfolioGovernorLedgerEntry``) into a deterministic, immutable **current-state** view for
paper-governor audit / readiness: the current active vs blocked plan states (latest entry per plan,
**with their blockers**), the current total active paper weight/notional, and a sorted blocker summary.

This is the smallest bounded extension over the replay layer: it **reuses**
``replay_portfolio_governor_ledger`` for chain validation and base metrics (head digest, counts,
totals) — no append/store/sizing logic is duplicated — and adds only the lifecycle dimension the
replay snapshot omits (per-plan blockers + active/blocked split + blocker summary). No orders, live
routes, controller wiring, persistence, scheduler, or venue.

Design rules:
  - Reuse, don't duplicate: chain validation + base metrics come from the replay layer; this view
    re-derives nothing about sizing or the append chain.
  - Current state = latest entry per plan (consistent with the replay's per-plan counts/totals).
  - Fail closed: a malformed source or a broken/tampered chain is rejected through replay validation
    (``PortfolioGovernorLedgerReplayError``); nothing defaults permissive.
  - Deterministic + immutable: identical input yields an identical view (including ``lifecycle_digest``).
  - PAPER ONLY: no order intent, live route, venue execution, scheduler, or execution field.

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16H.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from crypto_core.audit.portfolio_governor_ledger import (
    PortfolioGovernorLedgerEntry,
    PortfolioGovernorLedgerStatus,
)
from crypto_core.audit.portfolio_governor_ledger_replay import (
    replay_portfolio_governor_ledger,
)
from crypto_core.audit.portfolio_governor_ledger_store import PortfolioGovernorLedgerStore

_LIFECYCLE_SCHEMA_VERSION = "portfolio-governor-lifecycle-view.v1"


@dataclass(frozen=True)
class PaperGovernorPlanState:
    """Current (latest) paper-governor state for a single plan, including its blockers. PAPER ONLY."""

    plan_id: str
    status: PortfolioGovernorLedgerStatus
    entry_digest: str
    total_weight: float
    total_notional: float
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class PaperGovernorLifecycleView:
    """Deterministic, immutable current-state view over the governor ledger chain. PAPER ONLY."""

    schema_version: str
    head_digest: str | None
    entry_count: int
    active_count: int
    blocked_count: int
    current_active_plans: tuple[PaperGovernorPlanState, ...]
    current_blocked_plans: tuple[PaperGovernorPlanState, ...]
    total_active_weight: float
    total_active_notional: float
    blocker_summary: tuple[str, ...]
    replay_digest: str
    lifecycle_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _entries_of(source: object) -> tuple[PortfolioGovernorLedgerEntry, ...]:
    # Called only after replay validation has accepted the source, so it is a store or an ordered
    # tuple/list of validated entries here.
    if isinstance(source, PortfolioGovernorLedgerStore):
        return source.snapshot()
    return tuple(source)  # type: ignore[arg-type]


def _serialize_plan_states(states: tuple[PaperGovernorPlanState, ...]) -> list[list[object]]:
    return [
        [
            state.plan_id,
            state.status.value,
            state.entry_digest,
            state.total_weight,
            state.total_notional,
            list(state.blockers),
        ]
        for state in states
    ]


def summarize_paper_governor_lifecycle(
    source: PortfolioGovernorLedgerStore
    | tuple[PortfolioGovernorLedgerEntry, ...]
    | list[PortfolioGovernorLedgerEntry],
) -> PaperGovernorLifecycleView:
    """Summarize a governor ledger chain (store or ordered entries) into a current-state view.

    The chain is validated and the base metrics (head digest, counts, current active totals) are
    produced by ``replay_portfolio_governor_ledger`` — reused, not duplicated. This view adds the
    current active vs blocked plan states (latest entry per plan, with blockers) and a sorted-unique
    ``blocker_summary``. A malformed source or broken/tampered chain fails closed through replay
    validation. The result is deterministic and immutable; no order intent or live wiring is produced.
    """
    replay = replay_portfolio_governor_ledger(source)
    entries = _entries_of(source)

    latest: dict[str, PortfolioGovernorLedgerEntry] = {}
    for entry in entries:
        latest[entry.plan_id] = entry  # last occurrence in chain order wins (current state)

    plan_states = tuple(
        PaperGovernorPlanState(
            plan_id=entry.plan_id,
            status=entry.status,
            entry_digest=entry.entry_digest,
            total_weight=entry.total_weight,
            total_notional=entry.total_notional,
            blockers=tuple(entry.blockers),
        )
        for entry in (latest[plan_id] for plan_id in sorted(latest))
    )
    current_active_plans = tuple(
        state for state in plan_states if state.status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE
    )
    current_blocked_plans = tuple(
        state for state in plan_states if state.status == PortfolioGovernorLedgerStatus.RECORDED_BLOCKED
    )
    blocker_summary = tuple(sorted({blocker for state in plan_states for blocker in state.blockers}))

    lifecycle_payload: dict[str, object] = {
        "schema_version": _LIFECYCLE_SCHEMA_VERSION,
        "head_digest": replay.head_digest,
        "entry_count": replay.entry_count,
        "active_count": replay.active_count,
        "blocked_count": replay.blocked_count,
        "current_active_plans": _serialize_plan_states(current_active_plans),
        "current_blocked_plans": _serialize_plan_states(current_blocked_plans),
        "total_active_weight": replay.total_active_weight,
        "total_active_notional": replay.total_active_notional,
        "blocker_summary": list(blocker_summary),
        "replay_digest": replay.replay_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PaperGovernorLifecycleView(
        schema_version=_LIFECYCLE_SCHEMA_VERSION,
        head_digest=replay.head_digest,
        entry_count=replay.entry_count,
        active_count=replay.active_count,
        blocked_count=replay.blocked_count,
        current_active_plans=current_active_plans,
        current_blocked_plans=current_blocked_plans,
        total_active_weight=replay.total_active_weight,
        total_active_notional=replay.total_active_notional,
        blocker_summary=blocker_summary,
        replay_digest=replay.replay_digest,
        lifecycle_digest=_canonical_digest(lifecycle_payload),
    )


def paper_governor_lifecycle_view_to_dict(view: PaperGovernorLifecycleView) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a lifecycle view (deterministic key/value shape)."""

    def _plan(state: PaperGovernorPlanState) -> dict[str, object]:
        return {
            "plan_id": state.plan_id,
            "status": state.status.value,
            "entry_digest": state.entry_digest,
            "total_weight": state.total_weight,
            "total_notional": state.total_notional,
            "blockers": list(state.blockers),
        }

    return {
        "schema_version": view.schema_version,
        "head_digest": view.head_digest,
        "entry_count": view.entry_count,
        "active_count": view.active_count,
        "blocked_count": view.blocked_count,
        "current_active_plans": [_plan(state) for state in view.current_active_plans],
        "current_blocked_plans": [_plan(state) for state in view.current_blocked_plans],
        "total_active_weight": view.total_active_weight,
        "total_active_notional": view.total_active_notional,
        "blocker_summary": list(view.blocker_summary),
        "replay_digest": view.replay_digest,
        "lifecycle_digest": view.lifecycle_digest,
        "paper_only": view.paper_only,
        "real_orders_enabled": view.real_orders_enabled,
        "real_money_enabled": view.real_money_enabled,
    }
