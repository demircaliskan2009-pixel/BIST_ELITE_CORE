"""Deterministic paper governor ledger replay — Phase 16G.

Reads the append-only ``PortfolioGovernorLedgerStore`` (or an ordered tuple of
``PortfolioGovernorLedgerEntry``) and projects the validated chain into a deterministic,
immutable paper-governor lifecycle replay snapshot: ordered entry digests, head digest,
active/blocked counts, the latest governor state per ``plan_id``, and the current total active
paper weight/notional. This turns "stored entries" into "replayable state" for the paper governor
audit trail — without orders, live routes, controller wiring, persistence, scheduler, or venue.

Design rules:
  - Reuse, don't duplicate: the append-only chain and per-entry integrity are re-validated by
    replaying the entries through a fresh ``PortfolioGovernorLedgerStore`` — no store-append or
    sizing logic is reimplemented here.
  - Fail closed: a non-store/non-entry source, or any broken-chain / duplicate / tampered entry,
    is rejected with ``PortfolioGovernorLedgerReplayError``.
  - Consume, don't re-size: totals are summed verbatim from the latest active entry per plan; no
    per-sleeve sizing is recomputed.
  - Deterministic: identical store state yields an identical replay (including ``replay_digest``).
  - PAPER ONLY: no order intent, live route, venue execution, scheduler, or execution field.

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16G.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from crypto_core.audit.portfolio_governor_ledger import (
    PortfolioGovernorLedgerEntry,
    PortfolioGovernorLedgerStatus,
)
from crypto_core.audit.portfolio_governor_ledger_store import (
    PortfolioGovernorLedgerStore,
    PortfolioGovernorLedgerStoreError,
)

_REPLAY_SCHEMA_VERSION = "portfolio-governor-ledger-replay.v1"
_PRECISION = 12


class PortfolioGovernorLedgerReplayError(RuntimeError):
    """Raised when a replay source is malformed or its entry chain is broken/tampered (fail-closed)."""


@dataclass(frozen=True)
class PlanGovernorState:
    """Latest recorded paper-governor state for a single plan in the replayed chain. PAPER ONLY."""

    plan_id: str
    status: PortfolioGovernorLedgerStatus
    entry_digest: str
    total_weight: float
    total_notional: float


@dataclass(frozen=True)
class PortfolioGovernorLedgerReplay:
    """Deterministic, immutable paper-governor lifecycle replay snapshot. PAPER ONLY."""

    schema_version: str
    entry_count: int
    active_count: int
    blocked_count: int
    head_digest: str | None
    ordered_entry_digests: tuple[str, ...]
    latest_by_plan_id: tuple[PlanGovernorState, ...]
    total_active_weight: float
    total_active_notional: float
    replay_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coerce_entries(source: object) -> tuple[PortfolioGovernorLedgerEntry, ...]:
    if isinstance(source, PortfolioGovernorLedgerStore):
        return source.snapshot()
    if isinstance(source, (tuple, list)):
        entries = tuple(source)
        for entry in entries:
            if not isinstance(entry, PortfolioGovernorLedgerEntry):
                raise PortfolioGovernorLedgerReplayError("portfolio_governor_ledger_replay:entry_malformed")
        return entries
    raise PortfolioGovernorLedgerReplayError("portfolio_governor_ledger_replay:source_malformed")


def replay_portfolio_governor_ledger(
    source: PortfolioGovernorLedgerStore
    | tuple[PortfolioGovernorLedgerEntry, ...]
    | list[PortfolioGovernorLedgerEntry],
) -> PortfolioGovernorLedgerReplay:
    """Project an append-only governor ledger (store or ordered entries) into a replay snapshot.

    The chain and per-entry integrity are independently re-validated by replaying the entries
    through a fresh ``PortfolioGovernorLedgerStore`` (first ``previous_entry_digest`` is None, each
    next references the prior ``entry_digest``, no duplicate digests, every entry self-consistent).
    Any breach yields a fail-closed ``PortfolioGovernorLedgerReplayError``. The returned snapshot is
    deterministic and immutable; totals are summed verbatim from the latest active entry per plan
    (no re-sizing). No order intent or live wiring is produced.
    """
    entries = _coerce_entries(source)

    # Independently re-validate the append-only chain + entry integrity by replaying through a fresh
    # store. This reuses the canonical append validation; no chain/sizing logic is duplicated here.
    store = PortfolioGovernorLedgerStore()
    try:
        for entry in entries:
            store.append(entry)
    except PortfolioGovernorLedgerStoreError as exc:
        raise PortfolioGovernorLedgerReplayError(f"portfolio_governor_ledger_replay:chain_invalid:{exc}") from exc
    validated = store.snapshot()

    ordered_entry_digests = tuple(entry.entry_digest for entry in validated)
    active_count = sum(1 for entry in validated if entry.status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE)
    blocked_count = sum(1 for entry in validated if entry.status == PortfolioGovernorLedgerStatus.RECORDED_BLOCKED)
    head_digest = validated[-1].entry_digest if validated else None

    latest: dict[str, PortfolioGovernorLedgerEntry] = {}
    for entry in validated:
        latest[entry.plan_id] = entry  # last occurrence in chain order wins
    latest_by_plan_id = tuple(
        PlanGovernorState(
            plan_id=entry.plan_id,
            status=entry.status,
            entry_digest=entry.entry_digest,
            total_weight=entry.total_weight,
            total_notional=entry.total_notional,
        )
        for entry in (latest[plan_id] for plan_id in sorted(latest))
    )
    total_active_weight = round(
        math.fsum(
            state.total_weight
            for state in latest_by_plan_id
            if state.status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE
        ),
        _PRECISION,
    )
    total_active_notional = round(
        math.fsum(
            state.total_notional
            for state in latest_by_plan_id
            if state.status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE
        ),
        _PRECISION,
    )

    replay_payload: dict[str, object] = {
        "schema_version": _REPLAY_SCHEMA_VERSION,
        "entry_count": len(validated),
        "active_count": active_count,
        "blocked_count": blocked_count,
        "head_digest": head_digest,
        "ordered_entry_digests": list(ordered_entry_digests),
        "latest_by_plan_id": [
            [state.plan_id, state.status.value, state.entry_digest, state.total_weight, state.total_notional]
            for state in latest_by_plan_id
        ],
        "total_active_weight": total_active_weight,
        "total_active_notional": total_active_notional,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PortfolioGovernorLedgerReplay(
        schema_version=_REPLAY_SCHEMA_VERSION,
        entry_count=len(validated),
        active_count=active_count,
        blocked_count=blocked_count,
        head_digest=head_digest,
        ordered_entry_digests=ordered_entry_digests,
        latest_by_plan_id=latest_by_plan_id,
        total_active_weight=total_active_weight,
        total_active_notional=total_active_notional,
        replay_digest=_canonical_digest(replay_payload),
    )


def portfolio_governor_ledger_replay_to_dict(replay: PortfolioGovernorLedgerReplay) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a replay snapshot (deterministic key/value shape)."""
    return {
        "schema_version": replay.schema_version,
        "entry_count": replay.entry_count,
        "active_count": replay.active_count,
        "blocked_count": replay.blocked_count,
        "head_digest": replay.head_digest,
        "ordered_entry_digests": list(replay.ordered_entry_digests),
        "latest_by_plan_id": [
            {
                "plan_id": state.plan_id,
                "status": state.status.value,
                "entry_digest": state.entry_digest,
                "total_weight": state.total_weight,
                "total_notional": state.total_notional,
            }
            for state in replay.latest_by_plan_id
        ],
        "total_active_weight": replay.total_active_weight,
        "total_active_notional": replay.total_active_notional,
        "replay_digest": replay.replay_digest,
        "paper_only": replay.paper_only,
        "real_orders_enabled": replay.real_orders_enabled,
        "real_money_enabled": replay.real_money_enabled,
    }
